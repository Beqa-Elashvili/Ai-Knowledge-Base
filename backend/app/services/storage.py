"""Supabase Storage operations for uploaded PDFs.

Objects live in a private bucket at {user_id}/{document_id}.pdf. Putting the
user id first lets Storage RLS scope access by top-level folder, and using
the document id (not the user's filename) avoids collisions and path tricks.
"""

import logging
import uuid

import httpx
from storage3.exceptions import StorageApiError

from app.config import get_settings
from app.errors import ExternalServiceError
from app.supabase_client import get_supabase, with_reconnect

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"


class StorageError(ExternalServiceError):
    """A storage operation failed. The message is safe to show to users."""


def build_storage_path(user_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"{user_id}/{document_id}.pdf"


def _bucket():
    settings = get_settings()
    return get_supabase().storage.from_(settings.storage_bucket)


def upload_pdf(user_id: uuid.UUID, document_id: uuid.UUID, data: bytes) -> str:
    """Upload PDF bytes and return the storage path. Never overwrites."""
    path = build_storage_path(user_id, document_id)
    try:
        with_reconnect(
            lambda: _bucket().upload(path, data, file_options={"content-type": PDF_CONTENT_TYPE, "upsert": "false"}),
            "Storage upload",
        )
    except StorageApiError as exc:
        logger.error("Storage upload failed path=%s status=%s code=%s", path, exc.status, exc.code)
        raise StorageError("Could not store the uploaded file.") from exc
    except httpx.HTTPError as exc:
        logger.error("Storage upload failed path=%s: %s", path, type(exc).__name__)
        raise StorageError("Could not store the uploaded file.") from exc
    logger.info("Stored PDF path=%s bytes=%d", path, len(data))
    return path


def delete_file(path: str) -> None:
    """Delete an object. Missing objects are not an error (idempotent)."""
    try:
        with_reconnect(lambda: _bucket().remove([path]), "Storage delete")
    except StorageApiError as exc:
        logger.error("Storage delete failed path=%s status=%s code=%s", path, exc.status, exc.code)
        raise StorageError("Could not delete the stored file.") from exc
    except httpx.HTTPError as exc:
        logger.error("Storage delete failed path=%s: %s", path, type(exc).__name__)
        raise StorageError("Could not delete the stored file.") from exc
    logger.info("Deleted stored file path=%s", path)


def create_signed_url(path: str, expires_in: int | None = None) -> str:
    """Short-lived URL for downloading/viewing a private object."""
    seconds = expires_in or get_settings().signed_url_expires_seconds
    try:
        result = with_reconnect(lambda: _bucket().create_signed_url(path, seconds), "Storage signed URL")
    except StorageApiError as exc:
        logger.error("Signed URL failed path=%s status=%s code=%s", path, exc.status, exc.code)
        raise StorageError("Could not create a link to the file.") from exc
    except httpx.HTTPError as exc:
        logger.error("Signed URL failed path=%s: %s", path, type(exc).__name__)
        raise StorageError("Could not create a link to the file.") from exc
    url = result.get("signedUrl") or result.get("signedURL")
    if not url:
        raise StorageError("Could not create a link to the file.")
    return url
