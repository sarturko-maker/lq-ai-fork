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

from pydantic import BaseModel, ConfigDict, field_validator

# The matter wiki is a brief, living one-pager (ADR-F042 / the matter-memory skill),
# NOT a log. We cap it well under the ``projects.context_md`` PATCH ceiling
# (100 KiB) so it always fits comfortably in the prompt budget; on overflow the
# write is rejected and the model is told to consolidate (never truncated here).
MATTER_WIKI_MAX_CHARS = 16_000


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
