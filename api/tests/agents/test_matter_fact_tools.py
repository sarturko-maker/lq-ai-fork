"""C3b-1 matter_fact_tools tests (ADR-F042).

Drives the typed fact-ledger tool through the real test DB:

* the grant set (one tool; DISJOINT from the matter-memory wiki grant AND the
  ROPA/assessment/commercial domain grants — confinement),
* the write path (validate → add a ``kind='fact'`` row with the typed columns;
  ``author='agent'`` / ``trust='normal'`` fixed by the tool, not the model),
* supersede (the prior fact's window closes — ``invalid_at`` + ``superseded_by`` —
  and is never deleted), and supersede-not-found / a-correction-id rejected,
* reject-not-truncate (blank / oversize / bad enum / oversize source) — no row,
* the as-of query (``facts_valid_at``) across a supersede boundary, ``live_facts``,
  and the append-only ``memory_log`` ordering,
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
from app.agents.matter_fact_tools import (
    MATTER_FACT_TOOL_NAMES,
    _record_matter_fact,
    build_matter_fact_tools,
    facts_valid_at,
    live_facts,
    memory_log,
)
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.ropa_tools import ROPA_TOOL_NAMES
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.project import MatterMemoryEntry, Project
from app.models.user import User
from app.schemas.matter_memory import MATTER_FACT_MAX_CHARS, MATTER_FACT_SOURCE_MAX_CHARS
from app.security import hash_password

pytestmark = pytest.mark.integration

_T0 = "2026-01-01T00:00:00+00:00"
_T1 = "2026-03-01T00:00:00+00:00"


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_matter(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        user = User(
            email=f"mf-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Matter Fact User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Fact Matter",
            slug=f"fact-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
        )
        db.add(project)
        await db.commit()
        return user.id, project.id


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="Fact Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


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
            # matter_memory_entries CASCADE on the project delete.
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def _facts(db: AsyncSession, project_id: uuid.UUID) -> list[MatterMemoryEntry]:
    rows = await db.execute(
        select(MatterMemoryEntry)
        .where(MatterMemoryEntry.project_id == project_id, MatterMemoryEntry.kind == "fact")
        .order_by(MatterMemoryEntry.created_at, MatterMemoryEntry.id)
    )
    return list(rows.scalars().all())


# --------------------------------------------------------------------------- #
# Grant set / confinement
# --------------------------------------------------------------------------- #


def test_build_grants_exactly_one_tool() -> None:
    tools = build_matter_fact_tools(
        async_sessionmaker(), run_id=uuid.uuid4(), binding=_binding(uuid.uuid4(), uuid.uuid4())
    )
    assert [t.__name__ for t in tools] == ["record_matter_fact"]
    assert sorted(MATTER_FACT_TOOL_NAMES) == ["record_matter_fact"]


def test_grant_set_disjoint_from_other_grants() -> None:
    """Confinement: the fact ledger shares no tool with the wiki tool or the typed
    ROPA/assessment/commercial stores — additive grant, no collision."""
    assert MATTER_FACT_TOOL_NAMES.isdisjoint(MATTER_MEMORY_TOOL_NAMES)
    assert MATTER_FACT_TOOL_NAMES.isdisjoint(ROPA_TOOL_NAMES)
    assert MATTER_FACT_TOOL_NAMES.isdisjoint(ASSESSMENT_TOOL_NAMES)
    assert MATTER_FACT_TOOL_NAMES.isdisjoint(COMMERCIAL_TOOL_NAMES)


# --------------------------------------------------------------------------- #
# Write path
# --------------------------------------------------------------------------- #


async def test_record_fact_sets_typed_columns(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    run_id = uuid.uuid4()
    async with commit_factory() as db:
        out = await _record_matter_fact(
            db,
            _binding(user_id, project_id),
            run_id=run_id,
            fact="Liability cap is 12 months' fees.",
            fact_type="term",
            source="Cirrus MSA §9",
            valid_from=_T0,
            supersedes=None,
        )
        await db.commit()
    assert "Recorded a term fact" in out

    async with commit_factory() as db:
        facts = await _facts(db, project_id)
        assert len(facts) == 1
        f = facts[0]
        assert f.kind == "fact"
        assert f.body_md == "Liability cap is 12 months' fees."
        assert f.fact_type == "term"
        assert f.author == "agent"  # tool-fixed, never model-supplied
        assert f.trust == "normal"  # never human-pinned
        assert f.source_citation == "Cirrus MSA §9"
        assert f.valid_at == datetime(2026, 1, 1, tzinfo=UTC)
        assert f.invalid_at is None
        assert f.superseded_by is None
        assert f.run_id == run_id


async def test_record_fact_defaults_valid_at_to_now(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        await _record_matter_fact(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            fact="We act for the buyer.",
            fact_type="party",
            source=None,
            valid_from=None,
            supersedes=None,
        )
        await db.commit()
    async with commit_factory() as db:
        facts = await _facts(db, project_id)
        assert len(facts) == 1
        assert facts[0].valid_at is not None  # defaulted to now()
        assert facts[0].source_citation is None


async def test_supersede_closes_prior_and_links_forward(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    binding = _binding(user_id, project_id)
    async with commit_factory() as db:
        await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="Liability cap is 1 month (from the draft).",
            fact_type="term",
            source="draft MSA §9",
            valid_from=_T0,
            supersedes=None,
        )
        await db.commit()
    async with commit_factory() as db:
        prior_id = (await _facts(db, project_id))[0].id

    async with commit_factory() as db:
        out = await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="Liability cap agreed at 12 months.",
            fact_type="term",
            source="markup §9",
            valid_from=_T1,
            supersedes=str(prior_id),
        )
        await db.commit()
    assert "superseding the prior fact" in out

    async with commit_factory() as db:
        prior = await db.get(MatterMemoryEntry, prior_id)
        assert prior is not None
        assert prior.invalid_at == datetime(2026, 3, 1, tzinfo=UTC)  # == new fact's valid_at
        assert prior.superseded_by is not None
        # The forward link points at a LIVE successor that is a fact of this matter.
        successor = await db.get(MatterMemoryEntry, prior.superseded_by)
        assert successor is not None
        assert successor.kind == "fact"
        assert successor.invalid_at is None
        assert successor.body_md == "Liability cap agreed at 12 months."


async def test_naive_iso_date_valid_from_is_normalised_utc_and_supersede_does_not_crash(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Review fix: the tool docstring asks the model for "an ISO date" — a BARE date
    ("2026-01-01") parses tz-naive. It must be normalised to UTC-aware so it stores
    correctly AND the supersede comparison against the tz-aware stored column does not
    raise (which would escape as a crash, not a reject-and-retry)."""
    user_id, project_id = matter
    binding = _binding(user_id, project_id)
    async with commit_factory() as db:
        await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="cap 1 month",
            fact_type="term",
            source=None,
            valid_from="2026-01-01",
            supersedes=None,
        )
        await db.commit()
    async with commit_factory() as db:
        prior = (await _facts(db, project_id))[0]
        # Bare date stored as tz-aware UTC midnight (not naive, not an asyncpg guess).
        assert prior.valid_at == datetime(2026, 1, 1, tzinfo=UTC)
        prior_id = prior.id

    # The supersede path compares new_valid_at <= prior.valid_at — a bare date here
    # would have raised TypeError before the fix.
    async with commit_factory() as db:
        out = await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="cap 12 months",
            fact_type="term",
            source=None,
            valid_from="2026-02-01",
            supersedes=str(prior_id),
        )
        await db.commit()
    assert "superseding the prior fact" in out
    async with commit_factory() as db:
        closed = await db.get(MatterMemoryEntry, prior_id)
        assert closed is not None
        assert closed.invalid_at == datetime(2026, 2, 1, tzinfo=UTC)


