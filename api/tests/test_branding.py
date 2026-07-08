"""Tests for the BRAND-1a deployment-branding surface (ADR-F068).

Covers the contract documented in :mod:`app.api.branding`:

* The GET is unauthenticated (login screen consults it pre-auth), returns
  200 defaults on an empty singleton (never 404) and carries the bounded
  cache header. Per-IP rate limiting is exercised at the limiter level
  (the ASGITransport test app runs the fail-open null limiter).
* PUT is admin-only, upserts the singleton, audit-logs counts/lengths
  only, and REJECTS control characters in ``product_name`` (SMTP subject
  header-injection surface) and anything outside the closed palette
  allowlist.
* The logo endpoints sniff magic bytes (PNG/JPEG/WEBP), never trust the
  client-declared content type (SVG with a spoofed ``image/png`` header
  is refused), enforce the 512 KB cap with 413, and serve the SNIFFED
  type with nosniff/inline/immutable headers.
* ``ensure_first_run_branding`` seeds from BRAND_* env exactly once
  (empty table only; admin rows win), fanning an accent out into the
  brandable token family (drift-guarded against the API allowlist).
* The email composer carries the configured product name into the
  subject and strips CR/LF belt-and-braces (composed message inspected —
  no SMTP).

Tests run against the same SAVEPOINT-rolled-back per-test session as the
rest of the API tests (per ``tests/conftest.py``).
"""

from __future__ import annotations

import re
import types
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_bootstrap import ensure_first_run_branding
from app.api.branding import ALLOWED_PALETTE_TOKENS, LOGO_MAX_BYTES
from app.config import Settings, get_settings
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, DeploymentBranding, User
from app.security import create_access_token, hash_password

# Minimal payloads whose MAGIC BYTES satisfy the sniffer — content beyond the
# signature is irrelevant (the server never decodes).
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP_BYTES = b"RIFF" + (36).to_bytes(4, "little") + b"WEBP" + b"\x00" * 32
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


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
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"branding-admin-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Branding Admin",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=True,
        mfa_enabled=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"branding-user-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Regular User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _bearer(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /branding — unauthenticated read
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_branding_is_unauthenticated_with_defaults(client: AsyncClient) -> None:
    """No token, empty singleton → 200 with defaults, never 401/404."""
    resp = await client.get("/api/v1/branding")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["product_name"] == ""
    assert body["palette"] == {}
    assert body["logo_version"] is None
    assert body["updated_at"] is None


@pytest.mark.integration
async def test_get_branding_carries_bounded_cache_header(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/branding")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=300"


@pytest.mark.integration
async def test_get_branding_returns_configured_values(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    db_session.add(
        DeploymentBranding(
            product_name="Acme Legal",
            palette={"light": {"brand": "#c02020"}},
            updated_by=admin_user.id,
        )
    )
    await db_session.flush()

    resp = await client.get("/api/v1/branding")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["product_name"] == "Acme Legal"
    assert body["palette"] == {"light": {"brand": "#c02020"}}
    # No logo yet → no version to cache-bust with.
    assert body["logo_version"] is None
    assert body["updated_at"] is not None


@pytest.mark.unit
async def test_enforce_branding_rate_limits_per_ip() -> None:
    """The enforce_branding bucket 429s past the per-IP limit (unit-level:
    the ASGITransport app runs the fail-open null limiter, so the brake is
    exercised at the limiter seam like the other auth buckets)."""
    from fastapi import HTTPException

    from app.security.rate_limit import RateLimiter

    class _Backend:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}

        async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key], window_seconds

    settings = Settings(_env_file=None, rate_limit_branding_ip_per_window=2)  # type: ignore[call-arg]
    limiter = RateLimiter(_Backend(), settings)  # type: ignore[arg-type]
    request = types.SimpleNamespace(client=types.SimpleNamespace(host="203.0.113.7"))

    await limiter.enforce_branding(request)  # type: ignore[arg-type]
    await limiter.enforce_branding(request)  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc:
        await limiter.enforce_branding(request)  # type: ignore[arg-type]
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


