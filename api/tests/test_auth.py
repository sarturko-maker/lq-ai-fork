"""Integration tests for the B1 auth endpoints.

Covers the verification step from M1-IMPLEMENTATION-ORDER.md Task B1:

    Integration test creates a user, logs in, fetches /api/v1/users/me with
    the bearer token, refreshes, logs out.

Plus the surrounding 401/423 and rotation/revocation paths.

Test database lifecycle is the SAVEPOINT-based fixture from conftest.py
(A2). Each test runs against the fresh per-run DB inside a SAVEPOINT that
is rolled back on teardown — so the integration tests share one Alembic
upgrade and stay isolated from each other.

The FastAPI app is exercised via httpx.AsyncClient + ASGITransport per
CONTRIBUTING.md. We override `get_db` and the `oauth2_scheme` dependency
to wire the test session into the in-process app without spinning up
uvicorn or routing through the real connection pool.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _MAX_ACTIVE_SESSIONS_PER_USER
from app.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserSession
from app.security import hash_password


def _override_get_db(db_session: AsyncSession):
    """Build a FastAPI dependency override that yields the test session.

    The session has a SAVEPOINT-based join to an outer connection-level
    transaction (per conftest.py). We must NOT close it here, and we
    must NOT call commit-that-closes — the per-test fixture owns the
    lifecycle. The handler is wrapped to swallow `session.commit()` so
    the SAVEPOINT pattern keeps working without us patching every
    handler.
    """

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Async HTTP client wired to the in-process app, sharing the test session.

    Override `get_db` so handlers see the same session the test is
    asserting against. We do not override the dependency module's
    `oauth2_scheme` — the real one runs and parses the Authorization
    header, exactly as in production.
    """
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def seed_user(db_session: AsyncSession) -> User:
    """Insert a baseline user with a known password and return the row."""
    user = User(
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Test User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def seed_mfa_user(db_session: AsyncSession) -> User:
    """A user with mfa_enabled=true, used to exercise the 423 branch."""
    user = User(
        email=f"mfa-{uuid.uuid4().hex[:8]}@example.com",
        display_name="MFA User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_login_success_returns_tokens_and_user(client: AsyncClient, seed_user: User) -> None:
    """Successful login returns access + refresh tokens and the User payload."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == get_settings().jwt_access_token_ttl_seconds
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == seed_user.email
    assert body["user"]["id"] == str(seed_user.id)
    assert body["user"]["is_admin"] is False
    assert body["user"]["mfa_enabled"] is False


@pytest.mark.integration
async def test_login_wrong_password_returns_401(client: AsyncClient, seed_user: User) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "totally-wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    """Unknown email also returns 401 — no user-existence disclosure."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "anything"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_login_email_is_case_insensitive(client: AsyncClient, seed_user: User) -> None:
    """`users.email` is CITEXT — login works regardless of case."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": seed_user.email.upper(),
            "password": "correct-horse-battery-staple",
        },
    )
    assert resp.status_code == 200


@pytest.mark.integration
async def test_login_with_mfa_enabled_returns_423_with_mfa_token(
    client: AsyncClient, seed_mfa_user: User
) -> None:
    """User with mfa_enabled=true: 423 + MFA challenge, no tokens issued yet."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_mfa_user.email, "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 423
    body = resp.json()
    assert body["mfa_token"]
    assert "totp" in body["methods"]
    # No access_token/refresh_token should be in the body — the user has not
    # completed authentication.
    assert "access_token" not in body
    assert "refresh_token" not in body


@pytest.mark.integration
async def test_login_creates_session_row(
    client: AsyncClient, db_session: AsyncSession, seed_user: User
) -> None:
    """A successful login inserts exactly one active session row."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200

    sessions = (
        (await db_session.execute(select(UserSession).where(UserSession.user_id == seed_user.id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 1
    s = sessions[0]
    assert s.revoked_at is None
    assert s.expires_at > datetime.now(tz=UTC)
    # The plaintext refresh token from the response is NOT what's stored.
    assert s.refresh_token_hmac != resp.json()["refresh_token"]


@pytest.mark.integration
async def test_login_caps_active_sessions_per_user(
    client: AsyncClient, db_session: AsyncSession, seed_user: User
) -> None:
    """Minting a session revokes the user's oldest sessions beyond the cap.

    Bounds the /auth/refresh per-row bcrypt scan: unbounded session growth
    made that scan take ~79s with 359 stale dev sessions, which stranded the
    web layout on a permanent blank screen. The most-recently-active sessions
    survive; the oldest are revoked.
    """
    settings = get_settings()
    now = datetime.now(tz=UTC)
    # Seed cap + 2 active sessions, oldest-active first (i=0 is the least
    # recently active) so we can assert exactly which ones survive.
    seeded: list[UserSession] = []
    for i in range(_MAX_ACTIVE_SESSIONS_PER_USER + 2):
        s = UserSession(
            user_id=seed_user.id,
            refresh_token_hmac=f"seeded-hash-{i}",
            expires_at=now + timedelta(seconds=settings.jwt_refresh_token_ttl_seconds),
            absolute_expires_at=now + timedelta(seconds=settings.session_absolute_timeout_seconds),
            created_at=now - timedelta(minutes=(100 - i)),
            last_active_at=now - timedelta(minutes=(100 - i)),
        )
        db_session.add(s)
        seeded.append(s)
    await db_session.flush()

    # A fresh login mints one more session (the newest) and triggers the cap.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200, resp.text

    active = (
        (
            await db_session.execute(
                select(UserSession).where(
                    UserSession.user_id == seed_user.id,
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                )
            )
        )
        .scalars()
        .all()
    )
    # Exactly the cap remains active (the new login + the newest kept).
    assert len(active) == _MAX_ACTIVE_SESSIONS_PER_USER
    # The two least-recently-active seeded sessions were revoked …
    await db_session.refresh(seeded[0])
    await db_session.refresh(seeded[1])
    assert seeded[0].revoked_at is not None
    assert seeded[1].revoked_at is not None
    # … while the most-recently-active seeded session survives.
    await db_session.refresh(seeded[-1])
    assert seeded[-1].revoked_at is None


@pytest.mark.integration
async def test_login_updates_last_login_at(
    client: AsyncClient, db_session: AsyncSession, seed_user: User
) -> None:
    """`last_login_at` is set to (approximately) now after a successful login."""
    assert seed_user.last_login_at is None
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200
    await db_session.refresh(seed_user)
    assert seed_user.last_login_at is not None


# ---------------------------------------------------------------------------
# /users/me
# ---------------------------------------------------------------------------


async def _login(client: AsyncClient, user: User) -> dict:
    """Convenience helper — log in `user` and return the token bundle."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.integration
async def test_users_me_with_valid_token_returns_profile(
    client: AsyncClient, seed_user: User
) -> None:
    tokens = await _login(client, seed_user)
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(seed_user.id)
    assert body["email"] == seed_user.email
    assert body["mfa_enabled"] is False


@pytest.mark.integration
async def test_users_me_without_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


@pytest.mark.integration
async def test_users_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer this-is-not-a-jwt"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_users_me_with_expired_token_returns_401(
    client: AsyncClient, seed_user: User
) -> None:
    """Hand-craft an expired JWT for `seed_user` and verify it's rejected."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(seed_user.id),
        "email": seed_user.email,
        "is_admin": False,
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),  # expired 1h ago
        "typ": "access",
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_users_me_with_wrong_signature_returns_401(
    client: AsyncClient, seed_user: User
) -> None:
    """A JWT signed with the wrong secret is rejected."""
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(seed_user.id),
        "email": seed_user.email,
        "is_admin": False,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "typ": "access",
    }
    token = pyjwt.encode(payload, "not-the-real-secret", algorithm="HS256")
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_users_me_for_soft_deleted_user_returns_401(
    client: AsyncClient, db_session: AsyncSession, seed_user: User
) -> None:
    """A user with `deleted_at` set is treated as nonexistent for auth."""
    tokens = await _login(client, seed_user)
    seed_user.deleted_at = datetime.now(tz=UTC)
    await db_session.flush()

    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/refresh
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_refresh_with_valid_token_rotates_session(
    client: AsyncClient, db_session: AsyncSession, seed_user: User
) -> None:
    """Refresh issues new tokens AND revokes the old session row."""
    tokens = await _login(client, seed_user)
    old_refresh = tokens["refresh_token"]

    # Brief pause so revoked_at is observably after created_at.
    time.sleep(0.01)

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["refresh_token"] != old_refresh
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == get_settings().jwt_access_token_ttl_seconds

    # Two session rows should now exist for this user — the old one revoked,
    # the new one active.
    sessions = (
        (await db_session.execute(select(UserSession).where(UserSession.user_id == seed_user.id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 2
    revoked = [s for s in sessions if s.revoked_at is not None]
    active = [s for s in sessions if s.revoked_at is None]
    assert len(revoked) == 1
    assert len(active) == 1


@pytest.mark.integration
async def test_refresh_with_garbage_token_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "this-token-was-never-issued"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_refresh_with_revoked_session_returns_401(
    client: AsyncClient, seed_user: User
) -> None:
    """After rotating, the OLD refresh token must not be usable again."""
    tokens = await _login(client, seed_user)
    old_refresh = tokens["refresh_token"]

    # First refresh succeeds and revokes the original session.
    first = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert first.status_code == 200

    # Second use of the original (now-revoked) token must fail.
    second = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert second.status_code == 401


@pytest.mark.integration
async def test_refresh_with_expired_session_returns_401(
    client: AsyncClient, db_session: AsyncSession, seed_user: User
) -> None:
    """A session past `expires_at` is rejected even if not revoked."""
    tokens = await _login(client, seed_user)
    old_refresh = tokens["refresh_token"]

    # Backdate the session's expiry.
    sessions = (
        (await db_session.execute(select(UserSession).where(UserSession.user_id == seed_user.id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 1
    sessions[0].expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_logout_revokes_all_active_sessions(
    client: AsyncClient, db_session: AsyncSession, seed_user: User
) -> None:
    """Logout revokes every active session for the calling user."""
    # Two logins → two active sessions.
    t1 = await _login(client, seed_user)
    t2 = await _login(client, seed_user)
    assert t1["refresh_token"] != t2["refresh_token"]

    sessions = (
        (await db_session.execute(select(UserSession).where(UserSession.user_id == seed_user.id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 2
    assert all(s.revoked_at is None for s in sessions)

    # Logout with the second access token.
    resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {t2['access_token']}"},
    )
    assert resp.status_code == 204

    # Both sessions are now revoked.
    for s in sessions:
        await db_session.refresh(s)
    assert all(s.revoked_at is not None for s in sessions)


@pytest.mark.integration
async def test_logout_without_token_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Full round-trip — the verification described in M1-IMPLEMENTATION-ORDER.md
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_full_round_trip(client: AsyncClient, seed_user: User) -> None:
    """Login → /users/me → refresh → /users/me with new token → logout → expired refresh."""
    # 1) Login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "correct-horse-battery-staple"},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()

    # 2) /users/me with the access token
    me_resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == seed_user.email

    # 3) Refresh. Sleep briefly so the rotated JWT's `iat` falls in a
    # different POSIX second than the original — otherwise the two tokens
    # are byte-identical (same sub/email/is_admin/iat/exp) and equality
    # checks below are meaningless. The refresh token, however, is
    # always fresh randomness regardless of timing.
    time.sleep(1.05)
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_resp.status_code == 200
    rotated = refresh_resp.json()
    assert rotated["access_token"] != tokens["access_token"]
    assert rotated["refresh_token"] != tokens["refresh_token"]

    # 4) /users/me with the rotated access token
    me2_resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert me2_resp.status_code == 200

    # 5) Logout (revokes all active sessions)
    logout_resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert logout_resp.status_code == 204

    # 6) The original (already-rotated, already-revoked) refresh fails.
    fail_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert fail_resp.status_code == 401

    # 7) The rotated refresh token also fails — logout revoked everything.
    fail2_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert fail2_resp.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting — brute-force brakes (SAAS-2, ADR-F059)
# ---------------------------------------------------------------------------


class _Clock:
    """Driven clock for the fake rate-limit backend (no sleeps)."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class _FakeRLBackend:
    """In-memory fixed-window backend injected through the limiter's seam."""

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        self.store: dict[str, tuple[int, float]] = {}

    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = self._clock()
        count, expiry = self.store.get(key, (0, 0.0))
        if now >= expiry:
            count = 0
            expiry = now + window_seconds
        count += 1
        self.store[key] = (count, expiry)
        return count, max(0, round(expiry - now))


@pytest_asyncio.fixture
async def rl_clock() -> _Clock:
    return _Clock()


@pytest_asyncio.fixture
async def rate_limited_client(
    db_session: AsyncSession, rl_clock: _Clock
) -> AsyncIterator[AsyncClient]:
    """Client whose auth endpoints run a REAL limiter over a fake backend.

    Injected through ``get_rate_limiter`` — the same seam the lifespan uses.
    """
    from app.security.rate_limit import RateLimiter, get_rate_limiter

    limiter = RateLimiter(_FakeRLBackend(rl_clock), get_settings())
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_rate_limiter, None)


