"""Pydantic request/response schemas."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DocumentStatus = Literal["processing", "ready", "failed"]


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str


class ComponentStatus(BaseModel):
    status: Literal["ok", "error"]
    details: dict[str, Any] = {}


class ReadinessResponse(BaseModel):
    status: Literal["ok", "error"]
    database: ComponentStatus
    supabase: ComponentStatus


class ErrorResponse(BaseModel):
    detail: str


class DocumentResponse(BaseModel):
    """Public view of a document. storage_path is internal and never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    status: DocumentStatus
    page_count: int | None
    summary: str | None
    questions: list[str] | None
    created_at: datetime


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str | None


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class SearchRequest(BaseModel):
    question: Question
    top_k: int | None = Field(default=None, ge=1, le=50, description="Defaults to SEARCH_TOP_K (5)")


class SearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_index: int
    page_number: int
    page_end: int
    similarity: float
    content: str


class SearchResponse(BaseModel):
    document_id: uuid.UUID
    question: str
    results: list[SearchResult]


class AskRequest(BaseModel):
    question: Question


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    similarity: float


class AskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer: str
    sources: list[SourceResponse]
    model: str


class ChatRequest(BaseModel):
    document_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    message: Question