# ---------------------------------------------------------------------------
# PUT /branding — admin upsert + boundary validation
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_put_creates_singleton_and_get_reflects_it(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    payload = {
        "product_name": "Acme Legal",
        "palette": {"light": {"brand": "#c02020"}, "dark": {"brand": "#ff6a6a"}},
    }
    resp = await client.put("/api/v1/branding", headers=_bearer(admin_user), json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["product_name"] == "Acme Legal"
    assert body["palette"]["dark"]["brand"] == "#ff6a6a"

    rows = (await db_session.execute(select(DeploymentBranding))).scalars().all()
    assert len(rows) == 1
    assert rows[0].updated_by == admin_user.id

    unauth = await client.get("/api/v1/branding")
    assert unauth.json()["product_name"] == "Acme Legal"


@pytest.mark.integration
async def test_put_converges_to_a_single_row(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    """PUT is an upsert — a second PUT replaces, never adds a row."""
    first = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": "First Name", "palette": {}},
    )
    assert first.status_code == 200, first.text
    second = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": "Second Name", "palette": {}},
    )
    assert second.status_code == 200, second.text
    assert second.json()["product_name"] == "Second Name"

    rows = (await db_session.execute(select(DeploymentBranding))).scalars().all()
    assert len(rows) == 1, "PUT must not create a second singleton row"
    assert rows[0].product_name == "Second Name"


@pytest.mark.integration
async def test_put_by_non_admin_returns_403(client: AsyncClient, regular_user: User) -> None:
    resp = await client.put(
        "/api/v1/branding",
        headers=_bearer(regular_user),
        json={"product_name": "Nope", "palette": {}},
    )
    assert resp.status_code == 403


@pytest.mark.integration
async def test_put_without_bearer_returns_401(client: AsyncClient) -> None:
    resp = await client.put("/api/v1/branding", json={"product_name": "Nope", "palette": {}})
    assert resp.status_code == 401


@pytest.mark.integration
async def test_put_audit_logs_counts_only(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    resp = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": "Audited Name", "palette": {"light": {"brand": "#c02020"}}},
    )
    assert resp.status_code == 200, resp.text

    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.user_id == admin_user.id)))
        .scalars()
        .all()
    )
    matched = [r for r in rows if r.action == "deployment_branding.updated"]
    assert matched, "PUT must emit a deployment_branding.updated audit row"
    details = matched[0].details or {}
    assert details == {
        "product_name_length": len("Audited Name"),
        "palette_theme_count": 1,
        "palette_token_count": 1,
    }
    # Counts/lengths only — never the configured values themselves.
    assert "Audited Name" not in str(details)
    assert "#c02020" not in str(details)


@pytest.mark.integration
@pytest.mark.parametrize(
    "bad_name",
    [
        "Acme\r\nBcc: evil@example.com",
        "Acme\nLegal",
        "Acme\x00",
        "Acme\x85Legal",  # C1 control (NEL) — not caught by an ord()<32 check
        "Acme\u2028Legal",  # Unicode line separator (Zl)
        "Acme\u202egnp.txt",  # RTL override (Cf) — display spoofing
    ],
)
async def test_put_rejects_control_characters_in_name(
    client: AsyncClient, admin_user: User, bad_name: str
) -> None:
    """Control/format/line-separator chars → 422 (the name lands in SMTP
    subject headers; C1 and U+2028/29 count, not just C0/DEL)."""
    resp = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": bad_name, "palette": {}},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.unit
def test_shared_control_char_rules_cover_c1_and_separators() -> None:
    """The single-source predicate/strip pair (app/models/deployment_branding)
    covers C0, C1, DEL, U+2028/29 and format chars — and both sides agree."""
    from app.models.deployment_branding import contains_control_chars, strip_control_chars

    for bad in ["\r", "\n", "\x00", "\x7f", "\x85", "\u2028", "\u2029", "\u202e", "\u200b"]:
        assert contains_control_chars(f"Acme{bad}Legal"), f"{bad!r} must be flagged"
        assert strip_control_chars(f"Acme{bad}Legal") == "AcmeLegal", f"{bad!r} must strip"
    # Ordinary names (incl. spaces and punctuation) pass untouched.
    assert not contains_control_chars("Acme Legal & Co. GmbH")
    assert strip_control_chars("Acme Legal & Co. GmbH") == "Acme Legal & Co. GmbH"


