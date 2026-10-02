"""Streaming RAG chat turns.

    prepare_turn()   ownership, conversation check, recent history, follow-up
                     rewritten as a standalone search query, vector search,
                     prompt (sync; any failure is a normal HTTP error)
    open_stream()    starts the LLM and waits for its first text, THEN saves
                     the question (creating the conversation if needed), so
                     a request that fails before answering leaves nothing
                     behind; returns the Server-Sent Events stream

Events, each `event: <name>\\ndata: <json>\\n\\n`:
    meta    {"conversation_id", "user_message_id"}
    token   {"text"}                                  many, in order
    done    {"message_id", "sources": [{"page", "similarity"}]}
    error   {"detail", "message_id"}                  instead of done

The answer is saved when the stream ends. If the model fails mid-answer or
the client disconnects (closed tab, Stop button), the text produced so far
is saved with INTERRUPTED_NOTE, so the conversation never silently loses or
fakes part of an answer.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass

import anyio
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_sessionmaker
from app.models import Document
from app.services import conversations
from app.services import documents as document_service
from app.services.llm import ChatMessage, LLMError, stream_generate
from app.services.rag import (
    SYSTEM_PROMPT,
    build_context,
    build_messages,
    condense_question,
    extract_sources,
    history_messages,
)
from app.services.vector_search import DocumentNotReadyError, RetrievedChunk, search_owned_document

logger = logging.getLogger(__name__)

INTERRUPTED_NOTE = "\n\n[Answer interrupted]"


@dataclass(frozen=True)
class ChatTurn:
    user_id: uuid.UUID
    document: Document
    conversation_id: uuid.UUID | None
    question: str
    excerpts: list[RetrievedChunk]
    messages: list[ChatMessage]


def prepare_turn(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    question: str,
) -> ChatTurn:
    settings = get_settings()
    document = document_service.get_owned_document(db, user_id, document_id)
    history: list[ChatMessage] = []
    if conversation_id is not None:
        conversation = conversations.get_owned_conversation(db, user_id, conversation_id)
        if conversation.document_id != document.id:
            raise conversations.ConversationNotFoundError()
        previous = conversations.recent_messages(db, conversation_id, settings.chat_history_messages)
        history = history_messages([(m.role, m.content) for m in previous], settings.chat_history_message_chars)

    question = question.strip()
    if document.status != "ready":  # fail fast, before spending an LLM call on the rewrite
        raise DocumentNotReadyError()
    search_query = condense_question(history, question)
    chunks = search_owned_document(db, document, search_query)
    context, used = build_context(chunks, settings.rag_max_context_chars)
    return ChatTurn(
        user_id=user_id,
        document=document,
        conversation_id=conversation_id,
        question=question,
        excerpts=used,
        messages=build_messages(document.title, context, question, history),
    )


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def open_stream(db: Session, turn: ChatTurn) -> AsyncIterator[str]:
    """Start answering. Raises LLMError (502) if the model fails before its
    first text; nothing is saved in that case."""
    deltas = stream_generate(SYSTEM_PROMPT, turn.messages)
    try:
        first = await anext(deltas)
    except StopAsyncIteration as exc:  # stream_generate raises on empty answers; defensive
        raise LLMError() from exc
    except BaseException:
        await deltas.aclose()
        raise

    try:
        conversation_id, user_message_id = await anyio.to_thread.run_sync(
            conversations.start_turn, db, turn.user_id, turn.document.id, turn.conversation_id, turn.question
        )
    except BaseException:
        await deltas.aclose()
        raise
    return _events(turn, conversation_id, user_message_id, first, deltas)


async def _events(
    turn: ChatTurn,
    conversation_id: uuid.UUID,
    user_message_id: int,
    first: str,
    deltas: AsyncIterator[str],
) -> AsyncIterator[str]:
    parts = [first]
    error: str | None = None
    try:
        yield sse("meta", {"conversation_id": conversation_id, "user_message_id": user_message_id})
        yield sse("token", {"text": first})
        async for text in deltas:
            parts.append(text)
            yield sse("token", {"text": text})
    except LLMError as exc:
        error = exc.message
    except BaseException:
        # Client went away (GeneratorExit / cancellation): keep what was said.
        logger.info("Client disconnected mid-answer conversation=%s chars=%d", conversation_id, len("".join(parts)))
        with anyio.CancelScope(shield=True):
            await deltas.aclose()  # stop generating
            await _save_answer(turn, conversation_id, parts, interrupted=True)
        raise

    message_id, sources = await _save_answer(turn, conversation_id, parts, interrupted=error is not None)
    if error is None:
        yield sse("done", {"message_id": message_id, "sources": sources})
    else:
        yield sse("error", {"detail": error, "message_id": message_id})


async def _save_answer(
    turn: ChatTurn, conversation_id: uuid.UUID, parts: list[str], interrupted: bool
) -> tuple[int | None, list[dict]]:
    answer = "".join(parts).strip()
    sources = [asdict(s) for s in extract_sources(answer, turn.excerpts)]
    content = answer + INTERRUPTED_NOTE if interrupted else answer

    def save() -> int:
        with get_sessionmaker()() as db:  # the request's session may already be closed
            return conversations.save_assistant_message(db, conversation_id, content, sources)

    try:
        message_id = await anyio.to_thread.run_sync(save)
    except Exception:
        logger.exception("Answer could not be saved conversation=%s", conversation_id)
        return None, sources
    logger.info(
        "Chat turn conversation=%s interrupted=%s chars=%d sources=%s",
        conversation_id, interrupted, len(answer), [s["page"] for s in sources],
    )
    return message_id, sources
