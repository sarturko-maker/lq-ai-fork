"""Matter-memory read tools — C3c-1 (fork, ADR-F042/F044): the agent's recall surface.

The read half of the unit-of-work memory tier's agent surface. C3a/C3b gave the agent
tools to WRITE its matter memory (the wiki, the typed fact ledger) and to consolidate
it; this module gives it two tools to READ it back mid-run:

* :func:`search_matter_memory` — keyword search over the matter's **LIVE** memory (the
  current fact ledger + the current wiki + the live pinned corrections). The corpus is
  deliberately the live set: searching the full append-only log would surface a
  **superseded / retired / injected-then-superseded** statement to the model as if it
  were current — a correctness *and* injection hazard. Historical recall is the as-of
  tool, which labels every fact by its validity window.
* :func:`matter_facts_as_of` — the bi-temporal "what did we believe at T" query
  (:func:`app.agents.matter_fact_tools.facts_valid_at`), so the agent can answer
  "what was the cap at signing" from the dated ledger C3b-1 built.

The wiki + the pinned corrections are already injected (read-only) into every run's
prompt (C3a); these tools add the **fact ledger** (not injected) + on-demand search +
the as-of view. Both are READ-ONLY but still route through ``guarded_dispatch`` (R6
grant / R5 halt / R4 cost) — the uniform tool chokepoint, exactly like the read-only
``list_assessments``: the guard's auto-audit (counts/IDs, ``result_chars`` not body) is
the only receipt, so no matter text leaks into an audit row.

**Untrusted input, reject-not-crash.** ``query``/``as_of_date`` are model-supplied. The
query is validated (non-blank) then matched **Python-side** over loaded rows — it never
builds SQL (no injection surface). The as-of date is normalised to UTC-aware at the
schema boundary (:class:`app.schemas.matter_memory.MatterFactsAsOfInput`); a bare date
would otherwise be tz-naive and crash the temporal comparison (the C3b-1 trap). A
malformed date is rejected back to the model, never a crash.

**Area-agnostic**, like the rest of the matter-memory tier — granted to every
matter-bound run regardless of area. Its grant set is DISJOINT from the wiki / fact /
consolidation grants and from the ROPA / assessment / commercial domain grants
(confinement); being read-only it touches no write path at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.matter_fact_tools import facts_valid_at, live_corrections, live_facts
from app.agents.tools import MatterBinding
from app.models.project import MatterMemoryEntry, Project
from app.schemas.matter_memory import MatterFactsAsOfInput, MatterMemorySearchInput

MATTER_READ_TOOL_NAMES = frozenset({"search_matter_memory", "matter_facts_as_of"})

# Bounds on what a read tool returns to the model: keep the digest scannable (the guard
# audits result_chars only, but a dump would still bloat the model's context). At matter
# scale (tens of facts) these are generous.
_MAX_FACT_MATCHES = 25
_MAX_CORRECTION_MATCHES = 25
_MAX_WIKI_LINE_MATCHES = 25
_GONE_MSG = "This matter is no longer available; nothing was read."


def build_matter_read_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the matter-memory read tools for one matter-bound run (any area).

    The guard context grants exactly :data:`MATTER_READ_TOOL_NAMES`; the matter
    (``binding.project_id``) scopes every read — a run can only read its own matter's
    memory.
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=MATTER_READ_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def search_matter_memory(query: str) -> str:
        """Search THIS matter's CURRENT memory for what you already know.

        Use this to recall what the matter has already learned before you re-read a
        document or re-ask the lawyer — the parties and their roles, the documents in
        play, the key terms and where they stand, open points, decisions taken. Pass a
        short keyword query (e.g. "liability cap", "opposing counsel", "termination").

        It searches the matter's LIVE memory: the current fact ledger, the current wiki,
        and the corrections the supervising lawyer has pinned. It deliberately does NOT
        return superseded or retired facts — to ask what was true at an earlier date,
        use matter_facts_as_of. Read-only; it records nothing.
        """
        return await guarded_dispatch(
            "search_matter_memory",
            lambda db: _search_matter_memory(db, binding, query=query),
            ctx,
        )

    async def matter_facts_as_of(as_of_date: str) -> str:
        """Recall the facts this matter believed true at a given date (as-of query).

        Use this to answer "what did we believe at signing / at the last round" — pass
        an ISO date (e.g. "2026-05-01"). It returns the dated facts whose validity
        window contained that date, including facts later superseded (with their
        window), so you can reconstruct the matter's history. A fact recorded without an
        explicit date is treated as valid from the start of the matter, so it always
        appears. Read-only; it records nothing.
        """
        return await guarded_dispatch(
            "matter_facts_as_of",
            lambda db: _matter_facts_as_of(db, binding, as_of_date=as_of_date),
            ctx,
        )

    return [search_matter_memory, matter_facts_as_of]


async def _load_owned_matter(db: AsyncSession, binding: MatterBinding) -> Project | None:
    """Reload the matter under owner + not-archived scope (defense in depth).

    Mirrors the write tools' reload: the binding was owner/active validated at
    composition, but a dispatch is short-lived — re-scope here so a mid-run archive or
    a stale binding degrades to "no longer available" rather than reading on.
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


def _query_tokens(query: str) -> list[str]:
    """The distinct lowercase whitespace-split terms of the query (order-preserving)."""
    seen: set[str] = set()
    tokens: list[str] = []
    for raw in query.lower().split():
        if raw and raw not in seen:
            seen.add(raw)
            tokens.append(raw)
    return tokens


