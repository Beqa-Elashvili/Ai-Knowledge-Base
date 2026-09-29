"""Page-aware PDF text extraction with PyMuPDF.

Page numbers are the PDF's physical pages, 1-based: exactly what PDF viewers
show and what `#page=N` links open. Every piece of text keeps the page it came
from, which is what makes source citations trustworthy later on.
"""

import logging
import re
import unicodedata
from dataclasses import asdict, dataclass

import pymupdf

from app.errors import InvalidFileError

logger = logging.getLogger(__name__)

# Expand ligatures (no TEXT_PRESERVE_LIGATURES), keep text inside the page
# box, keep glyphs without a unicode mapping, and join hyphenated words where
# PyMuPDF can detect them.
TEXT_FLAGS = (
    pymupdf.TEXT_PRESERVE_WHITESPACE
    | pymupdf.TEXT_MEDIABOX_CLIP
    | pymupdf.TEXT_CID_FOR_UNKNOWN_UNICODE
    | pymupdf.TEXT_DEHYPHENATE
)

# Below this many characters in the whole document we treat the PDF as having
# no text layer (typically a scan), since OCR is out of scope.
MIN_DOCUMENT_CHARACTERS = 20

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # keeps \t \n \r
_HYPHEN_BREAK = re.compile(r"(\w)-\n(?=[a-z])")  # "exam-\nple" -> "example"
_SPACES = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class UnprocessablePdfError(InvalidFileError):
    """The file is a PDF but its text cannot be used."""

    status_code = 422
    default_message = "The PDF could not be processed."


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based physical page
    text: str


@dataclass(frozen=True)
class ExtractedPdf:
    page_count: int
    pages: list[PageText]  # one entry per page, including pages with no text

    @property
    def text_pages(self) -> list[PageText]:
        return [page for page in self.pages if page.text]

    @property
    def character_count(self) -> int:
        return sum(len(page.text) for page in self.pages)

    def to_dicts(self) -> list[dict[str, int | str]]:
        return [asdict(page) for page in self.pages]


def clean_text(text: str) -> str:
    """Normalize extracted text without changing its meaning.

    - NFC normalization, CRLF -> LF
    - strip control characters (Postgres TEXT cannot store NUL)
    - rejoin words hyphenated across line breaks
    - collapse runs of spaces and excess blank lines
    """
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1", text)
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def extract_pages(data: bytes, max_pages: int | None = None) -> ExtractedPdf:
    """Extract cleaned text for every page, preserving page numbers.

    Raises UnprocessablePdfError for corrupt, password-protected, empty,
    oversized (page count) or text-less PDFs.
    """
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        logger.info("PDF open failed: %s", type(exc).__name__)
        raise UnprocessablePdfError("The PDF is damaged or unreadable.") from exc

    with doc:
        if doc.needs_pass:
            raise UnprocessablePdfError("The PDF is password-protected. Remove the password and upload it again.")
        if doc.page_count == 0:
            raise UnprocessablePdfError("The PDF has no pages or is damaged.")
        if max_pages is not None and doc.page_count > max_pages:
            raise UnprocessablePdfError(f"The PDF has {doc.page_count} pages; the maximum is {max_pages}.")

        pages: list[PageText] = []
        for index, page in enumerate(doc):
            try:
                raw = page.get_text("text", flags=TEXT_FLAGS)
            except (RuntimeError, ValueError):
                # One broken page should not sink the whole document.
                logger.warning("Text extraction failed on page %d; treating it as empty", index + 1)
                raw = ""
            pages.append(PageText(page_number=index + 1, text=clean_text(raw)))

    extracted = ExtractedPdf(page_count=len(pages), pages=pages)
    logger.info(
        "Extracted PDF pages=%d text_pages=%d chars=%d",
        extracted.page_count,
        len(extracted.text_pages),
        extracted.character_count,
    )

    if extracted.character_count < MIN_DOCUMENT_CHARACTERS:
        raise UnprocessablePdfError(
            "No selectable text was found in this PDF. Scanned documents need OCR, which is not supported yet."
        )
    return extracted
