"""Agentic tabular review — the Commercial "grids" tool (ADR-F055, F2 Tabular T1).

The Commercial Deep Agent builds a cross-document review grid (a column per question, a
row per document) as a model-driven TOOL — NOT the frozen linear executor
(``app.tabular.*`` stays untouched, ADR-F001). The flow is three guarded tools:

* :func:`start_tabular_review` — snapshot the columns + resolve the documents, create the
  ``mode='agentic'`` grid row, and return a ``grid_id`` plus a recommended fill strategy.
* :func:`record_tabular_row` — a (sub)agent that has read ONE document writes that
  document's row. Committed incrementally (a token-budget halt leaves a partial-but-
  persisted grid, F1-S1) and serialized with ``SELECT … FOR UPDATE`` so parallel fan-out
  subagents never lose a row to a read-modify-write race on the ``results`` JSONB.
* :func:`finalize_tabular_review` — the completeness gate (ADR-F034/F032 no-silent-action):
  refuses until every (document x column) cell was ATTEMPTED (``confidence='failed'`` is a
  legitimate attempt), then flips the grid to ``completed``.

**Matter-scoped (ADR-F035).** Every grid carries ``project_id`` + ``user_id``; load/record/
finalize re-assert both (cross-user / cross-matter is the same 404-conflated absence). The
grant set (:data:`TABULAR_TOOL_NAMES`) is disjoint from every other matter/domain grant
(confinement) and is wired only when the Grids capability is enabled (ADR-F054).

The persisted cell shape mirrors the frozen executor's (``cited_chunk_ids`` + ``value`` +
``confidence``) so the existing read API + web grid render it unchanged, plus the
LQ-Grid-derived ``source_quote`` + ``notes``. Audit rows carry counts/types/IDs only —
never cell values or quotes (CLAUDE.md audit contract).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch

# The shared matter-membership query is the security boundary (membership union + owner
# re-assertion + not-deleted) — reuse it, never re-derive the scope (drift = a leak).
from app.agents.tools import MatterBinding, _matter_files_query
from app.audit import audit_action
from app.models.document import Document
from app.models.file import File
from app.models.project import ProjectFile
from app.models.tabular import TabularExecution
from app.schemas.tabular_agent import (
    AgenticCellInput,
    FinalizeTabularReviewInput,
    RecordTabularRowInput,
    StartTabularReviewInput,
)

logger = logging.getLogger(__name__)

TABULAR_TOOL_NAMES = frozenset(
    {"start_tabular_review", "record_tabular_row", "finalize_tabular_review"}
)


def build_tabular_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
    fan_out_quota: int,
) -> list[Callable[..., Any]]:
    """Build the matter's guarded agentic-tabular ("grids") tools for one run.

    ``fan_out_quota`` is the run's resolved subagent ceiling (ADR-F053 budget envelope);
    it sets the fan-out↔retrieval crossover ``start_tabular_review`` recommends. The guard
    context grants exactly :data:`TABULAR_TOOL_NAMES`; ``binding`` scopes every grid to the
    matter + owner.
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=TABULAR_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def start_tabular_review(
        columns: list[dict[str, Any]], documents: list[str] | None = None
    ) -> str:
        """Start a cross-document review GRID (a column per question, a row per document).

        Use this when the lawyer asks you to compare / extract / summarise a field across
        SEVERAL of this matter's documents (a due-diligence sweep, "what is the X in
        each", a key-terms table) — build a grid instead of answering in prose.

        - ``columns``: the grid's columns, each an object with ``name`` (the header) and
          ``query`` (the question to ask of every document, e.g. "What is the governing
          law?"). At least one column.
        - ``documents`` (optional): the filenames to cover, exactly as shown by
          search_documents. Omit (or pass an empty list) to cover the whole matter.

        Returns a ``grid_id`` and a recommended fill strategy. Then fill the grid: fan out
        one subagent per document with the task tool — each reads its document and calls
        record_tabular_row(grid_id, its filename, the cells) — and when every row is
        recorded, call finalize_tabular_review(grid_id).
        """
        return await guarded_dispatch(
            "start_tabular_review",
            lambda db: _start_tabular_review(
                db,
                binding,
                columns=columns,
                documents=documents,
                run_id=run_id,
                fan_out_quota=fan_out_quota,
            ),
            ctx,
        )

    async def record_tabular_row(
        grid_id: str, document: str, cells: dict[str, dict[str, Any]]
    ) -> str:
        """Record ONE document's row in a grid (call after reading that document).

        - ``grid_id``: the id returned by start_tabular_review.
        - ``document``: the document's filename, exactly as shown by search_documents.
        - ``cells``: a map of column name → cell, where each cell is an object with:
          ``value`` (the extracted answer; omit/null when not found), ``confidence``
          ("high" | "medium" | "low" | "failed"), an optional short ``source_quote``
          (verbatim text from the document that grounds the value), optional ``notes``
          (a note on anything ambiguous), and optional ``cited_chunk_ids``.

        Fill a cell for EVERY column — use ``confidence='failed'`` (with no value) when the
        document does not answer a column; never leave a column out silently. Calling again
        for the same document merges/overwrites its cells (use this to fix or fill in a
        row). The row is saved immediately.
        """
        return await guarded_dispatch(
            "record_tabular_row",
            lambda db: _record_tabular_row(
                db, binding, grid_id=grid_id, document=document, cells=cells, run_id=run_id
            ),
            ctx,
        )

    async def finalize_tabular_review(grid_id: str) -> str:
        """Finalize a grid once every document's row is recorded.

        Checks that every (document x column) cell was attempted — it REFUSES, listing the
        gaps, if any row or cell is missing (record the missing cells, using
        ``confidence='failed'`` where the document does not answer, then finalize again).
        On success the grid is marked complete and saved for the lawyer to open.
        """
        return await guarded_dispatch(
            "finalize_tabular_review",
            lambda db: _finalize_tabular_review(db, binding, grid_id=grid_id, run_id=run_id),
            ctx,
        )

    return [start_tabular_review, record_tabular_row, finalize_tabular_review]


