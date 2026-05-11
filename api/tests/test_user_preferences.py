"""Integration tests for /users/me/preferences — Wave A (PRD §3.2).

Covers:

* GET returns the current preferences slice (defaulting to ``disclosure``
  for newly-created users via the migration's server-default).
* GET /users/me also surfaces ``reasoning_visibility`` on the user shape.
* PATCH with a real change persists + writes a ``user.preferences_updated``
  audit row with before/after.
* Idempotent PATCH (same value) is a no-op — returns 200 with no audit row.
* PATCH with no fields supplied returns the current state, no audit row.
* Invalid enum value returns 422.
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
from app.models import AuditLog, User
from app.security import create_access_token, hash_password


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
async def caller(db_session: AsyncSession) -> User:
    user = User(
        email=f"prefs-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Prefs Test",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _bearer(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
async def test_get_preferences_defaults_to_disclosure(
    client: AsyncClient, caller: User
) -> None:
    resp = await client.get("/api/v1/users/me/preferences", headers=_bearer(caller))
    assert resp.status_code == 200
    assert resp.json() == {"reasoning_visibility": "disclosure"}


@pytest.mark.integration
async def test_users_me_surfaces_reasoning_visibility(
    client: AsyncClient, caller: User
) -> None:
    resp = await client.get("/api/v1/users/me", headers=_bearer(caller))
    assert resp.status_code == 200
    assert resp.json()["reasoning_visibility"] == "disclosure"


@pytest.mark.integration
async def test_patch_preferences_changes_value_and_writes_audit(
    client: AsyncClient, db_session: AsyncSession, caller: User
) -> None:
    resp = await client.patch(
        "/api/v1/users/me/preferences",
        headers=_bearer(caller),
        json={"reasoning_visibility": "always_show"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"reasoning_visibility": "always_show"}

    # Audit row written with before/after.
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user.preferences_updated",
                AuditLog.resource_id == str(caller.id),
            )
        )
    ).scalar_one()
    changes = audit.details["changes"]
    assert changes["reasoning_visibility"]["before"] == "disclosure"
    assert changes["reasoning_visibility"]["after"] == "always_show"


@pytest.mark.integration
async def test_patch_preferences_idempotent_no_audit(
    client: AsyncClient, db_session: AsyncSession, caller: User
) -> None:
    # PATCH with the same value as the default; should not audit.
    resp = await client.patch(
        "/api/v1/users/me/preferences",
        headers=_bearer(caller),
        json={"reasoning_visibility": "disclosure"},
    )
    assert resp.status_code == 200

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user.preferences_updated",
                AuditLog.resource_id == str(caller.id),
            )
        )
    ).scalars().all()
    assert audit == []


@pytest.mark.integration
async def test_patch_preferences_empty_body_is_noop(
    client: AsyncClient, caller: User
) -> None:
    resp = await client.patch(
        "/api/v1/users/me/preferences",
        headers=_bearer(caller),
        json={},
    )
    assert resp.status_code == 200
    assert resp.json() == {"reasoning_visibility": "disclosure"}


@pytest.mark.integration
async def test_patch_preferences_invalid_enum_returns_422(
    client: AsyncClient, caller: User
) -> None:
    resp = await client.patch(
        "/api/v1/users/me/preferences",
        headers=_bearer(caller),
        json={"reasoning_visibility": "loud_and_proud"},
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_users_check_constraint_blocks_invalid_value(
    db_session: AsyncSession, caller: User
) -> None:
    """The DB-side CHECK is defense-in-depth — invalid values must not
    survive a direct write either."""

    from sqlalchemy.exc import IntegrityError

    caller.reasoning_visibility = "invalid_value"
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
