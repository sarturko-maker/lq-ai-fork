"""Assessment domain spine — PRIV-A1 (fork, ADR-F018).

Two layers, both proving the code-validated-write invariants (the ROPA PRIV-1
shape):

* **Schema invariants (pure, no DB)** — ``AssessmentInput`` / ``RiskInput`` are
  the contracts the PRIV-A2 write path validates a model proposal against, plus
  the pure ``validate_assessment_completable`` headline cross-row guard. Accept +
  reject cases for each ADR-F018 invariant, both directions.
* **DB defense-in-depth (integration)** — the CHECK constraints mirror the
  within-row invariants (incl. ``completed ⇒ risk_rating``), and the FK CASCADE
  drops a risk with its parent assessment. The test DB migrates to head
  (conftest), so 0064 is present.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, Risk
from app.models.project import Project
from app.models.user import User
from app.schemas.assessment import (
    AssessmentInput,
    AssessmentStatus,
    AssessmentType,
    RiskInput,
    RiskLevel,
    RiskStatus,
    validate_assessment_completable,
)
from tests.agents.test_agent_runs_api import _make_user


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": AssessmentType.DPIA,
        "title": "DPIA — new HR analytics platform",
        "summary": "Assessing the rollout of an HR analytics tool.",
        "status": AssessmentStatus.DRAFT,
        "risk_rating": None,
        "conditions": None,
    }
    base.update(overrides)
    return base


# --- AssessmentInput invariants (pure) ---------------------------------------


def test_minimal_assessment_passes() -> None:
    a = AssessmentInput(type=AssessmentType.PIA, title="Quick PIA")
    assert a.type is AssessmentType.PIA
    assert a.status is AssessmentStatus.DRAFT
    assert a.risk_rating is None
    assert a.summary is None and a.conditions is None


def test_full_completed_assessment_passes() -> None:
    a = AssessmentInput(
        **_valid_kwargs(
            status=AssessmentStatus.COMPLETED,
            risk_rating=RiskLevel.HIGH,
            conditions="DPO sign-off + review at 6 months",
        )
    )
    assert a.status is AssessmentStatus.COMPLETED
    assert a.risk_rating is RiskLevel.HIGH


def test_off_enum_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AssessmentInput(**_valid_kwargs(type="vendor_review"))


def test_off_enum_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AssessmentInput(**_valid_kwargs(status="archived"))


def test_off_enum_risk_rating_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AssessmentInput(**_valid_kwargs(risk_rating="critical"))


def test_blank_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AssessmentInput(**_valid_kwargs(title="   "))


def test_completed_without_rating_is_rejected() -> None:
    # Within-row half of the headline invariant: can't close an unrated assessment.
    with pytest.raises(ValidationError, match="risk_rating"):
        AssessmentInput(**_valid_kwargs(status=AssessmentStatus.COMPLETED, risk_rating=None))


def test_blank_optional_normalises_to_none() -> None:
    a = AssessmentInput(**_valid_kwargs(summary="   ", conditions="\t"))
    assert a.summary is None and a.conditions is None


def test_assessment_unknown_field_is_rejected() -> None:
    # extra="forbid": reject, don't sanitize (CLAUDE.md boundary rule).
    with pytest.raises(ValidationError):
        AssessmentInput(**_valid_kwargs(owner="DPO"))


# --- RiskInput invariants (pure) ---------------------------------------------


def test_minimal_risk_passes() -> None:
    r = RiskInput(description="Excessive data retention", likelihood="medium", impact="high")
    assert r.likelihood is RiskLevel.MEDIUM
    assert r.impact is RiskLevel.HIGH
    assert r.status is RiskStatus.OPEN
    assert r.mitigation is None and r.owner is None


def test_full_risk_passes() -> None:
    r = RiskInput(
        description="Profiling without a balancing test",
        likelihood="high",
        impact="high",
        mitigation="Document an LIA; add an opt-out.",
        owner="Privacy team",
        status="mitigated",
    )
    assert r.status is RiskStatus.MITIGATED
    assert r.owner == "Privacy team"


def test_off_enum_likelihood_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskInput(description="x", likelihood="severe", impact="low")


def test_off_enum_risk_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskInput(description="x", likelihood="low", impact="low", status="closed")


def test_risk_blank_description_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskInput(description="   ", likelihood="low", impact="low")


def test_risk_blank_optional_normalises_to_none() -> None:
    r = RiskInput(description="x", likelihood="low", impact="low", mitigation="   ")
    assert r.mitigation is None


def test_risk_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskInput(description="x", likelihood="low", impact="low", severity="bad")


# --- Headline cross-row invariant (validate_assessment_completable, pure) -----


def test_completable_noop_for_draft() -> None:
    # Not completed → no-op regardless of risks.
    validate_assessment_completable(
        assessment_type=AssessmentType.DPIA,
        risk_rating=None,
        status=AssessmentStatus.DRAFT,
        risk_mitigations=[],
    )


def test_completable_noop_for_low_risk_non_dpia() -> None:
    # Completed but neither a DPIA nor high-rated → no mitigation required.
    validate_assessment_completable(
        assessment_type=AssessmentType.LIA,
        risk_rating=RiskLevel.LOW,
        status=AssessmentStatus.COMPLETED,
        risk_mitigations=[],
    )


def test_completed_dpia_without_mitigation_is_rejected() -> None:
    # Headline invariant (forward): a completed DPIA needs a documented mitigation.
    with pytest.raises(ValueError, match="mitigation"):
        validate_assessment_completable(
            assessment_type=AssessmentType.DPIA,
            risk_rating=RiskLevel.MEDIUM,
            status=AssessmentStatus.COMPLETED,
            risk_mitigations=[None, "   "],
        )


def test_completed_high_risk_non_dpia_without_mitigation_is_rejected() -> None:
    # Headline invariant: high rating triggers it even for a non-DPIA type.
    with pytest.raises(ValueError, match="mitigation"):
        validate_assessment_completable(
            assessment_type=AssessmentType.PIA,
            risk_rating=RiskLevel.HIGH,
            status=AssessmentStatus.COMPLETED,
            risk_mitigations=[],
        )


def test_completed_dpia_with_mitigation_passes() -> None:
    # Headline invariant satisfied: one non-blank mitigation present.
    validate_assessment_completable(
        assessment_type=AssessmentType.DPIA,
        risk_rating=RiskLevel.HIGH,
        status=AssessmentStatus.COMPLETED,
        risk_mitigations=[None, "Add SCCs and an opt-out."],
    )


# --- DB defense-in-depth (integration) ---------------------------------------


async def _make_matter(db_session: AsyncSession, owner: User) -> Project:
    project = Project(
        owner_id=owner.id,
        name="Programme — GDPR",
        slug=f"priv-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(project)
    await db_session.flush()
    return project


@pytest.mark.integration
async def test_valid_assessment_row_persists(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="assess-valid")
    matter = await _make_matter(db_session, owner)
    row = Assessment(
        source_project_id=matter.id,
        type=AssessmentType.DPIA.value,
        title="DPIA — analytics rollout",
        status=AssessmentStatus.DRAFT.value,
    )
    db_session.add(row)
    await db_session.flush()
    assert row.id is not None
    # Server defaults applied.
    await db_session.refresh(row)
    assert row.status == "draft"
    assert row.created_at is not None and row.updated_at is not None


@pytest.mark.integration
async def test_db_check_rejects_completed_without_rating(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="assess-rating")
    matter = await _make_matter(db_session, owner)
    row = Assessment(
        source_project_id=matter.id,
        type=AssessmentType.DPIA.value,
        title="DPIA — no rating",
        status=AssessmentStatus.COMPLETED.value,
        risk_rating=None,  # violates chk_assessments_completed_requires_rating
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_db_check_rejects_off_enum_type(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="assess-enum")
    matter = await _make_matter(db_session, owner)
    row = Assessment(
        source_project_id=matter.id,
        type="vendor_review",  # off-enum → chk_assessments_type rejects
        title="Mystery assessment",
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def _make_assessment(db_session: AsyncSession, matter: Project) -> Assessment:
    assessment = Assessment(
        source_project_id=matter.id,
        type=AssessmentType.DPIA.value,
        title="DPIA — analytics rollout",
        status=AssessmentStatus.DRAFT.value,
    )
    db_session.add(assessment)
    await db_session.flush()
    return assessment


@pytest.mark.integration
async def test_valid_risk_row_persists(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="risk-valid")
    matter = await _make_matter(db_session, owner)
    assessment = await _make_assessment(db_session, matter)
    row = Risk(
        assessment_id=assessment.id,
        description="Excessive retention of analytics data",
        likelihood=RiskLevel.MEDIUM.value,
        impact=RiskLevel.HIGH.value,
        mitigation="Set a 13-month TTL.",
        status=RiskStatus.OPEN.value,
    )
    db_session.add(row)
    await db_session.flush()
    assert row.id is not None


@pytest.mark.integration
async def test_db_check_rejects_off_enum_risk_impact(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="risk-enum")
    matter = await _make_matter(db_session, owner)
    assessment = await _make_assessment(db_session, matter)
    row = Risk(
        assessment_id=assessment.id,
        description="x",
        likelihood=RiskLevel.LOW.value,
        impact="catastrophic",  # off-enum → chk_risks_impact rejects
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_deleting_assessment_cascades_to_risks(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="risk-cascade")
    matter = await _make_matter(db_session, owner)
    assessment = await _make_assessment(db_session, matter)
    db_session.add(
        Risk(
            assessment_id=assessment.id,
            description="A finding",
            likelihood=RiskLevel.LOW.value,
            impact=RiskLevel.LOW.value,
        )
    )
    await db_session.flush()
    assessment_id = assessment.id

    await db_session.delete(assessment)
    await db_session.flush()

    remaining = (
        (await db_session.execute(select(Risk).where(Risk.assessment_id == assessment_id)))
        .scalars()
        .all()
    )
    assert remaining == []