# --- impls ----------------------------------------------------------------------------


async def _start_tabular_review(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    columns: list[dict[str, Any]],
    documents: list[str] | None,
    run_id: uuid.UUID,
    fan_out_quota: int,
) -> str:
    """Validate → resolve documents (matter-scoped) → create the agentic grid row."""
    try:
        proposal = StartTabularReviewInput(columns=columns, documents=documents)  # type: ignore[arg-type]
    except ValidationError as exc:
        return _rejection_text(exc, "start_tabular_review")

    resolved, unresolved = await _resolve_documents(db, binding, proposal.documents)
    if not resolved:
        if unresolved:
            return (
                "None of those filenames matched ingested documents in this matter: "
                f"{', '.join(unresolved)}. Check the names with search_documents (an empty "
                "query lists them)."
            )
        return (
            "This matter has no ingested documents to build a grid over. Upload or attach "
            "documents first."
        )

    column_names = [c.name for c in proposal.columns]
    grid_id = uuid.uuid4()
    execution = TabularExecution(
        id=grid_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        mode="agentic",
        status="running",
        created_by_run_id=run_id,
        document_ids=list(resolved.keys()),
        columns=[c.model_dump(mode="json") for c in proposal.columns],
        results={"rows": []},
        started_at=datetime.now(UTC),
    )
    db.add(execution)
    await db.flush()

    await audit_action(
        db,
        user_id=binding.user_id,
        action="tabular.grid_started",
        resource_type="tabular_execution",
        resource_id=str(grid_id),
        project_id=binding.project_id,
        practice_area_id=binding.practice_area_id,
        details={"columns": len(column_names), "documents": len(resolved)},
    )

    n_docs = len(resolved)
    fits_fanout = fan_out_quota <= 0 or n_docs <= fan_out_quota
    if fits_fanout:
        strategy = (
            "fan out one subagent per document with the task tool — each reads its document "
            "and calls record_tabular_row with the cells for every column"
        )
    else:
        strategy = (
            f"there are more documents ({n_docs}) than your subagent limit ({fan_out_quota}); "
            "read the most relevant documents and record their rows, retrieving passages with "
            "search_documents for the rest — fill every row"
        )
    note = f" (skipped {len(unresolved)} unmatched: {', '.join(unresolved)})" if unresolved else ""
    return (
        f"Started grid {grid_id} over {n_docs} document(s){note} with "
        f"{len(column_names)} column(s): {', '.join(column_names)}.\n"
        f"Recommended fill: {strategy}.\n"
        f'When every document\'s row is recorded, call finalize_tabular_review("{grid_id}").'
    )


