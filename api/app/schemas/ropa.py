"""ROPA domain schema — PRIV-1 (fork, ADR-F018).

The **validation contract** for the Privacy module's typed domain. This module
is the single source of truth for what a valid Records-of-Processing-Activities
entry is — the code invariants the ADR-F018 write path enforces:

1. ``lawful_basis`` is one of the six Article 6(1) GDPR bases (enum).
2. ``retention`` is required and non-empty (a ROPA entry must state how long
   the data is kept — Article 30(1)(f)).
3. ``special_category`` ⇒ ``art9_condition`` present (Article 9 processing
   needs an Article 9(2) condition); conversely a non-special record must not
   carry one (an Article 9 condition on non-special data is incoherent).

``ProcessingActivityInput`` is what PRIV-2's guarded write tool validates a
model proposal against **before** commit: a proposal that fails is rejected back
to the agent with the validation error (agent proposes → code disposes → commit
or reject-and-retry; never a silent write or a silent fix — ADR-F018). The ORM
model (``app.models.ropa.ProcessingActivity``) carries the same invariants as DB
CHECK constraints (defense-in-depth).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LawfulBasis(StrEnum):
    """Article 6(1) GDPR lawful bases for processing."""

    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTERESTS = "legitimate_interests"


class Art9Condition(StrEnum):
    """Article 9(2)(a)-(j) conditions for processing special-category data."""

    EXPLICIT_CONSENT = "explicit_consent"
    EMPLOYMENT_SOCIAL_SECURITY = "employment_social_security"
    VITAL_INTERESTS = "vital_interests"
    NOT_FOR_PROFIT_BODY = "not_for_profit_body"
    MADE_PUBLIC_BY_DATA_SUBJECT = "made_public_by_data_subject"
    LEGAL_CLAIMS = "legal_claims"
    SUBSTANTIAL_PUBLIC_INTEREST = "substantial_public_interest"
    HEALTH_OR_SOCIAL_CARE = "health_or_social_care"
    PUBLIC_HEALTH = "public_health"
    ARCHIVING_RESEARCH_STATISTICS = "archiving_research_statistics"


class ControllerRole(StrEnum):
    """The data-protection role the operator plays for this activity."""

    CONTROLLER = "controller"
    JOINT_CONTROLLER = "joint_controller"
    PROCESSOR = "processor"


class ProcessingActivityInput(BaseModel):
    """A proposed ROPA entry — the validated write contract (ADR-F018).

    Reject, don't sanitize (CLAUDE.md): an out-of-enum basis, an empty
    retention, or a special-category entry without an Article 9(2) condition is
    a hard validation error, surfaced verbatim to whoever (PRIV-2: the agent)
    proposed it.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=2000)
    lawful_basis: LawfulBasis
    controller_role: ControllerRole
    # Article 30(1)(f): the envisaged time limits for erasure. Free text (e.g.
    # "7 years after contract end") but REQUIRED — invariant 2.
    retention: str = Field(min_length=1, max_length=1000)
    special_category: bool = False
    art9_condition: Art9Condition | None = None

    @field_validator("retention")
    @classmethod
    def _retention_not_blank(cls, v: str) -> str:
        # str_strip_whitespace already trimmed; an all-whitespace value would
        # have become "" and tripped min_length, but guard explicitly so the
        # invariant reads at the seam it governs.
        if not v.strip():
            raise ValueError("retention is required and must not be blank")
        return v

    @model_validator(mode="after")
    def _special_category_requires_art9(self) -> ProcessingActivityInput:
        """Invariant 3: special-category ⇔ Article 9(2) condition present.

        Both directions: special data needs a condition; non-special data must
        not assert one (an Article 9 condition on ordinary data is incoherent
        and would mislead the ROPA).
        """
        if self.special_category and self.art9_condition is None:
            raise ValueError(
                "special-category processing requires an Article 9(2) condition (art9_condition)"
            )
        if not self.special_category and self.art9_condition is not None:
            raise ValueError("art9_condition must be set only when special_category is true")
        return self
