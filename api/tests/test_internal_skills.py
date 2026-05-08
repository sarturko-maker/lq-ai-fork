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
