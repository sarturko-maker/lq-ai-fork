"""SETUP-3a (ADR-F061) — operator fence + escalation guard.

Covers:
* Structural drift guard: every reclassified gateway-proxy route depends on
  ``get_operator_user`` and NOT ``get_admin_user`` (and GET /admin/tier-policy
  stays the other way round) — so a future route can't silently land on the
  wrong side of the fence.
* Behavioural: a reclassified route 403s for an org-admin and passes for the
  bootstrap operator; operator ALSO passes org-admin surfaces (superset).
* Escalation guard (D3): PATCH role=operator → 422; role=operator invite → 422;
  role/disable targeting an operator → 403.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_admin_user, get_operator_user
from app.clients.gateway import get_gateway_client
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.security import create_access_token, hash_password

# The gateway-proxy surfaces reclassified to OperatorUser (ADR-F061 D4).
FENCED_ROUTES: list[tuple[str, str]] = [
    ("/api/v1/admin/aliases", "GET"),
    ("/api/v1/admin/aliases/{name}", "GET"),
    ("/api/v1/admin/aliases", "POST"),
    ("/api/v1/admin/aliases/{name}", "PATCH"),
    ("/api/v1/admin/aliases/{name}", "DELETE"),
    ("/api/v1/admin/provider-keys", "GET"),
    ("/api/v1/admin/provider-keys", "POST"),
    ("/api/v1/admin/provider-keys/{provider}", "PATCH"),
    ("/api/v1/admin/provider-keys/{provider}", "DELETE"),
    ("/api/v1/admin/config", "GET"),
    ("/api/v1/admin/tier-policy", "PATCH"),
    ("/api/v1/inference/override-tier-floor", "POST"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


def _bearer(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


class _StubGateway:
    """Returns benign payloads so a fenced route reaches 200 once auth passes."""

    async def list_aliases(self) -> dict:
        return {}

    async def list_provider_keys(self) -> dict:
        return {}

    async def get_admin_config(self) -> dict:
        return {}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.dependency_overrides[get_gateway_client] = lambda: _StubGateway()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_gateway_client, None)


async def _seed(db: AsyncSession, *, role: str, is_admin: bool) -> User:
    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        display_name=role.capitalize(),
        hashed_password=hash_password("s3cr3t-battery-staple-xyz"),
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


@pytest_asyncio.fixture
async def operator_user(db_session: AsyncSession) -> User:
    # Bootstrap mints operator with is_admin=True (superset of org-admin).
    return await _seed(db_session, role="operator", is_admin=True)


# ---------------------------------------------------------------------------
# Structural drift guard
# ---------------------------------------------------------------------------


def _route_dep_calls(path: str, method: str) -> set:
    from fastapi.routing import APIRoute

    calls: set = set()

    def _walk(dependant: object) -> None:
        call = getattr(dependant, "call", None)
        if call is not None:
            calls.add(call)
        for sub in getattr(dependant, "dependencies", []):
            _walk(sub)

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            _walk(route.dependant)
            return calls
    raise AssertionError(f"route not found: {method} {path}")


@pytest.mark.unit
@pytest.mark.parametrize(("path", "method"), FENCED_ROUTES)
def test_fenced_route_requires_operator_not_admin(path: str, method: str) -> None:
    """Each fenced route carries the operator dependency and NOT the admin one."""
    calls = _route_dep_calls(path, method)
    assert get_operator_user in calls, f"{method} {path} missing operator fence"
    assert get_admin_user not in calls, f"{method} {path} still on the admin gate"


@pytest.mark.unit
def test_get_tier_policy_stays_admin() -> None:
    """READ tier-policy stays org-admin (transparency) — NOT operator-fenced."""
    calls = _route_dep_calls("/api/v1/admin/tier-policy", "GET")
    assert get_admin_user in calls
    assert get_operator_user not in calls


# ---------------------------------------------------------------------------
# Behavioural fence
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "path",
    ["/api/v1/admin/aliases", "/api/v1/admin/provider-keys", "/api/v1/admin/config"],
)
async def test_org_admin_403_on_fenced_get(
    client: AsyncClient, admin_user: User, path: str
) -> None:
    resp = await client.get(path, headers=_bearer(admin_user))
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.parametrize(
    "path",
    ["/api/v1/admin/aliases", "/api/v1/admin/provider-keys", "/api/v1/admin/config"],
)
async def test_operator_passes_fenced_get(
    client: AsyncClient, operator_user: User, path: str
) -> None:
    resp = await client.get(path, headers=_bearer(operator_user))
    assert resp.status_code == 200, resp.text


@pytest.mark.integration
async def test_operator_also_passes_org_admin_surface(
    client: AsyncClient, operator_user: User
) -> None:
    """Operator is a superset of org-admin: it passes AdminUser routes too."""
    resp = await client.get("/api/v1/admin/users", headers=_bearer(operator_user))
    assert resp.status_code == 200, resp.text


@pytest.mark.integration
async def test_plain_member_403_on_fenced_route(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    member = await _seed(db_session, role="member", is_admin=False)
    resp = await client.get("/api/v1/admin/config", headers=_bearer(member))
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Escalation guard (D3)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_patch_role_operator_is_422(
    client: AsyncClient, admin_user: User, db_session: AsyncSession
) -> None:
    """No promotion path to operator through the org-admin role endpoint."""
    member = await _seed(db_session, role="member", is_admin=False)
    resp = await client.patch(
        f"/api/v1/admin/users/{member.id}/role",
        headers=_bearer(admin_user),
        json={"role": "operator"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
async def test_role_update_on_operator_target_is_403(
    client: AsyncClient, admin_user: User, operator_user: User
) -> None:
    """An admin cannot reclassify the operator account."""
    resp = await client.patch(
        f"/api/v1/admin/users/{operator_user.id}/role",
        headers=_bearer(admin_user),
        json={"role": "member"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
async def test_invite_role_operator_is_422(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        "/api/v1/admin/users/invites",
        headers=_bearer(admin_user),
        json={"email": f"x-{uuid.uuid4().hex[:8]}@example.com", "role": "operator"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
async def test_disable_operator_target_is_403(
    client: AsyncClient, admin_user: User, operator_user: User
) -> None:
    resp = await client.post(
        f"/api/v1/admin/users/{operator_user.id}/disable",
        headers=_bearer(admin_user),
    )
    assert resp.status_code == 403, resp.text
