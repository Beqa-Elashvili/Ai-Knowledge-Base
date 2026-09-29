"""Document records: creation, ownership-scoped reads, deletion.

Every function takes the authenticated user's id and filters by it, so a
user can never read or delete another user's document. Lookups for someone
else's document raise NotFoundError (404), not 403, to avoid revealing that
the id exists.
"""

import logging
import uuid

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import ExternalServiceError, NotFoundError
from app.models import Document, DocumentChunk
from app.services import storage
from app.services.chunking import TextChunk
from app.services.uploads import ValidatedPdf, title_from_filename

logger = logging.getLogger(__name__)


class DocumentNotFoundError(NotFoundError):
    default_message = "Document not found."


def create_document(
    db: Session,
    user_id: uuid.UUID,
    pdf: ValidatedPdf,
    page_count: int,
    chunks: list[TextChunk],
    title: str | None = None,
    document_id: uuid.UUID | None = None,
) -> Document:
    """Store the PDF in Supabase Storage, then create its record and chunks.

    The document row and all of its chunks are written in ONE transaction:
    either everything is saved or nothing is. If that transaction fails, the
    file that was just uploaded is deleted, so no orphaned file or
    half-written document is left behind.
    """
    document_id = document_id or uuid.uuid4()
    path = storage.upload_pdf(user_id, document_id, pdf.data)

    document = Document(
        id=document_id,
        user_id=user_id,
        title=(title or "").strip()[:200] or title_from_filename(pdf.filename),
        filename=pdf.filename,
        storage_path=path,
        page_count=page_count,
        status="processing",
    )
    try:
        db.add(document)
        db.flush()  # document row must exist before chunks reference it
        if chunks:
            db.execute(
                insert(DocumentChunk),
                [
                    {
                        "document_id": document_id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "page_end": chunk.page_end,
                    }
                    for chunk in chunks
                ],
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Document insert failed id=%s; removing stored file", document_id)
        try:
            storage.delete_file(path)
        except storage.StorageError:
            logger.error("Cleanup failed: orphaned file path=%s", path)
        raise ExternalServiceError("Could not save the document. Please try again.") from exc

    db.refresh(document)
    logger.info(
        "Created document id=%s user=%s bytes=%d pages=%d chunks=%d",
        document.id, user_id, len(pdf.data), page_count, len(chunks),
    )
    return document


def list_documents(db: Session, user_id: uuid.UUID) -> list[Document]:
    stmt = select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
    return list(db.scalars(stmt))


def get_owned_document(db: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    stmt = select(Document).where(Document.id == document_id, Document.user_id == user_id)
    document = db.scalars(stmt).first()
    if document is None:
        raise DocumentNotFoundError()
    return document


def delete_document(db: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """Delete the record (chunks/conversations/messages cascade), then the file.

    The database row goes first: if file deletion then fails, the result is a
    harmless orphaned private file (logged) rather than a record pointing at
    a missing file.
    """
    document = get_owned_document(db, user_id, document_id)
    path = document.storage_path
    try:
        db.delete(document)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ExternalServiceError("Could not delete the document. Please try again.") from exc

    if path:
        try:
            storage.delete_file(path)
        except storage.StorageError:
            logger.error("Document id=%s deleted but file remains path=%s", document_id, path)
    logger.info("Deleted document id=%s user=%s", document_id, user_id)
