"""Matter typed-fact ledger — C3b-1 (fork, ADR-F042): the dated, supersede-able facts.

The second half of the unit-of-work memory tier's agent surface. Where the C3a
``update_matter_memory`` tool keeps the brief *prose wiki* (the current one-pager),
this module's ONE write tool — :func:`record_matter_fact` — keeps a **typed fact
ledger** beside it: individual, dated facts the agent records as it learns them, each
with its source and a WORLD-time validity window, so a changed fact **supersedes**
its predecessor (sets ``invalid_at`` + ``superseded_by``) **without deleting it**.
That bi-temporal history is what answers *"what did we believe at signing"* (the
:func:`facts_valid_at` as-of query).

Facts are ``kind='fact'`` rows in the C3a ``matter_memory_entries`` table (the
additive-nullable columns from migration ``0070``). The write is code-validated
(ADR-F018 shape) through ``guarded_dispatch`` (R6 grant / R5 halt / R4 cost): the
proposal is validated against :class:`app.schemas.matter_memory.RecordMatterFactInput`
(reject blank / over-budget / malformed — never truncate), then a fact row is added
(and a superseded predecessor's window is closed). Guard auto-audit ONLY (counts/IDs,
``result_chars`` not body) — no domain audit row, so no matter text leaks.

**Structural guarantees carry over from C3a (B2).** ``record_matter_fact`` writes
only ``kind='fact'`` rows with ``author='agent'``/``trust='normal'`` — it can neither
mint a ``human-pinned`` correction (no-fabrication) nor touch a ``correction`` row
(no-overwrite). Pinned corrections remain immutable to the agent.

**Area-agnostic** (it is the matter fact ledger for every practice area); the grant
set is DISJOINT from the ROPA/assessment/commercial domain grants **and** from
``MATTER_MEMORY_TOOL_NAMES`` (confinement).

C3b-1 makes **zero model calls** — pure DB writes (like C3a). The gateway-routed
consolidation/Lint pass that reconciles this ledger automatically is **C3b-2** (where
the ADR-F010 egress obligation lands). The agent-facing read tools / REST / cockpit
panel over these reads are **C3c**; the read helpers below are their tested substrate.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.models.project import MatterMemoryEntry, Project
from app.schemas.matter_memory import RecordMatterFactInput

MATTER_FACT_TOOL_NAMES = frozenset({"record_matter_fact"})


def build_matter_fact_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the matter typed-fact write tool for one matter-bound run (any area).

    The guard context grants exactly :data:`MATTER_FACT_TOOL_NAMES`; the matter
    (``binding.project_id``) scopes every write — the blast radius is this one
    matter (ADR-F042).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=MATTER_FACT_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def record_matter_fact(
        fact: str,
        fact_type: str,
        source: str | None = None,
        valid_from: str | None = None,
        supersedes: str | None = None,
    ) -> str:
        """Record one durable fact about THIS matter in its dated fact ledger.

        Use this for an individual, durable fact worth keeping as its own dated
        record — distinct from the matter wiki (update_matter_memory), which is your
        brief current one-pager. Record a fact when you learn something durable:

        - who a party is / which side you act for / opposing counsel (fact_type
          "party"); a key commercial or regulatory term and where it stands
          ("term"); a key date or deadline ("date"); something the supervising
          lawyer has settled ("decision"); an unresolved issue ("open_point");
          otherwise "fact".

        Keep each fact a short, single statement and attach its `source` (the
        document name / section it came from, e.g. "Cirrus MSA §9"). Give
        `valid_from` (an ISO date) when you know WHEN the fact became true (e.g. the
        date a cap was agreed); otherwise it defaults to now.

        **When a fact changes, supersede it — never silently restate it.** Call this
        again with `supersedes` set to the prior fact's id (returned in the receipt
        when you recorded it). The old fact is kept and marked no-longer-current, so
        the matter can always answer "what did we believe at signing". A fact you
        record is yours (the agent's); you cannot record a lawyer's correction here —
        that is the supervising lawyer's own authenticated action.
        """
        return await guarded_dispatch(
            "record_matter_fact",
            lambda db: _record_matter_fact(
                db,
                binding,
                run_id=run_id,
                fact=fact,
                fact_type=fact_type,
                source=source,
                valid_from=valid_from,
                supersedes=supersedes,
            ),
            ctx,
        )

    return [record_matter_fact]


async def _record_matter_fact(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    fact: str,
    fact_type: str,
    source: str | None,
    valid_from: str | None,
    supersedes: str | None,
) -> str:
    """Validate → (optionally load the superseded fact) → add the fact row (or reject).

    Reject (return a fix-and-retry string), never sanitize/truncate (ADR-F018/F042).
    Writes only a ``kind='fact'`` row (``author='agent'``, ``trust='normal'``) and,
    on supersede, closes the prior fact's validity window — never a ``correction`` /
    ``human-pinned`` row (B2 carries over from C3a).
    """
    try:
        proposal = RecordMatterFactInput(
            fact=fact,
            fact_type=fact_type,  # type: ignore[arg-type]  # Pydantic coerces str → enum
            source=source,
            valid_from=valid_from,  # type: ignore[arg-type]  # Pydantic coerces ISO str → datetime
            supersedes=supersedes,  # type: ignore[arg-type]  # Pydantic coerces str → UUID
        )
    except ValidationError as exc:
        return _rejection_text(exc)

    # Reload the matter under owner scope in THIS guarded session (defense in depth —
    # mirrors update_matter_memory). Absent ⇒ the matter vanished underneath us.
    project = (
        await db.execute(
            select(Project).where(
                Project.id == binding.project_id,
                Project.owner_id == binding.user_id,
                Project.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if project is None:
        return "This matter is no longer available; nothing was recorded."

    new_valid_at = proposal.valid_from or datetime.now(UTC)

    prior: MatterMemoryEntry | None = None
    if proposal.supersedes is not None:
        # The superseded fact must be a LIVE fact of THIS matter — never a correction
        # (only kind='fact' is reachable), never another matter's, never already
        # superseded (invalid_at IS NULL).
        prior = (
            await db.execute(
                select(MatterMemoryEntry).where(
                    MatterMemoryEntry.id == proposal.supersedes,
                    MatterMemoryEntry.project_id == project.id,
                    MatterMemoryEntry.kind == "fact",
                    MatterMemoryEntry.invalid_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if prior is None:
            return (
                "The fact to supersede was not found among this matter's live facts "
                "(it may have been superseded already, or belong to another matter). "
                "Nothing was recorded."
            )
        # Temporal coherence: the new truth cannot start at or before the one it
        # replaces (the DB CHECK would also reject invalid_at <= valid_at).
        if prior.valid_at is not None and new_valid_at <= prior.valid_at:
            return (
                "The superseding fact's valid_from must be later than the superseded "
                "fact's validity start. Nothing was recorded."
            )

    new_fact = MatterMemoryEntry(
        project_id=project.id,
        user_id=binding.user_id,
        kind="fact",
        body_md=proposal.fact,
        trust="normal",
        author="agent",
        source_citation=proposal.source,
        fact_type=proposal.fact_type.value,
        valid_at=new_valid_at,
        run_id=run_id,
    )
    db.add(new_fact)
    # Flush to assign the new fact's id (returned in the receipt + used as the
    # prior's forward link). A CHECK violation surfaces inside the guard's try.
    await db.flush()

    if prior is not None:
        # Close the prior fact's window and link it forward — never delete (Graphiti
        # bi-temporal supersede; the as-of query reconstructs the history).
        prior.invalid_at = new_valid_at
        prior.superseded_by = new_fact.id
        await db.flush()

    superseded_note = "" if prior is None else " (superseding the prior fact)"
    return (
        f"Recorded a {proposal.fact_type.value} fact (id {new_fact.id}){superseded_note}. "
        "It is saved and available to future runs on this matter; supersede it later "
        "with supersedes=" + str(new_fact.id) + " if it changes."
    )


async def facts_valid_at(
    db: AsyncSession, project_id: uuid.UUID, at: datetime
) -> list[MatterMemoryEntry]:
    """The matter's facts whose WORLD-time validity window contains ``at``.

    The "what did we believe at signing" as-of query (ADR-F042): a fact is in scope
    when ``valid_at ≤ at`` (or unset) and ``at < invalid_at`` (or still live). NULL
    ``valid_at`` is treated as "valid from the beginning of the matter" so a fact
    recorded without an explicit world-time still shows. Ordered oldest-first by
    world-time then ingestion-time (id as a deterministic tiebreaker).
    """
    rows = await db.execute(
        select(MatterMemoryEntry)
        .where(
            MatterMemoryEntry.project_id == project_id,
            MatterMemoryEntry.kind == "fact",
            or_(MatterMemoryEntry.valid_at.is_(None), MatterMemoryEntry.valid_at <= at),
            or_(MatterMemoryEntry.invalid_at.is_(None), MatterMemoryEntry.invalid_at > at),
        )
        .order_by(
            MatterMemoryEntry.valid_at.asc().nulls_first(),
            MatterMemoryEntry.created_at.asc(),
            MatterMemoryEntry.id.asc(),
        )
    )
    return list(rows.scalars().all())


async def live_facts(db: AsyncSession, project_id: uuid.UUID) -> list[MatterMemoryEntry]:
    """The matter's CURRENT facts — those not yet superseded (``invalid_at IS NULL``)."""
    rows = await db.execute(
        select(MatterMemoryEntry)
        .where(
            MatterMemoryEntry.project_id == project_id,
            MatterMemoryEntry.kind == "fact",
            MatterMemoryEntry.invalid_at.is_(None),
        )
        .order_by(MatterMemoryEntry.created_at.asc(), MatterMemoryEntry.id.asc())
    )
    return list(rows.scalars().all())


async def memory_log(db: AsyncSession, project_id: uuid.UUID) -> list[MatterMemoryEntry]:
    """The matter's append-only log — every entry (fact / snapshot / correction),
    oldest first.

    The table is append-only by construction (no entry is deleted; a fact is
    superseded, a correction soft-retired), so the chronological read IS the log
    (Karpathy ``log.md``). C3c renders it (``## [date] op | title``) and surfaces it
    in the cockpit memory panel; this helper is its tested substrate.
    """
    rows = await db.execute(
        select(MatterMemoryEntry)
        .where(MatterMemoryEntry.project_id == project_id)
        .order_by(MatterMemoryEntry.created_at.asc(), MatterMemoryEntry.id.asc())
    )
    return list(rows.scalars().all())


async def live_corrections(db: AsyncSession, project_id: uuid.UUID) -> list[MatterMemoryEntry]:
    """The matter's CURRENT pinned corrections — live (``superseded_at IS NULL``), oldest first.

    The **uncapped** row form for the read surface (C3c-1 search + the GET projection).
    Distinct from :func:`app.agents.matter_memory_tools.load_pinned_corrections`, which
    returns *bodies* newest-first capped to the per-run prompt-injection budget — that
    bound is correct for prompt injection but wrong for search/read, where every live
    correction must be visible.
    """
    rows = await db.execute(
        select(MatterMemoryEntry)
        .where(
            MatterMemoryEntry.project_id == project_id,
            MatterMemoryEntry.kind == "correction",
            MatterMemoryEntry.superseded_at.is_(None),
        )
        .order_by(MatterMemoryEntry.created_at.asc(), MatterMemoryEntry.id.asc())
    )
    return list(rows.scalars().all())


def _rejection_text(exc: ValidationError) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no body echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(fact)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        "Fact not recorded — the proposal was rejected. Nothing was recorded. Fix the "
        "following and call record_matter_fact again:\n" + "\n".join(problems)
    )
