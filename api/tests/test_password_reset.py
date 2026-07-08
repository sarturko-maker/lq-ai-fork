"""SETUP-3a (ADR-F061) — password reset: anti-enumeration request + single-use
confirm that revokes sessions.

The reset-request response is uniform 202 whether or not the account exists.
The reset token plaintext is never returned by any endpoint (it only ships in
the email), so the confirm tests mint the token via the service directly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_tokens import PASSWORD_RESET, hash_auth_token, issue_password_reset
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserSession
from app.models.user_auth_token import UserAuthToken
from app.security import hash_password


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


async def _make_user(
    db: AsyncSession, *, password: str = "correct-horse-battery", disabled: bool = False
) -> User:
    user = User(
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password(password),
        role="member",
        disabled_at=datetime.now(UTC) if disabled else None,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_session(db: AsyncSession, user: User) -> UserSession:
    now = datetime.now(UTC)
    sess = UserSession(
        user_id=user.id,
        refresh_token_hmac=uuid.uuid4().hex + uuid.uuid4().hex,  # 64 hex chars, unique
        expires_at=now + timedelta(days=1),
        absolute_expires_at=now + timedelta(hours=8),
        last_active_at=now,
    )
    db.add(sess)
    await db.flush()
    return sess


# ---------------------------------------------------------------------------
# password-reset-request (anti-enumeration)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_request_uniform_for_existing_and_missing(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing vs missing email → byte-identical status AND body."""

    async def _fake_send(**_kwargs: object) -> bool:
        return True

    monkeypatch.setattr("app.api.auth.send_password_reset_email", _fake_send)

    user = await _make_user(db_session)
    existing = await client.post("/api/v1/auth/password-reset-request", json={"email": user.email})
    missing = await client.post(
        "/api/v1/auth/password-reset-request",
        json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert existing.status_code == 202
    assert missing.status_code == 202
    assert existing.json() == {"status": "ok"}
    assert existing.content == missing.content


@pytest.mark.integration
async def test_request_issues_token_for_existing(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    async def _capture(*, to_addr: str, reset_url: str, product_name: str = "LQ.AI") -> bool:
        captured.append(to_addr)
        return True

    monkeypatch.setattr("app.api.auth.send_password_reset_email", _capture)

    user = await _make_user(db_session)
    resp = await client.post("/api/v1/auth/password-reset-request", json={"email": user.email})
    assert resp.status_code == 202
    assert captured == [user.email]

    row = (
        await db_session.execute(
            select(UserAuthToken).where(
                UserAuthToken.user_id == user.id,
                UserAuthToken.purpose == PASSWORD_RESET,
            )
        )
    ).scalar_one()
    assert row.expires_at is not None


@pytest.mark.integration
async def test_request_disabled_user_issues_no_token(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A disabled account still gets a uniform 202 but no reset token/email."""
    sent: list[str] = []

    async def _capture(*, to_addr: str, reset_url: str, product_name: str = "LQ.AI") -> bool:
        sent.append(to_addr)
        return True

    monkeypatch.setattr("app.api.auth.send_password_reset_email", _capture)

    user = await _make_user(db_session, disabled=True)
    resp = await client.post("/api/v1/auth/password-reset-request", json={"email": user.email})
    assert resp.status_code == 202
    assert sent == []
    count = (
        (await db_session.execute(select(UserAuthToken).where(UserAuthToken.user_id == user.id)))
        .scalars()
        .all()
    )
    assert count == []


# ---------------------------------------------------------------------------
# password-reset (confirm)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_reset_completes_changes_password_and_revokes_sessions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _make_user(db_session, password="old-password-123")
    sess = await _make_session(db_session, user)
    plaintext, _token = await issue_password_reset(db_session, user_id=user.id, ttl_seconds=3600)

    resp = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": plaintext, "new_password": "brand-new-passphrase-9"},
    )
    assert resp.status_code == 204, resp.text

    # Old password no longer works; new one does.
    old = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "old-password-123"}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "brand-new-passphrase-9"}
    )
    assert new.status_code == 200, new.text

    # The pre-existing session was revoked.
    await db_session.refresh(sess)
    assert sess.revoked_at is not None


@pytest.mark.integration
async def test_reset_token_is_single_use(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    plaintext, _token = await issue_password_reset(db_session, user_id=user.id, ttl_seconds=3600)
    first = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": plaintext, "new_password": "brand-new-passphrase-9"},
    )
    assert first.status_code == 204, first.text
    second = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": plaintext, "new_password": "another-passphrase-10"},
    )
    assert second.status_code == 400, second.text


@pytest.mark.integration
async def test_reset_invalid_token_is_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": "not-a-real-token", "new_password": "brand-new-passphrase-9"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.integration
async def test_reset_expired_token_is_400(client: AsyncClient, db_session: AsyncSession) -> None:
    """An expired token gets the same uniform 400 (no distinguishing signal)."""
    user = await _make_user(db_session)
    plaintext, _token = await issue_password_reset(
        db_session,
        user_id=user.id,
        ttl_seconds=-1,  # already expired
    )
    resp = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": plaintext, "new_password": "brand-new-passphrase-9"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.integration
async def test_reset_short_password_is_400(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    plaintext, _token = await issue_password_reset(db_session, user_id=user.id, ttl_seconds=3600)
    resp = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": plaintext, "new_password": "short"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.integration
async def test_reset_token_stores_hmac_only(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    plaintext, token = await issue_password_reset(db_session, user_id=user.id, ttl_seconds=3600)
    assert token.token_hmac == hash_auth_token(PASSWORD_RESET, plaintext)
    assert len(token.token_hmac) == 64
    assert plaintext not in token.token_hmac


# ---------------------------------------------------------------------------
# rate limiting (SAAS-2 mechanism applied to the new surfaces)
# ---------------------------------------------------------------------------


class _FakeRLBackend:
    """In-memory fixed-window backend injected through the limiter seam."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key], window_seconds


@pytest.mark.integration
async def test_reset_request_rate_limited_429_with_retry_after(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-submitted-email bucket trips 429 + Retry-After past the window."""
    from app.config import Settings
    from app.security.rate_limit import RateLimiter, get_rate_limiter

    async def _fake_send(**_kwargs: object) -> bool:
        return True

    monkeypatch.setattr("app.api.auth.send_password_reset_email", _fake_send)

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        rate_limit_password_reset_request_email_per_window=1,
        rate_limit_password_reset_request_ip_per_window=100,
    )
    limiter = RateLimiter(_FakeRLBackend(), settings)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
            first = await ac.post("/api/v1/auth/password-reset-request", json={"email": email})
            assert first.status_code == 202
            blocked = await ac.post("/api/v1/auth/password-reset-request", json={"email": email})
            assert blocked.status_code == 429
            assert "Retry-After" in blocked.headers
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_rate_limiter, None)


# ---------------------------------------------------------------------------
# security-review fixes 1-4
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_reset_request_email_send_runs_after_response(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 1 — the send is a BACKGROUND task, never awaited inside the request.

    Wraps the ASGI app to record when the final response body is sent; the fake
    sender records when it runs. Order must be response first, send second —
    proving the exists-branch does not carry the SMTP latency (the timing
    oracle the uniform 202 exists to prevent).
    """
    events: list[str] = []

    async def _fake_send(*, to_addr: str, reset_url: str, product_name: str = "LQ.AI") -> bool:
        events.append("send")
        return True

    monkeypatch.setattr("app.api.auth.send_password_reset_email", _fake_send)

    async def _wrapped_app(scope, receive, send):  # type: ignore[no-untyped-def]
        async def _send(message):  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                events.append("response_sent")
            await send(message)

        await app(scope, receive, _send)

    user = await _make_user(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=_wrapped_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/v1/auth/password-reset-request", json={"email": user.email})
            assert resp.status_code == 202
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert events == ["response_sent", "send"], events


@pytest.mark.integration
async def test_second_reset_request_revokes_first_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Fix 2 — issuing a new reset token revokes the prior one (one live link)."""
    user = await _make_user(db_session)
    first_plaintext, first_token = await issue_password_reset(
        db_session, user_id=user.id, ttl_seconds=3600
    )
    second_plaintext, _second = await issue_password_reset(
        db_session, user_id=user.id, ttl_seconds=3600
    )

    await db_session.refresh(first_token)
    assert first_token.revoked_at is not None

    # The first link is dead — uniform 400.
    dead = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": first_plaintext, "new_password": "brand-new-passphrase-9"},
    )
    assert dead.status_code == 400, dead.text

    # The second (latest) link works.
    ok = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": second_plaintext, "new_password": "brand-new-passphrase-9"},
    )
    assert ok.status_code == 204, ok.text


@pytest.mark.integration
async def test_completed_reset_revokes_sibling_tokens(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Fix 2 — a successful reset revokes any other outstanding reset token.

    The sibling is inserted directly (bypassing issue_password_reset's
    revoke-first) to simulate any path that could leave two live tokens.
    """
    from app.auth_tokens import generate_token

    user = await _make_user(db_session)
    plaintext_a, _token_a = await issue_password_reset(
        db_session, user_id=user.id, ttl_seconds=3600
    )
    sibling_plaintext = generate_token()
    sibling = UserAuthToken(
        purpose=PASSWORD_RESET,
        user_id=user.id,
        token_hmac=hash_auth_token(PASSWORD_RESET, sibling_plaintext),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sibling)
    await db_session.flush()

    ok = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": plaintext_a, "new_password": "brand-new-passphrase-9"},
    )
    assert ok.status_code == 204, ok.text

    await db_session.refresh(sibling)
    assert sibling.revoked_at is not None

    dead = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": sibling_plaintext, "new_password": "another-passphrase-10"},
    )
    assert dead.status_code == 400, dead.text


@pytest.mark.unit
@pytest.mark.parametrize("bad_base", ["https://", "https:", "http://", "   "])
def test_scheme_only_base_url_falls_back_to_path_only(
    bad_base: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 3 — a scheme-only PUBLIC_BASE_URL yields the path-only fallback,
    never a malformed "https:/reset-password?..." link."""
    from app.config import get_settings
    from app.lifecycle_email import build_accept_url, build_reset_url

    monkeypatch.setattr(get_settings(), "public_base_url", bad_base)
    assert build_reset_url("tok") == "/lq-ai/reset-password?token=tok"
    assert build_accept_url("tok") == "/lq-ai/accept-invite?token=tok"


@pytest.mark.unit
def test_real_base_url_builds_absolute_links(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix 3 companion — a real base still builds absolute links (trailing / trimmed)."""
    from app.config import get_settings
    from app.lifecycle_email import build_reset_url

    monkeypatch.setattr(get_settings(), "public_base_url", "https://tenant.example.com/")
    assert build_reset_url("tok") == "https://tenant.example.com/lq-ai/reset-password?token=tok"


@pytest.mark.integration
async def test_reset_confirm_refused_for_disabled_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Fix 4 — an account disabled AFTER the token was issued cannot complete
    the reset; the refusal is the uniform 400."""
    user = await _make_user(db_session)
    plaintext, _token = await issue_password_reset(db_session, user_id=user.id, ttl_seconds=3600)

    user.disabled_at = datetime.now(UTC)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/password-reset",
        json={"token": plaintext, "new_password": "brand-new-passphrase-9"},
    )
    assert resp.status_code == 400, resp.text
