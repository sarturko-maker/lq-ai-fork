"""Integration tests for the gateway-facing internal-skills endpoint (C2).

Covers the wire side of ``GET /api/v1/internal/skills/{skill_name}`` —
the route the gateway calls during prompt assembly per ADR 0006. The
route is auth-gated by ``X-LQ-AI-Gateway-Key`` (constant-time compare),
not by user token.

Mirrors the patterns in ``test_skill_endpoints.py`` so the two surfaces
share fixture machinery.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.organization_profile import OrganizationProfile
from app.skills import load_registry
from app.skills.registry import MutableSkillRegistry

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"

VALID_KEY = "test-gateway-secret-correct-horse"


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def client_with_key(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """In-process AsyncClient with skill registry installed and a known key."""

    monkeypatch.setenv("LQ_AI_GATEWAY_KEY", VALID_KEY)
    get_settings.cache_clear()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    holder = MutableSkillRegistry(load_registry(FIXTURES_DIR))
    prior_holder = getattr(app.state, "skill_registry", None)
    app.state.skill_registry = holder

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    if prior_holder is None:
        delattr(app.state, "skill_registry")
    else:
        app.state.skill_registry = prior_holder
    app.dependency_overrides.pop(get_db, None)
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client_without_key(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """Client where the operator has not configured LQ_AI_GATEWAY_KEY."""

    monkeypatch.setenv("LQ_AI_GATEWAY_KEY", "")
    get_settings.cache_clear()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    holder = MutableSkillRegistry(load_registry(FIXTURES_DIR))
    prior_holder = getattr(app.state, "skill_registry", None)
    app.state.skill_registry = holder

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    if prior_holder is None:
        delattr(app.state, "skill_registry")
    else:
        app.state.skill_registry = prior_holder
    app.dependency_overrides.pop(get_db, None)
    get_settings.cache_clear()


@pytest.mark.integration
async def test_internal_skill_unauthenticated_returns_401(client_with_key: AsyncClient) -> None:
    """No gateway-key header → 401 with structured envelope."""

    resp = await client_with_key.get("/api/v1/internal/skills/alpha-test-skill")
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["code"] == "unauthorized"


@pytest.mark.integration
async def test_internal_skill_wrong_key_returns_401(client_with_key: AsyncClient) -> None:
    """Wrong gateway-key value → 401."""

    resp = await client_with_key.get(
        "/api/v1/internal/skills/alpha-test-skill",
        headers={"X-LQ-AI-Gateway-Key": "wrong-secret"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["code"] == "unauthorized"


@pytest.mark.integration
async def test_internal_skill_happy_path(client_with_key: AsyncClient) -> None:
    """Valid key → 200 with the full Skill body (matches user-facing shape)."""

    resp = await client_with_key.get(
        "/api/v1/internal/skills/alpha-test-skill",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "alpha-test-skill"
    assert body["version"] == "1.0.0"
    assert body["scope"] == "builtin"
    assert "Alpha Test Skill" in body["content_md"]
    assert "name: alpha-test-skill" in body["content_yaml"]
    # Reference file is loaded.
    ref_paths = {f["path"] for f in body["reference_files"]}
    assert "reference/note.md" in ref_paths


@pytest.mark.integration
async def test_internal_skill_unknown_returns_404(client_with_key: AsyncClient) -> None:
    """Unknown skill name → 404 with structured envelope."""

    resp = await client_with_key.get(
        "/api/v1/internal/skills/never-existed",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "not_found"
    assert body["detail"]["details"]["skill_name"] == "never-existed"


@pytest.mark.integration
async def test_internal_skill_no_configured_key_returns_500(
    client_without_key: AsyncClient,
) -> None:
    """Operator hasn't set LQ_AI_GATEWAY_KEY → 500, not silent acceptance."""

    resp = await client_without_key.get(
        "/api/v1/internal/skills/alpha-test-skill",
        headers={"X-LQ-AI-Gateway-Key": "anything"},
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"]["code"] == "internal_error"


@pytest.mark.integration
async def test_internal_skill_constant_time_compare(client_with_key: AsyncClient) -> None:
    """Even a key with the right prefix is rejected — no early-exit leak."""

    # Same prefix, but wrong tail.
    near_miss = VALID_KEY[:-1] + "X"
    resp = await client_with_key.get(
        "/api/v1/internal/skills/alpha-test-skill",
        headers={"X-LQ-AI-Gateway-Key": near_miss},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_internal_skill_does_not_require_user_token(
    client_with_key: AsyncClient,
) -> None:
    """Auth is via gateway key only — no user token required.

    Regression guard: if someone accidentally mounts the internal router
    under `_active`, this test fails because the gateway has no user.
    """

    resp = await client_with_key.get(
        "/api/v1/internal/skills/alpha-test-skill",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 200


@pytest.mark.integration
async def test_internal_skill_user_token_alone_returns_401(
    client_with_key: AsyncClient,
) -> None:
    """A valid bearer token without the gateway key is NOT accepted.

    Trust-domain separation per ADR 0006 — the internal route only
    accepts the shared gateway secret.
    """

    resp = await client_with_key.get(
        "/api/v1/internal/skills/alpha-test-skill",
        headers={"Authorization": "Bearer some-user-token"},
    )
    assert resp.status_code == 401


# --- /internal/organization-profile (D4-coverage) ----------------------------


@pytest.mark.integration
async def test_internal_org_profile_unauthenticated_returns_401(
    client_with_key: AsyncClient,
) -> None:
    """No gateway-key header → 401 even when a Profile exists."""

    resp = await client_with_key.get("/api/v1/internal/organization-profile")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "unauthorized"


@pytest.mark.integration
async def test_internal_org_profile_wrong_key_returns_401(
    client_with_key: AsyncClient,
) -> None:
    """Wrong key → 401 (constant-time-compare path)."""

    resp = await client_with_key.get(
        "/api/v1/internal/organization-profile",
        headers={"X-LQ-AI-Gateway-Key": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_internal_org_profile_unset_returns_404(
    client_with_key: AsyncClient,
) -> None:
    """No row in the table → 404 ``not_found``.

    The gateway treats this the same as the empty-body case; "no
    profile to prepend" is a valid steady-state for a fresh
    deployment, not an error.
    """

    resp = await client_with_key.get(
        "/api/v1/internal/organization-profile",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "not_found"
    assert body["detail"]["details"]["resource"] == "organization_profile"


@pytest.mark.integration
async def test_internal_org_profile_present_returns_skill_shape(
    client_with_key: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A populated row → 200 with Skill-shaped JSON the gateway can parse.

    The gateway's :class:`Skill` parser is permissive (``extra="allow"``)
    so the exact field set isn't load-bearing, but the contract pins
    the keys the assembler reads: ``name``, ``content_md``,
    ``content_yaml``. The synthesized YAML carries
    ``use_organization_profile: false`` so the gateway never recursively
    re-prepends the Profile to itself.
    """

    db_session.add(OrganizationProfile(content_md="Always cite Delaware as choice of law."))
    await db_session.commit()

    resp = await client_with_key.get(
        "/api/v1/internal/organization-profile",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "organization-profile"
    assert body["content_md"] == "Always cite Delaware as choice of law."
    assert "is_organization_profile: true" in body["content_yaml"]
    assert "use_organization_profile: false" in body["content_yaml"]
    assert body["is_organization_profile"] is True
    assert body["use_organization_profile"] is False


@pytest.mark.integration
async def test_internal_org_profile_empty_body_returns_404(
    client_with_key: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A row with empty (or whitespace-only) ``content_md`` → 404.

    Operators may PUT an empty body to clear the Profile without
    deleting the row; the internal endpoint surfaces that as "no
    Profile" so the gateway has one branch instead of two.
    """

    db_session.add(OrganizationProfile(content_md="   \n\n  "))
    await db_session.commit()

    resp = await client_with_key.get(
        "/api/v1/internal/organization-profile",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.integration
async def test_internal_org_profile_no_configured_key_returns_500(
    client_without_key: AsyncClient,
) -> None:
    """Operator hasn't set LQ_AI_GATEWAY_KEY → 500, not silent acceptance.

    Same posture as ``/internal/skills/{name}`` — refusing the call is
    safer than serving Profile content over an unauthenticated channel.
    """

    resp = await client_without_key.get(
        "/api/v1/internal/organization-profile",
        headers={"X-LQ-AI-Gateway-Key": "anything"},
    )
    assert resp.status_code == 500
    assert resp.json()["detail"]["code"] == "internal_error"


# ---------------------------------------------------------------------------
# D8 — user_id query param resolves user-scope shadows (ADR 0012)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_internal_skill_with_user_id_returns_shadow(
    client_with_key: AsyncClient, db_session: AsyncSession
) -> None:
    """When a non-archived user_skills row exists at this slug for the
    requesting user, the internal endpoint returns the shadow rather
    than the filesystem-canonical built-in."""

    import uuid as _uuid

    from app.models import User, UserSkill
    from app.security import hash_password

    user = User(
        email=f"shadow-{_uuid.uuid4().hex[:8]}@example.com",
        display_name="Shadow Test",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()

    shadow = UserSkill(
        scope="user",
        owner_user_id=user.id,
        slug="alpha-test-skill",
        display_name="My Alpha",
        description="user-scope alpha",
        body="USER-SCOPE-SHADOW-BODY",
    )
    db_session.add(shadow)
    await db_session.flush()

    resp = await client_with_key.get(
        f"/api/v1/internal/skills/alpha-test-skill?user_id={user.id}",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "user"
    assert body["content_md"] == "USER-SCOPE-SHADOW-BODY"


@pytest.mark.integration
async def test_internal_skill_user_id_falls_back_to_builtin_when_no_shadow(
    client_with_key: AsyncClient, db_session: AsyncSession
) -> None:
    """Passing ``user_id`` with no shadow row for that user falls
    through to the registry. The built-in remains the response."""

    import uuid as _uuid

    from app.models import User
    from app.security import hash_password

    user = User(
        email=f"no-shadow-{_uuid.uuid4().hex[:8]}@example.com",
        display_name="No Shadow",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()

    resp = await client_with_key.get(
        f"/api/v1/internal/skills/alpha-test-skill?user_id={user.id}",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "builtin"


@pytest.mark.integration
async def test_internal_skill_user_id_shadow_is_per_user(
    client_with_key: AsyncClient, db_session: AsyncSession
) -> None:
    """User A's shadow does not affect user B's resolution."""

    import uuid as _uuid

    from app.models import User, UserSkill
    from app.security import hash_password

    async def make_user(suffix: str) -> User:
        u = User(
            email=f"per-user-{suffix}-{_uuid.uuid4().hex[:8]}@example.com",
            display_name=f"Per User {suffix}",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db_session.add(u)
        await db_session.flush()
        return u

    a = await make_user("a")
    b = await make_user("b")
    db_session.add(
        UserSkill(
            scope="user",
            owner_user_id=a.id,
            slug="alpha-test-skill",
            display_name="A's Alpha",
            description="a shadow",
            body="A-ONLY-BODY",
        )
    )
    await db_session.flush()

    a_resp = await client_with_key.get(
        f"/api/v1/internal/skills/alpha-test-skill?user_id={a.id}",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    b_resp = await client_with_key.get(
        f"/api/v1/internal/skills/alpha-test-skill?user_id={b.id}",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert a_resp.json()["scope"] == "user"
    assert a_resp.json()["content_md"] == "A-ONLY-BODY"
    assert b_resp.json()["scope"] == "builtin"


@pytest.mark.integration
async def test_internal_skill_archived_shadow_falls_through(
    client_with_key: AsyncClient, db_session: AsyncSession
) -> None:
    """Archived shadows are excluded from resolution; built-in wins."""

    import uuid as _uuid
    from datetime import datetime, timezone

    from app.models import User, UserSkill
    from app.security import hash_password

    user = User(
        email=f"archived-{_uuid.uuid4().hex[:8]}@example.com",
        display_name="Archived Shadow",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserSkill(
            scope="user",
            owner_user_id=user.id,
            slug="alpha-test-skill",
            display_name="Archived",
            description="archived",
            body="ARCHIVED-BODY",
            archived_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()

    resp = await client_with_key.get(
        f"/api/v1/internal/skills/alpha-test-skill?user_id={user.id}",
        headers={"X-LQ-AI-Gateway-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "builtin"