async def test_supersede_not_found_is_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _record_matter_fact(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            fact="orphan",
            fact_type="fact",
            source=None,
            valid_from=None,
            supersedes=str(uuid.uuid4()),
        )
        await db.commit()
    assert "not found" in out.lower()
    async with commit_factory() as db:
        assert await _facts(db, project_id) == []  # nothing recorded


async def test_supersede_cannot_target_a_correction(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A fact write can never reach a human-pinned correction (kind='fact' filter):
    confinement + the C3a no-overwrite guarantee, carried into the fact tool."""
    user_id, project_id = matter
    async with commit_factory() as db:
        pin = MatterMemoryEntry(
            project_id=project_id,
            user_id=user_id,
            kind="correction",
            body_md="We are the BUYER.",
            trust="human-pinned",
        )
        db.add(pin)
        await db.commit()
        pin_id = pin.id

    async with commit_factory() as db:
        out = await _record_matter_fact(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            fact="We are the seller.",
            fact_type="party",
            source=None,
            valid_from=None,
            supersedes=str(pin_id),
        )
        await db.commit()
    assert "not found" in out.lower()

    async with commit_factory() as db:
        survived = await db.get(MatterMemoryEntry, pin_id)
        assert survived is not None
        assert survived.body_md == "We are the BUYER."
        assert survived.trust == "human-pinned"
        assert survived.invalid_at is None and survived.superseded_by is None
        assert await _facts(db, project_id) == []  # no fact row written either


@pytest.mark.parametrize(
    "fact,fact_type,source",
    [
        ("   ", "term", None),  # blank fact
        ("x" * (MATTER_FACT_MAX_CHARS + 1), "term", None),  # oversize fact
        ("ok", "not-a-real-type", None),  # bad enum
        ("ok", "term", "s" * (MATTER_FACT_SOURCE_MAX_CHARS + 1)),  # oversize source
    ],
)
async def test_invalid_proposals_rejected_no_row(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    fact: str,
    fact_type: str,
    source: str | None,
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _record_matter_fact(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            fact=fact,
            fact_type=fact_type,
            source=source,
            valid_from=None,
            supersedes=None,
        )
        await db.commit()
    assert "not recorded" in out.lower()
    async with commit_factory() as db:
        assert await _facts(db, project_id) == []


# --------------------------------------------------------------------------- #
# As-of query / live facts / append-only log
# --------------------------------------------------------------------------- #


async def test_facts_valid_at_reconstructs_history(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    binding = _binding(user_id, project_id)
    async with commit_factory() as db:
        await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="cap 1 month",
            fact_type="term",
            source=None,
            valid_from=_T0,
            supersedes=None,
        )
        await db.commit()
    async with commit_factory() as db:
        prior_id = (await _facts(db, project_id))[0].id
    async with commit_factory() as db:
        await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="cap 12 months",
            fact_type="term",
            source=None,
            valid_from=_T1,
            supersedes=str(prior_id),
        )
        await db.commit()

    async with commit_factory() as db:
        # Between T0 and T1 we believed "cap 1 month".
        at_feb = await facts_valid_at(db, project_id, datetime(2026, 2, 1, tzinfo=UTC))
        assert [f.body_md for f in at_feb] == ["cap 1 month"]
        # After T1 the agreed cap is current.
        at_apr = await facts_valid_at(db, project_id, datetime(2026, 4, 1, tzinfo=UTC))
        assert [f.body_md for f in at_apr] == ["cap 12 months"]
        # Live facts = the current truth only.
        assert [f.body_md for f in await live_facts(db, project_id)] == ["cap 12 months"]


async def test_memory_log_is_append_only_chronological(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    binding = _binding(user_id, project_id)
    async with commit_factory() as db:
        await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="first",
            fact_type="fact",
            source=None,
            valid_from=_T0,
            supersedes=None,
        )
        await db.commit()
    async with commit_factory() as db:
        prior_id = (await _facts(db, project_id))[0].id
    async with commit_factory() as db:
        # A snapshot row (a different kind) shares the log with facts.
        db.add(
            MatterMemoryEntry(
                project_id=project_id,
                user_id=user_id,
                kind="wiki_snapshot",
                body_md="a prior wiki",
                trust="normal",
            )
        )
        await _record_matter_fact(
            db,
            binding,
            run_id=uuid.uuid4(),
            fact="second",
            fact_type="fact",
            source=None,
            valid_from=_T1,
            supersedes=str(prior_id),
        )
        await db.commit()

    async with commit_factory() as db:
        log = await memory_log(db, project_id)
        # Every entry appears (nothing deleted — the superseded fact is still logged).
        kinds = sorted(e.kind for e in log)
        assert kinds == ["fact", "fact", "wiki_snapshot"]
        # Chronological, non-decreasing created_at.
        assert all(log[i].created_at <= log[i + 1].created_at for i in range(len(log) - 1))


# --------------------------------------------------------------------------- #
# Guard audit receipt — counts/IDs only
# --------------------------------------------------------------------------- #


async def test_guard_audit_carries_no_body(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    marker = "GIRAFFE-MARKER-do-not-leak"
    async with commit_factory() as db:
        thread = AgentThread(user_id=user_id, project_id=project_id, title="mf guard")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user_id,
            thread_id=thread.id,
            project_id=project_id,
            status="running",
            prompt="record a fact",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    [record_matter_fact] = build_matter_fact_tools(
        commit_factory, run_id=run_id, binding=_binding(user_id, project_id)
    )
    out = await record_matter_fact(fact=f"A durable fact involving {marker}.", fact_type="fact")
    assert "Recorded a fact fact" in out

    async with commit_factory() as db:
        rows = (
            (await db.execute(select(AuditLog).where(AuditLog.user_id == user_id))).scalars().all()
        )
    assert [r.action for r in rows] == ["agent_run.tool_call"]
    details = str(rows[0].details)
    assert "record_matter_fact" in details
    assert "success" in details
    assert marker not in details  # the fact body never reaches the audit row
