"""SETUP-3a (ADR-F061) — invite lifecycle (create / list / resend / revoke /
accept) + token-at-rest + single-use race.

The client shares the test SAVEPOINT session (per the repo pattern). The
genuine two-connection race uses the session-scoped ``test_engine`` directly so
two real transactions contend on the same row lock.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.auth_tokens import INVITE, consume_token, generate_token, hash_auth_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.models.user_auth_token import UserAuthToken
from app.security import create_access_token, hash_password


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


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Admin",
        hashed_password=hash_password("s3cr3t-battery-staple-xyz"),
        is_admin=True,
        role="admin",
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _token_from_url(accept_url: str) -> str:
    return accept_url.split("token=", 1)[1]


# ---------------------------------------------------------------------------
# token hashing (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_hmac_domain_separated_and_deterministic() -> None:
    """The invite and reset HMACs of the SAME plaintext differ (domain sep)."""
    from app.auth_tokens import PASSWORD_RESET, hash_auth_token

    plaintext = "identical-plaintext-secret-value"
    invite = hash_auth_token(INVITE, plaintext)
    reset = hash_auth_token(PASSWORD_RESET, plaintext)
    assert invite != reset
    assert invite == hash_auth_token(INVITE, plaintext)  # deterministic
    assert len(invite) == 64
    assert plaintext not in invite


# ---------------------------------------------------------------------------
# create / list / resend / revoke
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_invite_returns_accept_url_when_mail_off(
    client: AsyncClient, admin_user: User
) -> None:
    """SMTP is unconfigured in tests ⇒ email_sent False + accept_url handed back."""
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == email
    assert body["role"] == "member"
    assert body["email_sent"] is False
    assert body["accept_url"] and "token=" in body["accept_url"]


@pytest.mark.integration
async def test_create_invite_stores_hmac_only(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    """The DB row carries ONLY the HMAC — the plaintext token never lands."""
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "viewer"},
    )
    assert resp.status_code == 201, resp.text
    plaintext = _token_from_url(resp.json()["accept_url"])

    row = (
        await db_session.execute(select(UserAuthToken).where(UserAuthToken.email == email))
    ).scalar_one()
    assert row.token_hmac == hash_auth_token(INVITE, plaintext)
    assert len(row.token_hmac) == 64
    # The plaintext appears nowhere on the row.
    for value in (row.token_hmac, row.email, str(row.id)):
        assert plaintext not in value


@pytest.mark.integration
async def test_create_invite_409_when_user_exists(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    existing = User(
        email=f"taken-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("x" * 14),
        role="member",
    )
    db_session.add(existing)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": existing.email, "role": "member"},
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.integration
async def test_create_invite_409_when_pending_invite_exists(
    client: AsyncClient, admin_user: User
) -> None:
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    first = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    assert second.status_code == 409, second.text


@pytest.mark.integration
async def test_create_invite_422_bad_role(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": f"x-{uuid.uuid4().hex[:8]}@example.com", "role": "wizard"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
async def test_create_invite_non_admin_403(client: AsyncClient, db_session: AsyncSession) -> None:
    member = User(
        email=f"member-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("x" * 14),
        role="member",
    )
    db_session.add(member)
    await db_session.flush()
    resp = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(member),
        json={"email": "y@example.com", "role": "member"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
async def test_list_invites_shows_status(client: AsyncClient, admin_user: User) -> None:
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    invite_id = created.json()["id"]

    resp = await client.get("/api/v1/admin/users/invites", headers=_bearer(admin_user))
    assert resp.status_code == 200, resp.text
    rows = {r["id"]: r for r in resp.json()["invites"]}
    assert invite_id in rows
    assert rows[invite_id]["status"] == "pending"
    assert rows[invite_id]["email"] == email


@pytest.mark.integration
async def test_resend_revokes_prior_token(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    """Resend revokes the prior invite and mints a fresh one for the email."""
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    first = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    old_url = first.json()["accept_url"]
    old_id = first.json()["id"]

    resent = await client.post(
        f"/api/v1/admin/users/invites/{old_id}/resend",
        headers=_bearer(admin_user),
    )
    assert resent.status_code == 200, resent.text
    new_url = resent.json()["accept_url"]
    assert new_url != old_url

    # The prior token no longer accepts (revoked) — uniform 400.
    reject = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": _token_from_url(old_url), "password": "n3w-password-1234"},
    )
    assert reject.status_code == 400, reject.text

    # The new token still works.
    ok = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": _token_from_url(new_url), "password": "n3w-password-1234"},
    )
    assert ok.status_code == 201, ok.text


@pytest.mark.integration
async def test_revoke_invite_blocks_accept(client: AsyncClient, admin_user: User) -> None:
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    invite_id = created.json()["id"]
    token = _token_from_url(created.json()["accept_url"])

    revoked = await client.delete(
        f"/api/v1/admin/users/invites/{invite_id}", headers=_bearer(admin_user)
    )
    assert revoked.status_code == 204, revoked.text

    resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "password": "n3w-password-1234"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.integration
async def test_resend_unknown_invite_404(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        f"/api/v1/admin/users/invites/{uuid.uuid4()}/resend", headers=_bearer(admin_user)
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# accept-invite
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_accept_invite_creates_verified_user(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "viewer"},
    )
    token = _token_from_url(created.json()["accept_url"])

    resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "password": "brand-new-passphrase-1", "display_name": "Vera"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == email
    assert body["role"] == "viewer"

    row = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    assert row.role == "viewer"
    assert row.is_admin is False
    assert row.must_change_password is False  # they set their own password
    assert row.email_verified_at is not None
    assert row.display_name == "Vera"

    # The user can now log in with the chosen password.
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "brand-new-passphrase-1"}
    )
    assert login.status_code == 200, login.text


@pytest.mark.integration
async def test_accept_invite_admin_role_sets_is_admin(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "admin"},
    )
    token = _token_from_url(created.json()["accept_url"])
    resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "password": "brand-new-passphrase-1"},
    )
    assert resp.status_code == 201, resp.text
    row = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    assert row.is_admin is True
    assert row.role == "admin"


@pytest.mark.integration
async def test_accept_invite_second_use_is_400(client: AsyncClient, admin_user: User) -> None:
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    token = _token_from_url(created.json()["accept_url"])
    first = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "password": "brand-new-passphrase-1"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "password": "brand-new-passphrase-1"},
    )
    assert second.status_code == 400, second.text


@pytest.mark.integration
async def test_accept_invite_unknown_token_is_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": "not-a-real-token", "password": "brand-new-passphrase-1"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.integration
async def test_accept_invite_short_password_is_400(client: AsyncClient, admin_user: User) -> None:
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": email, "role": "member"},
    )
    token = _token_from_url(created.json()["accept_url"])
    resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "password": "short"},
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# Genuine two-connection single-use race
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_parallel_accept_exactly_one_winner(test_engine: AsyncEngine) -> None:
    """Two concurrent redemptions of the SAME token: exactly one wins.

    Uses two real transactions contending on the row lock (not the shared
    SAVEPOINT session), so this exercises the atomic ``consumed_at`` write.
    """
    email = f"race-{uuid.uuid4().hex[:8]}@example.com"
    plaintext = generate_token()
    now = datetime.now(UTC)

    async with AsyncSession(test_engine) as setup, setup.begin():
        setup.add(
            UserAuthToken(
                purpose=INVITE,
                email=email,
                role="member",
                token_hmac=hash_auth_token(INVITE, plaintext),
                expires_at=now + timedelta(hours=1),
            )
        )

    async def _attempt() -> bool:
        async with AsyncSession(test_engine) as s, s.begin():
            token = await consume_token(s, purpose=INVITE, plaintext=plaintext)
            return token is not None

    try:
        results = await asyncio.gather(_attempt(), _attempt())
        assert sum(1 for r in results if r) == 1, f"expected exactly one winner, got {results}"
    finally:
        async with AsyncSession(test_engine) as cleanup, cleanup.begin():
            await cleanup.execute(
                UserAuthToken.__table__.delete().where(UserAuthToken.email == email)
            )
