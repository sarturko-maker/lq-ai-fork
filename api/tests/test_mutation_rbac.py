"""SETUP-5b (ADR-F064) — tenant-data RBAC drift guard + behaviour tests.

D1: every tenant-data MUTATING route (POST/PATCH/PUT/DELETE) is gated by a
role dependency that excludes ``viewer`` (``get_mutating_user``), or by an
admin/operator gate, OR is a justified exception in ``_ALLOWLIST`` below. The
drift guard walks ``app.routes`` so a NEW ungated mutating route fails CI.

D2 behaviour tests (operator cross-user 404, org-admin sees-all regression)
live in this file too — added by the §B commit.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models import User
from app.security import create_access_token, hash_password

MUTATING_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

# Dependency callables that, if present in a route's dependant tree, satisfy
# the "role-gated mutation" contract. ``get_mutating_user`` excludes viewer;
# the admin/operator gates are strictly stronger (both stack on ActiveUser).
_ROLE_GATES = frozenset({"get_mutating_user", "get_admin_user", "get_operator_user"})

# Justified exceptions: mutating /api/v1 routes NOT behind a _ROLE_GATE. Each
# is keyed (METHOD, path) so a NEW mutating route can never be silently
# absorbed — an unlisted, un-gated route fails the guard. Reason per entry.
_ALLOWLIST: dict[tuple[str, str], str] = {
    # /auth/* — unauthenticated or self-service on the caller's OWN account
    # (login/refresh/reset are pre-auth; logout/change-password/mfa/*/accept-invite
    # act only on the calling identity). No tenant-data surface; role gate N/A.
    ("POST", "/api/v1/auth/login"): "pre-auth self-service",
    ("POST", "/api/v1/auth/refresh"): "pre-auth self-service",
    ("POST", "/api/v1/auth/logout"): "self-service (own session)",
    ("POST", "/api/v1/auth/change-password"): "self-service (own account)",
    ("POST", "/api/v1/auth/mfa/setup"): "self-service (own MFA)",
    ("POST", "/api/v1/auth/mfa/enable"): "self-service (own MFA)",
    ("POST", "/api/v1/auth/mfa/verify"): "pre-auth self-service",
    ("POST", "/api/v1/auth/mfa/disable"): "self-service (own MFA)",
    ("POST", "/api/v1/auth/accept-invite"): "pre-auth self-service (invite token)",
    ("POST", "/api/v1/auth/password-reset-request"): "pre-auth self-service",
    ("POST", "/api/v1/auth/password-reset"): "pre-auth self-service (reset token)",
    # /users/me/* — self-service account management + GDPR data-subject rights
    # on the caller's OWN account (never a cross-user surface). A read-only
    # viewer keeps the right to manage/export/delete their own account.
    ("PATCH", "/api/v1/users/me"): "self-service (own profile)",
    ("PATCH", "/api/v1/users/me/preferences"): "self-service (own prefs)",
    ("POST", "/api/v1/users/me/export"): "self-service GDPR export (own data)",
    ("POST", "/api/v1/users/me/delete"): "self-service GDPR delete (own account)",
    ("POST", "/api/v1/users/me/delete/cancel"): "self-service (own account)",
    # POST-shaped READS — no persistent state mutation; a viewer legitimately
    # reads. Method is POST only to carry a request body.
    ("POST", "/api/v1/knowledge-bases/{kb_id}/query"): "POST-shaped read (retrieval)",
    ("POST", "/api/v1/tabular/preview-cost"): "POST-shaped read (cost estimate, no row)",
    # /wopi/* — WOPI clients authenticate with a file-scoped signed access_token
    # (editor-session JWT), re-validated + owner-scoped per request (ADR-F047);
    # not the user bearer, so no user role in the tree.
    ("POST", "/api/v1/wopi/files/{file_id}"): "WOPI access-token auth (ADR-F047)",
    ("POST", "/api/v1/wopi/files/{file_id}/contents"): "WOPI access-token auth (ADR-F047)",
    # /integrations/* — service-to-service bridge, shared-secret bearer
    # (require_bridge_auth); no user context.
    ("POST", "/api/v1/integrations/slack/workspaces"): "bridge-token auth (no user)",
    ("POST", "/api/v1/integrations/teams/tenants"): "bridge-token auth (no user)",
    # /autonomous/* — legacy Autonomous Layer (M4); per-user isolated + per-user
    # opt-in gate (get_autonomous_enabled_user, stacks on ActiveUser). Viewer
    # read-only enforcement on the legacy layer is out of SETUP-5b scope
    # (CLAUDE.md freezes the legacy executors — bugfix only). Deferred: see
    # MILESTONES backlog + ADR-F064 consequences.
    ("POST", "/api/v1/autonomous/sessions/{session_id}/halt"): "legacy autonomous (deferred)",
    ("POST", "/api/v1/autonomous/memory/{memory_id}/keep"): "legacy autonomous (deferred)",
    ("POST", "/api/v1/autonomous/memory/{memory_id}/dismiss"): "legacy autonomous (deferred)",
    ("DELETE", "/api/v1/autonomous/memory/{memory_id}"): "legacy autonomous (deferred)",
    (
        "POST",
        "/api/v1/autonomous/precedents/{precedent_id}/dismiss",
    ): "legacy autonomous (deferred)",
    (
        "POST",
        "/api/v1/autonomous/precedents/{precedent_id}/promote",
    ): "legacy autonomous (deferred)",
    (
        "POST",
        "/api/v1/autonomous/project-context-proposals/{proposal_id}/accept",
    ): "legacy autonomous (deferred)",
    (
        "POST",
        "/api/v1/autonomous/project-context-proposals/{proposal_id}/reject",
    ): "legacy autonomous (deferred)",
    ("POST", "/api/v1/autonomous/schedules"): "legacy autonomous (deferred)",
    ("PATCH", "/api/v1/autonomous/schedules/{schedule_id}"): "legacy autonomous (deferred)",
    ("DELETE", "/api/v1/autonomous/schedules/{schedule_id}"): "legacy autonomous (deferred)",
    ("POST", "/api/v1/autonomous/run-now"): "legacy autonomous (deferred)",
    ("POST", "/api/v1/autonomous/watches"): "legacy autonomous (deferred)",
    ("PATCH", "/api/v1/autonomous/watches/{watch_id}"): "legacy autonomous (deferred)",
    ("DELETE", "/api/v1/autonomous/watches/{watch_id}"): "legacy autonomous (deferred)",
    (
        "POST",
        "/api/v1/autonomous/notifications/{notification_id}/read",
    ): "legacy autonomous (deferred)",
}


def _auth_callables(dep: Dependant) -> set[str]:
    names: set[str] = set()
    call = getattr(dep, "call", None)
    if call is not None and getattr(call, "__name__", None):
        names.add(call.__name__)
    for sub in dep.dependencies:
        names |= _auth_callables(sub)
    return names


def _mutating_routes() -> list[tuple[str, str, APIRoute]]:
    out: list[tuple[str, str, APIRoute]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        for method in route.methods & MUTATING_METHODS:
            out.append((method, route.path, route))
    return out


# ---------------------------------------------------------------------------
# Drift guard (D1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_mutating_route_is_role_gated_or_allowlisted() -> None:
    """Every mutating /api/v1 route is behind a role gate or a justified
    allowlist entry. A new ungated tenant-data route fails here."""
    ungated: list[tuple[str, str]] = []
    used_allowlist: set[tuple[str, str]] = set()
    for method, path, route in _mutating_routes():
        gates = _auth_callables(route.dependant) & _ROLE_GATES
        if gates:
            continue
        key = (method, path)
        if key in _ALLOWLIST:
            used_allowlist.add(key)
            continue
        ungated.append(key)
    assert not ungated, (
        "Ungated mutating routes (add a role gate — MutatingUser/AdminUser/"
        f"OperatorUser — or a justified _ALLOWLIST entry): {sorted(ungated)}"
    )
    # Minimality: no stale allowlist entries (route removed but exception kept).
    stale = set(_ALLOWLIST) - used_allowlist
    assert not stale, f"Stale _ALLOWLIST entries (route gone or now gated): {sorted(stale)}"


@pytest.mark.unit
def test_mutating_route_entry_count_pinned() -> None:
    """Pins the mutating-route surface so an added mutating route trips the
    guard review (companion to the 171-path pin below)."""
    assert len(_mutating_routes()) == 124


@pytest.mark.unit
def test_api_v1_path_count_pinned() -> None:
    """SETUP-5b adds NO routes: the /api/v1 path surface stays 171."""
    paths = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1")
    }
    assert len(paths) == 171


@pytest.mark.unit
def test_swapped_routers_expose_no_ungated_write() -> None:
    """Spot-pin: the 52 tenant-data writes are all get_mutating_user-gated."""
    gated = sum(
        1
        for _m, _p, route in _mutating_routes()
        if "get_mutating_user" in _auth_callables(route.dependant)
    )
    assert gated == 52


# ---------------------------------------------------------------------------
# Behaviour fixtures
# ---------------------------------------------------------------------------


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


async def _make_user(db_session: AsyncSession, *, role: str, is_admin: bool) -> User:
    user = User(
        email=f"rbac-{role}-{uuid.uuid4().hex[:8]}@example.com",
        display_name=role.title(),
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=is_admin,
        role=role,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, role="viewer", is_admin=False)


@pytest_asyncio.fixture
async def member_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, role="member", is_admin=False)


def _bearer(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


# A representative MutatingUser route per router. All chosen with NO required
# request body (DELETE, or bodyless POST) so the response is unambiguously the
# viewer role-gate 403 — which fires on the caller's OWN role BEFORE any
# resource lookup, so a random UUID never leaks existence (stays 403, not 404).
_VIEWER_DENIED_ROUTES: list[tuple[str, str]] = [
    ("DELETE", f"/api/v1/projects/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/chats/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/files/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/knowledge-bases/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/saved-prompts/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/user-skills/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/playbooks/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/tabular/executions/{uuid.uuid4()}"),
    ("POST", f"/api/v1/agents/runs/{uuid.uuid4()}/cancel"),
    ("POST", f"/api/v1/matters/{uuid.uuid4()}/roster/{uuid.uuid4()}/retire"),
    ("POST", f"/api/v1/matters/{uuid.uuid4()}/memory/facts/{uuid.uuid4()}/retire"),
    ("DELETE", f"/api/v1/projects/{uuid.uuid4()}/skills/some-skill"),
]


@pytest.mark.integration
@pytest.mark.parametrize("method,path", _VIEWER_DENIED_ROUTES)
async def test_viewer_is_denied_mutation(
    client: AsyncClient, viewer_user: User, method: str, path: str
) -> None:
    """A viewer-role account is enforced read-only: 403 forbidden on every
    tenant-data mutation, regardless of resource existence."""
    resp = await client.request(method, path, headers=_bearer(viewer_user))
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["detail"]["code"] == "forbidden"


@pytest.mark.integration
@pytest.mark.parametrize("method,path", _VIEWER_DENIED_ROUTES)
async def test_member_passes_role_gate(
    client: AsyncClient, member_user: User, method: str, path: str
) -> None:
    """A member clears the role gate: the same requests do NOT 403 on role.
    They 404 (unknown resource) — proving the gate let them through to the
    owner-scoped handler body."""
    resp = await client.request(method, path, headers=_bearer(member_user))
    assert resp.status_code != 403, f"{method} {path} -> {resp.status_code}: {resp.text}"
