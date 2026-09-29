import io

import pytest

from app.errors import FileTooLargeError, InvalidFileError, UnsupportedFileTypeError
from app.services.uploads import clean_filename, title_from_filename, validate_pdf_upload

PDF = b"%PDF-1.7\n...content..."
MB = 1024 * 1024


def validate(filename="doc.pdf", content_type="application/pdf", data=PDF, max_bytes=20 * MB):
    return validate_pdf_upload(filename, content_type, io.BytesIO(data), max_bytes)


def test_valid_pdf_passes() -> None:
    result = validate()
    assert result.filename == "doc.pdf" and result.data == PDF


def test_uppercase_extension_and_charset_suffix_accepted() -> None:
    assert validate(filename="Report.PDF", content_type="application/pdf; charset=binary").filename == "Report.PDF"


@pytest.mark.parametrize("filename", ["notes.txt", "archive.pdf.zip", "noextension"])
def test_wrong_extension_rejected(filename: str) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate(filename=filename)


@pytest.mark.parametrize("content_type", ["text/plain", "application/octet-stream", None])
def test_wrong_mime_type_rejected(content_type) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate(content_type=content_type)


def test_fake_pdf_without_signature_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate(data=b"just some text renamed to .pdf")


def test_empty_file_rejected() -> None:
    with pytest.raises(InvalidFileError):
        validate(data=b"")


def test_missing_filename_rejected() -> None:
    with pytest.raises(InvalidFileError):
        validate(filename="")


def test_size_limit_is_inclusive() -> None:
    exact = PDF + b"0" * (100 - len(PDF))
    assert len(validate(data=exact, max_bytes=100).data) == 100
    with pytest.raises(FileTooLargeError):
        validate(data=exact + b"0", max_bytes=100)


def test_client_directories_are_stripped() -> None:
    assert clean_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert clean_filename(r"C:\Users\me\book.pdf") == "book.pdf"


def test_title_from_filename() -> None:
    assert title_from_filename("machine_learning--notes.pdf") == "machine learning notes"
    assert title_from_filename(".pdf") == "Untitled document"
