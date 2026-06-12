"""Character-precise sliding-window chunker — Task C5.

This module produces :class:`Chunk` records from a parsed document's
canonical text. The load-bearing invariant for every chunk is:

    canonical_text[chunk.char_offset_start:chunk.char_offset_end] == chunk.content

The M2 Citation Engine depends on this fidelity for its deterministic
substring verification step (PRD §3.6). Re-ingesting the M1 corpus to
fix offset drift is expensive and avoidable — this module's tests
guard the invariant on every change.

Strategy (M1 simple sliding window):

* Walk the canonical text in steps of ``target_chars - overlap_chars``.
* Each chunk is a half-open ``[start, end)`` slice of the canonical
  text. ``end`` is clamped to ``len(text)``; the final chunk is
  whatever remains.
* When possible, snap the chunk boundary back to the nearest
  sentence terminator (``.``, ``!``, ``?``, or paragraph break) within
  a configurable look-back window. Snapping never crosses the
  ``min_chars`` floor — we'd rather have a slightly longer chunk than
  a tiny one.
* Page assignment is computed by binary-search against the page-span
  table from the parser. A chunk that crosses a page boundary records
  its first page in ``page_start`` and last page in ``page_end``.

Why a simple chunker for M1 and not Docling-aware boundaries:

* Docling's structural boundaries (sections, paragraphs) are not
  character-precise against the PyMuPDF stream; using them would
  require a reconciliation layer that doesn't pay off until M2's
  citation engine wants finer-grained chunks.
* The M2 Citation Engine reads the canonical-text slice, not the
  chunk boundaries — chunk boundaries are an indexing optimisation
  (which chunks to include in the prompt), not a verification artifact.
* Premature optimisation on the chunker shape risks breaking the
  fidelity invariant. We ship the simple correct thing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.pipeline.parsers import PageSpan, ParsedDocument

# Default chunk shape — tuned for ~500 token chunks at ~4 chars/token,
# with a 200-char overlap. Operators can override via config / settings.
DEFAULT_TARGET_CHARS = 2_000
DEFAULT_OVERLAP_CHARS = 200
# A chunk shorter than this is "tiny"; we won't snap a boundary back
# behind this floor. 0 disables.
DEFAULT_MIN_CHARS = 200

# Look-back window for sentence-boundary snapping. We scan up to this
# many chars before the proposed end, looking for sentence punctuation
# followed by whitespace.
SENTENCE_BOUNDARY_LOOKBACK = 200

# Sentence terminators we'll snap to. Multilingual concerns are punted
# to M2; for M1's English-corpus assumption these cover the common cases.
_SENTENCE_TERMINATOR = re.compile(r"[.!?]\s")
# Paragraph break: two-or-more newlines (with possible whitespace between).
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


@dataclass(slots=True)
class Chunk:
    """A character-precise chunk of canonical text.

    Attributes:
        chunk_index: Zero-based position in the document.
        content: The chunk's text. Equal to
            ``canonical_text[char_offset_start:char_offset_end]`` byte
            for byte. Emphasised by the test in
            :mod:`api/tests/test_chunker_offset_fidelity`.
        char_offset_start: 0-based inclusive offset into the canonical
            text.
        char_offset_end: 0-based exclusive offset (Python slice
            semantics).
        page_start: 1-based page number of the chunk's first character,
            or None if no page span covers the offset.
        page_end: 1-based page number of the chunk's last character,
            or None.
        metadata: Free-form metadata about how this chunk was produced
            (e.g., snap target, sentence-aware boundary). Used for
            debugging; M1 readers don't depend on it.
    """

    chunk_index: int
    content: str
    char_offset_start: int
    char_offset_end: int
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_document(
    parsed: ParsedDocument,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[Chunk]:
    """Chunk a parsed document into character-precise records.

    Args:
        parsed: The :class:`ParsedDocument` produced by
            :func:`app.pipeline.parsers.parse_pdf`.
        target_chars: Approximate target chunk size in characters.
            Sentence-boundary snapping moves the actual end up to
            ``SENTENCE_BOUNDARY_LOOKBACK`` characters behind this.
        overlap_chars: Number of characters of overlap between
            consecutive chunks. ``0`` disables overlap.
        min_chars: Minimum chunk size — boundary-snapping won't move
            a chunk's end before this many characters past its start.
            Set to ``0`` to disable the floor.

    Returns:
        A list of :class:`Chunk` records in document order. Each chunk's
        ``[char_offset_start:char_offset_end]`` slice of
        ``parsed.canonical_text`` equals its ``content``.

    Raises:
        :class:`ValueError`: ``target_chars`` is non-positive or
            ``overlap_chars`` is greater than-or-equal-to
            ``target_chars`` (would produce no progress).
    """

    if target_chars <= 0:
        raise ValueError(f"target_chars must be positive; got {target_chars}")
    if overlap_chars < 0:
        raise ValueError(f"overlap_chars must be non-negative; got {overlap_chars}")
    if overlap_chars >= target_chars:
        raise ValueError(
            "overlap_chars must be strictly less than target_chars; "
            f"got overlap={overlap_chars}, target={target_chars}"
        )
    if min_chars < 0:
        raise ValueError(f"min_chars must be non-negative; got {min_chars}")

    text = parsed.canonical_text
    if not text:
        return []

    chunks: list[Chunk] = []
    pages = parsed.pages
    cursor = 0
    chunk_idx = 0

    while cursor < len(text):
        proposed_end = min(cursor + target_chars, len(text))

        # Sentence-boundary snap: if we're not at the end of the text
        # and there's a clean sentence boundary within the lookback
        # window, snap to it (but never below `min_chars` from the
        # cursor).
        actual_end = _snap_to_sentence_boundary(
            text=text,
            cursor=cursor,
            proposed_end=proposed_end,
            min_chars=min_chars,
        )

        # Defensive: actual_end must lie in (cursor, len(text)] — if
        # the snapper produced something outside this range, fall back
        # to the proposed end.
        if actual_end <= cursor or actual_end > len(text):
            actual_end = proposed_end

        content = text[cursor:actual_end]

        # Compute page span for this chunk by looking up the offsets in
        # the page-span table.
        page_start = _page_for_offset(pages, cursor)
        # page_end is the page of the LAST character — actual_end is
        # exclusive, so look up actual_end - 1.
        page_end = (
            _page_for_offset(pages, actual_end - 1)
            if actual_end > cursor
            else page_start
        )

        chunk = Chunk(
            chunk_index=chunk_idx,
            content=content,
            char_offset_start=cursor,
            char_offset_end=actual_end,
            page_start=page_start,
            page_end=page_end,
            metadata={
                "target_chars": target_chars,
                "overlap_chars": overlap_chars,
                "snapped": actual_end != proposed_end,
            },
        )
        chunks.append(chunk)
        chunk_idx += 1

        if actual_end >= len(text):
            break

        # Advance: step forward by (chunk size - overlap), but never less
        # than 1 char. The overlap is calculated against the actual chunk
        # length, not the target, so a snapped-short chunk overlaps less.
        chunk_len = actual_end - cursor
        step = max(1, chunk_len - overlap_chars)
        cursor = cursor + step

    return chunks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _snap_to_sentence_boundary(
    *,
    text: str,
    cursor: int,
    proposed_end: int,
    min_chars: int,
) -> int:
    """Return ``proposed_end`` snapped back to the nearest sentence boundary.

    The snap looks back up to :data:`SENTENCE_BOUNDARY_LOOKBACK`
    characters from ``proposed_end``, searching for either:

    * a sentence terminator (``.!?``) followed by whitespace, OR
    * a paragraph break (two or more newlines).

    If one is found, the chunk ends at the position just after the
    terminator's whitespace (or just after the paragraph break). If
    none is found within the window, ``proposed_end`` is returned
    unchanged.

    The snap never moves the boundary before ``cursor + min_chars`` —
    a tiny chunk is worse than a slightly long one.

    The function preserves the byte-precision invariant: the returned
    offset is a valid index into ``text`` and slicing
    ``text[cursor:returned]`` yields the chunk content.
    """

    # End-of-text: don't snap.
    if proposed_end >= len(text):
        return proposed_end

    # Don't snap if we'd have to look back more than is available.
    floor = max(cursor + min_chars, proposed_end - SENTENCE_BOUNDARY_LOOKBACK)
    if floor >= proposed_end:
        return proposed_end

    window = text[floor:proposed_end]

    # Prefer paragraph breaks over sentence terminators — they're a
    # cleaner semantic boundary.
    para_match = None
    for m in _PARAGRAPH_BREAK.finditer(window):
        para_match = m  # last match in the window
    if para_match is not None:
        return floor + para_match.end()

    sentence_match = None
    for m in _SENTENCE_TERMINATOR.finditer(window):
        sentence_match = m  # last match in the window
    if sentence_match is not None:
        return floor + sentence_match.end()

    return proposed_end


def _page_for_offset(pages: Sequence[PageSpan], offset: int) -> int | None:
    """Return the 1-based page number containing ``offset``, or None.

    Linear scan through the page-span table — page counts are bounded
    (PDFs >1000 pages are rare and even at 10K pages a 10K-step linear
    scan is fast). If we ever care about asymptotics, switch to
    bisect_right against ``[p.char_start for p in pages]``.

    Returns None when the offset doesn't fall within any page span;
    this can happen if the canonical text has trailing whitespace
    beyond the last page boundary, etc.
    """

    if not pages:
        return None
    for span in pages:
        if span.char_start <= offset < span.char_end:
            return span.page_number
    # Edge case: offset == last page's char_end. Treat as "on the last page."
    last = pages[-1]
    if offset == last.char_end:
        return last.page_number
    return None
