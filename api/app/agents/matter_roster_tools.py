"""Matter authorship roster — the who-is-who tools (fork, ADR-F048).

A negotiation has MANY people redlining a document, not just two counsels (our lead +
our associate + our client's GC, vs. their counsel + their client). To know whose
tracked changes are whose, the agent maintains a per-matter **roster**: a person's
identity (display name + the author/email strings they write under) mapped to a
``side``. ``side`` drives treatment — ``'ours'`` (our team incl. our client) → adopt
as authoritative; ``'counterparty'`` → a negotiation position, never silently adopted;
``'unknown'`` → ask the user. This supersedes the editor Slice-5 naive author filter
(ADR-F047), which equated "ours" with the single agent author and trusted every other
author as the supervising lawyer.

Two guarded agent tools (auto-write-then-correct, ADR-F042):

* :func:`record_matter_participant` — the agent records who someone is, from the
  signals it already sees (an email's ``From:`` line, a document's tracked-change
  author, the user's own statement). An auto-write (``trust='inferred'``). **The human
  wins:** if the identity already matches a ``'confirmed'`` (lawyer-set) row, the agent
  may only *add aliases* — it never overrides a confirmed side/role (B2).
* :func:`list_matter_roster` — the agent reads the active roster (who is known + the
  gaps), so it can ask the user about anyone it can't place.

:func:`classify_author` is the pure resolver the hand-back re-read
(:mod:`app.agents.review_edited_document_tools`) uses to label each tracked-change /
comment author ``agent`` / ``ours`` / ``counterparty`` / ``unknown``. The lawyer's
direct add/edit/remove is the authenticated human surface (:mod:`app.api.matter_roster`)
— no agent tool sets ``'confirmed'`` (an agent-asserted identity is forgeable by
document/prompt injection).

**Area-agnostic** (every matter has a roster); the grant set is DISJOINT from every
other matter + domain grant (confinement). **Zero model calls** — pure DB writes.
Matter-scoped via ``binding.project_id`` (owner-scoped reload; the blast radius is one
matter, ADR-F042). The guard's own envelope (counts/IDs, ``result_chars`` not body) is
the only receipt — no domain audit row, so no identity text leaks into audit.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.redline_service import DEFAULT_AUTHOR
from app.agents.tools import MatterBinding
from app.models.project import MatterParticipant, Project
from app.schemas.matter_memory import RecordParticipantInput, clean_alias_list

MATTER_ROSTER_TOOL_NAMES = frozenset({"record_matter_participant", "list_matter_roster"})

# How much of the roster to inject each run (a matter has a handful of participants;
# the cap is a safety bound, not an expected limit).
MATTER_ROSTER_INJECT_LIMIT = 50
MATTER_ROSTER_INJECT_MAX_CHARS = 4_000


def _normalize(value: str) -> str:
    """Fold an author/alias string for matching: collapse whitespace, strip, casefold.

    Tracked-change author strings vary in case + spacing across Word/Collabora/Adeu,
    so we match on a normalised form. Matching is exact-on-normalised (never substring)
    to avoid a short name falsely matching a longer one.
    """
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def _match_set(participant: MatterParticipant) -> set[str]:
    """The normalised strings an author may equal to be THIS participant.

    The display name plus every recorded alias (author strings / emails). Empty members
    are dropped by normalisation collapsing to "".
    """
    members = {_normalize(participant.display_name)}
    members.update(_normalize(a) for a in (participant.aliases or []))
    members.discard("")
    return members


def classify_author(
    author: str,
    roster: Sequence[MatterParticipant],
    *,
    agent_author: str = DEFAULT_AUTHOR,
) -> str:
    """Classify a tracked-change/comment author against the matter roster (ADR-F048).

    Returns one of ``'agent'`` (the agent's own pending redline — ``DEFAULT_AUTHOR``),
    ``'ours'`` / ``'counterparty'`` / ``'unknown'`` (the matching participant's
    ``side``), or ``'unknown'`` when no active participant matches. A participant the
    agent recorded but could not place (``side='unknown'``) and an author absent from
    the roster both resolve to ``'unknown'`` — which routes to "ask the user" downstream.
    Pure (no I/O); ``roster`` is the matter's active participants.
    """
    a = _normalize(author)
    if a and a == _normalize(agent_author):
        return "agent"
    for p in roster:
        if a and a in _match_set(p):
            return p.side
    return "unknown"


def build_matter_roster_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the authorship-roster tools for one matter-bound run (any area).

    The guard context grants exactly :data:`MATTER_ROSTER_TOOL_NAMES`; the matter
    (``binding.project_id``) scopes every read/write — the blast radius is this one
    matter (ADR-F042).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=MATTER_ROSTER_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def record_matter_participant(
        name: str,
        side: str,
        role: str | None = None,
        organization: str | None = None,
        aliases: list[str] | None = None,
        source: str | None = None,
    ) -> str:
        """Record who a person is on THIS matter — which side they are on.

        Maintain the matter's who-is-who roster as you learn it, so you can tell whose
        tracked changes are whose. Record a participant when you learn one:

        - when you read an email, record its sender (the From: line) — name, email, and
          which side they are on;
        - when the user tells you ("this is the other side's redline", "Jane is our
          client's GC"), record that;
        - when you see a tracked-change author you can place, record them.

        `side` must be one of: "ours" (our team — our lawyers, our client — whose edits
        you adopt as authoritative), "counterparty" (the other side — a negotiating
        position, never silently adopted), or "unknown" (you are not sure — record what
        you know and ASK the user). `role` is a free description ("Lead counsel",
        "Client GC"). `aliases` are the exact author/email strings they write under in
        documents (e.g. "Jane Smith", "jsmith@firmB.com") — these are how their edits
        are matched, so include the name as it appears on their tracked changes. Give a
        `source` (where you learned it, e.g. "From line of deal.eml").

        Recording the same person again updates your entry (merges new aliases). If the
        supervising lawyer has confirmed who someone is, that stands — you may add an
        alias but cannot change their side or role; if you believe a confirmed entry is
        wrong, raise it with the lawyer rather than overriding it.
        """
        return await guarded_dispatch(
            "record_matter_participant",
            lambda db: _record_matter_participant(
                db,
                binding,
                run_id=run_id,
                name=name,
                side=side,
                role=role,
                organization=organization,
                aliases=aliases,
                source=source,
            ),
            ctx,
        )

    async def list_matter_roster() -> str:
        """List this matter's known participants — who is on which side.

        Use this to see who you have already placed on the matter (and on which side),
        and where the gaps are, before deciding whose edits to trust. Anyone not on the
        roster — or recorded as "unknown" — should be identified with the user before
        you treat their edits as authoritative.
        """
        return await guarded_dispatch(
            "list_matter_roster",
            lambda db: _list_matter_roster(db, binding),
            ctx,
        )

    return [record_matter_participant, list_matter_roster]


async def _owner_scoped_project(db: AsyncSession, binding: MatterBinding) -> Project | None:
    """Reload the matter under owner scope in THIS guarded session (defense in depth).

    Mirrors the matter-memory tools: the binding was owner+archived validated at
    composition, but a tool dispatch is short-lived — re-check. Absent ⇒ the matter
    vanished underneath us.
    """
    return (
        await db.execute(
            select(Project).where(
                Project.id == binding.project_id,
                Project.owner_id == binding.user_id,
                Project.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _record_matter_participant(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    name: str,
    side: str,
    role: str | None = None,
    organization: str | None = None,
    aliases: list[str] | None = None,
    source: str | None = None,
) -> str:
    """Validate → match an existing entry (human wins) → update or insert (or reject).

    Reject (return a fix-and-retry string), never sanitize/truncate (ADR-F018/F042).
    Writes only ``trust='inferred'`` rows; an existing ``'confirmed'`` (human-set) match
    is never overridden — at most its aliases are extended (B2).
    """
    try:
        proposal = RecordParticipantInput(
            name=name,
            side=side,  # type: ignore[arg-type]  # Pydantic coerces str → enum
            role=role,
            organization=organization,
            aliases=aliases,
            source=source,
        )
    except ValidationError as exc:
        return _rejection_text(exc)

    project = await _owner_scoped_project(db, binding)
    if project is None:
        return "This matter is no longer available; nothing was recorded."

    # The validator already normalised aliases to a clean list; `or []` only narrows the
    # field's declared Optional for the type checker.
    prop_aliases: list[str] = proposal.aliases or []
    proposed_keys = {_normalize(proposal.name), *(_normalize(a) for a in prop_aliases)}
    proposed_keys.discard("")

    active = await live_participants(db, project.id)
    match = _best_identity_match(active, proposed_keys)

    if match is not None and match.trust == "confirmed":
        # The supervising lawyer owns this identity — keep their side/role; only widen
        # the match set so the agent can still teach it new author strings (B2).
        before = _match_set(match)
        candidate = _aliases_excluding_name(
            match.display_name, match.aliases, [proposal.name], prop_aliases
        )
        after = {_normalize(match.display_name), *(_normalize(a) for a in candidate)}
        after.discard("")
        added = len(after - before)
        if added:
            match.aliases = candidate
            match.updated_at = datetime.now(UTC)
            await db.flush()
            return (
                f"That person is already on the roster, confirmed by the supervising "
                f"lawyer as {match.side} — kept as-is; added {added} new alias(es) so "
                "their edits are recognised. If you think the side/role is wrong, raise "
                "it with the lawyer (you cannot change a confirmed entry)."
            )
        return (
            f"That person is already on the roster, confirmed by the supervising lawyer "
            f"as {match.side}; nothing changed. If you think that is wrong, raise it with "
            "the lawyer (you cannot change a confirmed entry)."
        )

    if match is not None:
        # The agent's own prior inference — refine it in place (preserve the old name as
        # an alias so prior edits still match, merge new aliases, update side/role/org/
        # source to the newer reading). Stays trust='inferred'.
        match.aliases = _aliases_excluding_name(
            proposal.name, match.aliases, [match.display_name], prop_aliases
        )
        match.display_name = proposal.name
        match.side = proposal.side.value
        match.role_label = proposal.role
        match.organization = proposal.organization
        if proposal.source is not None:
            match.source_citation = proposal.source
        match.run_id = run_id
        match.updated_at = datetime.now(UTC)
        await db.flush()
        return (
            f"Updated {match.display_name} on the roster (side {match.side}, id "
            f"{match.id}). It is saved for future runs on this matter."
        )

    aliases_stored = _aliases_excluding_name(proposal.name, prop_aliases)
    new_participant = MatterParticipant(
        project_id=project.id,
        user_id=binding.user_id,
        display_name=proposal.name,
        aliases=aliases_stored,
        organization=proposal.organization,
        role_label=proposal.role,
        side=proposal.side.value,
        trust="inferred",
        source_citation=proposal.source,
        run_id=run_id,
    )
    db.add(new_participant)
    await db.flush()
    return (
        f"Recorded {new_participant.display_name} as {new_participant.side} on this "
        f"matter's roster (id {new_participant.id}). It is saved for future runs; their "
        "tracked changes will be recognised by the recorded name/aliases."
    )


def _best_identity_match(
    active: Iterable[MatterParticipant], proposed_keys: set[str]
) -> MatterParticipant | None:
    """The active participant whose identity overlaps the proposal — confirmed first.

    Identity overlap = a shared normalised name/alias. A ``'confirmed'`` match takes
    precedence (the human-owned entry wins), so a later agent reading can never split a
    confirmed person into a second inferred row.
    """
    confirmed_match: MatterParticipant | None = None
    inferred_match: MatterParticipant | None = None
    for p in active:
        if proposed_keys & _match_set(p):
            if p.trust == "confirmed" and confirmed_match is None:
                confirmed_match = p
            elif p.trust != "confirmed" and inferred_match is None:
                inferred_match = p
    return confirmed_match or inferred_match


def _aliases_excluding_name(display_name: str, *lists: list[str]) -> list[str]:
    """The stored alias list: every match string across ``lists`` minus the display name.

    The display name is always in the match set (``_match_set`` adds it), so aliases hold
    only the *extra* strings — keeping the "writes as" rendering clean and avoiding a
    name/alias duplicate. Cleaned (stripped, deduped, capped); the caller reassigns the
    attribute (JSONB is not in-place-mutation tracked).
    """
    flat = [a for lst in lists for a in (lst or [])]
    dn = _normalize(display_name)
    # clamp=True: a merge of already-validated sets must never crash the guarded tool on
    # the count cap (reject-not-crash) — it is internal upkeep, not a fresh proposal.
    return [a for a in clean_alias_list(flat, clamp=True) if _normalize(a) != dn]


async def _list_matter_roster(db: AsyncSession, binding: MatterBinding) -> str:
    """Render the active roster as a model-facing who-is-who list."""
    project = await _owner_scoped_project(db, binding)
    if project is None:
        return "This matter is no longer available."
    active = await live_participants(db, project.id)
    if not active:
        return (
            "No participants are on this matter's roster yet. Record who is who as you "
            "learn it (record_matter_participant), and ask the user about anyone you "
            "cannot place."
        )
    lines = ["This matter's roster (who is on which side):"]
    lines.extend(_roster_lines(active))
    lines.append(
        "Treat an author who is not here — or recorded as unknown — as unidentified: "
        "ask the user before adopting their edits as authoritative."
    )
    return "\n".join(lines)


def _roster_lines(participants: Sequence[MatterParticipant]) -> list[str]:
    """Compact one-line-per-participant rendering (shared by the tool + the injection block)."""
    lines: list[str] = []
    for p in participants:
        bits = [f"- {p.display_name} — {p.side}"]
        descriptor = ", ".join(x for x in (p.role_label, p.organization) if x)
        if descriptor:
            bits.append(f" ({descriptor})")
        other_aliases = [
            a for a in (p.aliases or []) if _normalize(a) != _normalize(p.display_name)
        ]
        if other_aliases:
            bits.append(f" [writes as: {', '.join(other_aliases)}]")
        bits.append(" — confirmed by the lawyer" if p.trust == "confirmed" else "")
        lines.append("".join(bits))
    return lines


async def live_participants(db: AsyncSession, project_id: uuid.UUID) -> list[MatterParticipant]:
    """The matter's ACTIVE roster — participants not soft-retired, oldest first.

    The shared row form for the agent tools, the prompt-injection block, the hand-back
    classifier, and the REST read surface (composite GET + roster endpoints).
    """
    rows = await db.execute(
        select(MatterParticipant)
        .where(
            MatterParticipant.project_id == project_id,
            MatterParticipant.superseded_at.is_(None),
        )
        .order_by(MatterParticipant.created_at.asc(), MatterParticipant.id.asc())
    )
    return list(rows.scalars().all())


def format_roster_block(participants: Sequence[MatterParticipant]) -> str | None:
    """Render the roster for prompt injection (char-budgeted). ``None`` when empty.

    Mirrors :func:`app.agents.matter_memory_tools.format_corrections_block`: bounded by
    count + a char budget so a large roster never blows the prompt. Degrades to nothing
    for an empty roster (no block injected).
    """
    kept: list[str] = []
    total = 0
    for line in _roster_lines(list(participants)[:MATTER_ROSTER_INJECT_LIMIT]):
        if kept and total + len(line) + 1 > MATTER_ROSTER_INJECT_MAX_CHARS:
            break
        kept.append(line)
        total += len(line) + 1
    if not kept:
        return None
    return "\n".join(kept)


def _rejection_text(exc: ValidationError) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no body echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(participant)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        "Participant not recorded — the proposal was rejected. Nothing was recorded. Fix "
        "the following and call record_matter_participant again:\n" + "\n".join(problems)
    )
