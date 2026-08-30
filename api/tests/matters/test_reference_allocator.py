"""The counter-backed allocator — INTAKE-4a (ADR-F088).

The transactional half of ``app.matters.reference``: what the row lock buys and
what a matter with no practice area gets. The concurrency test deliberately uses
two REAL connections that commit — a savepoint-isolated session cannot exercise
``SELECT … FOR UPDATE`` against itself — and cleans its own rows up afterwards.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.matters.reference import (
    GENERIC_AREA_CODE,
    allocate_reference,
    assign_area_code,
    is_valid_reference,
    next_counter_value,
)
from app.models.organization_profile import OrganizationProfile
from app.models.practice_area import PracticeArea
from app.models.project import MatterReferenceCounter

pytestmark = pytest.mark.integration


def _number(reference: str) -> int:
    return int(reference.rsplit("-", 1)[1])


def _area_code(reference: str) -> str:
    return reference.split("-")[1]


@pytest_asyncio.fixture
async def area(db_session: AsyncSession) -> PracticeArea:
    row = PracticeArea(
        key=f"area-{uuid.uuid4().hex[:8]}",
        name="Zeta allocator area",
        unit_label="Matter",
        position=0,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def test_allocates_a_well_formed_reference(
    db_session: AsyncSession, area: PracticeArea
) -> None:
    reference = await allocate_reference(db_session, practice_area_id=area.id)
    assert is_valid_reference(reference)
    assert _area_code(reference) == "ZET"
    assert _number(reference) >= 1


async def test_consecutive_allocations_in_one_transaction_do_not_repeat(
    db_session: AsyncSession, area: PracticeArea
) -> None:
    first = await allocate_reference(db_session, practice_area_id=area.id)
    second = await allocate_reference(db_session, practice_area_id=area.id)
    assert _number(second) == _number(first) + 1


async def test_area_without_a_code_gets_one_assigned_once(
    db_session: AsyncSession, area: PracticeArea
) -> None:
    assert area.area_code is None
    code = await assign_area_code(db_session, area_id=area.id)
    assert code == "ZET"
    # Idempotent: a second call returns the persisted value, not a new derivation.
    assert await assign_area_code(db_session, area_id=area.id) == "ZET"
    refreshed = await db_session.get(PracticeArea, area.id)
    assert refreshed is not None
    assert refreshed.area_code == "ZET"


async def test_colliding_derived_codes_are_uniquified(db_session: AsyncSession) -> None:
    first = PracticeArea(
        key=f"a-{uuid.uuid4().hex[:8]}", name="Yankee one", unit_label="Matter", position=0
    )
    second = PracticeArea(
        key=f"b-{uuid.uuid4().hex[:8]}", name="Yankee two", unit_label="Matter", position=1
    )
    db_session.add_all([first, second])
    await db_session.flush()

    assert await assign_area_code(db_session, area_id=first.id) == "YAN"
    assert await assign_area_code(db_session, area_id=second.id) == "YAN2"


async def test_matter_with_no_practice_area_uses_the_generic_code(
    db_session: AsyncSession,
) -> None:
    reference = await allocate_reference(db_session, practice_area_id=None)
    assert _area_code(reference) == GENERIC_AREA_CODE


async def test_org_code_comes_from_the_organization_profile(
    db_session: AsyncSession, area: PracticeArea
) -> None:
    # The table is a singleton (partial unique index on ((true))) — update the row
    # if a committed one already exists rather than racing the constraint.
    existing = (await db_session.execute(select(OrganizationProfile).limit(1))).scalar_one_or_none()
    if existing is None:
        db_session.add(OrganizationProfile(content_md="", org_code="NWT"))
    else:
        existing.org_code = "NWT"
    await db_session.flush()
    reference = await allocate_reference(db_session, practice_area_id=area.id)
    assert reference.startswith("NWT-ZET-")


async def test_unknown_area_id_falls_back_to_the_generic_code(
    db_session: AsyncSession,
) -> None:
    reference = await allocate_reference(db_session, practice_area_id=uuid.uuid4())
    assert _area_code(reference) == GENERIC_AREA_CODE


async def test_two_concurrent_allocations_are_serialised(test_engine: AsyncEngine) -> None:
    """Two transactions racing on the SAME area code get consecutive numbers.

    Real connections, real ``COMMIT``s: the second allocator blocks on the first's
    row lock rather than reading the same ``next_value``. A test-local code keeps
    the series away from every other test's counters.
    """

    code = f"Z{uuid.uuid4().hex[:2].upper()}"

    async def allocate() -> int:
        async with AsyncSession(bind=test_engine, expire_on_commit=False) as session:
            value = await next_counter_value(session, area_code=code)
            # Hold the lock briefly so the sibling task is genuinely waiting on it.
            await asyncio.sleep(0.05)
            await session.commit()
            return value

    try:
        first, second = await asyncio.gather(allocate(), allocate())
        assert {first, second} == {1, 2}

        async with AsyncSession(bind=test_engine, expire_on_commit=False) as session:
            remaining = await session.scalar(
                select(MatterReferenceCounter.next_value).where(
                    MatterReferenceCounter.area_code == code
                )
            )
        assert remaining == 3
    finally:
        async with AsyncSession(bind=test_engine, expire_on_commit=False) as session:
            await session.execute(
                delete(MatterReferenceCounter).where(MatterReferenceCounter.area_code == code)
            )
            await session.commit()
