"""Document ingestion pipeline.

    validated PDF
      -> page-aware text extraction   (pdf.py)
      -> chunking with page ranges    (chunking.py)
      -> one embedding per chunk      (embeddings.py)
      -> Storage upload + document and chunk rows in one transaction
                                      (documents.py)

Everything that can fail on bad input or a busy AI service runs before
anything is stored, so a failed upload leaves no file or record behind.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document
from app.services import documents as document_service
from app.services.chunking import ChunkSettings, chunk_pages
from app.services.embeddings import embed_documents
from app.services.pdf import extract_pages
from app.services.uploads import ValidatedPdf

logger = logging.getLogger(__name__)


def ingest_pdf(db: Session, user_id: uuid.UUID, pdf: ValidatedPdf, title: str | None = None) -> Document:
    settings = get_settings()

    # Extract before storing anything: unusable PDFs are rejected up front
    # instead of becoming a stored file with a failed status.
    extracted = extract_pages(pdf.data, max_pages=settings.max_pdf_pages)

    document_id = uuid.uuid4()
    chunks = chunk_pages(
        extracted.pages,
        ChunkSettings(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap),
        document_id=document_id,
    )
    embeddings = embed_documents([chunk.content for chunk in chunks])

    return document_service.create_document(
        db,
        user_id,
        pdf,
        page_count=extracted.page_count,
        chunks=chunks,
        embeddings=embeddings,
        title=title,
        document_id=document_id,
    )
