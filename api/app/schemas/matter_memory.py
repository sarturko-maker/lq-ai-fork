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
        if value is not None and not value:
            return None
        return value

    @field_validator("valid_from")
    @classmethod
    def _valid_from_utc(cls, value: datetime | None) -> datetime | None:
        # The tool docstring asks the model for "an ISO date"; a bare date
        # ("2026-01-01") parses tz-NAIVE. Normalise to UTC-aware so the downstream
        # supersede comparison against the tz-aware stored column never raises a
        # TypeError (it would otherwise escape as a crash, not a reject-and-retry),
        # and so storage is explicit UTC rather than an implicit asyncpg assumption.
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
