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
from app.models.ropa import ProcessingActivity, System, processing_activity_systems
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
    await db_session.execute(delete(ProcessingActivity))
    await db_session.execute(delete(System))
    await db_session.flush()


async def _seed_linked(db_session: AsyncSession) -> tuple[ProcessingActivity, System]:
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
    db_session.add_all([pa, system])
    await db_session.flush()
    await db_session.execute(
        processing_activity_systems.insert().values(
            processing_activity_id=pa.id, system_id=system.id
        )
    )
    await db_session.flush()
    return pa, system


async def test_list_empty(client: AsyncClient, db_session: AsyncSession, user: User) -> None:
    await _clean(db_session)
    resp = await client.get("/api/v1/ropa/processing-activities", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json() == []
    resp = await client.get("/api/v1/ropa/systems", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_and_detail_render_cross_links(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    pa, system = await _seed_linked(db_session)

    # Processing-activities list carries the linked system summary.
    resp = await client.get("/api/v1/ropa/processing-activities", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Payroll processing"
    assert body[0]["lawful_basis"] == "legal_obligation"
    assert [s["name"] for s in body[0]["systems"]] == ["Production database"]

    # Activity detail.
    resp = await client.get(f"/api/v1/ropa/processing-activities/{pa.id}", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json()["systems"][0]["system_type"] == "database"

    # System detail carries the reverse link.
    resp = await client.get(f"/api/v1/ropa/systems/{system.id}", headers=_bearer(user))
    assert resp.status_code == 200
    sbody = resp.json()
    assert sbody["name"] == "Production database"
    assert sbody["ai_usage"] is False
    assert [a["name"] for a in sbody["processing_activities"]] == ["Payroll processing"]


async def test_unknown_ids_return_404(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    import uuid

    missing = uuid.uuid4()
    r1 = await client.get(f"/api/v1/ropa/processing-activities/{missing}", headers=_bearer(user))
    assert r1.status_code == 404
    r2 = await client.get(f"/api/v1/ropa/systems/{missing}", headers=_bearer(user))
    assert r2.status_code == 404


async def test_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ropa/processing-activities")
    assert resp.status_code == 401
