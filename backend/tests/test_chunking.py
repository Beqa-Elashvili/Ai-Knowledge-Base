import re
import uuid

import pytest

from app.services.chunking import ChunkSettings, _PageMap, chunk_pages
from app.services.pdf import PageText

SMALL = ChunkSettings(chunk_size=200, chunk_overlap=40)


def sentences(prefix: str, count: int) -> str:
    return " ".join(f"{prefix} sentence number {i} explains one idea." for i in range(count))


def page_of_marker(pages: list[PageText], marker: str) -> int:
    return next(p.page_number for p in pages if marker in p.text)


# --- page metadata -----------------------------------------------------------

def test_every_chunk_page_range_matches_its_actual_text() -> None:
    """Each word carries its page as a marker; the chunk's range must cover
    exactly the pages whose markers appear in it."""
    pages = [PageText(n, " ".join(f"w{n}x{i}" for i in range(80))) for n in range(1, 6)]
    for chunk in chunk_pages(pages, SMALL):
        seen = {int(m) for m in re.findall(r"w(\d+)x\d+", chunk.content)}
        assert chunk.page_number == min(seen)
        assert chunk.page_end == max(seen)
        assert seen == set(range(chunk.page_number, chunk.page_end + 1))


def test_chunk_within_one_page_has_single_page_range() -> None:
    pages = [PageText(1, sentences("Alpha", 3)), PageText(2, sentences("Beta", 3))]
    chunks = chunk_pages(pages, ChunkSettings(chunk_size=150, chunk_overlap=0))
    beta_only = [c for c in chunks if "Beta" in c.content and "Alpha" not in c.content]
    assert beta_only and all((c.page_number, c.page_end) == (2, 2) for c in beta_only)


def test_chunk_crossing_pages_records_both() -> None:
    pages = [PageText(14, "End of the argument on page fourteen."), PageText(15, "Continues on page fifteen.")]
    [chunk] = chunk_pages(pages, ChunkSettings(chunk_size=500, chunk_overlap=50))
    assert (chunk.page_number, chunk.page_end) == (14, 15)


def test_blank_pages_do_not_shift_numbering() -> None:
    pages = [PageText(1, "First page text."), PageText(2, ""), PageText(3, ""), PageText(4, "Fourth page text.")]
    chunks = chunk_pages(pages, ChunkSettings(chunk_size=100, chunk_overlap=0, min_tail_ratio=0))
    assert [(c.page_number, c.page_end) for c in chunks] == [(1, 4)]
    only_fourth = chunk_pages([PageText(2, ""), PageText(4, "Fourth page text.")])
    assert (only_fourth[0].page_number, only_fourth[0].page_end) == (4, 4)


def test_page_map_offsets() -> None:
    page_map = _PageMap([PageText(3, "abc"), PageText(4, ""), PageText(5, "de")])
    assert page_map.text == "abc\n\nde"
    assert [page_map.page_at(i) for i in range(len(page_map.text))] == [3, 3, 3, 3, 3, 5, 5]


# --- coverage, size, overlap ---------------------------------------------------

@pytest.fixture
def book() -> list[PageText]:
    return [PageText(n, "\n\n".join(sentences(f"P{n}p{k}", 6) for k in range(3))) for n in range(1, 9)]


def test_no_text_is_lost(book: list[PageText]) -> None:
    text = _PageMap(book).text
    chunks = chunk_pages(book, SMALL)
    covered = [False] * len(text)
    for c in chunks:
        assert text[c.start_char:c.end_char] == c.content
        for i in range(c.start_char, c.end_char):
            covered[i] = True
    assert all(covered[i] for i, ch in enumerate(text) if not ch.isspace())


def test_chunk_sizes_respect_limit(book: list[PageText]) -> None:
    chunks = chunk_pages(book, SMALL)
    limit = SMALL.chunk_size + int(SMALL.chunk_size * SMALL.min_tail_ratio)
    assert all(len(c.content) <= limit for c in chunks)
    # Boundary search keeps chunks reasonably full, except the last one.
    assert all(len(c.content) >= SMALL.chunk_size * 0.6 for c in chunks[:-1])


def test_consecutive_chunks_overlap(book: list[PageText]) -> None:
    chunks = chunk_pages(book, SMALL)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.start_char < prev.end_char, "expected overlap"
        assert prev.end_char - nxt.start_char <= SMALL.chunk_overlap


def test_zero_overlap_has_no_shared_text(book: list[PageText]) -> None:
    chunks = chunk_pages(book, ChunkSettings(chunk_size=200, chunk_overlap=0))
    assert all(nxt.start_char >= prev.end_char for prev, nxt in zip(chunks, chunks[1:]))


def test_chunks_prefer_sentence_or_paragraph_ends(book: list[PageText]) -> None:
    chunks = chunk_pages(book, SMALL)
    assert all(c.content.endswith(".") for c in chunks)


def test_visual_line_wraps_do_not_beat_sentence_ends() -> None:
    """PDF text wraps lines with '\\n' mid-sentence; those are not real boundaries."""
    import textwrap

    prose = " ".join(f"Sentence {i} discusses gradient descent and how networks update weights." for i in range(40))
    wrapped = textwrap.fill(prose, width=70)  # '\n' roughly every 70 chars, mid-sentence
    chunks = chunk_pages([PageText(1, wrapped)], SMALL)
    assert len(chunks) > 3
    assert all(c.content.endswith(".") for c in chunks), [c.content[-30:] for c in chunks if not c.content.endswith(".")]


def test_chunks_never_start_mid_word(book: list[PageText]) -> None:
    text = _PageMap(book).text
    assert all(c.start_char == 0 or text[c.start_char - 1].isspace() for c in chunk_pages(book, SMALL))


def test_indexes_are_sequential_and_document_id_attached(book: list[PageText]) -> None:
    doc_id = uuid.uuid4()
    chunks = chunk_pages(book, SMALL, document_id=doc_id)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.document_id == doc_id for c in chunks)


def test_tiny_tail_is_merged_into_previous_chunk() -> None:
    text = sentences("Body", 6)[:190] + " tail."
    chunks = chunk_pages([PageText(1, text)], ChunkSettings(chunk_size=190, chunk_overlap=20))
    assert chunks[-1].content.endswith("tail.") and len(chunks) == 1


# --- edge cases -------------------------------------------------------------

def test_long_unbroken_token_is_hard_split() -> None:
    chunks = chunk_pages([PageText(1, "x" * 450)], ChunkSettings(chunk_size=200, chunk_overlap=0, min_tail_ratio=0))
    assert [len(c.content) for c in chunks] == [200, 200, 50]


def test_empty_input_gives_no_chunks() -> None:
    assert chunk_pages([]) == []
    assert chunk_pages([PageText(1, ""), PageText(2, "")]) == []


def test_georgian_text() -> None:
    georgian = " ".join(["ნეირონული ქსელები სწავლობენ წონების შეცვლით."] * 30)
    chunks = chunk_pages([PageText(1, georgian)], ChunkSettings(chunk_size=300, chunk_overlap=50))
    assert len(chunks) > 1 and all(c.content.endswith(".") for c in chunks)


@pytest.mark.parametrize("size,overlap", [(50, 10), (200, 100), (200, -1)])
def test_invalid_settings_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        ChunkSettings(chunk_size=size, chunk_overlap=overlap)