@pytest.mark.integration
async def test_put_rejects_overlong_name(client: AsyncClient, admin_user: User) -> None:
    resp = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": "x" * 81, "palette": {}},
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_put_rejects_unknown_palette_theme(client: AsyncClient, admin_user: User) -> None:
    resp = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": "", "palette": {"sepia": {"brand": "#c02020"}}},
    )
    assert resp.status_code == 422
    assert "sepia" in resp.text


@pytest.mark.integration
async def test_put_rejects_unknown_palette_token(client: AsyncClient, admin_user: User) -> None:
    """--primary is ink by design — not brandable, and unknown keys never store."""
    resp = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": "", "palette": {"light": {"primary": "#c02020"}}},
    )
    assert resp.status_code == 422
    assert "primary" in resp.text


@pytest.mark.integration
@pytest.mark.parametrize(
    "bad_value",
    ["red", "#fff", "#c02020;} body{display:none", "url(javascript:alert(1))", "#c0202g"],
)
async def test_put_rejects_non_hex_palette_values(
    client: AsyncClient, admin_user: User, bad_value: str
) -> None:
    resp = await client.put(
        "/api/v1/branding",
        headers=_bearer(admin_user),
        json={"product_name": "", "palette": {"light": {"brand": bad_value}}},
    )
    assert resp.status_code == 422, f"{bad_value!r} must be rejected"


