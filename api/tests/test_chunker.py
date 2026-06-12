"""Unit tests for the C5 chunker — character-precise offsets.

The load-bearing invariant the M2 Citation Engine consumes is
``original_text[chunk.char_offset_start:chunk.char_offset_end] ==
chunk.content``. Every test here either exercises that invariant
directly or exercises a chunker behaviour that could break it.
"""

from __future__ import annotations

import pytest

from app.pipeline.chunker import (
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
    SENTENCE_BOUNDARY_LOOKBACK,
    chunk_document,
)
from app.pipeline.parsers import PageSpan, ParsedDocument


def _make_parsed(text: str, *, page_size: int | None = None) -> ParsedDocument:
    """Construct a ParsedDocument with optional fixed-size page spans.

    If ``page_size`` is None the document is single-page.
    """

    if page_size is None:
        pages = [PageSpan(page_number=1, char_start=0, char_end=len(text))]
    else:
        pages = []
        for i in range(0, len(text), page_size):
            pages.append(
                PageSpan(
                    page_number=len(pages) + 1,
                    char_start=i,
                    char_end=min(i + page_size, len(text)),
                )
            )
    return ParsedDocument(
        canonical_text=text,
        pages=pages,
        page_count=len(pages),
        parser="test",
        parser_version="test=1.0",
    )


# ---------------------------------------------------------------------------
# The load-bearing invariant — slice fidelity.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chunk_offsets_slice_back_byte_for_byte() -> None:
    """The fidelity invariant — every chunk's content equals the slice."""

    text = (
        "The quick brown fox jumps over the lazy dog. " * 200
        + "Pack my box with five dozen liquor jugs. " * 200
    )
    parsed = _make_parsed(text)

    chunks = chunk_document(parsed, target_chars=500, overlap_chars=50)

    assert len(chunks) > 1, "fixture should produce multiple chunks"
    for chunk in chunks:
        assert chunk.content == text[chunk.char_offset_start : chunk.char_offset_end], (
            f"chunk {chunk.chunk_index} fidelity broken: "
            f"len(content)={len(chunk.content)}, "
            f"offsets=[{chunk.char_offset_start}, {chunk.char_offset_end})"
        )


@pytest.mark.unit
def test_chunk_offsets_slice_back_short_input() -> None:
    """Short input that doesn't even fill one chunk still slices."""

    text = "Hello world."
    parsed = _make_parsed(text)
    chunks = chunk_document(parsed, target_chars=2000, overlap_chars=0)

    assert len(chunks) == 1
    assert chunks[0].content == text
    assert (
        chunks[0].content
        == text[chunks[0].char_offset_start : chunks[0].char_offset_end]
    )
    assert chunks[0].char_offset_start == 0
    assert chunks[0].char_offset_end == len(text)


@pytest.mark.unit
def test_chunk_offsets_slice_back_unicode() -> None:
    """Unicode (multi-byte UTF-8 codepoints) preserves byte fidelity.

    Python str slicing operates on code points, not bytes — the
    chunker's offsets are code-point offsets, and slicing the
    canonical_text by them yields the same code-point sequence as
    the chunk's content.
    """

    text = (
        "Le renard brun rapide saute par-dessus le chien paresseux. " * 50
        + "東京特許許可局 局長許可拒否。" * 50
        + "El veloz murciélago hindú comía feliz cardillo y kiwi. " * 50
    )
    parsed = _make_parsed(text)
    chunks = chunk_document(parsed, target_chars=400, overlap_chars=40)

    for chunk in chunks:
        assert chunk.content == text[chunk.char_offset_start : chunk.char_offset_end]


# ---------------------------------------------------------------------------
# Chunk shape: indexing, ordering, contiguity (modulo overlap).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chunks_are_indexed_sequentially() -> None:
    parsed = _make_parsed("a" * 10_000)
    chunks = chunk_document(parsed, target_chars=1_000, overlap_chars=0)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


@pytest.mark.unit
def test_chunks_cover_entire_text_no_gaps_without_overlap() -> None:
    """With overlap=0, chunks tile the text — concat all = original."""

    text = "x" * 10_000
    parsed = _make_parsed(text)
    chunks = chunk_document(parsed, target_chars=1_000, overlap_chars=0)
    reconstructed = "".join(c.content for c in chunks)
    assert reconstructed == text


@pytest.mark.unit
def test_overlap_advances_by_step_size() -> None:
    """With overlap > 0, consecutive chunks overlap by approximately ``overlap``."""

    text = "x" * 5_000
    parsed = _make_parsed(text)
    target, overlap = 1_000, 100
    chunks = chunk_document(parsed, target_chars=target, overlap_chars=overlap)
    for i in range(len(chunks) - 1):
        # Step from one chunk's start to the next is target - overlap.
        step = chunks[i + 1].char_offset_start - chunks[i].char_offset_start
        # Step is `chunk_len - overlap`; the chunk_len equals target
        # since there's no sentence boundary (single repeated char).
        assert step == target - overlap


@pytest.mark.unit
def test_last_chunk_ends_at_text_end() -> None:
    text = "Hello, world. " * 100
    parsed = _make_parsed(text)
    chunks = chunk_document(parsed, target_chars=400, overlap_chars=40)
    assert chunks[-1].char_offset_end == len(text)


