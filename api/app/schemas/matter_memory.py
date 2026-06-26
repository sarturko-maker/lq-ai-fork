"""Matter-memory schemas — C3a (fork, ADR-F042): the matter-wiki write boundary.

The model-free half of the unit-of-work memory tier's auto-write path. The agent's
``update_matter_memory`` tool is a code-validated write (ADR-F018 shape): the model
PROPOSES the rewritten wiki, code DISPOSES against this schema BEFORE commit, a pass
is written, a failure is rejected back to the model with the reason (reject, never
truncate — a too-long wiki must be *consolidated* by the model, never silently cut;
ADR-F042 §Decision).

This module imports nothing from the agent/runtime layers and touches no I/O, so the
caps are unit-testable with no model and no DB. The pinned-correction request body
lives with its endpoint (``app.api.matter_memory``), mirroring how ``app.api.projects``
carries its own attach-request bodies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The matter wiki is a brief, living one-pager (ADR-F042 / the matter-memory skill),
# NOT a log. We cap it well under the ``projects.context_md`` PATCH ceiling
# (100 KiB) so it always fits comfortably in the prompt budget; on overflow the
# write is rejected and the model is told to consolidate (never truncated here).
MATTER_WIKI_MAX_CHARS = 16_000

# C3b-1: a typed fact is a short statement (reject-not-truncate on overflow). Kept
# brief so the ledger stays scannable; the wiki is the place for prose.
MATTER_FACT_MAX_CHARS = 4_000
# The prose source citation cap — mirrors ``app.models.project.MATTER_FACT_SOURCE_MAX_CHARS``
# and the ``0070`` migration DDL (keep in sync).
MATTER_FACT_SOURCE_MAX_CHARS = 500

# C3b-2 (ADR-F043): bounds for one consolidation/Lint proposal (untrusted model
# output; reject-not-truncate). The op batch is bounded because a matter has tens of
# facts — a proposal naming hundreds is malformed, not a legitimate consolidation.
MATTER_CONSOLIDATION_MAX_OPS = 200
# How many live facts a single ``replace`` op may merge into one. Distinct from the
# op-batch cap above (a different quantity): generously above any real merge fan-in.
MATTER_CONSOLIDATION_MAX_SUPERSEDES = 50
MATTER_CONSOLIDATION_REASON_MAX_CHARS = 500
MATTER_CONSOLIDATION_LINT_MAX_CHARS = 2_000

# C3c-1 (ADR-F044): a matter-memory search query is a short keyword string
# (reject-not-truncate). The corpus is the matter's LIVE memory (tens of facts at
# matter scale), matched Python-side — never a SQL string built from the query.
MATTER_SEARCH_QUERY_MAX_CHARS = 500


def _utc_aware(value: datetime | None) -> datetime | None:
    """Normalise a model-supplied datetime to UTC-aware (C3b-1 trap, shared).

    The tools ask the model for "an ISO date"; a bare date ("2026-01-01") parses
    tz-NAIVE. Comparing that to a tz-aware ``DateTime(timezone=True)`` column raises
    ``TypeError`` — which escapes a guarded tool as a CRASH rather than a
    reject-and-retry. Normalise at the schema boundary so every downstream temporal
    comparison is apples-to-apples and storage is explicit UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_iso_date_string(value: Any) -> Any:
    """Reject a bare numeric string BEFORE Pydantic coerces it to a Unix timestamp.

    Pydantic v2 reads an int-like string ("2026", "1700000000") as a Unix timestamp, so a
    model passing a year like "2026" would silently become 1970-01-01 — a confidently
    wrong as-of recall, not a reject. The tools ask the model for "an ISO date"; we accept
    ISO date/datetime strings (and real datetime objects) and reject a purely numeric
    string back to the model (reject-and-retry, never silent-wrong). A ``mode="before"``
    validator so it runs ahead of the timestamp coercion.
    """
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        raise ValueError("provide an ISO date (e.g. 2026-05-01), not a bare number")
    return value


def _absent_if_blank(value: str | None) -> str | None:
    """Treat a blank (already-stripped) source as "no source" — never ``""``.

    The DB CHECK forbids a zero-length citation; a blank means the model meant to
    omit it, so normalise to ``None`` (absent) rather than rejecting.
    """
    if value is not None and not value:
        return None
    return value


