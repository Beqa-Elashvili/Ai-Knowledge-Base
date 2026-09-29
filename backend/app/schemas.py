"""Pydantic request/response schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

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
