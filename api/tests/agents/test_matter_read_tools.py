"""C3c-1 matter_read_tools tests (ADR-F042/F044).

Drives the two agent-facing matter-memory READ tools through the real test DB:

* the grant set (two tools; DISJOINT from the wiki / fact / consolidation grants AND
  the ROPA/assessment/commercial domain grants — confinement),
* ``search_matter_memory`` searches the LIVE corpus only — a superseded fact never
  resurfaces (the correctness + injection guarantee); it matches facts, the wiki, and
  pinned corrections; a blank query is rejected; a no-match is reported,
* ``matter_facts_as_of`` reconstructs history across a supersede boundary, includes a
  NULL-``valid_at`` fact, and — the load-bearing trap — a BARE ISO date does NOT crash
  while a non-date string is rejected (reject-and-retry, never a crash),
* a vanished/cross-owner matter degrades to "no longer available",
* the guard audit receipt carries counts/IDs only — never the fact body.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.assessment_tools import ASSESSMENT_TOOL_NAMES
from app.agents.commercial_tools import COMMERCIAL_TOOL_NAMES
from app.agents.matter_consolidation import MATTER_CONSOLIDATION_TOOL_NAMES
from app.agents.matter_fact_tools import MATTER_FACT_TOOL_NAMES
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.matter_read_tools import (
    MATTER_READ_TOOL_NAMES,
    _matter_facts_as_of,
    _search_matter_memory,
    build_matter_read_tools,
)
from app.agents.ropa_tools import ROPA_TOOL_NAMES
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.project import MatterMemoryEntry, Project
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2026, 3, 1, tzinfo=UTC)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_matter(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        user = User(
            email=f"mr-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Matter Read User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Read Matter",
            slug=f"read-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
            context_md="Deal: Acme acquires Cirrus.\nLiability cap: 12 months' fees.",
        )
        db.add(project)
        await db.commit()
        return user.id, project.id


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="Read Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


async def _seed_memory(factory: async_sessionmaker[AsyncSession], project_id: uuid.UUID) -> None:
    """A small drifted ledger: a live fact, a SUPERSEDED fact, a NULL-date fact, a pin."""
    async with factory() as db:
        user_id = (
            await db.execute(select(Project.owner_id).where(Project.id == project_id))
        ).scalar_one()
        # Superseded: cap 1 month, valid T0 → invalid T1 (NOT live; only in the as-of past).
        db.add(
            MatterMemoryEntry(
                project_id=project_id,
                user_id=user_id,
                kind="fact",
                body_md="Liability cap is 1 month (from the draft).",
                trust="normal",
                author="agent",
                fact_type="term",
                source_citation="draft MSA §9",
                valid_at=_T0,
                invalid_at=_T1,
            )
        )
        # Live: cap 12 months, valid T1 → current.
        db.add(
            MatterMemoryEntry(
                project_id=project_id,
                user_id=user_id,
                kind="fact",
                body_md="Liability cap is 12 months' fees.",
                trust="normal",
                author="agent",
                fact_type="term",
                source_citation="Cirrus MSA §9",
                valid_at=_T1,
            )
        )
        # Live, undated (valid_at NULL = from the start of the matter).
        db.add(
            MatterMemoryEntry(
                project_id=project_id,
                user_id=user_id,
                kind="fact",
                body_md="We act for the buyer.",
                trust="normal",
                author="agent",
                fact_type="party",
            )
        )
        # A pinned correction (human-pinned, live).
        db.add(
            MatterMemoryEntry(
                project_id=project_id,
                user_id=user_id,
                kind="correction",
                body_md="Counterparty counsel is Smith Crowell.",
                trust="human-pinned",
            )
        )
        await db.commit()


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    user_id, project_id = await _seed_matter(commit_factory)
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
            await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


# --------------------------------------------------------------------------- #
# Grant set / confinement
# --------------------------------------------------------------------------- #


def test_build_grants_exactly_the_read_tools() -> None:
    tools = build_matter_read_tools(
        async_sessionmaker(), run_id=uuid.uuid4(), binding=_binding(uuid.uuid4(), uuid.uuid4())
    )
    assert [t.__name__ for t in tools] == ["search_matter_memory", "matter_facts_as_of"]
    assert sorted(MATTER_READ_TOOL_NAMES) == ["matter_facts_as_of", "search_matter_memory"]


def test_grant_set_disjoint_from_other_grants() -> None:
    """Confinement: the read tools share no tool name with any write/domain grant."""
    assert MATTER_READ_TOOL_NAMES.isdisjoint(MATTER_MEMORY_TOOL_NAMES)
    assert MATTER_READ_TOOL_NAMES.isdisjoint(MATTER_FACT_TOOL_NAMES)
    assert MATTER_READ_TOOL_NAMES.isdisjoint(MATTER_CONSOLIDATION_TOOL_NAMES)
    assert MATTER_READ_TOOL_NAMES.isdisjoint(ROPA_TOOL_NAMES)
    assert MATTER_READ_TOOL_NAMES.isdisjoint(ASSESSMENT_TOOL_NAMES)
    assert MATTER_READ_TOOL_NAMES.isdisjoint(COMMERCIAL_TOOL_NAMES)


# --------------------------------------------------------------------------- #
# search_matter_memory — LIVE corpus only
# --------------------------------------------------------------------------- #


async def test_search_matches_live_facts_wiki_and_corrections(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_memory(commit_factory, project_id)
    async with commit_factory() as db:
        out = await _search_matter_memory(db, _binding(user_id, project_id), query="liability cap")
    # The LIVE fact + the wiki line are returned…
    assert "12 months' fees" in out
    assert "From the matter wiki:" in out
    # …but the SUPERSEDED draft fact is NOT (live-only — no stale resurfacing).
    assert "1 month" not in out
    assert "Cirrus MSA §9" in out  # provenance surfaced


async def test_search_matches_pinned_correction(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_memory(commit_factory, project_id)
    async with commit_factory() as db:
        out = await _search_matter_memory(db, _binding(user_id, project_id), query="Smith")
    assert "Smith Crowell" in out
    assert "supervising lawyer" in out.lower()


async def test_search_blank_query_rejected_not_crash(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _search_matter_memory(db, _binding(user_id, project_id), query="   ")
    assert "rejected" in out.lower()
    assert "search_matter_memory" in out


async def test_search_no_match_reports_counts(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_memory(commit_factory, project_id)
    async with commit_factory() as db:
        out = await _search_matter_memory(
            db, _binding(user_id, project_id), query="zzz-no-such-term"
        )
    assert "No live matter memory matched" in out
    assert "matter_facts_as_of" in out  # steered toward the as-of tool for history


async def test_search_vanished_matter_is_graceful(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, _project_id = matter
    # A binding pointing at a project this user does not own → "no longer available".
    async with commit_factory() as db:
        out = await _search_matter_memory(db, _binding(user_id, uuid.uuid4()), query="anything")
    assert "no longer available" in out.lower()


# --------------------------------------------------------------------------- #
# matter_facts_as_of — bi-temporal recall + the tz-naive trap
# --------------------------------------------------------------------------- #


async def test_as_of_reconstructs_history(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_memory(commit_factory, project_id)
    binding = _binding(user_id, project_id)
    # Between T0 and T1 we believed the 1-month cap; the undated buyer fact also holds.
    async with commit_factory() as db:
        feb = await _matter_facts_as_of(db, binding, as_of_date="2026-02-01")
    assert "1 month" in feb
    assert "We act for the buyer" in feb  # NULL valid_at = from the start
    assert "12 months" not in feb  # not yet valid in February
    # After T1 the agreed 12-month cap is current; the 1-month draft is gone.
    async with commit_factory() as db:
        apr = await _matter_facts_as_of(db, binding, as_of_date="2026-04-01")
    assert "12 months" in apr
    assert "1 month" not in apr


async def test_as_of_bare_date_does_not_crash(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The load-bearing trap: a BARE ISO date parses tz-naive; it must be normalised so
    the comparison against the tz-aware columns does not raise (which would escape as a
    crash, not a reject)."""
    user_id, project_id = matter
    await _seed_memory(commit_factory, project_id)
    async with commit_factory() as db:
        out = await _matter_facts_as_of(db, _binding(user_id, project_id), as_of_date="2026-02-01")
    assert "believed true on 2026-02-01" in out  # ran cleanly, no TypeError crash


