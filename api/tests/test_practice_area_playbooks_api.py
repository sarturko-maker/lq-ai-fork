"""Admin playbook attach/detach to a practice area (ADR-F054).

Mirrors the skill attach/detach surface: a playbook bound to an area becomes AVAILABLE
to matters under it (the lawyer then toggles it per matter). Admin-only; validated
against the (non-deleted) ``playbooks`` rows; re-attach is 409; detach is idempotent.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.playbook import Playbook
from app.models.practice_area import PracticeArea, PracticeAreaPlaybook
from app.models.user import User
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="pa-pb-admin")
    u.is_admin = True
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="pa-pb-user")


async def _make_playbook(db: AsyncSession) -> Playbook:
    pb = Playbook(name="NDA playbook", contract_type="NDA", description="Preferred positions.")
    db.add(pb)
    await db.flush()
    return pb


def _url(key: str) -> str:
    return f"/api/v1/practice-areas/{key}/playbooks"


async def test_attach_playbook_creates_binding(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    pb = await _make_playbook(db_session)
    resp = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"playbook_id": str(pb.id)}
    )
    assert resp.status_code == 204

    area_id = (
        await db_session.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
    ).scalar_one()
    binding = (
        await db_session.execute(
            select(PracticeAreaPlaybook).where(
                PracticeAreaPlaybook.practice_area_id == area_id,
                PracticeAreaPlaybook.playbook_id == pb.id,
            )
        )
    ).scalar_one_or_none()
    assert binding is not None


async def test_attach_unknown_playbook_is_404(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"playbook_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404


async def test_attach_unknown_area_is_404(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    pb = await _make_playbook(db_session)
    resp = await client.post(
        _url("no-such-area"), headers=_bearer(admin), json={"playbook_id": str(pb.id)}
    )
    assert resp.status_code == 404


async def test_attach_requires_admin(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    pb = await _make_playbook(db_session)
    resp = await client.post(
        _url("commercial"), headers=_bearer(user), json={"playbook_id": str(pb.id)}
    )
    assert resp.status_code == 403


async def test_reattach_is_409(client: AsyncClient, db_session: AsyncSession, admin: User) -> None:
    pb = await _make_playbook(db_session)
    first = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"playbook_id": str(pb.id)}
    )
    assert first.status_code == 204
    second = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"playbook_id": str(pb.id)}
    )
    assert second.status_code == 409


async def test_detach_removes_binding_and_is_idempotent(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    pb = await _make_playbook(db_session)
    await client.post(_url("commercial"), headers=_bearer(admin), json={"playbook_id": str(pb.id)})

    detach = await client.delete(f"{_url('commercial')}/{pb.id}", headers=_bearer(admin))
    assert detach.status_code == 204

    area_id = (
        await db_session.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
    ).scalar_one()
    gone = (
        await db_session.execute(
            select(PracticeAreaPlaybook).where(
                PracticeAreaPlaybook.practice_area_id == area_id,
                PracticeAreaPlaybook.playbook_id == pb.id,
            )
        )
    ).scalar_one_or_none()
    assert gone is None

    # Detaching again is a no-op 204.
    again = await client.delete(f"{_url('commercial')}/{pb.id}", headers=_bearer(admin))
    assert again.status_code == 204
