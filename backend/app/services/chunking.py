"""Page-aware text chunking.

Pages are joined into one text stream while recording which character range
belongs to which page. The stream is split into overlapping chunks at the
most natural boundary available, and each chunk's page range is then derived
from the exact characters it contains:

    page_number = page of the chunk's first character
    page_end    = page of the chunk's last character

So a chunk that crosses from page 14 into page 15 is cited as "Pages 14-15"
rather than being assigned one page arbitrarily.
"""

import bisect
import logging
import re
import uuid
from dataclasses import dataclass

from app.services.pdf import PageText

logger = logging.getLogger(__name__)

PAGE_SEPARATOR = "\n\n"  # also acts as a paragraph boundary between pages

# Preferred split points, strongest first. Each pattern matches the gap
# *after* which a chunk may end. A single '\n' is deliberately NOT a boundary
# of its own: in PDF text it is usually just a visual line wrap in the middle
# of a sentence, so it only counts as ordinary whitespace.
_BOUNDARIES = [
    re.compile(r"\n\s*\n"),            # paragraph / page break
    re.compile(r"[.!?…][\"')\]]*\s"),  # end of sentence
    re.compile(r"[;:,]\s"),            # clause
    re.compile(r"\s"),                 # any word boundary (incl. line wraps)
]


@dataclass(frozen=True)
class ChunkSettings:
    chunk_size: int = 1600
    chunk_overlap: int = 200
    # Only look for a boundary in the last part of the window, so chunks
    # don't end up much shorter than chunk_size.
    boundary_search_ratio: float = 0.3
    # A final remainder shorter than this is merged into the previous chunk
    # instead of producing a tiny, mostly-overlap chunk.
    min_tail_ratio: float = 0.15

    def __post_init__(self) -> None:
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be at least 100 characters")
        if not 0 <= self.chunk_overlap < self.chunk_size // 2:
            raise ValueError("chunk_overlap must be >= 0 and less than half of chunk_size")


@dataclass(frozen=True)
class TextChunk:
    document_id: uuid.UUID | None
    chunk_index: int
    content: str
    page_number: int  # first page
    page_end: int  # last page (== page_number unless the chunk spans pages)
    start_char: int  # offsets into the joined text (debugging / tests)
    end_char: int
    # Where each later page begins inside `content`: ((offset, page), ...).
    # Empty for single-page chunks.
    page_breaks: tuple[tuple[int, int], ...] = ()


class _PageMap:
    """Joins pages into one string and maps character offsets back to pages."""

    def __init__(self, pages: list[PageText]) -> None:
        parts: list[str] = []
        self.starts: list[int] = []
        self.page_numbers: list[int] = []
        offset = 0
        for page in pages:
            if not page.text:
                continue  # blank pages contribute no text, numbering is untouched
            if parts:
                parts.append(PAGE_SEPARATOR)
                offset += len(PAGE_SEPARATOR)
            self.starts.append(offset)
            self.page_numbers.append(page.page_number)
            parts.append(page.text)
            offset += len(page.text)
        self.text = "".join(parts)

    def page_at(self, offset: int) -> int:
        return self.page_numbers[bisect.bisect_right(self.starts, offset) - 1]

    def breaks_within(self, start: int, end: int) -> tuple[tuple[int, int], ...]:
        """Pages that begin strictly inside [start, end), as (offset from start, page)."""
        first = bisect.bisect_right(self.starts, start)
        last = bisect.bisect_left(self.starts, end)
        return tuple((self.starts[i] - start, self.page_numbers[i]) for i in range(first, last))


def _find_split(text: str, start: int, hard_end: int, settings: ChunkSettings) -> int:
    """Best end offset in (start, hard_end], preferring strong boundaries."""
    if hard_end >= len(text):
        return len(text)
    window_start = max(start + 1, hard_end - int(settings.chunk_size * settings.boundary_search_ratio))
    window = text[window_start:hard_end]
    for pattern in _BOUNDARIES:
        matches = list(pattern.finditer(window))
        if matches:
            return window_start + matches[-1].end()
    return hard_end  # no boundary at all (e.g. a very long token): hard cut


def _next_start(text: str, end: int, overlap: int, prev_start: int) -> int:
    """Start of the next chunk: `overlap` chars back, snapped to a word start."""
    if overlap == 0:
        return end
    start = max(end - overlap, prev_start + 1)
    # Move forward to the beginning of a word so no chunk starts mid-word.
    if start > 0 and not text[start - 1].isspace():
        match = re.compile(r"\s").search(text, start, end)
        start = match.end() if match else end
    return start


def _trimmed_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def chunk_pages(
    pages: list[PageText],
    settings: ChunkSettings | None = None,
    document_id: uuid.UUID | None = None,
) -> list[TextChunk]:
    settings = settings or ChunkSettings()
    page_map = _PageMap(pages)
    text = page_map.text
    chunks: list[TextChunk] = []
    min_tail = int(settings.chunk_size * settings.min_tail_ratio)

    start = 0
    while start < len(text):
        if len(text) - start <= settings.chunk_size + min_tail:
            end = len(text)  # the rest fits: avoid a tiny, mostly-overlap last chunk
        else:
            end = _find_split(text, start, start + settings.chunk_size, settings)

        content_start, content_end = _trimmed_bounds(text, start, end)
        if content_start < content_end:
            chunks.append(
                TextChunk(
                    document_id=document_id,
                    chunk_index=len(chunks),
                    content=text[content_start:content_end],
                    page_number=page_map.page_at(content_start),
                    page_end=page_map.page_at(content_end - 1),
                    start_char=content_start,
                    end_char=content_end,
                    page_breaks=page_map.breaks_within(content_start, content_end),
                )
            )
        if end >= len(text):
            break
        start = _next_start(text, end, settings.chunk_overlap, start)

    logger.info(
        "Chunked document=%s chars=%d chunks=%d multi_page=%d size=%d overlap=%d",
        document_id,
        len(text),
        len(chunks),
        sum(1 for c in chunks if c.page_end != c.page_number),
        settings.chunk_size,
        settings.chunk_overlap,
    )
    return chunks
