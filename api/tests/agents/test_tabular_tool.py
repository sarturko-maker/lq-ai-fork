"""Agentic tabular-review ("grids") tool tests — ADR-F055 (F2 Tabular T1).

Drives ``app.agents.tabular_tool`` against the real per-run test DB:

* the grant set (three tools; DISJOINT from the matter + every domain grant — confinement);
* start → resolve matter documents (ingested only; owner re-asserted), create the
  ``mode='agentic'`` grid row (matter-scoped, run provenance), recommend fan-out vs
  retrieval off the quota;
* record → upsert one document's row (merge on re-record), with matter/grid/column scope
  rejections; the persisted cell shape (``cited_chunk_ids`` + ``source_quote`` + ``notes``);
* finalize → the completeness gate (refuses gaps; ``failed`` counts as attempted) and the
  terminal state (``completed`` + ``fill_mode``);
* the persisted ``results`` JSONB validates as ``TabularResults`` (citations synthesized);
* audit receipts carry counts/IDs only (never a cell value or quote);
* the guarded closures end-to-end through a running run;
* the frozen linear worker refuses an agentic row.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.commercial_tools import COMMERCIAL_TOOL_NAMES
from app.agents.matter_fact_tools import MATTER_FACT_TOOL_NAMES
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.matter_read_tools import MATTER_READ_TOOL_NAMES
from app.agents.tabular_tool import (
    TABULAR_TOOL_NAMES,
    _finalize_tabular_review,
    _record_tabular_row,
    _start_tabular_review,
    build_tabular_tools,
)
from app.agents.tools import MATTER_TOOL_NAMES, MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.document import Document, DocumentChunk
from app.models.file import File
from app.models.project import Project, ProjectFile
from app.models.tabular import TabularExecution
from app.models.user import User
from app.schemas.tabular import TabularResults
from app.security import hash_password
from app.workers import tabular_worker

pytestmark = pytest.mark.integration

_COLUMNS = [
    {"name": "Term", "query": "What is the term?"},
    {"name": "Law", "query": "What is the governing law?"},
]


def _cells(
    *, term: str = "2 years", law: str | None = "England", law_conf: str = "medium"
) -> dict[str, dict[str, object]]:
    return {
        "Term": {
            "value": term,
            "confidence": "high",
            "source_quote": f"The term is {term}.",
            "notes": None,
        },
        "Law": {"value": law, "confidence": law_conf, "cited_chunk_ids": []},
    }


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_file(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    filename: str,
    body: str | None,
    column_project_id: uuid.UUID | None = None,
) -> File:
    """File (+ Document + one chunk when ``body`` is given; None = ingestion pending)."""
    f = File(
        owner_id=owner_id,
        project_id=column_project_id,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=1024,
        hash_sha256="a" * 64,
        storage_path=f"tabular-fixture/{uuid.uuid4()}",
        ingestion_status="processing" if body is None else "ready",
    )
    db.add(f)
    await db.flush()
    if body is not None:
        doc = Document(
            file_id=f.id,
            parser="pymupdf-only",
            page_count=1,
            character_count=len(body),
            normalized_content=body,
        )
        db.add(doc)
        await db.flush()
        db.add(
            DocumentChunk(
                document_id=doc.id,
                chunk_index=0,
                content=body,
                page_start=1,
                page_end=1,
                char_offset_start=0,
                char_offset_end=len(body),
            )
        )
    return f


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="Grid Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SimpleNamespace]:
    """A matter with two ingested docs (nda1/nda2), a pending doc, and a foreign-owned
    file maliciously column-joined into the matter (owner re-assertion must exclude it),
    plus a second matter, and a running run."""
    user_ids: list[uuid.UUID] = []
    project_ids: list[uuid.UUID] = []
    file_ids: list[uuid.UUID] = []

    async with commit_factory() as db:
        user = User(
            email=f"grid-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Grid User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        stranger = User(
            email=f"grid-stranger-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Grid Stranger",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add_all([user, stranger])
        await db.flush()
        user_ids += [user.id, stranger.id]

        project = Project(owner_id=user.id, name="Grid Matter", slug=f"grid-{uuid.uuid4().hex[:6]}")
        other = Project(owner_id=user.id, name="Other", slug=f"other-{uuid.uuid4().hex[:6]}")
        db.add_all([project, other])
        await db.flush()
        project_ids += [project.id, other.id]

        nda1 = await _seed_file(
            db, owner_id=user.id, filename="nda1.pdf", body="NDA one.", column_project_id=project.id
        )
        nda2 = await _seed_file(
            db, owner_id=user.id, filename="nda2.pdf", body="NDA two.", column_project_id=project.id
        )
        pending = await _seed_file(
            db, owner_id=user.id, filename="pending.pdf", body=None, column_project_id=project.id
        )
        # Foreign-owned, spoof-joined into our matter — must be excluded both ways.
        foreign = await _seed_file(
            db,
            owner_id=stranger.id,
            filename="foreign.pdf",
            body="Foreign.",
            column_project_id=project.id,
        )
        db.add(ProjectFile(project_id=project.id, file_id=foreign.id))
        file_ids += [nda1.id, nda2.id, pending.id, foreign.id]

        thread = AgentThread(user_id=user.id, project_id=project.id, title="grid tests")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            thread_id=thread.id,
            project_id=project.id,
            status="running",
            prompt="Build a grid.",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()

        nda1_doc = (
            await db.execute(select(Document.id).where(Document.file_id == nda1.id))
        ).scalar_one()
        nda2_doc = (
            await db.execute(select(Document.id).where(Document.file_id == nda2.id))
        ).scalar_one()

        env = SimpleNamespace(
            factory=commit_factory,
            user_id=user.id,
            stranger_id=stranger.id,
            project_id=project.id,
            other_project_id=other.id,
            run_id=run.id,
            nda1_doc=nda1_doc,
            nda2_doc=nda2_doc,
        )

    yield env

    async with commit_factory() as db:
        await db.execute(delete(TabularExecution).where(TabularExecution.user_id.in_(user_ids)))
        await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
        await db.execute(delete(AgentRun).where(AgentRun.user_id.in_(user_ids)))
        await db.execute(delete(AgentThread).where(AgentThread.user_id.in_(user_ids)))
        await db.execute(delete(Project).where(Project.id.in_(project_ids)))
        await db.execute(delete(File).where(File.id.in_(file_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


async def _only_grid(db: AsyncSession, project_id: uuid.UUID) -> TabularExecution:
    return (
        await db.execute(
            select(TabularExecution).where(
                TabularExecution.project_id == project_id, TabularExecution.mode == "agentic"
            )
        )
    ).scalar_one()


async def _start(
    m: SimpleNamespace,
    *,
    columns: list[dict[str, object]] | None = None,
    documents: list[str] | None = None,
    fan_out_quota: int = 8,
) -> tuple[str, TabularExecution]:
    """Run the start impl + return (message, the created grid row)."""
    async with m.factory() as db:
        msg = await _start_tabular_review(
            db,
            _binding(m.user_id, m.project_id),
            columns=columns if columns is not None else _COLUMNS,
            documents=documents,
            run_id=m.run_id,
            fan_out_quota=fan_out_quota,
        )
        await db.commit()
    async with m.factory() as db:
        try:
            grid = await _only_grid(db, m.project_id)
        except Exception:
            grid = None  # type: ignore[assignment]
    return msg, grid


# --------------------------------------------------------------------------- #
# Grant set / confinement
# --------------------------------------------------------------------------- #


def test_build_returns_three_named_tools() -> None:
    tools = build_tabular_tools(
        async_sessionmaker(),
        run_id=uuid.uuid4(),
        binding=_binding(uuid.uuid4(), uuid.uuid4()),
        fan_out_quota=8,
    )
    assert [t.__name__ for t in tools] == [
        "start_tabular_review",
        "record_tabular_row",
        "finalize_tabular_review",
    ]
    assert sorted(TABULAR_TOOL_NAMES) == [
        "finalize_tabular_review",
        "record_tabular_row",
        "start_tabular_review",
    ]


def test_grant_set_disjoint_from_other_grants() -> None:
    assert TABULAR_TOOL_NAMES.isdisjoint(MATTER_TOOL_NAMES)
    assert TABULAR_TOOL_NAMES.isdisjoint(COMMERCIAL_TOOL_NAMES)
    assert TABULAR_TOOL_NAMES.isdisjoint(MATTER_MEMORY_TOOL_NAMES)
    assert TABULAR_TOOL_NAMES.isdisjoint(MATTER_FACT_TOOL_NAMES)
    assert TABULAR_TOOL_NAMES.isdisjoint(MATTER_READ_TOOL_NAMES)


# --------------------------------------------------------------------------- #
# start
# --------------------------------------------------------------------------- #


async def test_start_creates_agentic_grid(matter: SimpleNamespace) -> None:
    msg, grid = await _start(matter)
    assert "Started grid" in msg and "fan out" in msg
    assert grid.mode == "agentic"
    assert grid.status == "running"
    assert grid.project_id == matter.project_id
    assert grid.user_id == matter.user_id
    assert grid.created_by_run_id == matter.run_id
    assert grid.fill_mode is None  # set only at finalize
    assert set(grid.document_ids) == {matter.nda1_doc, matter.nda2_doc}  # ingested + owned only
    assert [c["name"] for c in grid.columns] == ["Term", "Law"]
    assert grid.results == {"rows": []}
    assert grid.started_at is not None


async def test_start_named_subset_reports_unmatched(matter: SimpleNamespace) -> None:
    msg, grid = await _start(matter, documents=["nda1.pdf", "ghost.pdf"])
    assert set(grid.document_ids) == {matter.nda1_doc}
    assert "ghost.pdf" in msg  # the unmatched name is surfaced


async def test_start_recommends_retrieval_above_quota(matter: SimpleNamespace) -> None:
    msg, _ = await _start(matter, fan_out_quota=1)  # 2 docs > quota 1
    assert "more documents" in msg
    assert "subagent limit" in msg


async def test_start_rejects_empty_columns(matter: SimpleNamespace) -> None:
    msg, grid = await _start(matter, columns=[])
    assert "rejected" in msg.lower()
    assert grid is None  # nothing created


async def test_start_no_matching_documents(matter: SimpleNamespace) -> None:
    msg, grid = await _start(matter, documents=["ghost.pdf"])
    assert "None of those filenames matched" in msg
    assert grid is None


# --------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------- #


async def _record(
    m: SimpleNamespace, grid_id: uuid.UUID, document: str, cells: dict[str, dict[str, object]]
) -> str:
    async with m.factory() as db:
        msg = await _record_tabular_row(
            db,
            _binding(m.user_id, m.project_id),
            grid_id=str(grid_id),
            document=document,
            cells=cells,
            run_id=m.run_id,
        )
        await db.commit()
    return msg


async def test_record_upserts_row_with_cell_shape(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    chunk = uuid.uuid4()
    cells = {
        "Term": {
            "value": "2 years",
            "confidence": "high",
            "source_quote": "Term: two (2) years",
            "notes": "auto-renews",
            "cited_chunk_ids": [str(chunk)],
        },
        "Law": {"value": "England", "confidence": "medium"},
    }
    msg = await _record(matter, grid.id, "nda1.pdf", cells)
    assert "Recorded 2 cell(s)" in msg

    async with matter.factory() as db:
        row = (await _only_grid(db, matter.project_id)).results["rows"][0]
    assert row["document_id"] == str(matter.nda1_doc)
    assert row["document_name"] == "nda1.pdf"
    term = row["cells"]["Term"]
    assert term["value"] == "2 years"
    assert term["confidence"] == "high"
    assert term["source_quote"] == "Term: two (2) years"
    assert term["notes"] == "auto-renews"
    assert term["cited_chunk_ids"] == [str(chunk)]


async def test_record_merges_on_recall(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    await _record(matter, grid.id, "nda1.pdf", {"Term": {"value": "2y", "confidence": "high"}})
    await _record(matter, grid.id, "nda1.pdf", {"Law": {"value": "NY", "confidence": "low"}})
    async with matter.factory() as db:
        rows = (await _only_grid(db, matter.project_id)).results["rows"]
    assert len(rows) == 1  # same document → merged, not duplicated
    assert set(rows[0]["cells"]) == {"Term", "Law"}


async def test_record_rejects_unknown_column(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    msg = await _record(
        matter, grid.id, "nda1.pdf", {"Bogus": {"value": "x", "confidence": "high"}}
    )
    assert "Unknown column" in msg


async def test_record_rejects_document_not_in_grid(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter, documents=["nda1.pdf"])
    msg = await _record(matter, grid.id, "nda2.pdf", _cells())
    assert "not one of this grid's documents" in msg


async def test_record_rejects_document_not_in_matter(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    msg = await _record(matter, grid.id, "ghost.pdf", _cells())
    assert "No ingested document" in msg


async def test_record_unknown_grid(matter: SimpleNamespace) -> None:
    msg = await _record(matter, uuid.uuid4(), "nda1.pdf", _cells())
    assert "No grid" in msg


async def test_record_cross_matter_isolation(matter: SimpleNamespace) -> None:
    """A grid created under matter A is invisible to a binding for matter B (404-conflated)."""
    _, grid = await _start(matter)
    async with matter.factory() as db:
        msg = await _record_tabular_row(
            db,
            _binding(matter.user_id, matter.other_project_id),  # different matter
            grid_id=str(grid.id),
            document="nda1.pdf",
            cells=_cells(),
            run_id=matter.run_id,
        )
        await db.commit()
    assert "No grid" in msg


# --------------------------------------------------------------------------- #
# finalize
# --------------------------------------------------------------------------- #


async def _finalize(m: SimpleNamespace, grid_id: uuid.UUID) -> str:
    async with m.factory() as db:
        msg = await _finalize_tabular_review(
            db, _binding(m.user_id, m.project_id), grid_id=str(grid_id), run_id=m.run_id
        )
        await db.commit()
    return msg


async def test_finalize_rejects_missing_row(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    await _record(matter, grid.id, "nda1.pdf", _cells())  # nda2 row never recorded
    msg = await _finalize(matter, grid.id)
    assert "Not finalized" in msg
    assert "no row recorded" in msg
    async with matter.factory() as db:
        assert (await _only_grid(db, matter.project_id)).status == "running"  # not flipped


async def test_finalize_rejects_missing_cell(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    await _record(matter, grid.id, "nda1.pdf", _cells())
    await _record(matter, grid.id, "nda2.pdf", {"Term": {"value": "1y", "confidence": "high"}})
    msg = await _finalize(matter, grid.id)
    assert "missing column(s) Law" in msg


async def test_finalize_succeeds_when_all_attempted(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    await _record(matter, grid.id, "nda1.pdf", _cells())
    # nda2: Law is a legitimate 'failed' attempt (no value) — counts as attempted.
    await _record(
        matter,
        grid.id,
        "nda2.pdf",
        {
            "Term": {"value": "5y", "confidence": "high"},
            "Law": {"value": None, "confidence": "failed"},
        },
    )
    msg = await _finalize(matter, grid.id)
    assert "Finalized grid" in msg and "1 marked failed" in msg
    async with matter.factory() as db:
        g = await _only_grid(db, matter.project_id)
    assert g.status == "completed"
    assert g.completed_at is not None
    assert g.fill_mode == "fanout"


async def test_finalize_idempotent_when_already_complete(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    await _record(matter, grid.id, "nda1.pdf", _cells())
    await _record(matter, grid.id, "nda2.pdf", _cells())
    await _finalize(matter, grid.id)
    again = await _finalize(matter, grid.id)
    assert "already finalized" in again


async def test_record_into_completed_grid_rejected(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    await _record(matter, grid.id, "nda1.pdf", _cells())
    await _record(matter, grid.id, "nda2.pdf", _cells())
    await _finalize(matter, grid.id)
    msg = await _record(matter, grid.id, "nda1.pdf", _cells(term="changed"))
    assert "no longer open for writing" in msg


# --------------------------------------------------------------------------- #
# persisted shape + audit
# --------------------------------------------------------------------------- #


async def test_persisted_results_validate_as_tabular_results(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    chunk = uuid.uuid4()
    await _record(
        matter,
        grid.id,
        "nda1.pdf",
        {
            "Term": {
                "value": "2y",
                "confidence": "high",
                "source_quote": "two years",
                "cited_chunk_ids": [str(chunk)],
            },
            "Law": {"value": "England", "confidence": "medium"},
        },
    )
    await _record(matter, grid.id, "nda2.pdf", _cells())
    await _finalize(matter, grid.id)

    async with matter.factory() as db:
        raw = (await _only_grid(db, matter.project_id)).results
    results = TabularResults.model_validate(raw)  # the read-side wire shape
    row = next(r for r in results.rows if r.document_id == matter.nda1_doc)
    cell = row.cells["Term"]
    assert cell.value == "2y"
    assert cell.source_quote == "two years"
    # cited_chunk_ids → synthesized display citation keyed to the row's document.
    assert len(cell.citations) == 1
    assert cell.citations[0].chunk_id == chunk
    assert cell.citations[0].document_id == matter.nda1_doc


async def test_audit_receipts_carry_counts_not_content(matter: SimpleNamespace) -> None:
    _, grid = await _start(matter)
    await _record(
        matter,
        grid.id,
        "nda1.pdf",
        {"Term": {"value": "secret value", "confidence": "high", "source_quote": "secret quote"}},
    )
    async with matter.factory() as db:
        rows = (
            (
                await db.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.resource_type == "tabular_execution",
                        AuditLog.resource_id == str(grid.id),
                    )
                    .order_by(AuditLog.timestamp.asc())
                )
            )
            .scalars()
            .all()
        )
    actions = [r.action for r in rows]
    assert "tabular.grid_started" in actions
    assert "tabular.row_recorded" in actions
    for r in rows:
        blob = str(r.details)
        assert "secret value" not in blob and "secret quote" not in blob


# --------------------------------------------------------------------------- #
# guarded closures end-to-end + worker refusal
# --------------------------------------------------------------------------- #


async def test_guarded_closures_end_to_end(matter: SimpleNamespace) -> None:
    """start → record → finalize through guarded_dispatch on a live running run."""
    start, record, finalize = build_tabular_tools(
        matter.factory,
        run_id=matter.run_id,
        binding=_binding(matter.user_id, matter.project_id),
        fan_out_quota=8,
    )
    out = await start(_COLUMNS, None)
    assert "Started grid" in out
    async with matter.factory() as db:
        grid_id = (await _only_grid(db, matter.project_id)).id
    await record(str(grid_id), "nda1.pdf", _cells())
    await record(str(grid_id), "nda2.pdf", _cells())
    done = await finalize(str(grid_id))
    assert "Finalized grid" in done
    # The guard wrote one agent_run.tool_call row per dispatch.
    async with matter.factory() as db:
        calls = (
            await db.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.resource_type == "agent_run",
                    AuditLog.resource_id == str(matter.run_id),
                    AuditLog.action == "agent_run.tool_call",
                )
            )
        ).scalar_one()
    assert calls >= 4  # start + 2 records + finalize


async def test_linear_worker_refuses_agentic_row(
    matter: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frozen linear worker skips an agentic row without running the executor."""
    async with matter.factory() as db:
        grid = TabularExecution(
            user_id=matter.user_id,
            project_id=matter.project_id,
            mode="agentic",
            status="running",
            document_ids=[matter.nda1_doc],
            columns=[{"name": "Term", "query": "?"}],
            results={"rows": []},
        )
        db.add(grid)
        await db.commit()
        grid_id = grid.id

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the linear executor must not run on an agentic row")

    monkeypatch.setattr(tabular_worker, "get_session_factory", lambda: matter.factory)
    monkeypatch.setattr(tabular_worker, "run_tabular_execution", _boom)
    result = await tabular_worker.tabular_execution_job({}, str(grid_id))
    assert result["status"] == "skipped_agentic"

    async with matter.factory() as db:
        g = await db.get(TabularExecution, grid_id)
        assert g is not None and g.status == "running"  # untouched
