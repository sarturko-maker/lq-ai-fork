"""Matter authorship-roster agent-tool tests (ADR-F048).

The who-is-who roster the agent maintains (auto-write-then-correct, ADR-F042):

* the grant set (two tools; DISJOINT from every other matter + domain grant),
* :func:`classify_author` (pure) — agent / ours / counterparty / unknown, normalised
  + alias matching,
* :func:`record_matter_participant` — insert (inferred), refine the agent's own prior
  inference (merge aliases, change side), the **human-wins** guard (a confirmed entry's
  side/role is never overridden; only aliases widen), reject an invalid side, and the
  matter-gone path,
* :func:`list_matter_roster` rendering + :func:`format_roster_block` (the injection).
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
from app.agents.matter_read_tools import MATTER_READ_TOOL_NAMES
from app.agents.matter_roster_tools import (
    MATTER_ROSTER_TOOL_NAMES,
    _record_matter_participant,
    classify_author,
    ensure_operator_participant,
    format_roster_block,
    live_participants,
)
from app.agents.redline_service import DEFAULT_AUTHOR
from app.agents.review_edited_document_tools import REVIEW_EDITED_DOCUMENT_TOOL_NAMES
from app.agents.ropa_tools import ROPA_TOOL_NAMES
from app.agents.tools import MatterBinding
from app.models.project import MatterParticipant, Project
from app.models.user import User
from app.schemas.matter_memory import MATTER_PARTICIPANT_MAX_ALIASES, clean_alias_list
from app.security import hash_password

pytestmark = pytest.mark.integration


def _p(display_name: str, side: str, *, aliases: list[str] | None = None) -> MatterParticipant:
    return MatterParticipant(
        display_name=display_name, side=side, aliases=aliases or [], trust="inferred"
    )


# --------------------------------------------------------------------------- #
# Grant set / confinement
# --------------------------------------------------------------------------- #


def test_grant_names_and_disjoint() -> None:
    assert sorted(MATTER_ROSTER_TOOL_NAMES) == ["list_matter_roster", "record_matter_participant"]
    for other in (
        MATTER_MEMORY_TOOL_NAMES,
        MATTER_FACT_TOOL_NAMES,
        MATTER_CONSOLIDATION_TOOL_NAMES,
        MATTER_READ_TOOL_NAMES,
        REVIEW_EDITED_DOCUMENT_TOOL_NAMES,
        ROPA_TOOL_NAMES,
        ASSESSMENT_TOOL_NAMES,
        COMMERCIAL_TOOL_NAMES,
    ):
        assert MATTER_ROSTER_TOOL_NAMES.isdisjoint(other)


# --------------------------------------------------------------------------- #
# classify_author (pure)
# --------------------------------------------------------------------------- #


def test_classify_agent_author() -> None:
    assert classify_author(DEFAULT_AUTHOR, []) == "agent"
    # Whitespace/case-insensitive on the agent author too.
    assert classify_author(f"  {DEFAULT_AUTHOR.upper()} ", []) == "agent"


def test_classify_by_side_and_alias() -> None:
    roster = [
        _p("Jane Smith", "ours", aliases=["jsmith@acme.com"]),
        _p("Mark Counsel", "counterparty"),
    ]
    assert classify_author("Jane Smith", roster) == "ours"
    assert classify_author("  jane   smith ", roster) == "ours"  # normalised
    assert classify_author("JSMITH@acme.com", roster) == "ours"  # alias, case-insensitive
    assert classify_author("Mark Counsel", roster) == "counterparty"


def test_classify_unknown_when_absent_or_unplaced() -> None:
    roster = [_p("Sam", "unknown")]  # recorded but not placed
    assert classify_author("Sam", roster) == "unknown"
    assert classify_author("Nobody Here", roster) == "unknown"
    assert classify_author("", roster) == "unknown"


def test_classify_other_third_party_side() -> None:
    """ADR-F048 Slice 2: a known third party classifies as 'other' (its own side)."""
    roster = [_p("Escrow Agent", "other", aliases=["escrow@bank.example"])]
    assert classify_author("Escrow Agent", roster) == "other"
    assert classify_author("ESCROW@bank.example", roster) == "other"  # alias, case-insensitive


# --------------------------------------------------------------------------- #
# Write tool (DB)
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="Roster Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


async def _make_matter(factory: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        user = User(
            email=f"ros-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Roster User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Roster Matter",
            slug=f"roster-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
        )
        db.add(project)
        await db.commit()
        return user.id, project.id


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    user_id, project_id = await _make_matter(commit_factory)
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            await db.execute(delete(MatterParticipant).where(MatterParticipant.user_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def _record(
    factory: async_sessionmaker[AsyncSession],
    binding: MatterBinding,
    **kwargs: object,
) -> str:
    async with factory() as db:
        out = await _record_matter_participant(db, binding, run_id=uuid.uuid4(), **kwargs)  # type: ignore[arg-type]
        await db.commit()
        return out


async def test_record_inserts_inferred_row(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    user_id, project_id = matter
    binding = _binding(user_id, project_id)
    out = await _record(
        commit_factory,
        binding,
        name="Jane Smith",
        side="ours",
        role="Lead counsel",
        organization="Acme LLP",
        aliases=["jsmith@acme.com"],
        source="From line of deal.eml",
    )
    assert "Recorded Jane Smith as ours" in out
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1
    p = rows[0]
    assert p.display_name == "Jane Smith"
    assert p.side == "ours"
    assert p.trust == "inferred"
    assert p.role_label == "Lead counsel"
    assert "jsmith@acme.com" in p.aliases
    # The display name is matched via _match_set, not stored as a redundant alias.
    assert "Jane Smith".casefold() not in [a.casefold() for a in p.aliases]


async def test_record_again_updates_own_inference(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    user_id, project_id = matter
    binding = _binding(user_id, project_id)
    await _record(commit_factory, binding, name="Jane", side="unknown", aliases=["jsmith@acme.com"])
    # Re-record the SAME person (matched via the email alias) with a fuller reading.
    out = await _record(
        commit_factory, binding, name="Jane Smith", side="ours", aliases=["jsmith@acme.com"]
    )
    assert "Updated Jane Smith" in out
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1  # updated in place, not duplicated
    p = rows[0]
    assert p.display_name == "Jane Smith"
    assert p.side == "ours"
    # The old name "Jane" is preserved as an alias so prior edits under it still match.
    assert classify_author("Jane", rows) == "ours"


async def test_human_confirmed_is_never_overridden(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    user_id, project_id = matter
    binding = _binding(user_id, project_id)
    # A lawyer-confirmed entry (as the endpoint writes it).
    async with commit_factory() as db:
        db.add(
            MatterParticipant(
                project_id=project_id,
                user_id=user_id,
                display_name="Jane Smith",
                side="ours",
                aliases=["jsmith@acme.com"],
                trust="confirmed",
            )
        )
        await db.commit()
    # The agent tries to (wrongly) reclassify the same person as the counterparty.
    out = await _record(
        commit_factory,
        binding,
        name="Jane Smith",
        side="counterparty",
        aliases=["jane.smith@newaddr.com"],
    )
    assert "confirmed by the supervising lawyer" in out
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1
    p = rows[0]
    assert p.side == "ours"  # NOT overridden
    assert p.trust == "confirmed"
    assert "jane.smith@newaddr.com" in p.aliases  # but the new alias was merged in


async def test_record_other_side(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """ADR-F048 Slice 2: the agent can record a third party under the new 'other' side."""
    user_id, project_id = matter
    out = await _record(
        commit_factory,
        _binding(user_id, project_id),
        name="Escrow Agent",
        side="other",
        organization="Bank plc",
    )
    assert "Recorded Escrow Agent as other" in out
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1
    assert rows[0].side == "other"


async def test_record_rejects_invalid_side(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    user_id, project_id = matter
    out = await _record(
        commit_factory, _binding(user_id, project_id), name="X", side="enemy-of-the-state"
    )
    assert "rejected" in out.lower()
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert rows == []


async def test_record_matter_gone(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    user_id, _project_id = matter
    out = await _record(commit_factory, _binding(user_id, uuid.uuid4()), name="X", side="ours")
    assert "no longer available" in out


def test_clean_alias_list_clamp_vs_reject() -> None:
    """A fresh proposal over the count cap REJECTS (raise); a merge CLAMPS (no crash)."""
    many = [f"alias{i}@x.example" for i in range(MATTER_PARTICIPANT_MAX_ALIASES + 5)]
    with pytest.raises(ValueError, match="too many aliases"):
        clean_alias_list(many)
    clamped = clean_alias_list(many, clamp=True)
    assert len(clamped) == MATTER_PARTICIPANT_MAX_ALIASES


async def test_record_merge_over_cap_clamps_not_crashes(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """An agent re-record that pushes an at-cap entry over the alias cap clamps, never
    crashes the guarded tool (reject-not-crash — the SF1 fix)."""
    user_id, project_id = matter
    # Seed an inferred entry already AT the alias cap.
    async with commit_factory() as db:
        db.add(
            MatterParticipant(
                project_id=project_id,
                user_id=user_id,
                display_name="Jane Smith",
                side="ours",
                aliases=[f"a{i}@x.example" for i in range(MATTER_PARTICIPANT_MAX_ALIASES)],
                trust="inferred",
            )
        )
        await db.commit()
    # Re-record the same person (matched via an existing alias) with fresh aliases.
    out = await _record(
        commit_factory,
        _binding(user_id, project_id),
        name="Jane Smith",
        side="ours",
        aliases=["a0@x.example", "brand-new@x.example"],
    )
    assert "Updated Jane Smith" in out  # a normal receipt, not a crash
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1
    assert len(rows[0].aliases) <= MATTER_PARTICIPANT_MAX_ALIASES  # clamped


# --------------------------------------------------------------------------- #
# Read tool + injection rendering
# --------------------------------------------------------------------------- #


def test_format_roster_block_renders_sides_and_aliases() -> None:
    block = format_roster_block(
        [
            _p("Jane Smith", "ours", aliases=["jsmith@acme.com"]),
            _p("Mark Counsel", "counterparty"),
        ]
    )
    assert block is not None
    assert "Jane Smith — ours" in block
    assert "writes as: jsmith@acme.com" in block
    assert "Mark Counsel — counterparty" in block


def test_format_roster_block_empty_is_none() -> None:
    assert format_roster_block([]) is None


# --------------------------------------------------------------------------- #
# Operator auto-seed (ADR-F048 Slice 2)
# --------------------------------------------------------------------------- #


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    project_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    display_name: str | None,
    email: str,
) -> MatterParticipant | None:
    async with factory() as db:
        res = await ensure_operator_participant(
            db, project_id, user_id=user_id, display_name=display_name, email=email
        )
        await db.commit()
        return res


async def test_ensure_operator_seeds_ours_confirmed(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """The operator is seeded as a confirmed 'ours' row; name + email both classify ours."""
    user_id, project_id = matter
    res = await _seed(
        commit_factory,
        project_id,
        user_id=user_id,
        display_name="Alex Lawyer",
        email="alex@firm.example",
    )
    assert res is not None
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1
    p = rows[0]
    assert p.display_name == "Alex Lawyer"
    assert p.side == "ours"
    assert p.trust == "confirmed"  # structurally human-set (the authenticated session user)
    assert p.run_id is None
    assert "alex@firm.example" in p.aliases
    # Both the operator's display name and their email resolve to our side.
    assert classify_author("Alex Lawyer", rows) == "ours"
    assert classify_author("alex@firm.example", rows) == "ours"


async def test_ensure_operator_idempotent(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """A second seed (same operator) is a no-op — no duplicate row."""
    user_id, project_id = matter
    first = await _seed(
        commit_factory, project_id, user_id=user_id, display_name="Alex", email="alex@firm.example"
    )
    second = await _seed(
        commit_factory, project_id, user_id=user_id, display_name="Alex", email="alex@firm.example"
    )
    assert first is not None and second is None
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1


async def test_ensure_operator_skips_when_already_on_roster(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """If the operator is already on the roster (matched by email), no seed is added."""
    user_id, project_id = matter
    # The agent (or lawyer) already recorded the operator under their email.
    await _record(
        commit_factory,
        _binding(user_id, project_id),
        name="Alex L.",
        side="ours",
        aliases=["alex@firm.example"],
    )
    res = await _seed(
        commit_factory,
        project_id,
        user_id=user_id,
        display_name="Alex Lawyer",
        email="alex@firm.example",
    )
    assert res is None  # matched via the email alias → not seeded again
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert len(rows) == 1


async def test_ensure_operator_does_not_resurrect_a_retired_operator(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """A lawyer-retired operator row is NOT re-seeded on the next run (ADR-F042 B2)."""
    user_id, project_id = matter
    first = await _seed(
        commit_factory,
        project_id,
        user_id=user_id,
        display_name="Alex Lawyer",
        email="alex@firm.example",
    )
    assert first is not None
    # The lawyer soft-retires the operator (as the retire endpoint does).
    async with commit_factory() as db:
        row = (
            await db.execute(select(MatterParticipant).where(MatterParticipant.id == first.id))
        ).scalar_one()
        row.superseded_at = datetime.now(UTC)
        await db.commit()
    # A subsequent run must respect that removal — no resurrection.
    again = await _seed(
        commit_factory,
        project_id,
        user_id=user_id,
        display_name="Alex Lawyer",
        email="alex@firm.example",
    )
    assert again is None
    async with commit_factory() as db:
        active = await live_participants(db, project_id)
        all_rows = (
            (
                await db.execute(
                    select(MatterParticipant).where(MatterParticipant.project_id == project_id)
                )
            )
            .scalars()
            .all()
        )
    assert active == []  # nothing active
    assert len(all_rows) == 1  # the retired row stays retired, not resurrected


async def test_ensure_operator_display_name_falls_back_to_email(
    commit_factory: async_sessionmaker[AsyncSession], matter: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """No display name → the email is the display name (and not duplicated as an alias)."""
    user_id, project_id = matter
    res = await _seed(
        commit_factory, project_id, user_id=user_id, display_name=None, email="solo@firm.example"
    )
    assert res is not None
    async with commit_factory() as db:
        rows = await live_participants(db, project_id)
    assert rows[0].display_name == "solo@firm.example"
    assert rows[0].aliases == []  # email == display name → no redundant alias
    assert classify_author("solo@firm.example", rows) == "ours"