# ---------------------------------------------------------------------------
# Logo upload / serve / delete
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    ("data", "expected_type"),
    [
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (WEBP_BYTES, "image/webp"),
    ],
)
async def test_logo_upload_sniffs_and_serves_raster_types(
    client: AsyncClient, admin_user: User, data: bytes, expected_type: str
) -> None:
    """Accepted magic bytes → stored + served under the SNIFFED type, with
    the nosniff/inline/immutable headers. The client-declared content type
    is deliberately wrong here to prove it is ignored."""
    up = await client.post(
        "/api/v1/branding/logo",
        headers=_bearer(admin_user),
        files={"file": ("logo.bin", data, "application/octet-stream")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["logo_version"] is not None

    served = await client.get("/api/v1/branding/logo")
    assert served.status_code == 200
    assert served.headers["content-type"] == expected_type
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["content-disposition"] == "inline"
    assert served.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert served.content == data


@pytest.mark.integration
async def test_logo_upload_rejects_svg_with_spoofed_png_header(
    client: AsyncClient, admin_user: User
) -> None:
    """SVG bytes declaring image/png → 422: the sniff, not the header, decides."""
    resp = await client.post(
        "/api/v1/branding/logo",
        headers=_bearer(admin_user),
        files={"file": ("logo.png", SVG_BYTES, "image/png")},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
async def test_logo_upload_rejects_oversize_with_413(client: AsyncClient, admin_user: User) -> None:
    oversized = PNG_BYTES + b"\x00" * LOGO_MAX_BYTES  # valid magic, > 512 KB
    resp = await client.post(
        "/api/v1/branding/logo",
        headers=_bearer(admin_user),
        files={"file": ("logo.png", oversized, "image/png")},
    )
    assert resp.status_code == 413, resp.text


@pytest.mark.integration
async def test_logo_upload_by_non_admin_returns_403(
    client: AsyncClient, regular_user: User
) -> None:
    resp = await client.post(
        "/api/v1/branding/logo",
        headers=_bearer(regular_user),
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 403


@pytest.mark.integration
async def test_logo_upload_audit_logs_size_and_type_only(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    resp = await client.post(
        "/api/v1/branding/logo",
        headers=_bearer(admin_user),
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.user_id == admin_user.id)))
        .scalars()
        .all()
    )
    matched = [r for r in rows if r.action == "deployment_branding.logo_uploaded"]
    assert matched
    assert matched[0].details == {
        "logo_size_bytes": len(PNG_BYTES),
        "logo_content_type": "image/png",
    }


@pytest.mark.integration
async def test_logo_get_404_when_unset(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/branding/logo")
    assert resp.status_code == 404


@pytest.mark.integration
async def test_logo_version_is_updated_at_ms_epoch_after_upload(
    client: AsyncClient, admin_user: User
) -> None:
    """logo_version is opaque to clients but derives from updated_at at
    MILLISECOND resolution — whole seconds would let two uploads in the same
    second share a version, pinning the immutable-cached (1y) old logo."""
    up = await client.post(
        "/api/v1/branding/logo",
        headers=_bearer(admin_user),
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert up.status_code == 200, up.text
    body = up.json()
    updated_at = datetime.fromisoformat(body["updated_at"])
    assert body["logo_version"] == int(updated_at.timestamp() * 1000)


@pytest.mark.integration
async def test_logo_delete_clears_and_audits(
    client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    up = await client.post(
        "/api/v1/branding/logo",
        headers=_bearer(admin_user),
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert up.status_code == 200, up.text

    deleted = await client.delete("/api/v1/branding/logo", headers=_bearer(admin_user))
    assert deleted.status_code == 204

    gone = await client.get("/api/v1/branding/logo")
    assert gone.status_code == 404
    # The name/palette row survives with the logo columns nulled.
    row = (await db_session.execute(select(DeploymentBranding))).scalar_one()
    assert row.logo_bytes is None
    assert row.logo_content_type is None

    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.user_id == admin_user.id)))
        .scalars()
        .all()
    )
    assert any(r.action == "deployment_branding.logo_deleted" for r in rows)


@pytest.mark.integration
async def test_logo_delete_404_when_unset(client: AsyncClient, admin_user: User) -> None:
    resp = await client.delete("/api/v1/branding/logo", headers=_bearer(admin_user))
    assert resp.status_code == 404


@pytest.mark.integration
async def test_logo_delete_by_non_admin_returns_403(
    client: AsyncClient, regular_user: User
) -> None:
    resp = await client.delete("/api/v1/branding/logo", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# ensure_first_run_branding — BRAND_* seed (ADR-F068)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_seed_noop_when_nothing_configured(db_session: AsyncSession) -> None:
    """Shipped defaults (no BRAND_*) → clean no-op, no row."""
    settings = get_settings()
    assert settings.brand_product_name == ""
    assert settings.brand_accent_light is None
    assert settings.brand_accent_dark is None

    seeded = await ensure_first_run_branding(db_session)
    assert seeded is False
    rows = (await db_session.execute(select(DeploymentBranding))).scalars().all()
    assert rows == []


@pytest.mark.integration
async def test_seed_creates_row_with_accent_fan_out(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "brand_product_name", "Acme Legal")
    monkeypatch.setattr(settings, "brand_accent_light", "#c02020")
    monkeypatch.setattr(settings, "brand_accent_dark", "#ff6a6a")

    seeded = await ensure_first_run_branding(db_session)
    assert seeded is True

    row = (await db_session.execute(select(DeploymentBranding))).scalar_one()
    assert row.product_name == "Acme Legal"
    for theme, accent, foreground in (
        ("light", "#c02020", "#ffffff"),
        ("dark", "#ff6a6a", "#111111"),
    ):
        tokens = row.palette[theme]
        # Drift guard: the seeder's fan-out must stay inside the API allowlist.
        assert set(tokens) == set(ALLOWED_PALETTE_TOKENS)
        for key in ("brand", "ring", "sidebar_ring", "status_running", "chart_1"):
            assert tokens[key] == accent
        assert tokens["brand_foreground"] == foreground
        # The wash is derived — a valid hex in the accent's hue, not the accent.
        assert re.fullmatch(r"#[0-9a-f]{6}", tokens["status_running_wash"])
        assert tokens["status_running_wash"] != accent


@pytest.mark.integration
async def test_seed_idempotent_and_never_overwrites_existing_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing (admin-written) row blocks the seed — env never wins."""
    db_session.add(DeploymentBranding(product_name="Admin Chosen", palette={}))
    await db_session.flush()

    settings = get_settings()
    monkeypatch.setattr(settings, "brand_product_name", "Env Name")

    seeded = await ensure_first_run_branding(db_session)
    assert seeded is False
    rows = (await db_session.execute(select(DeploymentBranding))).scalars().all()
    assert len(rows) == 1
    assert rows[0].product_name == "Admin Chosen"

    # And a second run over the seeder's own row is equally a no-op.
    seeded_again = await ensure_first_run_branding(db_session)
    assert seeded_again is False


@pytest.mark.integration
async def test_seed_skips_invalid_accent_but_keeps_valid_name(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid accent is warned about and skipped — never sanitized."""
    settings = get_settings()
    monkeypatch.setattr(settings, "brand_product_name", "Acme Legal")
    monkeypatch.setattr(settings, "brand_accent_light", "not-a-colour")

    seeded = await ensure_first_run_branding(db_session)
    assert seeded is True
    row = (await db_session.execute(select(DeploymentBranding))).scalar_one()
    assert row.product_name == "Acme Legal"
    assert row.palette == {}


@pytest.mark.integration
async def test_seed_rejects_control_chars_in_env_name(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A control-char name is dropped; with nothing else set, no row seeds."""
    settings = get_settings()
    monkeypatch.setattr(settings, "brand_product_name", "Acme\r\nBcc: evil@example.com")

    seeded = await ensure_first_run_branding(db_session)
    assert seeded is False
    rows = (await db_session.execute(select(DeploymentBranding))).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# Email composition — the subject carries the configured name (no SMTP)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_invite_subject_carries_product_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import lifecycle_email

    captured: list[dict[str, str]] = []

    async def _capture(*, to_addr: str, subject: str, body: str) -> bool:
        captured.append({"to_addr": to_addr, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(lifecycle_email, "send_email", _capture)

    ok = await lifecycle_email.send_invite_email(
        to_addr="new-user@example.com",
        accept_url="https://tenant.example.com/lq-ai/accept-invite?token=x",
        product_name="Acme Legal",
    )
    assert ok is True
    assert captured[0]["subject"] == "You've been invited to Acme Legal"
    assert "An administrator has invited you to Acme Legal." in captured[0]["body"]


@pytest.mark.unit
async def test_reset_subject_carries_product_name_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import lifecycle_email

    captured: list[str] = []

    async def _capture(*, to_addr: str, subject: str, body: str) -> bool:
        captured.append(subject)
        return True

    monkeypatch.setattr(lifecycle_email, "send_email", _capture)

    await lifecycle_email.send_password_reset_email(
        to_addr="user@example.com",
        reset_url="https://tenant.example.com/lq-ai/reset-password?token=x",
        product_name="Acme Legal",
    )
    # Default kwarg keeps the shipped brand.
    await lifecycle_email.send_password_reset_email(
        to_addr="user@example.com",
        reset_url="https://tenant.example.com/lq-ai/reset-password?token=x",
    )
    assert captured == ["Reset your Acme Legal password", "Reset your LQ.AI password"]


@pytest.mark.unit
async def test_composer_strips_crlf_belt_and_braces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if a hostile name reached the composer, no CR/LF lands in the
    subject header (the PUT boundary already rejects; this is depth)."""
    from app import lifecycle_email

    captured: list[str] = []

    async def _capture(*, to_addr: str, subject: str, body: str) -> bool:
        captured.append(subject)
        return True

    monkeypatch.setattr(lifecycle_email, "send_email", _capture)

    await lifecycle_email.send_invite_email(
        to_addr="x@example.com",
        accept_url="https://tenant.example.com/lq-ai/accept-invite?token=x",
        product_name="Acme\r\nBcc: evil@example.com",
    )
    assert "\r" not in captured[0]
    assert "\n" not in captured[0]
    assert captured[0] == "You've been invited to AcmeBcc: evil@example.com"

    # Same character classes as the boundary: C1 controls (NEL) and format
    # chars (RTL override) strip too, not just C0/DEL.
    await lifecycle_email.send_invite_email(
        to_addr="x@example.com",
        accept_url="https://tenant.example.com/lq-ai/accept-invite?token=x",
        product_name="Acme\x85\u202eLegal",
    )
    assert captured[1] == "You've been invited to AcmeLegal"


@pytest.mark.integration
async def test_get_branding_name_reads_singleton_with_default(
    db_session: AsyncSession,
) -> None:
    from app.lifecycle_email import get_branding_name

    assert await get_branding_name(db_session) == "LQ.AI"

    db_session.add(DeploymentBranding(product_name="Acme Legal", palette={}))
    await db_session.flush()
    assert await get_branding_name(db_session) == "Acme Legal"
