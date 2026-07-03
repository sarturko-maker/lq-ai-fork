"""SETUP-3a (ADR-F061 D5) — admin disable / re-enable + guards.

Covers: disable stamps disabled_at + revokes sessions; a live access token 401s
on its next request; login for a disabled user is byte-identical to a wrong
password (anti-enumeration); refresh 401s; enable restores; self / last-admin /
operator guards.
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
from app.models.user import User, UserSession
from app.security import create_access_token, hash_password

_PW = "correct-horse-battery-staple"


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


def _bearer(user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.email, is_admin=user.is_admin)}"
    }


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


async def _seed(db: AsyncSession, *, role: str = "member", is_admin: bool = False) -> User:
    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password(_PW),
        is_admin=is_admin,
        role=role,
        mfa_enabled=False,
        must_change_password=False,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await _seed(db_session, role="admin", is_admin=True)


# ---------------------------------------------------------------------------
# disable
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_disable_stamps_disabled_at_and_revokes_sessions(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    target = await _seed(db_session)
    # A live session for the target.
    login = await client.post("/api/v1/auth/login", json={"email": target.email, "password": _PW})
    assert login.status_code == 200

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/disable", headers=_bearer(admin_user)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["disabled"] is True
    assert resp.json()["disabled_at"] is not None

    await db_session.refresh(target)
    assert target.disabled_at is not None

    # All the target's sessions are revoked.
    active = (
        (
            await db_session.execute(
                select(UserSession).where(
                    UserSession.user_id == target.id, UserSession.revoked_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    assert active == []


@pytest.mark.integration
async def test_live_access_token_401s_after_disable(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    target = await _seed(db_session)
    token_headers = _bearer(target)

    # Works before disable.
    before = await client.get("/api/v1/users/me", headers=token_headers)
    assert before.status_code == 200, before.text

    await client.post(f"/api/v1/admin/users/{target.id}/disable", headers=_bearer(admin_user))

    # The same (still-unexpired) access token now 401s.
    after = await client.get("/api/v1/users/me", headers=token_headers)
    assert after.status_code == 401, after.text


@pytest.mark.integration
async def test_disabled_login_byte_identical_to_wrong_password(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    target = await _seed(db_session)

    wrong = await client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": "totally-wrong"}
    )
    assert wrong.status_code == 401

    await client.post(f"/api/v1/admin/users/{target.id}/disable", headers=_bearer(admin_user))

    disabled = await client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": _PW}
    )
    assert disabled.status_code == 401
    # Byte-identical: an attacker cannot tell "disabled" from "wrong password".
    assert disabled.status_code == wrong.status_code
    assert disabled.content == wrong.content


@pytest.mark.integration
async def test_refresh_401s_after_disable(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    target = await _seed(db_session)
    login = await client.post("/api/v1/auth/login", json={"email": target.email, "password": _PW})
    refresh_token = login.json()["refresh_token"]

    await client.post(f"/api/v1/admin/users/{target.id}/disable", headers=_bearer(admin_user))

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401, resp.text


@pytest.mark.integration
async def test_refresh_401s_when_user_disabled_without_session_revoke(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Belt-and-braces (D5): a session minted the instant before disable can't
    refresh — the refresh handler re-checks disabled_at directly."""
    from datetime import UTC, datetime

    target = await _seed(db_session)
    login = await client.post("/api/v1/auth/login", json={"email": target.email, "password": _PW})
    refresh_token = login.json()["refresh_token"]

    # Disable the user directly, WITHOUT revoking sessions (simulates the race).
    target.disabled_at = datetime.now(UTC)
    await db_session.flush()

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# enable
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_enable_restores_access(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    target = await _seed(db_session)
    await client.post(f"/api/v1/admin/users/{target.id}/disable", headers=_bearer(admin_user))

    resp = await client.post(f"/api/v1/admin/users/{target.id}/enable", headers=_bearer(admin_user))
    assert resp.status_code == 200, resp.text
    assert resp.json()["disabled"] is False
    assert resp.json()["disabled_at"] is None

    await db_session.refresh(target)
    assert target.disabled_at is None

    # The user can log in again (fresh session — the old ones stay revoked).
    login = await client.post("/api/v1/auth/login", json={"email": target.email, "password": _PW})
    assert login.status_code == 200, login.text


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_self_disable_refused(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        f"/api/v1/admin/users/{admin_user.id}/disable", headers=_bearer(admin_user)
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
async def test_last_admin_disable_refused(client: AsyncClient, db_session: AsyncSession) -> None:
    """An operator disabling the ONLY admin is refused (lockout protection)."""
    operator = await _seed(db_session, role="operator", is_admin=True)
    sole_admin = await _seed(db_session, role="admin", is_admin=True)

    resp = await client.post(
        f"/api/v1/admin/users/{sole_admin.id}/disable", headers=_bearer(operator)
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
async def test_disable_unknown_user_404(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/disable", headers=_bearer(admin_user)
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
async def test_disable_non_admin_403(client: AsyncClient, db_session: AsyncSession) -> None:
    actor = await _seed(db_session, role="member")
    target = await _seed(db_session, role="member")
    resp = await client.post(f"/api/v1/admin/users/{target.id}/disable", headers=_bearer(actor))
    assert resp.status_code == 403, resp.text
