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
from typing import Annotated, Literal

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
