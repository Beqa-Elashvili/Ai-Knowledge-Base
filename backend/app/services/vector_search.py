"""Semantic search over ONE document's chunks.

    question
      -> query embedding                  (embeddings.py)
      -> match_document_chunks() in SQL   (pgvector cosine search, HNSW index)
      -> chunks ranked by similarity

Isolation: the caller's ownership of the document is checked first, and the
SQL function only ever reads rows with that document_id, so a question about
document A can never return chunks from document B (or another user's).
"""

import logging
import time
import uuid
from dataclasses import dataclass

from fastapi import status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, ExternalServiceError
from app.models import Document
from app.services import documents as document_service
from app.services.embeddings import embed_query

logger = logging.getLogger(__name__)

MAX_MATCH_COUNT = 50  # the SQL function caps match_count at 50 too

_MATCH_SQL = text(
    """
    select id, document_id, content, page_number, page_end, page_breaks, chunk_index, similarity
    from public.match_document_chunks(
        cast(:embedding as extensions.vector), :document_id, :match_count, :min_similarity
    )
    """
)


class VectorSearchError(ExternalServiceError):
    default_message = "Search failed. Please try again."


class DocumentNotReadyError(AppError):
    status_code = status.HTTP_409_CONFLICT
    default_message = "This document is still being processed. Try again shortly."


@dataclass(frozen=True)
class RetrievedChunk:
    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    page_number: int  # first page
    page_end: int  # last page
    chunk_index: int
    similarity: float  # 1 = same direction, 0 = unrelated
    # [[offset, page], ...]: where later pages begin in `content`
    page_breaks: list[list[int]] | None = None


def search_document(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    question: str,
    top_k: int | None = None,
    min_similarity: float | None = None,
) -> list[RetrievedChunk]:
    """Return the chunks of the user's document most relevant to `question`,
    best match first. Raises DocumentNotFoundError (404) if the document is
    missing or not the user's, DocumentNotReadyError (409) if it has no
    embeddings yet."""
    document = document_service.get_owned_document(db, user_id, document_id)
    return search_owned_document(db, document, question, top_k, min_similarity)


def search_owned_document(
    db: Session,
    document: Document,
    question: str,
    top_k: int | None = None,
    min_similarity: float | None = None,
) -> list[RetrievedChunk]:
    """search_document for a document whose ownership is already verified."""
    question = question.strip()
    if not question:
        raise ValueError("Question is empty")
    if document.status != "ready":
        raise DocumentNotReadyError()
    settings = get_settings()
    top_k = max(1, min(top_k or settings.search_top_k, MAX_MATCH_COUNT))
    min_similarity = settings.search_min_similarity if min_similarity is None else min_similarity

    started = time.perf_counter()
    query_embedding = embed_query(question)
    embedded = time.perf_counter()
    chunks = match_chunks(db, document.id, query_embedding, top_k, min_similarity)

    logger.info(
        "Vector search document=%s top_k=%d hits=%d best=%.3f embed=%.2fs search=%.2fs",
        document.id, top_k, len(chunks), chunks[0].similarity if chunks else 0.0,
        embedded - started, time.perf_counter() - embedded,
    )
    return chunks


def match_chunks(
    db: Session,
    document_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    min_similarity: float,
) -> list[RetrievedChunk]:
    """Run the pgvector search for one document. No ownership check: callers
    must have verified that the user owns `document_id`."""
    params = {
        "embedding": "[" + ",".join(repr(float(x)) for x in query_embedding) + "]",
        "document_id": document_id,
        "match_count": top_k,
        "min_similarity": min_similarity,
    }
    try:
        rows = db.execute(_MATCH_SQL, params).all()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Vector search failed document=%s: %s", document_id, type(exc).__name__)
        raise VectorSearchError() from exc
    return [RetrievedChunk(**row._mapping) for row in rows]
