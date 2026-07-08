"""Knowledge-collection search tool — B-3 (fork, ADR-F067 D1) over REAL rows.

Real Postgres, real ``knowledge_bases`` / ``files`` / ``documents`` / ``document_chunks``
rows, real ``hybrid_search`` + audit rows: the ``build_knowledge_tools`` closure is
exercised exactly as the runner dispatches it. Load-bearing assertions:

* build confinement — the group builds exactly ``search_knowledge``; off ⇒ absent from
  ``build_area_tool_groups`` output ⇒ its name never enters ``GuardContext.granted``;
* R6 fail-closed — a context that did NOT grant ``search_knowledge`` refuses the dispatch
  and leaves one body-free ``tool_not_granted`` audit row;
* the fenced RETRIEVED-DATA render shape — the header constant, the
  ``[collection · file — page]`` provenance line, the ``Provenance: chunk ids`` line, and
  the ~700-char snippet cap;
* cross-collection merge — hits from several collections are merged by hybrid score, not
  concatenated per collection;
* embed-failure degrade — a gateway embed failure logs and falls back to FTS-only, still
  returning results (retrieval never hard-fails on the embedder).

The gateway is injected via ``set_gateway_client`` (the codebase's test seam) — NEVER a
real network call. Chunks are seeded with NULL ``embedding`` (the 1536-dim KB column), so
the vector side of ``hybrid_search`` is empty and FTS drives ranking deterministically; the
fake vector only exercises the embed-success code path.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.budget import BudgetEnvelope
from app.agents.capabilities import (
    KNOWLEDGE_GROUP,
    GroupBuildContext,
    build_area_tool_groups,
)
from app.agents.guard import AgentToolNotGranted, GuardContext, guarded_dispatch
from app.agents.knowledge_tools import (
    _RETRIEVED_HEADER,
    KNOWLEDGE_TOOL_NAMES,
    build_knowledge_tools,
)
from app.agents.redline_service import RedlineService
from app.agents.tools import MatterBinding
from app.clients.gateway import GatewayClient, set_gateway_client
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.document import Document, DocumentChunk
from app.models.file import File
from app.models.knowledge import KnowledgeBase, KnowledgeBaseFile
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration


# --- fake gateway ------------------------------------------------------------
class _FakeGateway:
    """Duck-typed :class:`GatewayClient` whose ``embeddings`` returns a fixed 1536-dim
    vector (or raises when ``fail``) — no network. The vector is never actually compared
    (seeded chunks have NULL ``embedding``), so it only drives the embed-success path."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.calls = 0

    async def embeddings(
        self, *, model: str, input_: Any, request_id: str | None = None
    ) -> dict[str, Any]:
        self.calls += 1
        if self._fail:
            raise RuntimeError("gateway embeddings unavailable")
        return {"data": [{"embedding": [0.1] * 1536}]}


@pytest.fixture(autouse=True)
def _reset_gateway() -> AsyncIterator[None]:
    """Reset the process-global gateway after each test so the lazy global rebuilds."""
    yield
    set_gateway_client(None)


def _use_gateway(*, fail: bool = False) -> _FakeGateway:
    gw = _FakeGateway(fail=fail)
    set_gateway_client(cast(GatewayClient, gw))
    return gw


