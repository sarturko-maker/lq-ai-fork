"""Assessment domain schema — PRIV-A1 (fork, ADR-F018, ADR-F027).

The **validation contract** for the Privacy module's assessment track — PIA /
DPIA / LIA / TIA records and the risk findings within them. This is the
assessment analogue of ``app.schemas.ropa``: the single source of truth for what
a valid assessment (and risk) is, and the code invariants the ADR-F018 write
path (PRIV-A2) validates a model proposal against BEFORE commit (agent proposes →
code disposes → commit or reject-and-retry; never a silent write or a silent
fix).

Two layers carry the invariants, exactly as the ROPA spine does:

1. **Within-row invariants** live as Pydantic field constraints + a
   ``model_validator`` on :class:`AssessmentInput`, mirrored by DB CHECK
   constraints in ``app.models.assessment`` (defense-in-depth). The within-row
   piece of the headline rule is *a completed assessment must carry a
   risk_rating* — you cannot close an assessment you have not rated.
2. **The headline cross-row invariant** — *a DPIA (or any ``high``-rated)
   assessment cannot be ``completed`` unless it has at least one risk with a
   non-blank mitigation* — is a relation between an assessment and its risk rows,
   so it is NOT expressible as a single-row CHECK (it would need a DB trigger,
   which we deliberately do not add — the same way ROPA enforces its cross-row
   link rules in the app layer). It lives in the pure
   :func:`validate_assessment_completable` guard, which the PRIV-A2 write path
   calls with the assessment's proposed state and its risks' mitigations.

This is the assessment-track analogue of ROPA's ``special_category ⇔
art9_condition`` / ``restricted ⇔ mechanism`` invariants: one clean, enforced
rule that captures the accountability point — *you can't sign off a high-risk
assessment with no documented mitigation.*
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssessmentType(StrEnum):
    """The kind of privacy assessment.

    ``pia`` (privacy impact assessment), ``dpia`` (Article 35 data-protection
    impact assessment), ``lia`` (legitimate-interests assessment, Article 6(1)(f)
    balancing test), ``tia`` (transfer impact assessment, Chapter V). Extensible
    to ``ai_risk`` once the spine exists (plan § Non-goals). The SQL CHECK in
    ``app.models.assessment`` mirrors this set.
    """

    PIA = "pia"
    DPIA = "dpia"
    LIA = "lia"
    TIA = "tia"


class AssessmentStatus(StrEnum):
    """Lifecycle state of an assessment."""

    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class RiskLevel(StrEnum):
    """A low / medium / high band.

    One enum reused for the three places the domain uses this scale: an
    assessment's overall ``risk_rating`` and a risk finding's ``likelihood`` and
    ``impact``. The SQL CHECKs in ``app.models.assessment`` mirror this set.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskStatus(StrEnum):
    """Disposition of a risk finding."""

    OPEN = "open"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"


class AssessmentInput(BaseModel):
    """A proposed assessment — the validated write contract (ADR-F018).

    Only ``type`` and ``title`` are required — an assessment is useful the moment
    it is named and typed (mirrors :class:`app.schemas.ropa.SystemInput`); the
    rating, summary and conditions fill in as the assessment progresses. Reject,
    don't sanitize (CLAUDE.md): an out-of-enum type/status/rating, or a
    ``completed`` assessment with no ``risk_rating``, is a hard validation error
    surfaced verbatim to whoever (PRIV-2: the agent) proposed it. Blank optional
    fields normalise to ``None`` so the record stores absence as NULL, not "".
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: AssessmentType
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    status: AssessmentStatus = AssessmentStatus.DRAFT
    # Nullable until assessed; required once the assessment is completed (the
    # within-row half of the headline invariant — see below + the DB CHECK).
    risk_rating: RiskLevel | None = None
    # Required mitigations/conditions before the processing may proceed
    # (free text; e.g. "DPO sign-off + DPIA review at 6 months"). Nullable.
    conditions: str | None = Field(default=None, max_length=5000)

    @field_validator("summary", "conditions")
    @classmethod
    def _blank_optional_to_none(cls, v: str | None) -> str | None:
        # str_strip_whitespace already trimmed; a whitespace-only optional should
        # mean "not provided", not an empty string in the record.
        if v is not None and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _completed_requires_rating(self) -> AssessmentInput:
        """Within-row half of the headline invariant: completed ⇒ risk_rating set.

        You cannot close an assessment you have not rated. The cross-row half
        (completed high-risk/DPIA ⇒ a documented mitigation) lives in
        :func:`validate_assessment_completable`, which needs the risk rows.
        """
        if self.status is AssessmentStatus.COMPLETED and self.risk_rating is None:
            raise ValueError("a completed assessment must carry a risk_rating")
        return self


class RiskInput(BaseModel):
    """A proposed risk finding within an assessment — the validated write contract.

    A risk has no meaning without its parent assessment (the relational id is
    resolved against the register by the agent write tool, like ROPA's links), so
    this contract carries only the finding's own content. ``description``,
    ``likelihood`` and ``impact`` are required — a finding is only useful once it
    says what the risk is and scores it; ``mitigation`` and ``owner`` fill in.
    Reject, don't sanitize; blank optional fields normalise to ``None``.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=2000)
    likelihood: RiskLevel
    impact: RiskLevel
    mitigation: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=200)
    status: RiskStatus = RiskStatus.OPEN

    @field_validator("mitigation", "owner")
    @classmethod
    def _blank_optional_to_none(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v


def validate_assessment_completable(
    *,
    assessment_type: AssessmentType,
    risk_rating: RiskLevel | None,
    status: AssessmentStatus,
    risk_mitigations: Sequence[str | None],
) -> None:
    """Headline ADR-F018/F027 cross-row invariant for the assessment track.

    *A DPIA, or any assessment rated ``high``, cannot be ``completed`` unless it
    has at least one risk carrying a non-blank mitigation.* This is the
    accountability rule — you can't sign off a high-risk assessment with no
    documented mitigation — and the assessment-track analogue of ROPA's
    ``special_category ⇔ art9_condition``.

    It is a relation between an assessment and its risk rows, so it cannot be a
    single-row DB CHECK (a trigger would be needed; we deliberately do not add
    one, mirroring how ROPA keeps cross-row rules in the app layer). The PRIV-A2
    write path calls this with the proposed assessment state and the mitigations
    of its linked risks; a violation is rejected back to the agent verbatim.

    No-ops unless the assessment is being completed AND is high-risk (a DPIA, or
    rated ``high``) — a draft, or a completed low/medium non-DPIA, is unaffected.
    Raises ``ValueError`` on violation.
    """
    if status is not AssessmentStatus.COMPLETED:
        return
    high_risk = assessment_type is AssessmentType.DPIA or risk_rating is RiskLevel.HIGH
    if not high_risk:
        return
    if not any(m is not None and m.strip() for m in risk_mitigations):
        raise ValueError(
            "a completed DPIA or high-risk assessment requires at least one risk with a "
            "documented (non-blank) mitigation"
        )