class UpdateMatterMemoryInput(BaseModel):
    """Validate one ``update_matter_memory`` proposal (the rewritten matter wiki).

    ``content_md`` is the FULL new wiki body (the tool rewrites in place). It is
    stripped, must be non-blank, and must fit the wiki budget — an over-budget
    proposal is rejected so the model consolidates rather than the store truncating.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    content_md: str

    @field_validator("content_md")
    @classmethod
    def _non_blank_within_budget(cls, value: str) -> str:
        # str_strip_whitespace already trimmed; reject blank and over-budget.
        if not value:
            raise ValueError("the matter wiki cannot be blank")
        if len(value) > MATTER_WIKI_MAX_CHARS:
            raise ValueError(
                f"the matter wiki is too long ({len(value)} characters; max "
                f"{MATTER_WIKI_MAX_CHARS}). Consolidate it into a briefer one-pager — "
                "keep the durable facts, drop the noise — and call update_matter_memory "
                "again. Nothing was recorded."
            )
        return value


class MatterFactType(StrEnum):
    """A small, area-neutral taxonomy for the matter fact ledger (C3b-1).

    The authoritative set — mirrored by the ORM CHECK
    (``app.models.project._MATTER_FACT_TYPES``) and the ``0070`` migration DDL.
    Start here; extend additively (a new member is a one-line migration + ORM tuple).
    """

    PARTY = "party"  # who a party is / which side we act for / opposing counsel
    TERM = "term"  # a commercial/regulatory term and where it stands
    DATE = "date"  # a key date or deadline
    DECISION = "decision"  # something the supervising lawyer has settled
    OPEN_POINT = "open_point"  # an unresolved issue
    FACT = "fact"  # a general durable fact that is none of the above


class RecordMatterFactInput(BaseModel):
    """Validate one ``record_matter_fact`` proposal — the typed fact-ledger write.

    Code-validated write (ADR-F018 shape): the model proposes a fact, code disposes
    against this schema BEFORE commit; a failure is rejected back with the reason
    (reject, never truncate/sanitize). Only A-class content args appear here — the
    ``author``/``trust``/``run_id``/``project`` are B-class, set by the tool.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    fact: str = Field(min_length=1, max_length=MATTER_FACT_MAX_CHARS)
    fact_type: MatterFactType
    # The prose source ("Cirrus MSA §9"). Optional; a blank value normalises to None
    # (absent), never the empty string (the DB CHECK forbids a zero-length citation).
    source: str | None = Field(default=None, max_length=MATTER_FACT_SOURCE_MAX_CHARS)
    # WORLD-time the fact became true (e.g. the date a cap was agreed). Optional —
    # the tool defaults it to "now" when omitted.
    valid_from: datetime | None = None
    # The id of a live fact this one replaces. When set, the tool supersedes that
    # fact (sets its invalid_at + superseded_by) instead of adding an independent one.
    supersedes: uuid.UUID | None = None

    @field_validator("source")
    @classmethod
    def _blank_source_is_absent(cls, value: str | None) -> str | None:
        # str_strip_whitespace already trimmed; treat a blank source as "no source".
        return _absent_if_blank(value)

    @field_validator("valid_from", mode="before")
    @classmethod
    def _valid_from_iso(cls, value: Any) -> Any:
        return _require_iso_date_string(value)

    @field_validator("valid_from")
    @classmethod
    def _valid_from_utc(cls, value: datetime | None) -> datetime | None:
        return _utc_aware(value)


# --- C3b-2 (ADR-F043): the consolidation/Lint proposal -----------------------
#
# The model output of the in-run ``consolidate_matter_memory`` tool. The model
# judges the matter's live fact set + wiki (mem0 extract→judge + Karpathy/OpenClaw
# Lint) and proposes a batch of SUPERSEDE-ONLY ops plus the rewritten wiki. This is
# untrusted output: code disposes against this schema, then a second pure validation
# pass checks every id is a live ``kind='fact'`` row of THIS matter BEFORE any write
# (reject-not-truncate; all-or-nothing apply). The mutation is supersede-only — a
# corrected statement is a NEW superseding fact (``replace``), never an in-place edit,
# so the bi-temporal history is preserved (ADR-F043 decision).


class RetireConsolidationOp(BaseModel):
    """Close a stale/contradicted/orphaned fact's window with no replacement.

    Sets the fact's ``invalid_at`` (and leaves ``superseded_by`` NULL — there is no
    replacing fact). The row is never deleted; the as-of query still reconstructs it.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    op: Literal["retire"]
    fact_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=MATTER_CONSOLIDATION_REASON_MAX_CHARS)


class ReplaceConsolidationOp(BaseModel):
    """Supersede one or more facts with a single new consolidated fact.

    Dedup / merge / correct: insert the new ``kind='fact'`` row, then close each
    superseded prior's window (``invalid_at`` + ``superseded_by`` → the new id). The
    new fact carries the tool-fixed ``author='agent'``/``trust='normal'`` (B-class).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    op: Literal["replace"]
    # The live facts this op supersedes (1+; merging several into one is valid).
    supersedes: list[uuid.UUID] = Field(
        min_length=1, max_length=MATTER_CONSOLIDATION_MAX_SUPERSEDES
    )
    fact: str = Field(min_length=1, max_length=MATTER_FACT_MAX_CHARS)
    fact_type: MatterFactType
    source: str | None = Field(default=None, max_length=MATTER_FACT_SOURCE_MAX_CHARS)
    # WORLD-time the consolidated fact becomes true; the tool defaults it to "now".
    valid_from: datetime | None = None
    reason: str = Field(min_length=1, max_length=MATTER_CONSOLIDATION_REASON_MAX_CHARS)

    @field_validator("source")
    @classmethod
    def _blank_source_is_absent(cls, value: str | None) -> str | None:
        return _absent_if_blank(value)

    @field_validator("valid_from", mode="before")
    @classmethod
    def _valid_from_iso(cls, value: Any) -> Any:
        return _require_iso_date_string(value)

    @field_validator("valid_from")
    @classmethod
    def _valid_from_utc(cls, value: datetime | None) -> datetime | None:
        return _utc_aware(value)