def _match_score(text: str | None, tokens: list[str]) -> int:
    """How many distinct query tokens appear (case-insensitive substring) in ``text``."""
    if not text:
        return 0
    low = text.lower()
    return sum(1 for t in tokens if t in low)


def _fact_line(fact: MatterMemoryEntry) -> str:
    """Render one live fact as a digest line with its open validity start + provenance.

    No closing window — live facts have none (``invalid_at IS NULL``), unlike
    :func:`_matter_facts_as_of`, which prints a two-ended ``valid → until`` range.
    """
    bits = [f"[{fact.fact_type or 'fact'}] {fact.body_md}"]
    if fact.source_citation:
        bits.append(f"source: {fact.source_citation}")
    if fact.valid_at is not None:
        bits.append(f"since {fact.valid_at.date().isoformat()}")
    bits.append(f"id {fact.id}")
    return "- " + " — ".join(bits)


async def _search_matter_memory(db: AsyncSession, binding: MatterBinding, *, query: str) -> str:
    """Validate → load the LIVE corpus → Python-side keyword match → rendered digest.

    Reject a blank/oversize query (no crash). Searches live facts + the current wiki +
    ALL live pinned corrections; superseded/retired facts are out of scope by
    construction (live_facts / live_corrections filter on the live window). The corpus
    is uncapped (the read surface must see every live correction, not the per-run
    prompt-injection slice).
    """
    try:
        proposal = MatterMemorySearchInput(query=query)
    except ValidationError as exc:
        return _rejection_text(exc, "search_matter_memory", "(query)")

    project = await _load_owned_matter(db, binding)
    if project is None:
        return _GONE_MSG

    tokens = _query_tokens(proposal.query)
    facts = await live_facts(db, project.id)
    corrections = await live_corrections(db, project.id)
    wiki = (project.context_md or "").strip()

    # Rank facts by how many distinct query tokens they hit (body + source), keep order
    # among ties, drop non-matches.
    scored_facts = sorted(
        (
            (f, score)
            for f in facts
            if (score := _match_score(f.body_md, tokens) + _match_score(f.source_citation, tokens))
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    matched_corrections = [c.body_md for c in corrections if _match_score(c.body_md, tokens)][
        :_MAX_CORRECTION_MATCHES
    ]
    matched_wiki_lines = [
        line.strip() for line in wiki.splitlines() if line.strip() and _match_score(line, tokens)
    ][:_MAX_WIKI_LINE_MATCHES]

    sections: list[str] = []
    if scored_facts:
        sections.append(
            "Live facts:\n" + "\n".join(_fact_line(f) for f, _ in scored_facts[:_MAX_FACT_MATCHES])
        )
    if matched_corrections:
        sections.append(
            "Corrections recorded by the supervising lawyer:\n"
            + "\n".join(f"- {c}" for c in matched_corrections)
        )
    if matched_wiki_lines:
        sections.append(
            "From the matter wiki:\n" + "\n".join(f"- {ln}" for ln in matched_wiki_lines)
        )

    if not sections:
        return (
            f"No live matter memory matched '{proposal.query}'. "
            f"(Searched {len(facts)} live fact(s), {len(corrections)} pinned correction(s), "
            "and the matter wiki.) To recall what was true at an earlier date, use "
            "matter_facts_as_of."
        )
    return f"Matter memory matching '{proposal.query}':\n\n" + "\n\n".join(sections)


async def _matter_facts_as_of(db: AsyncSession, binding: MatterBinding, *, as_of_date: str) -> str:
    """Validate/normalise the date → as-of query → rendered digest (reject, never crash).

    The date is normalised to UTC-aware at the schema boundary so the temporal
    comparison in :func:`facts_valid_at` never raises (the C3b-1 tz-naive trap).
    """
    try:
        proposal = MatterFactsAsOfInput(as_of=as_of_date)  # type: ignore[arg-type]  # Pydantic coerces ISO str → datetime
    except ValidationError as exc:
        return _rejection_text(exc, "matter_facts_as_of", "(as_of_date)")

    project = await _load_owned_matter(db, binding)
    if project is None:
        return _GONE_MSG

    at = proposal.as_of
    facts = await facts_valid_at(db, project.id, at)
    on = at.date().isoformat()
    if not facts:
        return f"No facts were recorded as valid on {on}."

    lines = []
    for f in facts:
        bits = [f"[{f.fact_type or 'fact'}] {f.body_md}"]
        if f.source_citation:
            bits.append(f"source: {f.source_citation}")
        since = f.valid_at.date().isoformat() if f.valid_at is not None else "the start"
        until = f.invalid_at.date().isoformat() if f.invalid_at is not None else "current"
        bits.append(f"valid {since} → {until}")
        bits.append(f"id {f.id}")
        lines.append("- " + " — ".join(bits))
    return f"Facts the matter believed true on {on}:\n" + "\n".join(lines)


def _rejection_text(exc: ValidationError, tool: str, fallback_loc: str) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no body echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or fallback_loc
        problems.append(f"- {loc}: {err['msg']}")
    return (
        f"Could not run {tool} — the input was rejected. Nothing was read. Fix the "
        f"following and call {tool} again:\n" + "\n".join(problems)
    )
