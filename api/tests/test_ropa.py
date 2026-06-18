"""ROPA domain spine — PRIV-1 (fork, ADR-F018).

Two layers, both proving the code-validated-write invariants:

* **Schema invariants (pure, no DB)** — ``ProcessingActivityInput`` is the
  contract the PRIV-2 write path validates a model proposal against. Accept +
  reject cases for each ADR-F018 invariant.
* **DB defense-in-depth (integration)** — the CHECK constraints mirror the same
  invariants, so an inconsistent row is refused even if a caller bypasses the
  schema. The test DB migrates to head (conftest), so 0058 is present.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.ropa import ProcessingActivity
from app.models.user import User
from app.schemas.ropa import (
    Art9Condition,
    ControllerRole,
    LawfulBasis,
    ProcessingActivityInput,
    SystemInput,
    SystemType,
)
from tests.agents.test_agent_runs_api import _make_user


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Payroll processing",
        "purpose": "Run monthly payroll for employees.",
        "lawful_basis": LawfulBasis.CONTRACT,
        "controller_role": ControllerRole.CONTROLLER,
        "retention": "7 years after end of employment",
        "special_category": False,
        "art9_condition": None,
    }
    base.update(overrides)
    return base


# --- Schema invariants (pure) ------------------------------------------------


def test_valid_ordinary_activity_passes() -> None:
    pa = ProcessingActivityInput(**_valid_kwargs())
    assert pa.lawful_basis is LawfulBasis.CONTRACT
    assert pa.art9_condition is None


def test_valid_special_category_with_art9_passes() -> None:
    pa = ProcessingActivityInput(
        **_valid_kwargs(
            name="Occupational health records",
            special_category=True,
            art9_condition=Art9Condition.HEALTH_OR_SOCIAL_CARE,
        )
    )
    assert pa.special_category is True
    assert pa.art9_condition is Art9Condition.HEALTH_OR_SOCIAL_CARE


def test_off_enum_lawful_basis_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProcessingActivityInput(**_valid_kwargs(lawful_basis="best_interests"))


def test_blank_retention_is_rejected() -> None:
    # Invariant 2: retention required. Whitespace is stripped to "" → min_length.
    with pytest.raises(ValidationError):
        ProcessingActivityInput(**_valid_kwargs(retention="   "))


def test_missing_retention_is_rejected() -> None:
    kwargs = _valid_kwargs()
    del kwargs["retention"]
    with pytest.raises(ValidationError):
        ProcessingActivityInput(**kwargs)


def test_special_category_without_art9_is_rejected() -> None:
    # Invariant 3 (forward): special data needs an Article 9(2) condition.
    with pytest.raises(ValidationError, match="Article 9"):
        ProcessingActivityInput(**_valid_kwargs(special_category=True, art9_condition=None))


def test_art9_without_special_category_is_rejected() -> None:
    # Invariant 3 (reverse): an Article 9 condition on ordinary data is incoherent.
    with pytest.raises(ValidationError, match="special_category"):
        ProcessingActivityInput(
            **_valid_kwargs(special_category=False, art9_condition=Art9Condition.EXPLICIT_CONSENT)
        )


def test_unknown_field_is_rejected() -> None:
    # extra="forbid": reject, don't sanitize (CLAUDE.md boundary rule).
    with pytest.raises(ValidationError):
        ProcessingActivityInput(**_valid_kwargs(categories_of_data="employees"))


# --- SystemInput invariants (PRIV-3, pure) -----------------------------------


def test_minimal_system_passes() -> None:
    s = SystemInput(name="Production database", system_type=SystemType.DATABASE)
    assert s.system_type is SystemType.DATABASE
    # Optional fields default to None.
    assert s.description is None and s.owner is None and s.ai_usage is False


def test_full_system_passes() -> None:
    s = SystemInput(
        name="Salesforce",
        system_type="crm",
        description="CRM of record",
        owner="RevOps",
        hosting_location="EU (Frankfurt)",
        retention="Life of account + 2 years",
        security_measures="SSO, field-level encryption",
        ai_usage=True,
    )
    assert s.system_type is SystemType.CRM
    assert s.ai_usage is True


def test_off_enum_system_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SystemInput(name="Mystery", system_type="quantum_orb")


def test_blank_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SystemInput(name="   ", system_type=SystemType.OTHER)


def test_blank_optional_normalises_to_none() -> None:
    s = SystemInput(name="Logs", system_type=SystemType.LOGS, owner="   ")
    assert s.owner is None


def test_system_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SystemInput(name="X", system_type=SystemType.OTHER, vendor="Acme")


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
async def test_valid_row_persists(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="ropa-valid")
    matter = await _make_matter(db_session, owner)
    row = ProcessingActivity(
        source_project_id=matter.id,
        name="Payroll processing",
        purpose="Run monthly payroll.",
        lawful_basis=LawfulBasis.CONTRACT.value,
        controller_role=ControllerRole.CONTROLLER.value,
        retention="7 years after end of employment",
        special_category=False,
        art9_condition=None,
    )
    db_session.add(row)
    await db_session.flush()
    assert row.id is not None


@pytest.mark.integration
async def test_db_check_rejects_special_without_art9(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="ropa-check")
    matter = await _make_matter(db_session, owner)
    row = ProcessingActivity(
        source_project_id=matter.id,
        name="Health records",
        purpose="Store occupational health data.",
        lawful_basis=LawfulBasis.LEGAL_OBLIGATION.value,
        controller_role=ControllerRole.CONTROLLER.value,
        retention="while employed",
        special_category=True,
        art9_condition=None,  # violates chk_processing_activities_art9_requires_special
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_db_check_rejects_off_enum_lawful_basis(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="ropa-enum")
    matter = await _make_matter(db_session, owner)
    row = ProcessingActivity(
        source_project_id=matter.id,
        name="Marketing",
        purpose="Send marketing emails.",
        lawful_basis="best_interests",  # off-enum → CHECK rejects
        controller_role=ControllerRole.CONTROLLER.value,
        retention="until consent withdrawn",
        special_category=False,
        art9_condition=None,
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
