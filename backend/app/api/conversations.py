"""Conversation endpoints: a user's chats about their documents."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.database import get_db
from app.schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationResponse,
    ErrorResponse,
)
from app.services import conversations as conversation_service

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid access token"}},
)

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Conversation not found"}}


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse, "description": "Document not found"}},
)
def create_conversation(
    body: ConversationCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Start an empty conversation about one of your documents. Without a
    title, the first question becomes the title. (POST /chat without a
    conversation_id also creates one.)"""
    conversation = conversation_service.create_conversation(db, user.id, body.document_id, body.title or None)
    return ConversationResponse.model_validate(conversation)


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    document_id: uuid.UUID | None = Query(None, description="Only conversations about this document"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationResponse]:
    """Your conversations, most recently active first."""
    return [
        ConversationResponse.model_validate(c)
        for c in conversation_service.list_conversations(db, user.id, document_id)
    ]


@router.get("/{conversation_id}", response_model=ConversationDetailResponse, responses=NOT_FOUND)
def get_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    """A conversation with all its messages, oldest first."""
    conversation = conversation_service.get_conversation_with_messages(db, user.id, conversation_id)
    return ConversationDetailResponse.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    conversation_service.delete_conversation(db, user.id, conversation_id)
