"""Conversations and their messages, always scoped to the owning user.

A conversation belongs to one user and one document. Lookups for someone
else's conversation raise ConversationNotFoundError (404), never 403.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import ExternalServiceError, NotFoundError
from app.models import Conversation, Message

logger = logging.getLogger(__name__)

TITLE_MAX_CHARS = 80


class ConversationNotFoundError(NotFoundError):
    default_message = "Conversation not found."


def title_from_question(question: str) -> str:
    title = " ".join(question.split())
    return title if len(title) <= TITLE_MAX_CHARS else title[: TITLE_MAX_CHARS - 1].rstrip() + "…"


def get_owned_conversation(db: Session, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    stmt = select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    conversation = db.scalars(stmt).first()
    if conversation is None:
        raise ConversationNotFoundError()
    return conversation


def start_turn(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    question: str,
) -> tuple[uuid.UUID, int]:
    """Save the user's question, creating the conversation if needed.
    Returns (conversation_id, message_id). One transaction."""
    try:
        if conversation_id is None:
            conversation = Conversation(user_id=user_id, document_id=document_id, title=title_from_question(question))
            db.add(conversation)
            db.flush()
            conversation_id = conversation.id
        message = Message(conversation_id=conversation_id, role="user", content=question)
        db.add(message)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Saving user message failed conversation=%s: %s", conversation_id, type(exc).__name__)
        raise ExternalServiceError("Could not save your message. Please try again.") from exc
    logger.info("Saved user message id=%s conversation=%s", message.id, conversation_id)
    return conversation_id, message.id


def save_assistant_message(
    db: Session, conversation_id: uuid.UUID, content: str, sources: list[dict[str, Any]]
) -> int:
    try:
        message = Message(conversation_id=conversation_id, role="assistant", content=content, sources=sources)
        db.add(message)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Saving assistant message failed conversation=%s: %s", conversation_id, type(exc).__name__)
        raise ExternalServiceError("Could not save the answer.") from exc
    logger.info("Saved assistant message id=%s conversation=%s chars=%d", message.id, conversation_id, len(content))
    return message.id