# --- environment -------------------------------------------------------------
@dataclass
class KnowledgeEnv:
    factory: async_sessionmaker[AsyncSession]
    owner_id: uuid.UUID
    run_id: uuid.UUID
    project_id: uuid.UUID
    practice_area_id: uuid.UUID
    kb_ids: list[uuid.UUID] = field(default_factory=list)
    file_ids: list[uuid.UUID] = field(default_factory=list)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def env(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[KnowledgeEnv]:
    """A Commercial matter + a running run; collections are seeded per-test via helpers."""
    async with commit_factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
        ).scalar_one()

        user = User(
            email=f"know-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Knowledge User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()

        project = Project(
            owner_id=user.id,
            name="Project Atlas",
            slug=f"atlas-{uuid.uuid4().hex[:6]}",
            practice_area_id=area_id,
        )
        db.add(project)
        await db.flush()

        thread = AgentThread(user_id=user.id, project_id=project.id, title="knowledge tools tests")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            thread_id=thread.id,
            project_id=project.id,
            status="running",
            prompt="Search the knowledge collections.",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()

        environment = KnowledgeEnv(
            factory=commit_factory,
            owner_id=user.id,
            run_id=run.id,
            project_id=project.id,
            practice_area_id=area_id,
        )

    yield environment

    async with commit_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == environment.owner_id))
        await db.execute(delete(AgentRun).where(AgentRun.user_id == environment.owner_id))
        await db.execute(delete(AgentThread).where(AgentThread.user_id == environment.owner_id))
        await db.execute(delete(Project).where(Project.id == environment.project_id))
        # KB delete cascades knowledge_base_files; File delete cascades documents → chunks.
        if environment.kb_ids:
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(environment.kb_ids)))
        if environment.file_ids:
            await db.execute(delete(File).where(File.id.in_(environment.file_ids)))
        await db.execute(delete(User).where(User.id == environment.owner_id))
        await db.commit()


async def _seed_kb(
    env: KnowledgeEnv, *, name: str, alpha: float = 0.5, archived: bool = False
) -> uuid.UUID:
    async with env.factory() as db:
        kb = KnowledgeBase(
            owner_id=env.owner_id,
            name=name,
            hybrid_alpha=alpha,
            archived_at=(datetime.now(UTC) if archived else None),
        )
        db.add(kb)
        await db.commit()
        env.kb_ids.append(kb.id)
        return kb.id


async def _add_chunk(
    env: KnowledgeEnv,
    kb_id: uuid.UUID,
    *,
    filename: str,
    content: str,
    page_start: int | None = None,
    page_end: int | None = None,
) -> uuid.UUID:
    """Seed one file+document+chunk attached to ``kb_id`` (content_tsv is DB-generated)."""
    async with env.factory() as db:
        f = File(
            owner_id=env.owner_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=len(content),
            hash_sha256=uuid.uuid4().hex,
            storage_path=f"seed/{uuid.uuid4().hex}",
            ingestion_status="ready",  # hybrid_search requires ready + not deleted
        )
        db.add(f)
        await db.flush()
        env.file_ids.append(f.id)
        doc = Document(
            file_id=f.id,
            parser="test",
            normalized_content=content,
            page_count=page_start,
        )
        db.add(doc)
        await db.flush()
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            content=content,
            char_offset_start=0,
            char_offset_end=len(content),
            page_start=page_start,
            page_end=page_end,
        )
        db.add(chunk)
        db.add(KnowledgeBaseFile(kb_id=kb_id, file_id=f.id))
        await db.commit()
        return chunk.id


def _build(env: KnowledgeEnv, kb_ids: list[uuid.UUID]) -> dict[str, Any]:
    binding = MatterBinding(
        project_id=env.project_id,
        user_id=env.owner_id,
        name="Project Atlas",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=env.practice_area_id,
    )
    tools = build_knowledge_tools(
        env.factory, run_id=env.run_id, binding=binding, knowledge_base_ids=kb_ids
    )
    return {t.__name__: t for t in tools}


async def _audit_rows(env: KnowledgeEnv) -> list[AuditLog]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.resource_type == "agent_run",
                    AuditLog.resource_id == str(env.run_id),
                )
                .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
            )
        ).scalars()
        return list(rows)


# --- build confinement / grant (no DB) ---------------------------------------
def test_tool_names_is_exactly_search_knowledge() -> None:
    assert frozenset({"search_knowledge"}) == KNOWLEDGE_TOOL_NAMES


def test_build_returns_only_search_knowledge() -> None:
    binding = MatterBinding(
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="M",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )
    # Build stashes inputs in the closure (no I/O), so a None factory is fine here.
    tools = build_knowledge_tools(
        cast(Any, None),
        run_id=uuid.uuid4(),
        binding=binding,
        knowledge_base_ids=(uuid.uuid4(),),
    )
    assert [t.__name__ for t in tools] == ["search_knowledge"]