async def test_as_of_bad_date_rejected_not_crash(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _matter_facts_as_of(
            db, _binding(user_id, project_id), as_of_date="last Tuesday"
        )
    assert "rejected" in out.lower()
    assert "matter_facts_as_of" in out


async def test_as_of_empty_window_reports_nothing(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_memory(commit_factory, project_id)
    # Before any dated fact's window AND undated facts are "from the start", so pick a
    # date so early only the undated fact is valid — assert the dated ones are absent.
    async with commit_factory() as db:
        out = await _matter_facts_as_of(db, _binding(user_id, project_id), as_of_date="2025-01-01")
    assert "1 month" not in out and "12 months" not in out
    assert "We act for the buyer" in out  # undated fact valid from the start


# --------------------------------------------------------------------------- #
# Guard audit receipt — counts/IDs only
# --------------------------------------------------------------------------- #


async def test_guard_audit_carries_no_body(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    marker = "PLATYPUS-MARKER-do-not-leak"
    async with commit_factory() as db:
        db.add(
            MatterMemoryEntry(
                project_id=project_id,
                user_id=user_id,
                kind="fact",
                body_md=f"A durable fact involving {marker}.",
                trust="normal",
                author="agent",
                fact_type="fact",
            )
        )
        thread = AgentThread(user_id=user_id, project_id=project_id, title="mr guard")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user_id,
            thread_id=thread.id,
            project_id=project_id,
            status="running",
            prompt="search memory",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    [search_matter_memory, _as_of] = build_matter_read_tools(
        commit_factory, run_id=run_id, binding=_binding(user_id, project_id)
    )
    out = await search_matter_memory(query="durable")
    assert marker in out  # the body IS returned to the model (that's the tool's job)…

    async with commit_factory() as db:
        rows = (
            (await db.execute(select(AuditLog).where(AuditLog.user_id == user_id))).scalars().all()
        )
    assert [r.action for r in rows] == ["agent_run.tool_call"]
    details = str(rows[0].details)
    assert "search_matter_memory" in details
    assert "success" in details
    assert marker not in details  # …but never reaches the audit row
