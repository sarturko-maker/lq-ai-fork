"""AI-systems register read API — AIC-1 (fork, ADR-F057/F019).

The deployment-global register read surface. Runs inside the per-test rolled-back
``db_session`` (the endpoint reads through the same overridden session), so seeded
rows are visible to the handler and nothing leaks into the shared register.

Asserted: list + detail render the register; retired rows are hidden by default and
shown with ``?include_retired=true``; a missing id is a 404; the register is
reachable by any active user (shared firm-wide, ADR-F019); no bearer → 401; the read
projection never leaks the scoping key / provenance.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.compliance import AiSystem
from app.models.practice_area import PracticeArea
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
        email="aic-reader@example.com",
        display_name="AIC Reader",
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


async def _area_id(db_session: AsyncSession) -> uuid.UUID:
    return (
        await db_session.execute(select(PracticeArea.id).where(PracticeArea.key == "ai-compliance"))
    ).scalar_one()


async def _clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(AiSystem))
    await db_session.flush()


async def _seed(db_session: AsyncSession, **overrides: object) -> AiSystem:
    row = AiSystem(
        practice_area_id=await _area_id(db_session),
        name="Applicant ranking model",
        intended_purpose="Score and rank job applicants for recruiter review.",
        lifecycle_status="in_service",
        development_origin="third_party",
        is_gpai=False,
        gpai_systemic=False,
        **overrides,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def test_list_empty(client: AsyncClient, db_session: AsyncSession, user: User) -> None:
    await _clean(db_session)
    resp = await client.get("/api/v1/compliance/ai-systems", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_and_detail(client: AsyncClient, db_session: AsyncSession, user: User) -> None:
    await _clean(db_session)
    row = await _seed(db_session)

    resp = await client.get("/api/v1/compliance/ai-systems", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Applicant ranking model"
    assert body[0]["lifecycle_status"] == "in_service"
    assert body[0]["development_origin"] == "third_party"
    # The read projection never leaks the scoping key / provenance.
    assert "practice_area_id" not in body[0]
    assert "source_project_id" not in body[0]

    resp = await client.get(f"/api/v1/compliance/ai-systems/{row.id}", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(row.id)


async def test_missing_id_is_404(client: AsyncClient, db_session: AsyncSession, user: User) -> None:
    await _clean(db_session)
    resp = await client.get(f"/api/v1/compliance/ai-systems/{uuid.uuid4()}", headers=_bearer(user))
    assert resp.status_code == 404


async def test_retired_hidden_by_default_shown_with_flag(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    await _clean(db_session)
    await _seed(db_session, retired_at=datetime.now(UTC))

    resp = await client.get("/api/v1/compliance/ai-systems", headers=_bearer(user))
    assert resp.json() == []
    resp = await client.get(
        "/api/v1/compliance/ai-systems?include_retired=true", headers=_bearer(user)
    )
    assert len(resp.json()) == 1


async def test_no_bearer_is_401(client: AsyncClient, db_session: AsyncSession) -> None:
    resp = await client.get("/api/v1/compliance/ai-systems")
    assert resp.status_code == 401