def _route_depends_on_rate_limiter(path: str, method: str) -> bool:
    """True iff the APIRoute for (path, method) has get_rate_limiter in its
    dependency tree — a structural drift guard so a dropped ``limiter:
    RateLimiterDep`` on any rate-limited endpoint fails loudly (ADR-F059 N3)."""
    from fastapi.routing import APIRoute

    from app.security.rate_limit import get_rate_limiter

    def _tree_has(dependant: object) -> bool:
        if getattr(dependant, "call", None) is get_rate_limiter:
            return True
        return any(_tree_has(sub) for sub in getattr(dependant, "dependencies", []))

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return _tree_has(route.dependant)
    raise AssertionError(f"route not found: {method} {path}")


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/auth/login", "POST"),
        ("/api/v1/auth/refresh", "POST"),
        ("/api/v1/auth/mfa/verify", "POST"),
        ("/api/v1/auth/change-password", "POST"),
        ("/api/v1/auth/mfa/setup", "POST"),
        ("/api/v1/auth/mfa/enable", "POST"),
        ("/api/v1/auth/mfa/disable", "POST"),
        ("/api/v1/admin/bootstrap-status", "GET"),
    ],
)
def test_rate_limiter_wired_on_every_exposed_auth_endpoint(path: str, method: str) -> None:
    """Every internet-facing auth endpoint must carry the rate-limit dependency.

    A behavioural 429 test covers login + refresh; this catches a silently
    dropped ``Depends(get_rate_limiter)`` on the authenticated/MFA endpoints
    (hard to exercise end-to-end) so the brake can't regress unnoticed.
    """
    assert _route_depends_on_rate_limiter(path, method), f"no rate limiter on {method} {path}"


