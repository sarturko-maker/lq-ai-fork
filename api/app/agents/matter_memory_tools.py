"""Matter-memory agent tool — C3a (fork, ADR-F042): the auto-write matter wiki.

The unit-of-work memory tier's ONE agent tool: :func:`update_matter_memory`. The
agent maintains a brief, evolving **wiki of this matter** (the free-form
``projects.context_md``) automatically — no approval step (ADR-F042 reverses the
F030 §2A propose/accept direction). The human's control is *after* the write:
correct (a human-authenticated, enforced-un-overwritable pin — see
:mod:`app.api.matter_memory`), undo (the prior-version snapshots this tool writes),
delete (C3c).

The write is code-validated (ADR-F018 shape) through ``guarded_dispatch`` (R6 grant
/ R5 halt / R4 cost): the proposed wiki is validated against
:class:`app.schemas.matter_memory.UpdateMatterMemoryInput` (reject blank / over the
budget — **consolidate, never truncate**), the prior ``context_md`` is snapshotted
(undo substrate), then ``context_md`` is rewritten in place. There is **no domain
audit row** — the guard's own envelope (counts/IDs, ``result_chars`` not body) is the
only receipt, so no matter text can leak into an audit row (ADR-F042 / ADR-F005).

**The tool writes only the wiki + a ``wiki_snapshot`` row** — never a ``correction``
row, never a ``human-pinned`` entry. That is structural: the agent's auto-curation
is gate-forbidden to fabricate a pin (an agent-asserted "the lawyer said X" is
forgeable by document/prompt injection; B2) and is gate-forbidden to alter/drop a
pinned correction (the no-overwrite guarantee — pins live in a table this tool does
not write).

**Area-agnostic.** Matter memory exists for every practice area (it is "Programme
memory" in Privacy — same mechanism, longer-running unit), so the composition point
grants this tool to every matter-bound run regardless of area; the grant set is
DISJOINT from the ROPA/assessment/commercial domain grants (confinement —
an injected fact in the wiki shares no write path with the typed ROPA/assessment
stores).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.models.project import MatterMemoryEntry, Project
from app.schemas.matter_memory import UpdateMatterMemoryInput

MATTER_MEMORY_TOOL_NAMES = frozenset({"update_matter_memory"})

# How much of the live pinned-corrections history to inject each run (C3a bound —
# C3b's consolidation/Lint pass supersedes this). Newest-first selection by count
# and a char budget so a long correction history can't blow the prompt before C3b.
MATTER_CORRECTIONS_INJECT_LIMIT = 30
MATTER_CORRECTIONS_INJECT_MAX_CHARS = 8_000


def build_matter_memory_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the matter-memory write tool for one matter-bound run (any area).

    The guard context grants exactly :data:`MATTER_MEMORY_TOOL_NAMES` (R6's grant
    set); the matter (``binding.project_id``) scopes the write — the blast radius is
    this one matter (ADR-F042).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=MATTER_MEMORY_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def update_matter_memory(content_md: str) -> str:
        """Rewrite this matter's working memory (the matter wiki) — saved automatically.

        This is your durable memory of THIS matter: a brief, evolving one-pager you
        keep current so future runs on the matter start from what is already known
        (the parties and their roles, the documents in play, the key terms and where
        they stand, open points, what the supervising lawyer has decided). It is
        injected, read-only, into every future run on this matter.

        Pass the FULL updated wiki each time — this rewrites it in place (it does not
        append). So read the current memory, fold your new facts in, and pass back the
        whole consolidated one-pager. Keep it brief and durable:

        - Record what you LEARN about the matter, each fact with its source (the
          document name / where it came from) — not your working notes or this turn's
          chat. You record; the supervising lawyer checks caps, dates and obligations.
        - Keep it a living summary, not a log: consolidate, drop the stale, stay well
          under the size limit (an over-long wiki is rejected — you consolidate it).
        - Never contradict a correction the supervising lawyer has recorded; treat
          those as ground truth and keep the wiki consistent with them.

        The prior version is snapshotted automatically, so a change can be undone.
        """
        return await guarded_dispatch(
            "update_matter_memory",
            lambda db: _update_matter_memory(db, binding, run_id=run_id, content_md=content_md),
            ctx,
        )

    return [update_matter_memory]


async def _update_matter_memory(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    content_md: str,
) -> str:
    """Validate → snapshot prior → rewrite ``context_md`` in place (or reject).

    Reject (return a fix-and-retry string), never sanitize/truncate (ADR-F018/F042).
    Writes a ``wiki_snapshot`` row of the prior body (undo) but never a
    ``correction`` / ``human-pinned`` row — those are human-authenticated only (B2).
    """
    try:
        proposal = UpdateMatterMemoryInput(content_md=content_md)
    except ValidationError as exc:
        return _rejection_text(exc)

    # Reload the matter under owner scope in THIS guarded session (defense in depth —
    # the binding was owner+archived validated at composition; a tool dispatch is
    # short-lived). Absent ⇒ the matter vanished underneath us; record nothing.
    project = (
        await db.execute(
            select(Project).where(
                Project.id == binding.project_id,
                Project.owner_id == binding.user_id,
                # Mirror the composition load + the rest of the project surface: a
                # mid-run-archived matter degrades to "no longer available".
                Project.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if project is None:
        return "This matter is no longer available; nothing was recorded."

    prior = (project.context_md or "").strip()
    if prior:
        # Snapshot the prior body for undo (trust='normal'; never a pin). Created
        # BEFORE the overwrite so a constraint failure on either rolls both back.
        db.add(
            MatterMemoryEntry(
                project_id=project.id,
                user_id=binding.user_id,
                kind="wiki_snapshot",
                body_md=prior,
                trust="normal",
                run_id=run_id,
            )
        )

    project.context_md = proposal.content_md
    # Flush (not commit) so a DB CHECK violation surfaces inside the guard's try
    # (audited as an error, rolled back); the guard commits the row + its audit row.
    await db.flush()

    return (
        f"Updated this matter's memory ({len(proposal.content_md)} characters). It is "
        "saved and will be available in future runs on this matter; the prior version "
        "was snapshotted so the change can be undone."
    )


async def load_pinned_corrections(db: AsyncSession, project_id: uuid.UUID) -> list[str]:
    """The live (non-superseded) pinned-correction bodies of one matter, newest first.

    Bounded by :data:`MATTER_CORRECTIONS_INJECT_LIMIT` (C3a cap — a long history is
    consolidated by C3b). Returned newest-first so :func:`format_corrections_block`
    keeps the most recent under the char budget; the block reverses to oldest-first
    for stable reading.
    """
    rows = (
        (
            await db.execute(
                select(MatterMemoryEntry.body_md)
                .where(
                    MatterMemoryEntry.project_id == project_id,
                    MatterMemoryEntry.kind == "correction",
                    MatterMemoryEntry.superseded_at.is_(None),
                )
                # id.desc() is a deterministic tiebreaker for same-transaction
                # inserts that share a created_at, so selection + display are stable.
                .order_by(MatterMemoryEntry.created_at.desc(), MatterMemoryEntry.id.desc())
                .limit(MATTER_CORRECTIONS_INJECT_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def format_corrections_block(newest_first_bodies: list[str]) -> str | None:
    """Render the pinned corrections as a markdown list (oldest first), char-budgeted.

    ``newest_first_bodies`` is what :func:`load_pinned_corrections` returns; we keep
    the most recent within :data:`MATTER_CORRECTIONS_INJECT_MAX_CHARS`, then present
    oldest-first for stable reading. ``None`` when there are no corrections (the
    block degrades to nothing — empty matters inject no corrections sub-block).
    """
    kept: list[str] = []
    total = 0
    for body in newest_first_bodies:
        item = f"- {body.strip()}"
        if kept and total + len(item) + 1 > MATTER_CORRECTIONS_INJECT_MAX_CHARS:
            break
        kept.append(item)
        total += len(item) + 1
    if not kept:
        return None
    return "\n".join(reversed(kept))


def _rejection_text(exc: ValidationError) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no body echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(wiki)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        "Matter memory not updated — the proposed wiki was rejected. Nothing was "
        "recorded. Fix the following and call update_matter_memory again:\n" + "\n".join(problems)
    )