async def _record_tabular_row(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    grid_id: str,
    document: str,
    cells: dict[str, dict[str, Any]],
    run_id: uuid.UUID,
) -> str:
    """Validate → lock the grid → resolve the document → upsert its row (merge cells)."""
    try:
        proposal = RecordTabularRowInput(grid_id=grid_id, document=document, cells=cells)  # type: ignore[arg-type]
    except ValidationError as exc:
        return _rejection_text(exc, "record_tabular_row")

    # FOR UPDATE: serialize concurrent fan-out writers on this grid's results JSONB
    # (read-modify-write would otherwise lose rows). The lock holds until the dispatch
    # commits — brief (one row update).
    execution = await _load_grid_for_update(db, binding, proposal.grid_id)
    if execution is None:
        return _no_grid_text(proposal.grid_id)
    if execution.status != "running":
        return (
            f"Grid {proposal.grid_id} is no longer open for writing (status="
            f"{execution.status!r}). Start a new grid if you need to."
        )

    resolved = await _resolve_one_document(db, binding, proposal.document)
    if resolved is None:
        return (
            f'No ingested document named "{proposal.document}" in this matter. Use '
            "search_documents (empty query) to list the matter's documents."
        )
    document_id, document_name = resolved
    if document_id not in set(execution.document_ids):
        names = await _names_for_documents(db, binding, list(execution.document_ids))
        covered = ", ".join(sorted(names.values())) or "(none)"
        return (
            f'"{document_name}" is not one of this grid\'s documents. The grid covers: {covered}.'
        )

    column_names = _column_names(execution)
    unknown = [name for name in proposal.cells if name not in column_names]
    if unknown:
        return (
            f"Unknown column(s) {', '.join(unknown)} — this grid's columns are: "
            f"{', '.join(column_names)}. Use the exact column names."
        )

    new_cells = {name: _cell_payload(cell) for name, cell in proposal.cells.items()}
    execution.results = _upsert_row(
        execution.results,
        document_id=str(document_id),
        document_name=document_name,
        cells=new_cells,
    )
    await db.flush()

    await audit_action(
        db,
        user_id=binding.user_id,
        action="tabular.row_recorded",
        resource_type="tabular_execution",
        resource_id=str(execution.id),
        project_id=binding.project_id,
        practice_area_id=binding.practice_area_id,
        details={"document_id": str(document_id), "cells": len(new_cells)},
    )

    filled, total = _coverage_counts(execution)
    return (
        f'Recorded {len(new_cells)} cell(s) for "{document_name}" in grid {execution.id}. '
        f"{filled}/{total} cell(s) filled across the grid. When every row is recorded, call "
        f"finalize_tabular_review."
    )