def _group_ctx() -> GroupBuildContext:
    binding = MatterBinding(
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="M",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=uuid.uuid4(),
    )
    return GroupBuildContext(
        session_factory=cast(Any, None),  # builders only stash it (no I/O at build time)
        run_id=uuid.uuid4(),
        binding=binding,
        envelope=BudgetEnvelope(
            token_budget=8_000_000, fan_out_quota=8, max_steps=400, wall_clock_seconds=3600.0
        ),
        redline_service_provider=lambda: cast(RedlineService, object()),
        knowledge_base_ids=(uuid.uuid4(),),
    )


def test_group_absent_yields_no_knowledge_tool() -> None:
    """Group off ⇒ search_knowledge is never built ⇒ its name never enters the grant set."""
    tools, ledger = build_area_tool_groups(_group_ctx(), set())
    assert not any(t.__name__ == "search_knowledge" for t in tools)
    assert ledger is None


def test_group_present_builds_search_knowledge_with_no_ledger() -> None:
    tools, ledger = build_area_tool_groups(_group_ctx(), {KNOWLEDGE_GROUP.key})
    assert [t.__name__ for t in tools] == ["search_knowledge"]
    assert ledger is None  # the knowledge group streams no live changes


# --- R6 fail-closed ----------------------------------------------------------
async def test_r6_refuses_ungranted_search_knowledge(env: KnowledgeEnv) -> None:
    """A context that did NOT grant search_knowledge refuses the dispatch fail-closed and
    leaves one body-free tool_not_granted audit row (the group-off runtime shape)."""
    ctx = GuardContext(
        session_factory=env.factory,
        run_id=env.run_id,
        user_id=env.owner_id,
        project_id=env.project_id,
        granted=frozenset(),  # nothing granted — the knowledge group was not built
        practice_area_id=env.practice_area_id,
    )
    with pytest.raises(AgentToolNotGranted):
        await guarded_dispatch("search_knowledge", _never_runs, ctx)

    rows = await _audit_rows(env)
    refusals = [r for r in rows if (r.details or {}).get("tool") == "search_knowledge"]
    assert refusals, "no audit row recorded for the refused dispatch"
    assert refusals[0].details is not None
    assert refusals[0].details.get("outcome") == "tool_not_granted"
    # body-free: only tool name + outcome, never a query or chunk content
    assert set(refusals[0].details) <= {"tool", "outcome"}


async def _never_runs(db: AsyncSession) -> str:  # pragma: no cover - R6 refuses before this
    raise AssertionError("op body must not run when the tool is not granted")


# --- fenced render shape + snippet cap ---------------------------------------
async def test_fenced_render_shape_and_snippet_cap(env: KnowledgeEnv) -> None:
    _use_gateway()
    kb_id = await _seed_kb(env, name="House Knowledge")
    long_content = "Indemnity clause: " + ("lorem ipsum dolor " * 60)  # > 700 chars
    assert len(long_content) > 700
    chunk_id = await _add_chunk(
        env, kb_id, filename="terms.pdf", content=long_content, page_start=3
    )
    tools = _build(env, [kb_id])

    result = await tools["search_knowledge"]("indemnity")

    # header constant frames the block as DATA
    assert result.startswith(_RETRIEVED_HEADER)
    # per-hit provenance line: [collection · file — page]
    assert "[House Knowledge · terms.pdf — page 3]" in result
    # provenance chunk-ids line
    assert f"Provenance: chunk ids {chunk_id}" in result
    # snippet capped (~700) with an ellipsis; the full content is not echoed verbatim
    assert "…" in result
    assert long_content not in result
    assert long_content[:80] in result


