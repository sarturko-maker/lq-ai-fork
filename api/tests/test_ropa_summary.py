"""Pure programme-summary aggregation — PRIV-6b.

Unit tests for :func:`app.ropa_summary.build_summary` over Read DTOs (no DB): the
endpoint test in ``test_ropa_read.py`` covers the live HTTP/auth path; here we
pin the aggregation arithmetic in isolation — totals, enum-ordered breakdowns
(including zero buckets), and the "needs attention" gaps.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app import ropa_summary
from app.schemas.ropa import (
    DataCategorySummary,
    DataSubjectCategorySummary,
    ProcessingActivityRead,
    SystemRead,
    SystemSummary,
    TransferSummary,
    VendorRead,
    VendorSummary,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _pa(
    *,
    lawful_basis: str = "consent",
    controller_role: str = "controller",
    special_category: bool = False,
    art9_condition: str | None = None,
    systems: bool = False,
    vendors: bool = False,
    transfers: tuple[bool, ...] = (),
    data_subjects: bool = False,
    data_categories: bool = False,
) -> ProcessingActivityRead:
    """A processing-activity Read DTO; bool flags toggle whether each link is present."""
    return ProcessingActivityRead(
        id=uuid.uuid4(),
        name="activity",
        purpose="p",
        lawful_basis=lawful_basis,
        controller_role=controller_role,
        retention="1 year",
        special_category=special_category,
        art9_condition=art9_condition,
        created_at=_NOW,
        updated_at=_NOW,
        systems=(
            [SystemSummary(id=uuid.uuid4(), name="s", system_type="database")] if systems else []
        ),
        vendors=(
            [VendorSummary(id=uuid.uuid4(), name="v", vendor_role="processor")] if vendors else []
        ),
        transfers=[
            TransferSummary(
                id=uuid.uuid4(),
                destination="US",
                restricted=r,
                mechanism=None,
                details=None,
                vendor=None,
            )
            for r in transfers
        ],
        data_subject_categories=(
            [DataSubjectCategorySummary(id=uuid.uuid4(), name="d")] if data_subjects else []
        ),
        data_categories=(
            [DataCategorySummary(id=uuid.uuid4(), name="d")] if data_categories else []
        ),
    )


def _sys(*, ai_usage: bool = False) -> SystemRead:
    return SystemRead(
        id=uuid.uuid4(),
        name="system",
        system_type="database",
        description=None,
        owner=None,
        hosting_location=None,
        retention=None,
        security_measures=None,
        ai_usage=ai_usage,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _vendor(*, dpa_status: str) -> VendorRead:
    return VendorRead(
        id=uuid.uuid4(),
        name="vendor",
        vendor_role="processor",
        description=None,
        country=None,
        dpa_status=dpa_status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _as_dict(buckets: list) -> dict[str, int]:
    return {b.value: b.count for b in buckets}


def test_empty_register_is_all_zeros() -> None:
    s = ropa_summary.build_summary([], [], [])
    assert s.activities_total == 0
    assert s.systems_total == 0
    assert s.vendors_total == 0
    assert s.transfers_total == 0
    assert s.transfers_restricted == 0
    assert s.special_category_activities == 0
    assert s.systems_using_ai == 0
    # Breakdowns still carry every canonical bucket, all at zero.
    assert len(s.lawful_basis) == 6
    assert len(s.controller_role) == 3
    assert len(s.dpa_status) == 4
    assert all(b.count == 0 for b in s.lawful_basis + s.controller_role + s.dpa_status)
    assert s.gaps.activities_without_systems == 0
    assert s.gaps.activities_without_recipients == 0
    assert s.gaps.activities_without_data_categories == 0
    assert s.gaps.activities_without_data_subjects == 0
    assert s.gaps.vendors_without_dpa == 0


def test_breakdowns_are_canonical_enum_order() -> None:
    s = ropa_summary.build_summary([], [], [])
    assert [b.value for b in s.lawful_basis] == [
        "consent",
        "contract",
        "legal_obligation",
        "vital_interests",
        "public_task",
        "legitimate_interests",
    ]
    assert [b.value for b in s.controller_role] == ["controller", "joint_controller", "processor"]
    assert [b.value for b in s.dpa_status] == ["in_place", "pending", "not_required", "none"]


def test_aggregates_totals_breakdowns_and_gaps() -> None:
    activities = [
        # Fully linked, two transfers (one restricted).
        _pa(
            lawful_basis="consent",
            controller_role="controller",
            systems=True,
            vendors=True,
            transfers=(True, False),
            data_subjects=True,
            data_categories=True,
        ),
        # Special-category, processor, with NOTHING linked → fires every gap.
        _pa(
            lawful_basis="legal_obligation",
            controller_role="processor",
            special_category=True,
            art9_condition="explicit_consent",
        ),
    ]
    systems = [_sys(ai_usage=False), _sys(ai_usage=True)]
    vendors = [
        _vendor(dpa_status="in_place"),
        _vendor(dpa_status="pending"),
        _vendor(dpa_status="none"),
    ]

    s = ropa_summary.build_summary(activities, systems, vendors)

    assert s.activities_total == 2
    assert s.systems_total == 2
    assert s.vendors_total == 3
    assert s.transfers_total == 2
    assert s.transfers_restricted == 1
    assert s.special_category_activities == 1
    assert s.systems_using_ai == 1

    assert _as_dict(s.lawful_basis) == {
        "consent": 1,
        "contract": 0,
        "legal_obligation": 1,
        "vital_interests": 0,
        "public_task": 0,
        "legitimate_interests": 0,
    }
    assert _as_dict(s.controller_role) == {"controller": 1, "joint_controller": 0, "processor": 1}
    assert _as_dict(s.dpa_status) == {"in_place": 1, "pending": 1, "not_required": 0, "none": 1}

    # Only the second (unlinked) activity is missing each axis.
    assert s.gaps.activities_without_systems == 1
    assert s.gaps.activities_without_recipients == 1
    assert s.gaps.activities_without_data_categories == 1
    assert s.gaps.activities_without_data_subjects == 1
    # pending + none are outstanding; in_place is settled.
    assert s.gaps.vendors_without_dpa == 2
