"""Agent-facing input schemas for the agentic tabular-review ("grids") tool — ADR-F055.

The deepagents Commercial tool (:mod:`app.agents.tabular_tool`) validates the model's
tool arguments through these Pydantic models (reject-don't-sanitize, the same posture as
:mod:`app.schemas.commercial`). Kept separate from :mod:`app.schemas.tabular` (the frozen
executor's ``/api/v1/tabular`` wire surface) so the agentic WRITE path can evolve
independently; it reuses ``ColumnSpec`` + ``CellConfidence`` from there.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.schemas.tabular import CellConfidence, ColumnSpec

# Caps — reject an over-large tool call before it touches the DB (cells live in a JSONB
# grid; a runaway payload is a defect, not a feature). Display-grade bounds, not billing.
_VALUE_MAX = 4_000
_QUOTE_MAX = 2_000
_NOTES_MAX = 2_000
_MAX_CITED_CHUNKS = 32
_MAX_COLUMNS = 40
_MAX_DOCUMENTS = 500
_DOC_NAME_MAX = 500


class AgenticCellInput(BaseModel):
    """One cell a (sub)agent records for its row (``record_tabular_row``).

    Persisted into the grid's ``results`` JSONB as the executor-agnostic cell shape:
    ``cited_chunk_ids`` (NOT ``citations``) so the read-side
    ``TabularRow._synthesize_cell_citations`` validator builds display citations, plus
    ``source_quote`` + ``notes`` (LQ-Grid-derived). ``confidence='failed'`` is the honest
    empty-cell state (``value`` None) — never a silent gap.
    """

    value: str | None = Field(default=None, max_length=_VALUE_MAX)
    confidence: CellConfidence
    cited_chunk_ids: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_CITED_CHUNKS)
    source_quote: str | None = Field(default=None, max_length=_QUOTE_MAX)
    notes: str | None = Field(default=None, max_length=_NOTES_MAX)


class StartTabularReviewInput(BaseModel):
    """Args for ``start_tabular_review`` — the column spec + an optional document subset.

    ``documents`` are filenames exactly as shown by ``search_documents`` (the agent works
    in filenames; the tool resolves them to document ids). ``None``/empty ⇒ the whole
    matter's ingested documents.
    """

    columns: list[ColumnSpec] = Field(min_length=1, max_length=_MAX_COLUMNS)
    documents: list[str] | None = Field(default=None, max_length=_MAX_DOCUMENTS)


class RecordTabularRowInput(BaseModel):
    """Args for ``record_tabular_row`` — one document's row of cells (keyed by column name)."""

    grid_id: uuid.UUID
    document: str = Field(min_length=1, max_length=_DOC_NAME_MAX)
    cells: dict[str, AgenticCellInput] = Field(min_length=1)


class FinalizeTabularReviewInput(BaseModel):
    """Args for ``finalize_tabular_review``."""

    grid_id: uuid.UUID


class GatherRowEvidenceInput(BaseModel):
    """Args for ``gather_row_evidence`` — the bounded row-evidence retrieval (T4)."""

    grid_id: uuid.UUID
    document: str = Field(min_length=1, max_length=_DOC_NAME_MAX)


__all__ = [
    "AgenticCellInput",
    "FinalizeTabularReviewInput",
    "GatherRowEvidenceInput",
    "RecordTabularRowInput",
    "StartTabularReviewInput",
]