# Discriminated on ``op`` so a malformed/extra-field op is rejected per-variant.
ConsolidationOp = Annotated[
    RetireConsolidationOp | ReplaceConsolidationOp,
    Field(discriminator="op"),
]


class ConsolidationResult(BaseModel):
    """One consolidation/Lint proposal: supersede-only ops + the rewritten wiki.

    Facts NOT named in any op are kept as-is (the model lists only changes). ``new_wiki``
    is the FULL rewritten one-pager (non-blank, within the wiki budget — same rule as
    :class:`UpdateMatterMemoryInput`); ``lint_notes`` is the model's free-text summary
    of what it found (returned to the agent, never written to an audit row).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    operations: list[ConsolidationOp] = Field(
        default_factory=list, max_length=MATTER_CONSOLIDATION_MAX_OPS
    )
    new_wiki: str = Field(min_length=1, max_length=MATTER_WIKI_MAX_CHARS)
    lint_notes: str | None = Field(default=None, max_length=MATTER_CONSOLIDATION_LINT_MAX_CHARS)


# --- C3c-1 (ADR-F044): the agent-facing read-tool inputs ---------------------
#
# The matter-memory read tools (search + as-of) take untrusted model input. Both
# validate at this boundary (reject-and-retry, never crash). The as-of date is the
# load-bearing case: a bare ISO date parses tz-NAIVE, and comparing that to the
# tz-aware ``valid_at``/``invalid_at`` columns raises ``TypeError`` which escapes a
# guarded tool as a CRASH — so the date is normalised through ``_utc_aware`` here,
# exactly like ``RecordMatterFactInput.valid_from`` (the C3b-1 trap).


class MatterMemorySearchInput(BaseModel):
    """Validate one ``search_matter_memory`` query (a short keyword string).

    ``str_strip_whitespace`` trims first, so a whitespace-only query collapses to ""
    and fails ``min_length=1`` (rejected, never an empty search). The query is matched
    Python-side over the matter's loaded live memory — it never builds SQL.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(min_length=1, max_length=MATTER_SEARCH_QUERY_MAX_CHARS)


class MatterFactsAsOfInput(BaseModel):
    """Validate one ``matter_facts_as_of`` date (the "what did we believe at T" query).

    Pydantic coerces the model's ISO string → ``datetime`` (a bare date → tz-naive);
    the validator then normalises to UTC-aware so the downstream temporal comparison in
    :func:`app.agents.matter_fact_tools.facts_valid_at` never raises. A string Pydantic
    cannot coerce to a date (e.g. "last Tuesday") raises ``ValidationError`` → the tool
    returns a reject-and-retry message, never a crash.
    """

    model_config = ConfigDict(extra="forbid")

    as_of: datetime

    @field_validator("as_of", mode="before")
    @classmethod
    def _as_of_iso(cls, value: Any) -> Any:
        # Reject a bare numeric string ("2026") before Pydantic reads it as a Unix
        # timestamp → 1970 (a silent-wrong recall on a load-bearing arg).
        return _require_iso_date_string(value)

    @field_validator("as_of")
    @classmethod
    def _as_of_utc(cls, value: datetime) -> datetime:
        # value is required (non-None), so _utc_aware never returns None here; the
        # `or value` only narrows the optional return type for the type checker.
        return _utc_aware(value) or value


# --- Authorship roster (ADR-F048): the who-is-who model + agent-tool input -----------
#
# A negotiation has many people redlining. The roster maps a person's identity (display
# name + the author/email strings we MATCH against) to a ``side`` that drives how the
# agent treats their edits. ``RecordParticipantInput`` is the agent's auto-write input
# (code-validated, ADR-F018 shape — only A-class content args; ``trust``/``user``/
# ``run`` are B-class, set by the tool). ``ParticipantRead`` is the shared read
# projection both the roster endpoints and the composite GET return. The caps mirror
# ``app.models.project`` (keep in sync).

