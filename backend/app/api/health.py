"""Service status endpoints."""

import logging

from fastapi import APIRouter, Response, status

from app.database import check_database
from app.schemas import (
    ComponentStatus,
    HealthResponse,
    MessageResponse,
    ReadinessResponse,
)
from app.supabase_client import check_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/", response_model=MessageResponse)
async def root() -> MessageResponse:
    return MessageResponse(message="AI Knowledge Base API is running")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: the process is up. Does not touch external services."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness(response: Response) -> ReadinessResponse:
    """Readiness: Supabase PostgreSQL and Supabase API are reachable.

    Runs in FastAPI's threadpool (sync def) because the checks are blocking.
    Failure details are logged server-side only, never returned to the client.
    """
    try:
        database = ComponentStatus(status="ok", details=check_database())
    except Exception:
        logger.exception("Readiness check failed: database")
        database = ComponentStatus(status="error", details={"error": "Database connection failed"})

    try:
        supabase = ComponentStatus(status="ok", details=check_supabase())
    except Exception:
        logger.exception("Readiness check failed: supabase")
        supabase = ComponentStatus(status="error", details={"error": "Supabase API connection failed"})

    ready = database.status == "ok" and supabase.status == "ok"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if ready else "error", database=database, supabase=supabase)