async def _attempt_login(client: AsyncClient, email: str, password: str) -> int:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.status_code


@pytest.mark.integration
async def test_login_brute_force_per_account_returns_429(
    rate_limited_client: AsyncClient, seed_user: User
) -> None:
    """Wrong-password guesses on one account trip the per-account bucket (5/window)."""
    s = get_settings()
    for _ in range(s.rate_limit_login_account_per_window):
        assert await _attempt_login(rate_limited_client, seed_user.email, "wrong") == 401
    # The next attempt is throttled BEFORE the credential check.
    resp = await rate_limited_client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "wrong"},
    )
    assert resp.status_code == 429
    assert "retry-after" in {k.lower() for k in resp.headers}


@pytest.mark.integration
async def test_login_brute_force_per_ip_returns_429(rate_limited_client: AsyncClient) -> None:
    """Distinct emails from one IP trip the per-IP bucket (10/window) with no account trip."""
    s = get_settings()
    for i in range(s.rate_limit_login_ip_per_window):
        # A fresh nonexistent email each time → account bucket never accumulates.
        assert await _attempt_login(rate_limited_client, f"nobody-{i}@example.com", "x") == 401
    resp = await rate_limited_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody-final@example.com", "password": "x"},
    )
    assert resp.status_code == 429


@pytest.mark.integration
async def test_login_429_shape_identical_for_nonexistent_account(
    rate_limited_client: AsyncClient,
) -> None:
    """A throttled nonexistent account gets the same 429 shape — no existence leak."""
    s = get_settings()
    email = "ghost@example.com"
    for _ in range(s.rate_limit_login_account_per_window):
        assert await _attempt_login(rate_limited_client, email, "x") == 401
    resp = await rate_limited_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "x"}
    )
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") is not None
    # Uniform message — reveals nothing about whether the account exists.
    assert resp.json()["detail"] == "Too many requests. Please slow down and try again shortly."