async def _finalize_tabular_review(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    grid_id: str,
    run_id: uuid.UUID,
) -> str:
    """Validate → lock the grid → completeness gate → mark completed (or reject the gaps)."""
    try:
        proposal = FinalizeTabularReviewInput(grid_id=grid_id)  # type: ignore[arg-type]
    except ValidationError as exc:
        return _rejection_text(exc, "finalize_tabular_review")

    execution = await _load_grid_for_update(db, binding, proposal.grid_id)
    if execution is None:
        return _no_grid_text(proposal.grid_id)
    if execution.status == "completed":
        return f"Grid {execution.id} is already finalized."
    if execution.status != "running":
        return f"Grid {execution.id} cannot be finalized (status={execution.status!r})."

    column_names = _column_names(execution)
    rows_by_doc = _rows_by_doc(execution.results)
    names = await _names_for_documents(db, binding, list(execution.document_ids))

    gaps: list[str] = []
    for doc_id in execution.document_ids:
        key = str(doc_id)
        label = names.get(key, key)
        row = rows_by_doc.get(key)
        if row is None:
            gaps.append(f'"{label}": no row recorded')
            continue
        cells = row.get("cells", {}) if isinstance(row, dict) else {}
        absent = [c for c in column_names if c not in cells]
        if absent:
            gaps.append(f'"{label}": missing column(s) {", ".join(absent)}')
    if gaps:
        return (
            "Not finalized — every document x column cell must be attempted first. Record "
            "the missing cells (use confidence='failed' where the document does not answer), "
            "then call finalize_tabular_review again. Gaps:\n- " + "\n- ".join(gaps)
        )

    execution.status = "completed"
    execution.completed_at = datetime.now(UTC)
    execution.fill_mode = "fanout"  # T1 implements the fan-out engine; T4 adds retrieval.
    await db.flush()

    filled, total = _coverage_counts(execution)
    failed = _failed_count(execution)
    await audit_action(
        db,
        user_id=binding.user_id,
        action="tabular.grid_finalized",
        resource_type="tabular_execution",
        resource_id=str(execution.id),
        project_id=binding.project_id,
        practice_area_id=binding.practice_area_id,
        details={
            "documents": len(execution.document_ids),
            "columns": len(column_names),
            "cells": total,
            "failed": failed,
        },
    )
    return (
        f"Finalized grid {execution.id}: {len(execution.document_ids)} document(s) x "
        f"{len(column_names)} column(s) ({filled} cell(s) filled, {failed} marked failed). "
        "Saved — the lawyer can open it in the Grids tab."
    )


# --- helpers --------------------------------------------------------------------------