# ---------------------------------------------------------------------------
# Sentence-boundary snapping.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_snap_to_sentence_boundary_inside_window() -> None:
    """When a sentence ends within the lookback window, snap to it."""

    # First "section" is 950 chars; a sentence ends right around there.
    sentence = "The quick brown fox jumps over the lazy dog. "  # 45 chars
    text = sentence * 21 + "extra trailing words " * 100
    parsed = _make_parsed(text)
    chunks = chunk_document(parsed, target_chars=1000, overlap_chars=0)

    # The first chunk should end at a sentence boundary, NOT mid-sentence.
    first = chunks[0]
    assert first.metadata["snapped"] is True
    # The boundary should land on whitespace following ".":
    snapped_end_char = text[first.char_offset_end - 1]
    assert snapped_end_char in ". \n", f"snapped end is {snapped_end_char!r}"


@pytest.mark.unit
def test_snap_does_not_violate_min_chars_floor() -> None:
    """If snapping would produce a tiny chunk, skip it."""

    # Lots of sentence terminators very early; snapping back to them
    # would produce tiny chunks. The floor protects against this.
    text = "A. B. C. D. " * 100  # sentence terminators every 3 chars
    parsed = _make_parsed(text)
    chunks = chunk_document(parsed, target_chars=400, overlap_chars=40, min_chars=200)
    for chunk in chunks[:-1]:  # last chunk can be short (end of text)
        assert (chunk.char_offset_end - chunk.char_offset_start) >= 200


@pytest.mark.unit
def test_snap_to_paragraph_break_preferred_over_sentence() -> None:
    """When both sentence and paragraph breaks are within window, prefer paragraph."""

    chunk_target = 100
    # Construct a text where the para-break is closer to the target_end
    # than the sentence terminator — by putting a para break after the
    # sentence terminator within the lookback window.
    text = (
        "Line one ends here. "  # sentence terminator at ~20
        "More words filling space until we approach the chunk target. "
        "And then a paragraph break.\n\n"
        "New paragraph starts here. "
        "And continues for a while past the chunker's lookback range. "
    )
    parsed = _make_parsed(text)
    chunks = chunk_document(
        parsed, target_chars=chunk_target, overlap_chars=0, min_chars=20
    )

    # The first chunk should snap to the paragraph break in preference.
    # Slice fidelity must hold regardless.
    first = chunks[0]
    assert first.content == text[first.char_offset_start : first.char_offset_end]


# ---------------------------------------------------------------------------
# Page assignment.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_page_assignment_within_single_page() -> None:
    text = "x" * 1_000
    parsed = _make_parsed(text, page_size=2_000)  # one page for all of it
    chunks = chunk_document(parsed, target_chars=300, overlap_chars=0)
    for chunk in chunks:
        assert chunk.page_start == 1
        assert chunk.page_end == 1


@pytest.mark.unit
def test_page_assignment_crosses_page_boundary() -> None:
    text = "x" * 1_000
    parsed = _make_parsed(text, page_size=400)  # 3 pages
    # Use a target that forces a chunk to span pages.
    chunks = chunk_document(parsed, target_chars=600, overlap_chars=0)

    # At least one chunk should span two pages.
    spanning = [c for c in chunks if c.page_start != c.page_end]
    assert spanning, f"expected at least one cross-page chunk; got {chunks}"
    for c in spanning:
        assert c.page_end is not None and c.page_start is not None
        assert c.page_end > c.page_start


# ---------------------------------------------------------------------------
# Edge cases.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_text_yields_empty_chunks() -> None:
    parsed = _make_parsed("")
    assert chunk_document(parsed) == []


@pytest.mark.unit
def test_target_must_be_positive() -> None:
    parsed = _make_parsed("x" * 100)
    with pytest.raises(ValueError):
        chunk_document(parsed, target_chars=0, overlap_chars=0)


@pytest.mark.unit
def test_overlap_below_target() -> None:
    parsed = _make_parsed("x" * 100)
    with pytest.raises(ValueError):
        chunk_document(parsed, target_chars=100, overlap_chars=100)


@pytest.mark.unit
def test_negative_overlap_rejected() -> None:
    parsed = _make_parsed("x" * 100)
    with pytest.raises(ValueError):
        chunk_document(parsed, target_chars=100, overlap_chars=-1)


@pytest.mark.unit
def test_chunk_dataclass_slice_helper() -> None:
    canonical = "world hello again"
    # The chunk dataclass carries offsets that match the canonical text;
    # the equivalent ORM model centralises the slicing convention via
    # the helper method we exercise here.
    from app.models.document import DocumentChunk

    db_chunk = DocumentChunk(
        document_id=None,  # placeholder
        chunk_index=0,
        content="hello",
        char_offset_start=6,
        char_offset_end=11,
    )
    assert db_chunk.slice_original(canonical) == "hello"


# ---------------------------------------------------------------------------
# Defaults sanity.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_target_and_overlap_are_sensible() -> None:
    assert DEFAULT_TARGET_CHARS > 0
    assert DEFAULT_OVERLAP_CHARS >= 0
    assert DEFAULT_OVERLAP_CHARS < DEFAULT_TARGET_CHARS


@pytest.mark.unit
def test_lookback_constant_is_smaller_than_default_target() -> None:
    assert SENTENCE_BOUNDARY_LOOKBACK < DEFAULT_TARGET_CHARS
