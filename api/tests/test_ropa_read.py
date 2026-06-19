"""ROPA register read API — PRIV-3 (fork, ADR-F019).

The deployment-global register read surface (Systems ↔ Processing Activities).
These run inside the per-test rolled-back ``db_session`` (the endpoint reads
through the same overridden session), so seeded rows are visible to the handler
and nothing leaks into the shared global register.

Asserted: list + detail render the two-tier graph with cross-links; a missing
record id is a 404; the register is reachable by any active user (the gate is
"authenticated", not per-user ownership — the register is shared firm-wide); no
bearer → 401.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.ropa import (
    DataCategory,
    DataSubjectCategory,
    ProcessingActivity,
    System,
    Transfer,
    Vendor,
    processing_activity_data_categories,
    processing_activity_data_subject_categories,
    processing_activity_systems,
    processing_activity_vendors,
)
from app.models.user import User
from app.security import create_access_token, hash_password

pytestmark = pytest.mark.integration


def _override_get_db(session: AsyncSession) -> Callable[[], AsyncIterator[AsyncSession]]:
    async def _f() -> AsyncIterator[AsyncSession]:
        yield session

    return _f


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        email="ropa-reader@example.com",
        display_name="ROPA Reader",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(u)
    await db_session.flush()
    return u


def _bearer(u: User) -> dict[str, str]:
    token = create_access_token(u.id, u.email, is_admin=u.is_admin)
    return {"Authorization": f"Bearer {token}"}


async def _clean(db_session: AsyncSession) -> None:
    # Guarantee a clean register view within this rolled-back transaction,
    # regardless of any committed leftovers from earlier tests.
    await db_session.execute(delete(processing_activity_systems))
    await db_session.execute(delete(processing_activity_vendors))
    await db_session.execute(delete(processing_activity_data_subject_categories))
    await db_session.execute(delete(processing_activity_data_categories))
    await db_session.execute(delete(Transfer))
    await db_session.execute(delete(ProcessingActivity))
    await db_session.execute(delete(System))
    await db_session.execute(delete(Vendor))
    await db_session.execute(delete(DataSubjectCategory))
    await db_session.execute(delete(DataCategory))
    await db_session.flush()


async def _seed_linked(db_session: AsyncSession) -> tuple[ProcessingActivity, System, Vendor]:
    await _clean(db_session)
    pa = ProcessingActivity(
        name="Payroll processing",
        purpose="Pay employees and meet tax obligations",
        lawful_basis="legal_obligation",
        controller_role="controller",
        retention="7 years",
        special_category=False,
        art9_condition=None,
    )
    system = System(name="Production database", system_type="database", hosting_location="UK")
    vendor = Vendor(
        name="Acme Payroll Ltd",
        vendor_role="processor",
        dpa_status="in_place",
        country="UK",
    )
    db_session.add_all([pa, system, vendor])
    await db_session.flush()
    await db_session.execute(
        processing_activity_systems.insert().values(
            processing_activity_id=pa.id, system_id=system.id
        )
    )
    await db_session.execute(
        processing_activity_vendors.insert().values(
            processing_activity_id=pa.id, vendor_id=vendor.id
        )
    )
    # A restricted transfer of this activity's data, with the recipient vendor.
    transfer = Transfer(
        processing_activity_id=pa.id,
        vendor_id=vendor.id,
        destination="United States",
        restricted=True,
        mechanism="standard_contractual_clauses",
    )
    db_session.add(transfer)
    # Article 30(1)(c) personal-data taxonomy tagged on the activity (PRIV-6a).
    dsc = DataSubjectCategory(name="Employees")
    dc = DataCategory(name="Payroll data")
    db_session.add_all([dsc, dc])
    await db_session.flush()
    await db_session.execute(
        processing_activity_data_subject_categories.insert().values(
            processing_activity_id=pa.id, data_subject_category_id=dsc.id
        )
    )
    await db_session.execute(
        processing_activity_data_categories.insert().values(
            processing_activity_id=pa.id, data_category_id=dc.id
        )
    )
    await db_session.flush()
    return pa, system, vendor


async def test_list_empty(client: AsyncClient, db_session: AsyncSession, user: User) -> None:
    await _clean(db_session)
    resp = await client.get("/api/v1/ropa/processing-activities", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json() == []
    resp = await client.get("/api/v1/ropa/systems", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json() == []
    resp = await client.get("/api/v1/ropa/vendors", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_and_detail_render_cross_links(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    pa, system, _vendor = await _seed_linked(db_session)

    # Processing-activities list carries the linked system + recipient summaries.
    resp = await client.get("/api/v1/ropa/processing-activities", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Payroll processing"
    assert body[0]["lawful_basis"] == "legal_obligation"
    assert [s["name"] for s in body[0]["systems"]] == ["Production database"]
    assert [v["name"] for v in body[0]["vendors"]] == ["Acme Payroll Ltd"]
    assert body[0]["vendors"][0]["vendor_role"] == "processor"
    # The child transfer rides on the activity, with its recipient vendor nested.
    assert len(body[0]["transfers"]) == 1
    transfer = body[0]["transfers"][0]
    assert transfer["destination"] == "United States"
    assert transfer["restricted"] is True
    assert transfer["mechanism"] == "standard_contractual_clauses"
    assert transfer["vendor"]["name"] == "Acme Payroll Ltd"
    # The Article 30(1)(c) taxonomy rides on the activity (PRIV-6a).
    assert [c["name"] for c in body[0]["data_subject_categories"]] == ["Employees"]
    assert [c["name"] for c in body[0]["data_categories"]] == ["Payroll data"]

    # Activity detail.
    resp = await client.get(f"/api/v1/ropa/processing-activities/{pa.id}", headers=_bearer(user))
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["systems"][0]["system_type"] == "database"
    assert detail["transfers"][0]["destination"] == "United States"
    assert [c["name"] for c in detail["data_subject_categories"]] == ["Employees"]
    assert [c["name"] for c in detail["data_categories"]] == ["Payroll data"]

    # System detail carries the reverse link.
    resp = await client.get(f"/api/v1/ropa/systems/{system.id}", headers=_bearer(user))
    assert resp.status_code == 200
    sbody = resp.json()
    assert sbody["name"] == "Production database"
    assert sbody["ai_usage"] is False
    assert [a["name"] for a in sbody["processing_activities"]] == ["Payroll processing"]


async def test_vendor_list_and_detail_render_reverse_link(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    _, _, vendor = await _seed_linked(db_session)

    resp = await client.get("/api/v1/ropa/vendors", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Acme Payroll Ltd"
    assert body[0]["vendor_role"] == "processor"
    assert body[0]["dpa_status"] == "in_place"
    assert body[0]["country"] == "UK"

    # Vendor detail carries the reverse link back to the disclosing activities.
    resp = await client.get(f"/api/v1/ropa/vendors/{vendor.id}", headers=_bearer(user))
    assert resp.status_code == 200
    vbody = resp.json()
    assert [a["name"] for a in vbody["processing_activities"]] == ["Payroll processing"]


async def test_data_taxonomy_list_endpoints_render_usage(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    await _seed_linked(db_session)

    resp = await client.get("/api/v1/ropa/data-subject-categories", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Employees"
    assert [a["name"] for a in body[0]["processing_activities"]] == ["Payroll processing"]

    resp = await client.get("/api/v1/ropa/data-categories", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Payroll data"
    assert [a["name"] for a in body[0]["processing_activities"]] == ["Payroll processing"]


async def test_data_taxonomy_lists_require_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ropa/data-subject-categories")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/ropa/data-categories")
    assert resp.status_code == 401


async def test_unknown_ids_return_404(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    import uuid

    missing = uuid.uuid4()
    r1 = await client.get(f"/api/v1/ropa/processing-activities/{missing}", headers=_bearer(user))
    assert r1.status_code == 404
    r2 = await client.get(f"/api/v1/ropa/systems/{missing}", headers=_bearer(user))
    assert r2.status_code == 404
    r3 = await client.get(f"/api/v1/ropa/vendors/{missing}", headers=_bearer(user))
    assert r3.status_code == 404


async def test_shared_read_crosses_users_without_leaking_provenance(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """ADR-F019 posture lock: a row created under user A's matter is readable by a
    different authenticated user B (the register is firm-wide), and the wire shape
    never leaks the source_project_id / owner provenance."""
    from app.models.project import Project

    await _clean(db_session)
    # User A owns a matter; an activity is recorded with that matter as provenance.
    matter = Project(owner_id=user.id, name="A's private matter", slug="a-priv-readtest")
    db_session.add(matter)
    await db_session.flush()
    pa = ProcessingActivity(
        source_project_id=matter.id,
        name="Provenance-stamped activity",
        purpose="seeded with a non-null source_project_id",
        lawful_basis="legal_obligation",
        controller_role="controller",
        retention="7 years",
        special_category=False,
        art9_condition=None,
    )
    db_session.add(pa)
    await db_session.flush()

    # User B (no relation to the matter) reads the shared register.
    user_b = User(
        email="ropa-reader-b@example.com",
        display_name="Reader B",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user_b)
    await db_session.flush()

    resp = await client.get("/api/v1/ropa/processing-activities", headers=_bearer(user_b))
    assert resp.status_code == 200
    body = resp.json()
    assert [a["name"] for a in body] == ["Provenance-stamped activity"]
    # Provenance/ownership must NOT be on the wire (the Read DTO shape is the guard).
    for forbidden in ("source_project_id", "project_id", "owner", "owner_id"):
        assert forbidden not in body[0]

    detail = await client.get(
        f"/api/v1/ropa/processing-activities/{pa.id}", headers=_bearer(user_b)
    )
    assert detail.status_code == 200
    for forbidden in ("source_project_id", "project_id", "owner", "owner_id"):
        assert forbidden not in detail.json()


def _bd(buckets: list[dict]) -> dict[str, int]:
    """Flatten a summary breakdown ([{value, count}, …]) into {value: count}."""
    return {b["value"]: b["count"] for b in buckets}


async def test_programme_summary_aggregates_register(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """PRIV-6b: the programme summary aggregates the whole deployment-global register."""
    # Activity 1 (linked): legal_obligation / controller, 1 system, 1 vendor
    # (DPA in place), 1 restricted transfer, data-subject + data categories.
    await _seed_linked(db_session)
    # Activity 2: special-category / processor with NOTHING linked → fires gaps.
    pa2 = ProcessingActivity(
        name="Wellbeing surveys",
        purpose="Voluntary staff wellbeing analytics",
        lawful_basis="consent",
        controller_role="processor",
        retention="2 years",
        special_category=True,
        art9_condition="explicit_consent",
    )
    # An AI system + a vendor with an outstanding DPA, both unlinked.
    sys2 = System(name="Insights model", system_type="analytics", ai_usage=True)
    vendor2 = Vendor(name="Survey SaaS", vendor_role="recipient", dpa_status="pending")
    db_session.add_all([pa2, sys2, vendor2])
    await db_session.flush()

    resp = await client.get("/api/v1/ropa/programme-summary", headers=_bearer(user))
    assert resp.status_code == 200
    s = resp.json()

    assert s["activities_total"] == 2
    assert s["systems_total"] == 2
    assert s["vendors_total"] == 2
    assert s["transfers_total"] == 1
    assert s["transfers_restricted"] == 1
    assert s["special_category_activities"] == 1
    assert s["systems_using_ai"] == 1

    assert _bd(s["lawful_basis"])["legal_obligation"] == 1
    assert _bd(s["lawful_basis"])["consent"] == 1
    assert _bd(s["controller_role"]) == {"controller": 1, "joint_controller": 0, "processor": 1}
    assert _bd(s["dpa_status"]) == {"in_place": 1, "pending": 1, "not_required": 0, "none": 0}

    # Only activity 2 is unlinked on every axis; the pending vendor is outstanding.
    assert s["gaps"]["activities_without_systems"] == 1
    assert s["gaps"]["activities_without_recipients"] == 1
    assert s["gaps"]["activities_without_data_categories"] == 1
    assert s["gaps"]["activities_without_data_subjects"] == 1
    assert s["gaps"]["vendors_without_dpa"] == 1


async def test_programme_summary_empty_register_is_zeros(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    await _clean(db_session)
    resp = await client.get("/api/v1/ropa/programme-summary", headers=_bearer(user))
    assert resp.status_code == 200
    s = resp.json()
    assert s["activities_total"] == 0
    assert s["transfers_restricted"] == 0
    assert all(b["count"] == 0 for b in s["lawful_basis"])
    assert s["gaps"]["vendors_without_dpa"] == 0


async def test_programme_summary_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ropa/programme-summary")
    assert resp.status_code == 401


async def test_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ropa/processing-activities")
    assert resp.status_code == 401
