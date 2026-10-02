"""Chat endpoint: RAG answers streamed as Server-Sent Events."""

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.types import Send

from app.api.deps import CurrentUser, get_current_user
from app.database import get_db
from app.schemas import ChatRequest, ErrorResponse
from app.services import chat as chat_service

router = APIRouter(
    tags=["chat"],
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid access token"}},
)


class EventStreamResponse(StreamingResponse):
    """StreamingResponse that always closes its generator, so the chat
    service can save a partial answer when the client disconnects."""

    media_type = "text/event-stream"

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()  # type: ignore[attr-defined]


@router.post(
    "/chat",
    response_class=EventStreamResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Events: meta, token…, done | error"},
        404: {"model": ErrorResponse, "description": "Document or conversation not found"},
        409: {"model": ErrorResponse, "description": "Document has no embeddings yet"},
        502: {"model": ErrorResponse, "description": "Embedding, database or AI model failure before streaming"},
    },
)
async def chat(
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EventStreamResponse:
    """Ask a question about a document and receive the answer as it is
    generated. Omit `conversation_id` to start a new conversation; its id
    arrives in the first (`meta`) event."""
    turn = await anyio.to_thread.run_sync(
        chat_service.prepare_turn, db, user.id, body.document_id, body.conversation_id, body.message
    )
    events = await chat_service.open_stream(db, turn)
    return EventStreamResponse(
        events,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # no proxy buffering
    )