# Field caps — mirror app.models.project.MATTER_PARTICIPANT_* (and the 0076 DDL).
MATTER_PARTICIPANT_NAME_MAX_CHARS = 200
MATTER_PARTICIPANT_ROLE_MAX_CHARS = 200
MATTER_PARTICIPANT_ORG_MAX_CHARS = 200
MATTER_PARTICIPANT_ALIAS_MAX_CHARS = 200
MATTER_PARTICIPANT_MAX_ALIASES = 30
MATTER_PARTICIPANT_SOURCE_MAX_CHARS = 500


class MatterParticipantSide(StrEnum):
    """Which side a roster participant is on — the treatment driver (ADR-F048).

    The authoritative set, mirrored by the ORM CHECK
    (``app.models.project._MATTER_PARTICIPANT_SIDES``) and the ``0076`` DDL. Start
    here; extend additively (e.g. an ``'other'`` for a third party — a regulator or
    escrow agent — is a one-line migration + member).
    """

    OURS = "ours"  # our team incl. our client → adopt their edits as authoritative
    COUNTERPARTY = "counterparty"  # the other side → a negotiation position, never silently adopted
    UNKNOWN = "unknown"  # not yet identified → ask the user before trusting their edits


def clean_alias_list(value: list[str] | None, *, clamp: bool = False) -> list[str]:
    """Normalise a proposed alias list — strip, drop blanks, case-insensitive dedupe.

    The aliases are the match set (author strings / emails). Stored in display form
    (stripped) and matched case-insensitively downstream, so we dedupe case-insensitively
    here (keep first form seen). Reject (raise) an over-long alias — never truncate a
    single value (ADR-F018). ``None``/empty → ``[]`` (a participant may have no alias yet;
    the display name still matches).

    The over-COUNT cap depends on the caller: validating a fresh PROPOSAL rejects (raise)
    so the model/lawyer fixes it; an internal MERGE of two already-validated sets (the
    agent re-recording someone, or a rename folding the old name in) passes ``clamp=True``
    to keep the first ``MATTER_PARTICIPANT_MAX_ALIASES`` rather than crash the guarded tool
    / 500 the endpoint — merge upkeep is not a user proposal to reject.
    """
    if not value:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = (raw or "").strip()
        if not item:
            continue
        if len(item) > MATTER_PARTICIPANT_ALIAS_MAX_CHARS:
            raise ValueError(
                f"an alias is too long ({len(item)} characters; max "
                f"{MATTER_PARTICIPANT_ALIAS_MAX_CHARS})"
            )
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    if len(cleaned) > MATTER_PARTICIPANT_MAX_ALIASES:
        if clamp:
            return cleaned[:MATTER_PARTICIPANT_MAX_ALIASES]
        raise ValueError(f"too many aliases ({len(cleaned)}; max {MATTER_PARTICIPANT_MAX_ALIASES})")
    return cleaned


class RecordParticipantInput(BaseModel):
    """Validate one ``record_matter_participant`` proposal — the agent's roster auto-write.

    Code-validated write (ADR-F018 shape): the model proposes who a person is, code
    disposes against this schema BEFORE commit; a failure is rejected back with the
    reason (reject, never truncate/sanitize). Only A-class content args appear here —
    ``trust`` (always ``'inferred'`` for an agent write), ``user_id``, ``run_id`` and
    ``project`` are B-class, set by the tool. The agent cannot mint a ``'confirmed'``
    entry (that is the supervising lawyer's authenticated action; B2).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=MATTER_PARTICIPANT_NAME_MAX_CHARS)
    side: MatterParticipantSide
    role: str | None = Field(default=None, max_length=MATTER_PARTICIPANT_ROLE_MAX_CHARS)
    organization: str | None = Field(default=None, max_length=MATTER_PARTICIPANT_ORG_MAX_CHARS)
    aliases: list[str] | None = None
    source: str | None = Field(default=None, max_length=MATTER_PARTICIPANT_SOURCE_MAX_CHARS)

    @field_validator("role", "organization", "source")
    @classmethod
    def _blank_is_absent(cls, value: str | None) -> str | None:
        # str_strip_whitespace already trimmed; a blank optional means "omitted".
        return _absent_if_blank(value)

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, value: list[str] | None) -> list[str]:
        return clean_alias_list(value)


class ParticipantRead(BaseModel):
    """One active roster participant — the shared read projection (ADR-F048).

    Returned by the roster write endpoints and embedded in the composite
    ``GET /matters/{id}/memory`` so the cockpit panel loads the roster in one fetch.
    ``trust`` tells the panel whether the agent inferred the entry or the lawyer
    confirmed it; ``side`` drives the badge.
    """

    id: uuid.UUID
    display_name: str
    aliases: list[str]
    organization: str | None
    role_label: str | None
    side: str
    trust: str
    source_citation: str | None
    created_at: datetime
    updated_at: datetime