@pytest.mark.integration
async def test_login_window_expiry_restores_service(
    rate_limited_client: AsyncClient, rl_clock: _Clock, seed_user: User
) -> None:
    """After the window rolls over, a legitimate login succeeds again."""
    s = get_settings()
    for _ in range(s.rate_limit_login_account_per_window):
        await _attempt_login(rate_limited_client, seed_user.email, "wrong")
    blocked = await rate_limited_client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "wrong"},
    )
    assert blocked.status_code == 429

    rl_clock.advance(s.rate_limit_window_seconds + 1)

    ok = await rate_limited_client.post(
        "/api/v1/auth/login",
        json={"email": seed_user.email, "password": "correct-horse-battery-staple"},
    )
    assert ok.status_code == 200


@pytest.mark.integration
async def test_successful_logins_within_limit_unaffected(
    rate_limited_client: AsyncClient, seed_user: User
) -> None:
    """Logins under the limit are never throttled."""
    for _ in range(3):
        resp = await rate_limited_client.post(
            "/api/v1/auth/login",
            json={"email": seed_user.email, "password": "correct-horse-battery-staple"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /auth/refresh — HMAC index kills the O(n) bcrypt scan (SAAS-2, ADR-F059)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_refresh_scan_and_matcher_are_gone() -> None:
    """The bcrypt-scan machinery no longer exists (structural regression guard)."""
    import app.api.auth as auth_module
    import app.security as security_module

    assert not hasattr(auth_module, "_match_candidate")
    assert not hasattr(security_module, "refresh_token_matches")
    assert not hasattr(security_module, "hash_refresh_token")
    assert hasattr(security_module, "hmac_refresh_token")


@pytest.mark.integration
async def test_refresh_garbage_token_does_zero_bcrypt(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A garbage refresh with 50 seeded sessions is a cheap indexed miss — no bcrypt."""
    import bcrypt

    now = datetime.now(tz=UTC)
    settings = get_settings()
    for i in range(50):
        db_session.add(
            UserSession(
                user_id=seed_user.id,
                refresh_token_hmac=f"seed-hmac-{i}",
                expires_at=now + timedelta(seconds=settings.jwt_refresh_token_ttl_seconds),
                absolute_expires_at=now
                + timedelta(seconds=settings.session_absolute_timeout_seconds),
                last_active_at=now,
            )
        )
    await db_session.flush()

    calls = {"n": 0}
    real_checkpw = bcrypt.checkpw

    def _counting_checkpw(*args: object, **kwargs: object) -> bool:
        calls["n"] += 1
        return real_checkpw(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(bcrypt, "checkpw", _counting_checkpw)

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "never-issued-token"},
    )
    assert resp.status_code == 401
    assert calls["n"] == 0  # the refresh path bcrypt-compares nothing now


@pytest.mark.integration
async def test_refresh_rotated_pair_is_usable(client: AsyncClient, seed_user: User) -> None:
    """login → refresh → the rotated refresh token itself refreshes again."""
    tokens = await _login(client, seed_user)
    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200, first.text
    rotated = first.json()["refresh_token"]
    assert rotated != tokens["refresh_token"]

    second = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated})
    assert second.status_code == 200, second.text
    assert second.json()["refresh_token"] != rotated
