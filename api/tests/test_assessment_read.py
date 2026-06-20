"""Assessment register read API — PRIV-A3 (fork, ADR-F019/F027).

The deployment-global assessment record (PIA/DPIA/LIA/TIA + risk findings) read
surface, the sibling of ``test_ropa_read``. These run inside the per-test
rolled-back ``db_session`` (the endpoint reads through the same overridden
session), so seeded rows are visible to the handler and nothing leaks into the
shared global register.

Asserted: list + detail render the assessment with its risks and the activities
it covers; a missing id is a 404; reachable by any active user (the gate is
"authenticated", not per-user ownership — the record is shared firm-wide); no
bearer → 401; ``source_project_id`` (provenance) never reaches the wire; a
retired linked activity is hidden; and the PRIV-A3 **write-back** projection —
a ROPA activity surfaces the assessments covering it (the "DPIA on file" marker).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.assessment import Assessment, Risk, assessment_processing_activities
from app.models.ropa import ProcessingActivity
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
        email="assessment-reader@example.com",
        display_name="Assessment Reader",
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
    await db_session.execute(delete(assessment_processing_activities))
    await db_session.execute(delete(Risk))
    await db_session.execute(delete(Assessment))
    await db_session.execute(delete(ProcessingActivity))
    await db_session.flush()


async def _seed_assessment_with_risk_and_activity(
    db_session: AsyncSession,
) -> tuple[Assessment, ProcessingActivity]:
    """A completed DPIA with a mitigated risk, covering one live activity."""
    await _clean(db_session)
    activity = ProcessingActivity(
        name="Employee monitoring",
        purpose="Detect security incidents",
        lawful_basis="legitimate_interests",
        controller_role="controller",
        retention="12 months",
        special_category=False,
        art9_condition=None,
    )
    db_session.add(activity)
    await db_session.flush()
    assessment = Assessment(
        type="dpia",
        title="Employee monitoring DPIA",
        summary="Assessing the monitoring of staff endpoints",
        status="completed",
        risk_rating="high",
        conditions="DPO sign-off; 6-month review",
    )
    db_session.add(assessment)
    await db_session.flush()
    db_session.add(
        Risk(
            assessment_id=assessment.id,
            description="Excessive visibility into private activity",
            likelihood="medium",
            impact="high",
            mitigation="Scope monitoring to work apps; alert-only, no keystroke capture",
            owner="Head of Security",
            status="mitigated",
        )
    )
    await db_session.execute(
        assessment_processing_activities.insert().values(
            assessment_id=assessment.id, processing_activity_id=activity.id
        )
    )
    await db_session.flush()
    return assessment, activity


async def test_list_empty(client: AsyncClient, db_session: AsyncSession, user: User) -> None:
    await _clean(db_session)
    resp = await client.get("/api/v1/ropa/assessments", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_and_detail_render_risks_and_links(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    assessment, activity = await _seed_assessment_with_risk_and_activity(db_session)

    resp = await client.get("/api/v1/ropa/assessments", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    row = body[0]
    assert row["type"] == "dpia"
    assert row["title"] == "Employee monitoring DPIA"
    assert row["status"] == "completed"
    assert row["risk_rating"] == "high"
    assert row["conditions"] == "DPO sign-off; 6-month review"
    assert len(row["risks"]) == 1
    assert row["risks"][0]["likelihood"] == "medium"
    assert row["risks"][0]["impact"] == "high"
    assert row["risks"][0]["status"] == "mitigated"
    assert row["risks"][0]["mitigation"].startswith("Scope monitoring")
    assert [a["name"] for a in row["processing_activities"]] == ["Employee monitoring"]

    # Detail by id.
    resp = await client.get(f"/api/v1/ropa/assessments/{assessment.id}", headers=_bearer(user))
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == str(assessment.id)
    assert detail["title"] == "Employee monitoring DPIA"
    assert [a["id"] for a in detail["processing_activities"]] == [str(activity.id)]


async def test_detail_404_for_missing_id(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    await _clean(db_session)
    missing = "00000000-0000-4000-8000-000000000000"
    resp = await client.get(f"/api/v1/ropa/assessments/{missing}", headers=_bearer(user))
    assert resp.status_code == 404


async def test_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ropa/assessments")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/ropa/assessments/00000000-0000-4000-8000-000000000000")
    assert resp.status_code == 401


async def test_source_project_id_is_never_on_the_wire(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    # Provenance must not leak into the shared-read record (ADR-F019).
    await _clean(db_session)
    a = Assessment(
        type="pia",
        title="Newsletter PIA",
        status="draft",
        source_project_id=None,
    )
    db_session.add(a)
    await db_session.flush()
    resp = await client.get("/api/v1/ropa/assessments", headers=_bearer(user))
    assert resp.status_code == 200
    assert "source_project_id" not in resp.json()[0]


async def test_retired_linked_activity_is_hidden(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    # A retired activity has left the live register, so it must not appear under
    # the assessment's covered activities (parity with the ROPA reads, ADR-F023).
    assessment, activity = await _seed_assessment_with_risk_and_activity(db_session)
    activity.retired_at = datetime.now(UTC)
    await db_session.flush()

    resp = await client.get(f"/api/v1/ropa/assessments/{assessment.id}", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json()["processing_activities"] == []


async def test_writeback_activity_surfaces_covering_assessments(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    # PRIV-A3 write-back: the ROPA activity read carries the assessments covering
    # it (the "DPIA on file" marker is derived from a linked completed DPIA).
    _assessment, activity = await _seed_assessment_with_risk_and_activity(db_session)

    resp = await client.get("/api/v1/ropa/processing-activities", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert "assessments" in body[0]
    assert len(body[0]["assessments"]) == 1
    summary = body[0]["assessments"][0]
    assert summary["type"] == "dpia"
    assert summary["status"] == "completed"
    assert summary["title"] == "Employee monitoring DPIA"
    # The compact write-back projection carries the marker + deep-link fields only
    # (PRIV-A3); the rating lives on the assessment's own read, not here.
    assert "risk_rating" not in summary

    # And on the activity detail.
    resp = await client.get(
        f"/api/v1/ropa/processing-activities/{activity.id}", headers=_bearer(user)
    )
    assert resp.status_code == 200
    assert [s["type"] for s in resp.json()["assessments"]] == ["dpia"]


async def test_register_is_shared_across_active_users(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    # The assessment record is firm-wide (ADR-F019): a second active user sees the
    # same rows — no per-user scoping, no existence-hiding.
    await _seed_assessment_with_risk_and_activity(db_session)
    other = User(
        email="assessment-reader-2@example.com",
        display_name="Second Reader",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(other)
    await db_session.flush()

    resp = await client.get("/api/v1/ropa/assessments", headers=_bearer(other))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
