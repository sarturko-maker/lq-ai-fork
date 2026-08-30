"""Every matter carries an immutable ``ORG-AREA-NNNN`` reference — INTAKE-4a (ADR-F088).

Covers the cockpit creation path (``POST /api/v1/projects``): a reference is
allocated at creation, it is the area's series (a matter with no area falls to
``GEN``), consecutive matters get consecutive numbers, the sandbox — which is not
a matter — gets none, and no write surface will change one.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.matters.reference import GENERIC_AREA_CODE, is_valid_reference
from app.models.practice_area import PracticeArea
from app.models.user import User
from app.security import create_access_token, hash_password

pytestmark = pytest.mark.integration


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"ref-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Reference Test User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def configured_area(db_session: AsyncSession) -> PracticeArea:
    area = PracticeArea(
        key=f"area-{uuid.uuid4().hex[:8]}",
        name="Wolfram reference area",
        unit_label="Matter",
        position=0,
        profile_md="You are a Wolfram lawyer.",
    )
    db_session.add(area)
    await db_session.flush()
    return area


def _h(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, is_admin=False)}"}


def _number(reference: str) -> int:
    return int(reference.rsplit("-", 1)[1])


async def test_created_matter_carries_a_valid_reference(
    client: AsyncClient, db_user: User, configured_area: PracticeArea
) -> None:
    res = await client.post(
        "/api/v1/projects",
        headers=_h(db_user),
        json={"name": "Project Wolfram", "practice_area_id": str(configured_area.id)},
    )
    assert res.status_code == 201, res.text
    reference = res.json()["reference"]
    assert reference is not None
    assert is_valid_reference(reference)
    assert reference.split("-")[1] == "WOL"


async def test_consecutive_matters_in_one_area_get_consecutive_numbers(
    client: AsyncClient, db_user: User, configured_area: PracticeArea
) -> None:
    first = await client.post(
        "/api/v1/projects",
        headers=_h(db_user),
        json={"name": "First", "practice_area_id": str(configured_area.id)},
    )
    second = await client.post(
        "/api/v1/projects",
        headers=_h(db_user),
        json={"name": "Second", "practice_area_id": str(configured_area.id)},
    )
    assert first.status_code == 201 and second.status_code == 201
    assert _number(second.json()["reference"]) == _number(first.json()["reference"]) + 1


async def test_matter_without_an_area_uses_the_generic_series(
    client: AsyncClient, db_user: User
) -> None:
    res = await client.post("/api/v1/projects", headers=_h(db_user), json={"name": "Unfiled"})
    assert res.status_code == 201, res.text
    assert res.json()["reference"].split("-")[1] == GENERIC_AREA_CODE


async def test_the_sandbox_is_not_a_matter_and_gets_no_reference(
    client: AsyncClient, db_user: User
) -> None:
    res = await client.post("/api/v1/projects/sandbox/ensure", headers=_h(db_user))
    assert res.status_code in (200, 201), res.text
    assert res.json()["reference"] is None


async def test_the_reference_is_immutable(
    client: AsyncClient, db_user: User, configured_area: PracticeArea
) -> None:
    created = await client.post(
        "/api/v1/projects",
        headers=_h(db_user),
        json={"name": "Immutable", "practice_area_id": str(configured_area.id)},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    original = created.json()["reference"]

    # No write schema accepts it — ``extra="forbid"`` turns an attempt into a 422.
    patched = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_h(db_user),
        json={"reference": "AAA-BBB-9999"},
    )
    assert patched.status_code == 422, patched.text

    after = await client.get(f"/api/v1/projects/{project_id}", headers=_h(db_user))
    assert after.json()["reference"] == original


async def test_create_rejects_a_client_supplied_reference(
    client: AsyncClient, db_user: User
) -> None:
    res = await client.post(
        "/api/v1/projects",
        headers=_h(db_user),
        json={"name": "Forged", "reference": "AAA-BBB-9999"},
    )
    assert res.status_code == 422, res.text
