"""Integration tests for ``GET /api/v1/admin/model-menu`` (SETUP-4b, ADR-F062 addendum).

The endpoint is a narrow, read-only projection of the gateway's merged model-discovery
payload (the same one ``GET /api/v1/models`` proxies for every member) down to
``{"aliases": [{"alias", "tier"}]}`` — no provider names, model ids, base URLs,
fallback chains, or key material. These tests cover:

* Auth: 401 without a bearer token.
* Fence: AdminUser (not OperatorUser) — a non-admin member gets 403; an admin gets 200.
* Strip-down: a gateway payload carrying extra fields (incl. a would-be secret field)
  is reduced to exactly alias+tier; provider-native rows are excluded entirely.
* Gateway 5xx / timeout degrades the same way every other gateway-backed admin
  endpoint does (503 / 504) — no bespoke error handling in the new endpoint.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.gateway import GatewayClient, set_gateway_client
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.security import create_access_token, hash_password

GATEWAY_BASE = "http://test-gateway"
GATEWAY_KEY = "test-gw-key"

_URL = "/api/v1/admin/model-menu"


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"model-menu-admin-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Admin",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=True,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def member_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"model-menu-member-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Member",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    gw = GatewayClient(base_url=GATEWAY_BASE, gateway_key=GATEWAY_KEY)
    set_gateway_client(gw)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    set_gateway_client(None)
    await gw.aclose()
    app.dependency_overrides.pop(get_db, None)


def _bearer(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


# A gateway merged-discovery payload with extra fields on the alias rows (incl. a
# would-be secret-shaped field) plus a provider-native row that must be excluded.
_GATEWAY_PAYLOAD: dict[str, object] = {
    "object": "list",
    "data": [
        {
            "id": "smart",
            "object": "model",
            "created": 0,
            "owned_by": "lq-ai-gateway",
            "lq_ai_kind": "alias",
            "routed_inference_tier": 4,
            "lq_ai_resolves_to": "anthropic-prod/claude-opus-4-7",
            "lq_ai_fallback_count": 1,
            "api_key": "sk-should-never-appear",
        },
        {
            "id": "fast",
            "object": "model",
            "created": 0,
            "owned_by": "lq-ai-gateway",
            "lq_ai_kind": "alias",
            # No routed_inference_tier — the fallback-only alias case (tier: null).
            "lq_ai_resolves_to": "ollama-local/llama3.1:8b",
        },
        {
            "id": "anthropic-prod/claude-haiku-4-5",
            "object": "model",
            "created": 0,
            "owned_by": "anthropic-prod",
            "lq_ai_kind": "provider_native",
            "routed_inference_tier": 4,
            "provider_type": "anthropic",
        },
    ],
}


@pytest.mark.integration
async def test_model_menu_requires_auth(client: AsyncClient) -> None:
    resp = await client.get(_URL)
    assert resp.status_code == 401


@pytest.mark.integration
async def test_model_menu_requires_admin(client: AsyncClient, member_user: User) -> None:
    resp = await client.get(_URL, headers=_bearer(member_user))
    assert resp.status_code == 403


@pytest.mark.integration
@respx.mock
async def test_model_menu_strips_to_alias_and_tier_only(
    client: AsyncClient, admin_user: User
) -> None:
    respx.get(f"{GATEWAY_BASE}/v1/models").mock(
        return_value=httpx.Response(200, json=_GATEWAY_PAYLOAD)
    )

    resp = await client.get(_URL, headers=_bearer(admin_user))

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "aliases": [
            {"alias": "smart", "tier": 4},
            {"alias": "fast", "tier": None},
        ]
    }
    # The provider-native row never appears; no secret/provider/model/url material
    # rides along anywhere in the response body.
    raw = resp.text
    assert "sk-should-never-appear" not in raw
    assert "anthropic" not in raw
    assert "resolves_to" not in raw
    assert "claude" not in raw


@pytest.mark.integration
@respx.mock
async def test_model_menu_gateway_5xx_returns_503(client: AsyncClient, admin_user: User) -> None:
    respx.get(f"{GATEWAY_BASE}/v1/models").mock(return_value=httpx.Response(503, text="oops"))

    resp = await client.get(_URL, headers=_bearer(admin_user))

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "gateway_unreachable"


@pytest.mark.integration
@respx.mock
async def test_model_menu_gateway_timeout_returns_504(
    client: AsyncClient, admin_user: User
) -> None:
    respx.get(f"{GATEWAY_BASE}/v1/models").mock(side_effect=httpx.TimeoutException("slow"))

    resp = await client.get(_URL, headers=_bearer(admin_user))

    assert resp.status_code == 504
    assert resp.json()["detail"]["code"] == "gateway_timeout"
