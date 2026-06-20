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
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.ropa import (
    DataCategory,
    DataSubjectCategory,
    ProcessingActivity,
    Transfer,
    Vendor,
)
from app.models.user import User
from app.schemas.ropa import (
    Art9Condition,
    ControllerRole,
    DataCategoryInput,
    DataSubjectCategoryInput,
    DpaStatus,
    LawfulBasis,
    ProcessingActivityInput,
    SystemInput,
    SystemType,
    TransferInput,
    TransferMechanism,
    VendorInput,
    VendorRole,
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


# --- VendorInput invariants (PRIV-5a, pure) ----------------------------------


def test_minimal_vendor_passes() -> None:
    v = VendorInput(name="Acme Payroll Ltd", vendor_role="processor", dpa_status="in_place")
    assert v.vendor_role is VendorRole.PROCESSOR
    assert v.dpa_status is DpaStatus.IN_PLACE
    assert v.description is None and v.country is None


def test_full_vendor_passes() -> None:
    v = VendorInput(
        name="SubCo Analytics",
        vendor_role="sub_processor",
        dpa_status="pending",
        description="Provides analytics on behalf of our processor",
        country="United States",
    )
    assert v.vendor_role is VendorRole.SUB_PROCESSOR
    assert v.country == "United States"


def test_off_enum_vendor_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VendorInput(name="X", vendor_role="overlord", dpa_status="none")


def test_off_enum_dpa_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VendorInput(name="X", vendor_role="processor", dpa_status="maybe")


def test_vendor_blank_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VendorInput(name="   ", vendor_role="recipient", dpa_status="not_required")


def test_vendor_blank_optional_normalises_to_none() -> None:
    v = VendorInput(name="Acme", vendor_role="processor", dpa_status="in_place", country="   ")
    assert v.country is None


def test_vendor_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VendorInput(name="X", vendor_role="processor", dpa_status="none", risk_level="high")


# --- TransferInput invariants (PRIV-5b, pure) --------------------------------


def test_unrestricted_transfer_without_mechanism_passes() -> None:
    t = TransferInput(destination="Germany")
    assert t.restricted is False
    assert t.mechanism is None


def test_restricted_transfer_with_mechanism_passes() -> None:
    t = TransferInput(
        destination="United States",
        restricted=True,
        mechanism="standard_contractual_clauses",
        details="EU SCCs module 2 + UK Addendum",
    )
    assert t.restricted is True
    assert t.mechanism is TransferMechanism.STANDARD_CONTRACTUAL_CLAUSES


def test_restricted_transfer_without_mechanism_is_rejected() -> None:
    # Invariant (forward): a restricted transfer needs a Chapter V safeguard.
    with pytest.raises(ValidationError, match="mechanism"):
        TransferInput(destination="India", restricted=True, mechanism=None)


def test_mechanism_on_unrestricted_transfer_is_rejected() -> None:
    # Invariant (reverse): a mechanism on an intra-UK/EEA transfer is incoherent.
    with pytest.raises(ValidationError, match="restricted"):
        TransferInput(
            destination="France", restricted=False, mechanism="standard_contractual_clauses"
        )


def test_off_enum_transfer_mechanism_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TransferInput(destination="US", restricted=True, mechanism="vibes")


def test_blank_transfer_destination_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TransferInput(destination="   ")


def test_transfer_blank_details_normalises_to_none() -> None:
    t = TransferInput(destination="Germany", details="   ")
    assert t.details is None


def test_transfer_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TransferInput(destination="US", restricted=True, mechanism="uk_idta", country="US")


# --- DataSubjectCategoryInput / DataCategoryInput invariants (PRIV-6a, pure) --


def test_minimal_data_subject_category_passes() -> None:
    c = DataSubjectCategoryInput(name="Employees")
    assert c.name == "Employees"


def test_data_subject_category_blank_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DataSubjectCategoryInput(name="   ")


def test_data_subject_category_too_long_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DataSubjectCategoryInput(name="x" * 201)


def test_data_subject_category_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DataSubjectCategoryInput(name="Employees", description="people")


def test_data_subject_category_collapses_internal_whitespace() -> None:
    # Spacing variants converge so the controlled vocabulary stays a vocabulary.
    assert DataSubjectCategoryInput(name="Job   applicants").name == "Job applicants"
    assert DataCategoryInput(name="  Health\tdata  ").name == "Health data"


def test_minimal_data_category_passes() -> None:
    c = DataCategoryInput(name="Health data")
    assert c.name == "Health data"


def test_data_category_blank_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DataCategoryInput(name="")


def test_data_category_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DataCategoryInput(name="Health data", sensitivity="high")


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


@pytest.mark.integration
async def test_valid_vendor_row_persists(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="vendor-valid")
    matter = await _make_matter(db_session, owner)
    row = Vendor(
        source_project_id=matter.id,
        name="Acme Payroll Ltd",
        vendor_role=VendorRole.PROCESSOR.value,
        dpa_status=DpaStatus.IN_PLACE.value,
        country="UK",
    )
    db_session.add(row)
    await db_session.flush()
    assert row.id is not None


@pytest.mark.integration
async def test_db_check_rejects_off_enum_vendor_role(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="vendor-enum")
    matter = await _make_matter(db_session, owner)
    row = Vendor(
        source_project_id=matter.id,
        name="Mystery vendor",
        vendor_role="overlord",  # off-enum → chk_vendors_vendor_role rejects
        dpa_status=DpaStatus.NONE.value,
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def _make_activity(db_session: AsyncSession, matter: Project) -> ProcessingActivity:
    activity = ProcessingActivity(
        source_project_id=matter.id,
        name="Marketing analytics",
        purpose="Analyse campaign performance.",
        lawful_basis=LawfulBasis.LEGITIMATE_INTERESTS.value,
        controller_role=ControllerRole.CONTROLLER.value,
        retention="2 years",
        special_category=False,
        art9_condition=None,
    )
    db_session.add(activity)
    await db_session.flush()
    return activity


@pytest.mark.integration
async def test_valid_restricted_transfer_row_persists(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="transfer-valid")
    matter = await _make_matter(db_session, owner)
    activity = await _make_activity(db_session, matter)
    row = Transfer(
        source_project_id=matter.id,
        processing_activity_id=activity.id,
        destination="United States",
        restricted=True,
        mechanism=TransferMechanism.STANDARD_CONTRACTUAL_CLAUSES.value,
    )
    db_session.add(row)
    await db_session.flush()
    assert row.id is not None


@pytest.mark.integration
async def test_db_check_rejects_restricted_transfer_without_mechanism(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session, suffix="transfer-check")
    matter = await _make_matter(db_session, owner)
    activity = await _make_activity(db_session, matter)
    row = Transfer(
        source_project_id=matter.id,
        processing_activity_id=activity.id,
        destination="India",
        restricted=True,
        mechanism=None,  # violates chk_transfers_restricted_requires_mechanism
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_db_check_rejects_mechanism_on_unrestricted_transfer(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session, suffix="transfer-rev")
    matter = await _make_matter(db_session, owner)
    activity = await _make_activity(db_session, matter)
    row = Transfer(
        source_project_id=matter.id,
        processing_activity_id=activity.id,
        destination="France",
        restricted=False,
        mechanism=TransferMechanism.UK_IDTA.value,  # incoherent → CHECK rejects
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_valid_data_subject_category_row_persists(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, suffix="dsc-valid")
    matter = await _make_matter(db_session, owner)
    row = DataSubjectCategory(source_project_id=matter.id, name="Employees")
    db_session.add(row)
    await db_session.flush()
    assert row.id is not None


@pytest.mark.integration
async def test_db_unique_rejects_duplicate_data_subject_category_name(
    db_session: AsyncSession,
) -> None:
    # The controlled-vocabulary uniqueness backstop (uq_data_subject_categories_name).
    db_session.add(DataSubjectCategory(name="Customers"))
    await db_session.flush()
    db_session.add(DataSubjectCategory(name="Customers"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_db_unique_rejects_case_variant_data_subject_category_name(
    db_session: AsyncSession,
) -> None:
    # Uniqueness is on lower(name) (PRIV-6a) — a case variant is rejected at the DB
    # boundary, not just by the case-insensitive find in the write tool.
    db_session.add(DataSubjectCategory(name="Customers"))
    await db_session.flush()
    db_session.add(DataSubjectCategory(name="customers"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_db_check_rejects_blank_data_category_name(db_session: AsyncSession) -> None:
    row = DataCategory(name="")  # violates chk_data_categories_name_len
    db_session.add(row)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_db_unique_rejects_duplicate_data_category_name(db_session: AsyncSession) -> None:
    db_session.add(DataCategory(name="Health data"))
    await db_session.flush()
    db_session.add(DataCategory(name="Health data"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# --- Link-table reverse-FK index parity (PRIV-1 review fix, migration 0065) ----


@pytest.mark.integration
async def test_every_privacy_link_table_has_a_reverse_fk_index(
    db_session: AsyncSession,
) -> None:
    """Every M:N link table indexes its TRAILING composite-PK / FK column.

    A composite PK indexes only its leading column, so the reverse lookup
    (system/vendor/category/activity -> activities/assessments, via
    ``selectinload``) seq-scans without a standalone index. 0059/0060 added this
    reverse index; 0062 (taxonomy) and 0064 (assessments) missed it; 0065 closes
    the gap. This pins the parity so the precedent PRIV-A mirrors cannot regress.
    """
    expected = {
        "ix_processing_activity_systems_system_id",  # 0059
        "ix_processing_activity_vendors_vendor_id",  # 0060
        "ix_pa_dsc_data_subject_category_id",  # 0065 (was missing in 0062)
        "ix_pa_dc_data_category_id",  # 0065 (was missing in 0062)
        "ix_apa_processing_activity_id",  # 0065 (was missing in 0064)
    }
    present = set(
        (
            await db_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE indexname = ANY(:names)").bindparams(
                    names=list(expected)
                )
            )
        )
        .scalars()
        .all()
    )
    assert expected == present, f"missing reverse-FK indexes: {expected - present}"
