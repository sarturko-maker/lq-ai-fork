"""EU AI Act classification schema — AIC-2 (fork, ADR-F057).

The **fact and verdict vocabularies** for the deterministic risk-classification
engine (:mod:`app.aiact.classify`). This module is the single source of the enum
values; the ORM model (:class:`app.models.classification.RiskClassification`) and
migration 0086 mirror the tier/route sets as DB CHECK constraints
(defense-in-depth), exactly as :mod:`app.schemas.compliance` does for the register.

**The presence gate is structural here (ADR-F057).** :class:`ClassificationFactsInput`
is the *only* thing the model supplies to a classification — and it is ``extra="forbid"``
with **no tier/risk/route field**. There is no way to hand the engine a verdict: the
model provides facts, the engine (over these facts) is the sole author of
:class:`RiskTier`. A ``risk_tier`` the model tries to smuggle in is a hard validation
error (tested). The facts are booleans/enums about the system's characteristics under
Regulation (EU) 2024/1689 (as amended by the Digital Omnibus adopted 2026-06-30); the
engine maps them deterministically to a tier — the classification cannot be *argued*
down by an intake conversation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class RiskTier(StrEnum):
    """The EU AI Act risk pyramid — the engine's verdict, never a model input.

    The DB CHECK in :mod:`app.models.classification` mirrors this set.
    """

    PROHIBITED = "prohibited"  # Art 5 — unacceptable risk
    HIGH = "high"  # Art 6(1)/(2) — high-risk
    LIMITED = "limited"  # Art 50 — transparency obligations only
    MINIMAL = "minimal"  # no AI-Act-specific obligation


class ClassificationRoute(StrEnum):
    """The pathway that *determined* the tier — always explains the tier 1:1.

    A route maps to exactly one terminal tier. An Art 6(3) derogation is NOT a
    route: it is recorded in ``predicate_trace`` + ``article_refs`` + the
    ``draft_basis`` flag, and the residual tier (limited/minimal) keeps its own
    terminal route. This keeps route ⇔ tier coherent and auditable.
    """

    ART5_PROHIBITED = "art5_prohibited"  # → prohibited
    ANNEX_I_SAFETY_COMPONENT = "annex_i_safety_component"  # → high (Art 6(1))
    ANNEX_III = "annex_iii"  # → high (Art 6(2))
    ART50_TRANSPARENCY = "art50_transparency"  # → limited
    MINIMAL = "minimal"  # → minimal


class Art5Trigger(StrEnum):
    """Which Article 5 prohibited practice a system falls under (``none`` = clear).

    ``ncii_csam_generation`` is the practice added by the Digital Omnibus (adopted
    2026-06-30) — non-consensual intimate imagery / CSAM generators ("nudifiers").
    """

    NONE = "none"
    SUBLIMINAL_MANIPULATION = "subliminal_manipulation"
    EXPLOITS_VULNERABILITIES = "exploits_vulnerabilities"
    SOCIAL_SCORING = "social_scoring"
    PREDICTIVE_POLICING_PROFILING = "predictive_policing_profiling"
    UNTARGETED_FACIAL_SCRAPING = "untargeted_facial_scraping"
    EMOTION_RECOGNITION_WORKPLACE_EDUCATION = "emotion_recognition_workplace_education"
    BIOMETRIC_CATEGORISATION_SENSITIVE = "biometric_categorisation_sensitive"
    REALTIME_RBI_PUBLIC_LE = "realtime_rbi_public_le"
    NCII_CSAM_GENERATION = "ncii_csam_generation"  # Digital Omnibus 2026-06-30 addition


class AnnexIIIArea(StrEnum):
    """The Annex III high-risk use-case area (``none`` = not an Annex III system).

    ``essential_services_credit_insurance`` collapses Annex III(5): access to
    essential private/public services, incl. creditworthiness/credit scoring and
    life/health insurance risk assessment.
    """

    NONE = "none"
    BIOMETRICS = "biometrics"
    CRITICAL_INFRASTRUCTURE = "critical_infrastructure"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    ESSENTIAL_SERVICES_CREDIT_INSURANCE = "essential_services_credit_insurance"
    LAW_ENFORCEMENT = "law_enforcement"
    MIGRATION_BORDER = "migration_border"
    JUSTICE_DEMOCRACY = "justice_democracy"


class Art6_3Condition(StrEnum):
    """The Art 6(3) derogation ground claimed (``none`` = no derogation claimed).

    A single field carries the whole claim: a derogation is asserted iff the ground
    is not ``none``. The four grounds mirror Art 6(3)(a)-(d). The engine treats a
    claimed derogation conservatively (ADR-F057): it is honoured but flags the
    verdict ``draft_basis=true``, and it never applies when profiling of natural
    persons is present (Art 6(3) final subparagraph).
    """

    NONE = "none"
    NARROW_PROCEDURAL_TASK = "narrow_procedural_task"
    IMPROVES_PRIOR_HUMAN_ACTIVITY = "improves_prior_human_activity"
    DETECTS_DEVIATIONS_NO_REPLACE = "detects_deviations_no_replace"
    PREPARATORY_TASK = "preparatory_task"


class ClassificationFactsInput(BaseModel):
    """The structured facts the model supplies to classify one system (ADR-F057).

    ``extra="forbid"`` and NO tier/route field — the sole input to the engine, and
    it deliberately cannot carry a verdict. Coherence validators *reject* incoherent
    fact combinations (reject, don't sanitize — CLAUDE.md), surfaced verbatim to the
    proposer so it can fix and re-call.
    """

    model_config = ConfigDict(extra="forbid")

    # Art 5 — a single prohibited-practice trigger (or none).
    art5_trigger: Art5Trigger = Art5Trigger.NONE

    # Art 6(1) / Annex I — embedded safety component of a regulated product.
    annex_i_safety_component: bool = False
    requires_third_party_conformity_assessment: bool = False

    # Art 6(2) / Annex III — standalone high-risk use-case area.
    annex_iii_area: AnnexIIIArea = AnnexIIIArea.NONE
    # Art 6(3) final subparagraph: profiling of natural persons is ALWAYS high-risk
    # for an Annex III system — no derogation.
    profiling_of_natural_persons: bool = False
    # Art 6(3) derogation ground claimed (none = not claimed).
    art6_3_derogation_condition: Art6_3Condition = Art6_3Condition.NONE

    # Art 50 — transparency triggers (apply when the system is not prohibited).
    interacts_with_natural_persons: bool = False
    generates_synthetic_content: bool = False
    emotion_recognition: bool = False
    biometric_categorisation: bool = False

    @model_validator(mode="after")
    def _third_party_ca_requires_annex_i(self) -> ClassificationFactsInput:
        """A third-party conformity assessment is only meaningful for an Annex I component."""
        if self.requires_third_party_conformity_assessment and not self.annex_i_safety_component:
            raise ValueError(
                "requires_third_party_conformity_assessment is only valid when "
                "annex_i_safety_component is true (Art 6(1) applies to an Annex I "
                "product/safety component)"
            )
        return self

    @model_validator(mode="after")
    def _derogation_requires_annex_iii(self) -> ClassificationFactsInput:
        """An Art 6(3) derogation only exists for an Annex III system."""
        if (
            self.art6_3_derogation_condition is not Art6_3Condition.NONE
            and self.annex_iii_area is AnnexIIIArea.NONE
        ):
            raise ValueError(
                "art6_3_derogation_condition is only valid when annex_iii_area is set "
                "(Art 6(3) derogates an Annex III classification)"
            )
        return self

    @model_validator(mode="after")
    def _profiling_requires_annex_iii(self) -> ClassificationFactsInput:
        """Profiling only elevates within an Annex III context (Art 6(3) subparagraph).

        The flag is the Art 6(3) "profiling never derogates" carve-out, which only
        bites for an Annex III system — so profiling without an Annex III area is a
        meaningless combination, rejected rather than silently ignored.
        """
        if self.profiling_of_natural_persons and self.annex_iii_area is AnnexIIIArea.NONE:
            raise ValueError(
                "profiling_of_natural_persons is only valid when annex_iii_area is set "
                "(it is the Art 6(3) carve-out for an Annex III system)"
            )
        return self


class ClassificationSummary(BaseModel):
    """The current-verdict badge for the register list — no predicate_trace/facts."""

    model_config = ConfigDict(from_attributes=True)

    tier: str
    route: str
    ruleset_version: str
    draft_basis: bool
    verdict_hash: str
    created_at: datetime


class VerdictRead(BaseModel):
    """One risk classification (read projection) — the sealed, re-derivable verdict.

    The stored ``facts``/``facts_hash`` and the internal ``practice_area_id`` /
    ``source_project_id`` are NOT part of the read surface (the facts are the model's
    private input; the audit row already carries counts/types/IDs).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ai_system_id: uuid.UUID
    tier: str
    route: str
    article_refs: list[str]
    predicate_trace: list[dict[str, str]]
    ruleset_version: str
    verdict_hash: str
    draft_basis: bool
    created_at: datetime
