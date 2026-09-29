"""Service status endpoints."""

from fastapi import APIRouter

from app.schemas import HealthResponse, MessageResponse

router = APIRouter(tags=["health"])


@router.get("/", response_model=MessageResponse)
async def root() -> MessageResponse:
    return MessageResponse(message="AI Knowledge Base API is running")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