# --- cross-collection merge order --------------------------------------------
async def test_multi_kb_results_merge_by_score_not_per_collection(env: KnowledgeEnv) -> None:
    """Hits from two collections are merged by hybrid score (desc): Bravo's chunk interleaves
    between Alpha's strong and weak chunks. Naive per-collection concatenation would keep both
    Alpha chunks adjacent — the interleave proves a real merge."""
    _use_gateway()
    kb_alpha = await _seed_kb(env, name="Alpha KB")
    kb_bravo = await _seed_kb(env, name="Bravo KB")
    await _add_chunk(
        env,
        kb_alpha,
        filename="a-strong.pdf",
        content="STRONGMARK indemnity indemnity indemnity clause governs.",
    )
    await _add_chunk(
        env,
        kb_alpha,
        filename="a-weak.pdf",
        content="WEAKMARK a single indemnity is mentioned once here.",
    )
    await _add_chunk(
        env, kb_bravo, filename="b.pdf", content="BRAVOMARK the indemnity provision applies."
    )
    tools = _build(env, [kb_alpha, kb_bravo])

    result = await tools["search_knowledge"]("indemnity")

    i_strong = result.index("STRONGMARK")
    i_bravo = result.index("BRAVOMARK")
    i_weak = result.index("WEAKMARK")
    assert i_strong < i_bravo < i_weak


# --- embed-failure fallback --------------------------------------------------
async def test_embed_failure_degrades_to_fts_only(
    env: KnowledgeEnv, caplog: pytest.LogCaptureFixture
) -> None:
    """A gateway embed failure logs and falls back to FTS-only — results still returned."""
    _use_gateway(fail=True)
    kb_id = await _seed_kb(env, name="House Knowledge")
    chunk_id = await _add_chunk(
        env, kb_id, filename="terms.pdf", content="Indemnity and liability clauses apply."
    )
    tools = _build(env, [kb_id])

    with caplog.at_level(logging.WARNING):
        result = await tools["search_knowledge"]("indemnity")

    assert _RETRIEVED_HEADER in result
    assert str(chunk_id) in result  # FTS still returned the chunk with no vector side
    assert any(getattr(r, "event", None) == "knowledge_search_embed_failed" for r in caplog.records)


async def test_all_fts_only_collections_skip_the_embed_call(env: KnowledgeEnv) -> None:
    """When EVERY bound collection is FTS-only (hybrid_alpha 1.0) the gateway embed call
    is skipped entirely — the embedding would be unused (the query_kb posture); results
    still come back via FTS."""
    gw = _use_gateway()
    kb_a = await _seed_kb(env, name="Lexical Alpha", alpha=1.0)
    kb_b = await _seed_kb(env, name="Lexical Bravo", alpha=1.0)
    chunk_id = await _add_chunk(
        env, kb_a, filename="terms.pdf", content="Indemnity and liability clauses apply."
    )
    await _add_chunk(env, kb_b, filename="more.pdf", content="A further indemnity provision.")
    tools = _build(env, [kb_a, kb_b])

    result = await tools["search_knowledge"]("indemnity")

    assert _RETRIEVED_HEADER in result
    assert str(chunk_id) in result
    assert gw.calls == 0  # no gateway embed round-trip for a lexical-only search


# --- edge cases --------------------------------------------------------------
async def test_blank_query_is_refused_without_touching_the_gateway(env: KnowledgeEnv) -> None:
    gw = _use_gateway()
    tools = _build(env, [await _seed_kb(env, name="House Knowledge")])
    result = await tools["search_knowledge"]("   ")
    assert "Pass a search query" in result
    assert gw.calls == 0  # short-circuits before embedding


async def test_archived_collection_is_skipped_at_search_time(env: KnowledgeEnv) -> None:
    """Defense in depth: a collection archived after binding is dropped by the tool itself."""
    _use_gateway()
    kb_id = await _seed_kb(env, name="Retired KB", archived=True)
    await _add_chunk(env, kb_id, filename="old.pdf", content="Indemnity clause text.")
    tools = _build(env, [kb_id])
    result = await tools["search_knowledge"]("indemnity")
    assert "No knowledge collections are available" in result
