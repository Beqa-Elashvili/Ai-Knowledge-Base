"""Validation of uploaded files before anything is stored."""

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO

from app.errors import FileTooLargeError, InvalidFileError, UnsupportedFileTypeError

ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
PDF_MAGIC = b"%PDF-"
MAX_TITLE_LENGTH = 200
MAX_FILENAME_LENGTH = 255


@dataclass(frozen=True)
class ValidatedPdf:
    filename: str
    data: bytes


def clean_filename(filename: str | None) -> str:
    """Keep only the base name (drop any client-supplied directories)."""
    name = PurePath((filename or "").replace("\\", "/")).name.strip()
    return name[:MAX_FILENAME_LENGTH]


def title_from_filename(filename: str) -> str:
    """'machine_learning-notes.pdf' -> 'machine learning notes'."""
    # Not PurePath.stem: it treats ".pdf" as a dotfile and keeps the extension.
    stem = re.sub(r"\.pdf$", "", PurePath(filename).name, flags=re.IGNORECASE)
    title = re.sub(r"[_\-]+", " ", stem)
    title = re.sub(r"\s+", " ", title).strip()
    return (title or "Untitled document")[:MAX_TITLE_LENGTH]


def read_limited(stream: BinaryIO, max_bytes: int) -> bytes:
    """Read at most max_bytes; raise if the stream holds more.

    Reads one extra byte instead of trusting a client-supplied size.
    """
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise FileTooLargeError(f"File is too large. The maximum size is {max_bytes // (1024 * 1024)} MB.")
    return data


def validate_pdf_upload(
    filename: str | None,
    content_type: str | None,
    stream: BinaryIO,
    max_bytes: int,
) -> ValidatedPdf:
    """Check extension, declared MIME type, size, and the PDF signature."""
    name = clean_filename(filename)
    if not name:
        raise InvalidFileError("A file name is required.")
    if not name.lower().endswith(".pdf"):
        raise UnsupportedFileTypeError("Only PDF files are supported (.pdf).")

    declared_type = (content_type or "").split(";")[0].strip().lower()
    if declared_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedFileTypeError("Only PDF files are supported (application/pdf).")

    data = read_limited(stream, max_bytes)
    if not data:
        raise InvalidFileError("The uploaded file is empty.")
    # The extension and MIME type are client-controlled; the signature is not.
    if PDF_MAGIC not in data[:1024]:
        raise UnsupportedFileTypeError("The file is not a valid PDF.")

    return ValidatedPdf(filename=name, data=data)
