"""Conversations and their messages, always scoped to the owning user.

A conversation belongs to one user and one document. Lookups for someone
else's conversation raise ConversationNotFoundError (404), never 403.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.errors import ExternalServiceError, NotFoundError
from app.models import Conversation, Message
from app.services import documents as document_service

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


def create_conversation(
    db: Session, user_id: uuid.UUID, document_id: uuid.UUID, title: str | None = None
) -> Conversation:
    """Empty conversation about one of the user's documents. Without a title,
    the first question becomes the title."""
    document_service.get_owned_document(db, user_id, document_id)  # 404 if not the user's
    conversation = Conversation(
        user_id=user_id, document_id=document_id, title=title_from_question(title) if title else None
    )
    try:
        db.add(conversation)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ExternalServiceError("Could not create the conversation. Please try again.") from exc
    db.refresh(conversation)
    logger.info("Created conversation id=%s document=%s user=%s", conversation.id, document_id, user_id)
    return conversation


def list_conversations(db: Session, user_id: uuid.UUID, document_id: uuid.UUID | None = None) -> list[Conversation]:
    """The user's conversations, most recently active first."""
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    if document_id is not None:
        stmt = stmt.where(Conversation.document_id == document_id)
    return list(db.scalars(stmt.order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())))


def get_conversation_with_messages(db: Session, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .options(selectinload(Conversation.messages))  # ordered by id (insertion order)
    )
    conversation = db.scalars(stmt).first()
    if conversation is None:
        raise ConversationNotFoundError()
    return conversation


def delete_conversation(db: Session, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    """Delete a conversation and (by cascade) its messages."""
    conversation = get_owned_conversation(db, user_id, conversation_id)
    try:
        db.delete(conversation)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ExternalServiceError("Could not delete the conversation. Please try again.") from exc
    logger.info("Deleted conversation id=%s user=%s", conversation_id, user_id)


def recent_messages(db: Session, conversation_id: uuid.UUID, limit: int) -> list[Message]:
    """The last `limit` messages of a conversation, oldest first."""
    if limit <= 0:
        return []
    stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id.desc()).limit(limit)
    return list(reversed(db.scalars(stmt).all()))


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
        else:
            # A conversation created empty (POST /conversations) is named after its first question.
            conversation = db.get(Conversation, conversation_id)
            if conversation is not None and not conversation.title:
                conversation.title = title_from_question(question)
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
