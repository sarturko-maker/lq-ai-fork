"""AI Compliance domain schema — AIC-1 (fork, ADR-F057/F018).

The **validation contract** for the AI Compliance module's typed domain: what a
valid entry in the company **AI-systems register** is. The agent PROPOSES facts
about a system; this schema is what the guarded write path validates **before**
commit (agent proposes → code disposes → commit or reject-and-retry; never a
silent write/fix — ADR-F018). The ORM model (``app.models.compliance.AiSystem``)
carries the same invariants as DB CHECK constraints (defense-in-depth).

The register holds **FACTS ONLY**. There is deliberately no risk-tier or
legal-role field here: under the EU AI Act (Regulation (EU) 2024/1689) a risk
classification is a *legal determination* the deterministic engine owns (AIC-2,
ADR-F057) — the model records the facts that feed it (intended purpose, lifecycle,
build-vs-buy origin, GPAI flags), it never asserts the verdict. ``development_origin``
is stored as the raw fact that *informs* the provider/deployer role; the engine
derives the authoritative role (Art 25 role-flip included), the model does not.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.classification import ClassificationSummary


class LifecycleStatus(StrEnum):
    """Operational stage of an AI system in the organisation.

    Deliberately minimal for AIC-1; the placed-on-market vs put-into-service
    distinction (Art 3(11)/(12)) and the Art 111 transitional grandfathering land
    in a later slice. The SQL CHECK in ``app.models.compliance`` mirrors this set.
    """

    IN_DEVELOPMENT = "in_development"
    IN_SERVICE = "in_service"
    DECOMMISSIONED = "decommissioned"


class DevelopmentOrigin(StrEnum):
    """Build-vs-buy — the raw fact that informs the provider/deployer role.

    The EU AI Act role (provider Art 3(3) vs deployer Art 3(4), including the Art 25
    role-flip) is *derived by the classification engine*, not asserted here; this
    records only how the system came to be. ``hybrid`` = procured then
    substantially modified in-house (an Art 25 flip candidate the engine weighs).
    """

    IN_HOUSE = "in_house"
    THIRD_PARTY = "third_party"
    HYBRID = "hybrid"


class AiSystemInput(BaseModel):
    """A proposed AI-systems register entry — the validated write contract (ADR-F018).

    Reject, don't sanitize (CLAUDE.md): an out-of-enum lifecycle/origin, an empty
    intended purpose, or a systemic-GPAI flag without the GPAI flag is a hard
    validation error, surfaced verbatim to whoever (AIC-1: the agent) proposed it.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    # The single most classification-relevant fact (Art 3(12) intended purpose): it
    # drives the Annex III high-risk use-case match and the Art 5 prohibited-practice
    # screen. Required — a register entry is meaningless without it.
    intended_purpose: str = Field(min_length=1, max_length=2000)
    lifecycle_status: LifecycleStatus
    development_origin: DevelopmentOrigin
    # Chapter V (GPAI) carry-flags. The obligation logic is deferred to AIC-4b
    # (maintainer decision, ADR-F057); AIC-1 only records the flags so the later
    # ai_models entity + systemic axis slot in without a migration rework.
    is_gpai: bool = False
    gpai_systemic: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def _blank_optional_to_none(cls, v: str | None) -> str | None:
        # str_strip_whitespace already trimmed; a whitespace-only note means "not
        # provided", stored as NULL not "".
        if v is not None and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _systemic_requires_gpai(self) -> AiSystemInput:
        """A systemic-risk general-purpose model is, by definition, a GPAI model.

        Mirrors ROPA's special_category ⇔ art9_condition coherence invariant; the
        DB carries the same CHECK ``NOT gpai_systemic OR is_gpai``.
        """
        if self.gpai_systemic and not self.is_gpai:
            raise ValueError(
                "gpai_systemic can be true only when is_gpai is true "
                "(a systemic-risk model is a general-purpose AI model)"
            )
        return self


class AiSystemRead(BaseModel):
    """One AI-systems register entry (read projection).

    Provenance (``source_project_id``) and the ``practice_area_id`` scoping key are
    internal (never part of the read surface), exactly as ``ProcessingActivityRead``
    omits ``source_project_id``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    intended_purpose: str
    lifecycle_status: str
    development_origin: str
    is_gpai: bool
    gpai_systemic: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Soft-retire: NULL = live. Reads exclude retired rows by default; under
    # ?include_retired=true this carries the retirement timestamp.
    retired_at: datetime | None = None
    # The current risk verdict badge (AIC-2), attached by the read router from the
    # system's current classification; NULL until the engine has classified it. The
    # register stores no tier itself — this is the engine's separate sealed artifact.
    classification: ClassificationSummary | None = None
