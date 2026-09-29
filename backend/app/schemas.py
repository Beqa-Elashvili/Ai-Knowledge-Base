"""Pydantic request/response schemas."""

from typing import Any, Literal

from pydantic import BaseModel


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