async def _load_grid_for_update(
    db: AsyncSession, binding: MatterBinding, grid_id: uuid.UUID
) -> TabularExecution | None:
    """Load an AGENTIC grid for this matter + owner, locked for a read-modify-write.

    Matter + owner re-asserted (cross-user / cross-matter → None, 404-conflated). ``mode``
    pinned to 'agentic' so a tool can never touch a frozen linear execution row.
    """
    stmt = (
        select(TabularExecution)
        .where(
            TabularExecution.id == grid_id,
            TabularExecution.user_id == binding.user_id,
            TabularExecution.project_id == binding.project_id,
            TabularExecution.mode == "agentic",
            TabularExecution.deleted_at.is_(None),
        )
        .with_for_update()
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _resolve_documents(
    db: AsyncSession, binding: MatterBinding, filenames: list[str] | None
) -> tuple[dict[uuid.UUID, str], list[str]]:
    """Resolve ingested matter documents → ``{document_id: filename}`` (+ unmatched names).

    ``filenames`` None/empty ⇒ the whole matter's ingested documents. Names are matched
    parameterized over the matter scope (the security boundary in ``_matter_files_query``)
    — never built into SQL.
    """
    stmt = _matter_files_query(binding, Document.id.label("document_id"), File.filename).where(
        Document.id.is_not(None)
    )
    wanted = [f.strip() for f in filenames or [] if f.strip()]
    if wanted:
        stmt = stmt.where(func.lower(File.filename).in_([w.lower() for w in wanted]))
    rows = (await db.execute(stmt)).all()

    resolved: dict[uuid.UUID, str] = {}
    for row in rows:
        resolved.setdefault(row.document_id, row.filename)

    unresolved: list[str] = []
    if wanted:
        found = {name.lower() for name in resolved.values()}
        seen: set[str] = set()
        for name in wanted:
            low = name.lower()
            if low not in found and low not in seen:
                unresolved.append(name)
                seen.add(low)
    return resolved, unresolved


async def _resolve_one_document(
    db: AsyncSession, binding: MatterBinding, name: str
) -> tuple[uuid.UUID, str] | None:
    """Resolve one filename → (document_id, canonical filename), matter-scoped.

    Mirrors ``read_document``'s resolution (prefer the most recently added readable copy).
    """
    stmt = (
        _matter_files_query(binding, Document.id.label("document_id"), File.filename)
        .where(func.lower(File.filename) == name.strip().lower(), Document.id.is_not(None))
        .order_by(func.coalesce(ProjectFile.attached_at, File.created_at).desc())
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None
    return rows[0].document_id, rows[0].filename


async def _names_for_documents(
    db: AsyncSession, binding: MatterBinding, doc_ids: list[uuid.UUID]
) -> dict[str, str]:
    """Map ``{document_id_str: filename}`` for a grid's documents (matter-scoped)."""
    if not doc_ids:
        return {}
    stmt = _matter_files_query(binding, Document.id.label("document_id"), File.filename).where(
        Document.id.in_(doc_ids)
    )
    rows = (await db.execute(stmt)).all()
    out: dict[str, str] = {}
    for row in rows:
        out.setdefault(str(row.document_id), row.filename)
    return out


def _cell_payload(cell: AgenticCellInput) -> dict[str, Any]:
    """The persisted cell dict — ``cited_chunk_ids`` (not ``citations``) so the read-side
    ``TabularRow._synthesize_cell_citations`` validator builds display citations."""
    return {
        "value": cell.value,
        "confidence": cell.confidence,
        "cited_chunk_ids": [str(c) for c in cell.cited_chunk_ids],
        "source_quote": cell.source_quote,
        "notes": cell.notes,
    }


def _upsert_row(
    results: dict[str, Any] | None,
    *,
    document_id: str,
    document_name: str,
    cells: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return a NEW results dict with ``document_id``'s row merged in (new cells win).

    Reassigning the attribute (not mutating in place) is what makes SQLAlchemy flag the
    JSONB column dirty.
    """
    rows = [dict(r) for r in (results or {}).get("rows", []) if isinstance(r, dict)]
    for row in rows:
        if row.get("document_id") == document_id:
            merged = dict(row.get("cells", {}))
            merged.update(cells)
            row["cells"] = merged
            row["document_name"] = document_name
            return {"rows": rows}
    rows.append({"document_id": document_id, "document_name": document_name, "cells": cells})
    return {"rows": rows}


def _column_names(execution: TabularExecution) -> list[str]:
    return [
        c["name"]
        for c in (execution.columns or [])
        if isinstance(c, dict) and isinstance(c.get("name"), str)
    ]


def _rows_by_doc(results: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in (results or {}).get("rows", []):
        if isinstance(row, dict) and isinstance(row.get("document_id"), str):
            out[row["document_id"]] = row
    return out


def _coverage_counts(execution: TabularExecution) -> tuple[int, int]:
    """(cells filled, cells expected) across the grid (expected = docs x columns)."""
    columns = _column_names(execution)
    total = len(execution.document_ids) * len(columns)
    filled = 0
    for row in _rows_by_doc(execution.results).values():
        cells = row.get("cells", {})
        if isinstance(cells, dict):
            filled += sum(1 for c in columns if c in cells)
    return filled, total


def _failed_count(execution: TabularExecution) -> int:
    failed = 0
    for row in _rows_by_doc(execution.results).values():
        cells = row.get("cells", {})
        if isinstance(cells, dict):
            failed += sum(
                1 for c in cells.values() if isinstance(c, dict) and c.get("confidence") == "failed"
            )
    return failed


def _no_grid_text(grid_id: uuid.UUID) -> str:
    return (
        f"No grid {grid_id} in this matter (it may not exist, belong to another matter, or "
        "have been deleted). Start a new grid with start_tabular_review."
    )


def _rejection_text(exc: ValidationError, tool: str) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no cell content echoed)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(input)"
        problems.append(f"- {loc}: {err['msg']}")
    return f"{tool} was rejected — nothing was written. Fix the following and retry:\n" + "\n".join(
        problems
    )
