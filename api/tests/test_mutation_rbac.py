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
    # NOTE (SETUP-5b §E): /autonomous/* mutations are NOT allowlisted — they
    # are gated like all tenant-data writes. get_autonomous_enabled_user now
    # stacks on MutatingUser (both checks hold: viewer role gate first, then
    # the per-user opt-in flag); halt carries MutatingUser directly.
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
    guard review (companion to the 173-path pin below). STORE-1 (ADR-F065) adds
    2 mutating admin routes (POST /admin/library + DELETE /admin/library/{kind}/{key}),
    both AdminUser-gated — they pass the drift guard automatically (no allowlist entry).
    BRAND-1a (ADR-F068) adds 3 mutating branding routes (PUT /branding +
    POST/DELETE /branding/logo), all AdminUser-gated at the handler level
    (the router itself is unauth-mounted for the public GETs): 126 → 129.
    B-2a (ADR-F067 D2/D3) adds 4 mutating org-skills routes (POST propose,
    MutatingUser-gated; POST approve/reject/revoke, AdminUser-gated): 129 → 133.
    B-3 (ADR-F067 D1) adds 2 mutating practice-area routes (POST/DELETE
    /practice-areas/{key}/knowledge-bases), both AdminUser-gated: 133 → 135.
    HITL-2 (ADR-F071) adds 1 mutating route (POST /agents/runs/{run_id}/resume,
    MutatingUser-gated): 135 → 136.
    HITL-3 (ADR-F071) adds 1 mutating route (PUT
    /practice-areas/{key}/hitl-policy, AdminUser-gated — passes the drift guard
    automatically, no allowlist entry): 136 → 137.
    B-4 (ADR-F067 D2/D3) adds 4 mutating org-playbook routes (POST propose,
    MutatingUser-gated; POST approve/reject/revoke, AdminUser-gated): 137 → 141."""
    assert len(_mutating_routes()) == 141


@pytest.mark.unit
def test_api_v1_path_count_pinned() -> None:
    """STORE-1 (ADR-F065) adds 2 routes (the Org Library adopt/remove pair): 171 → 173.
    STORE-2 (ADR-F065 D-B) adds 1 route (GET /api/v1/library, member-readable): 173 → 174.
    BRAND-1a (ADR-F068) adds 2 paths (/branding + /branding/logo): 174 → 176.
    B-2a (ADR-F067 D2/D3) adds 6 paths (user-skills propose + proposals;
    admin/org-skills + approve/reject/revoke): 176 → 182.
    B-3 (ADR-F067 D1) adds 2 paths (POST/DELETE
    /practice-areas/{key}/knowledge-bases): 182 → 184.
    HITL-2 (ADR-F071) adds 1 path (POST /agents/runs/{run_id}/resume): 184 → 185.
    HITL-3 (ADR-F071) adds 1 path (PUT /practice-areas/{key}/hitl-policy): 185 → 186.
    B-4 (ADR-F067 D2/D3) adds 6 paths (playbooks propose + proposals;
    admin/org-playbooks + approve/reject/revoke): 186 → 192."""
    paths = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1")
    }
    assert len(paths) == 192


@pytest.mark.unit
def test_swapped_routers_expose_no_ungated_write() -> None:
    """Spot-pin: all get_mutating_user-gated writes (53 direct swaps + 16
    autonomous via the stacked opt-in gate, §E; B-2a adds POST
    /user-skills/{skill_id}/propose — the author-side org-skill propose).
    HITL-2 (ADR-F071) adds POST /agents/runs/{run_id}/resume (MutatingUser):
    69 → 70. HITL-3 (ADR-F071) adds PUT /practice-areas/{key}/hitl-policy but it
    is AdminUser-gated, so this get_mutating_user count is UNCHANGED at 70.
    B-4 (ADR-F067 D2/D3) adds POST /playbooks/{playbook_id}/propose — the
    author-side org-playbook propose (MutatingUser): 70 → 71 (approve/reject/
    revoke are AdminUser, so they do not add to this count)."""
    gated = sum(
        1
        for _m, _p, route in _mutating_routes()
        if "get_mutating_user" in _auth_callables(route.dependant)
    )
    assert gated == 71


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
    # §E — legacy autonomous halt (MutatingUser directly; no opt-in gate, so
    # the member happy-path lands on the 404 owner lookup like the others).
    ("POST", f"/api/v1/autonomous/sessions/{uuid.uuid4()}/halt"),
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


# ---------------------------------------------------------------------------
# tenant_admin_visibility (D2) — operator excluded from cross-user tenant data;
# org-admin keeps admin-sees-all (regression). Cross-user = 404, never 403.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def operator_user(db_session: AsyncSession) -> User:
    # ADR-F061 D3: operator is an is_admin superset. ADR-F064 D2 excludes it
    # from cross-user tenant-data visibility (tenant_admin_visibility → False).
    return await _make_user(db_session, role="operator", is_admin=True)


@pytest_asyncio.fixture
async def org_admin_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, role="admin", is_admin=True)


async def _member_playbook(db_session: AsyncSession, owner: User):
    from app.models.playbook import Playbook

    pb = Playbook(
        name=f"Member PB {uuid.uuid4().hex[:6]}", contract_type="nda", created_by=owner.id
    )
    db_session.add(pb)
    await db_session.flush()
    await db_session.refresh(pb)
    return pb


async def _member_tabular(db_session: AsyncSession, owner: User):
    from app.models.tabular import TabularExecution

    ex = TabularExecution(user_id=owner.id)
    db_session.add(ex)
    await db_session.flush()
    await db_session.refresh(ex)
    return ex


@pytest.mark.integration
async def test_operator_excluded_from_cross_user_playbook_list(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    operator_user: User,
    org_admin_user: User,
) -> None:
    """`list_playbooks` admin-sees-all bypass no longer extends to operator:
    the operator sees only its own; the org-admin still sees the member's."""
    pb = await _member_playbook(db_session, member_user)

    op = await client.get("/api/v1/playbooks", headers=_bearer(operator_user))
    assert op.status_code == 200
    assert str(pb.id) not in {p["id"] for p in op.json()}

    admin = await client.get("/api/v1/playbooks", headers=_bearer(org_admin_user))
    assert admin.status_code == 200
    assert str(pb.id) in {p["id"] for p in admin.json()}, (
        "org-admin must still see all (regression)"
    )

    owner = await client.get("/api/v1/playbooks", headers=_bearer(member_user))
    assert str(pb.id) in {p["id"] for p in owner.json()}


@pytest.mark.integration
async def test_operator_cross_user_playbook_delete_is_404_not_403(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    operator_user: User,
) -> None:
    """Operator deleting ANOTHER user's playbook is 404 (existence rule),
    never 403 — and the row survives."""
    pb = await _member_playbook(db_session, member_user)
    resp = await client.delete(f"/api/v1/playbooks/{pb.id}", headers=_bearer(operator_user))
    assert resp.status_code == 404, resp.text
    await db_session.refresh(pb)
    assert pb.deleted_at is None


@pytest.mark.integration
async def test_org_admin_cross_user_playbook_delete_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    org_admin_user: User,
) -> None:
    """Regression: the org-admin keeps admin-sees-all on the mutation path."""
    pb = await _member_playbook(db_session, member_user)
    resp = await client.delete(f"/api/v1/playbooks/{pb.id}", headers=_bearer(org_admin_user))
    assert resp.status_code in (200, 204), resp.text


@pytest.mark.integration
async def test_operator_excluded_from_cross_user_tabular_list(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    operator_user: User,
    org_admin_user: User,
) -> None:
    """`list_tabular_executions` admin-sees-all bypass no longer extends to
    operator; the org-admin still sees the member's execution."""
    ex = await _member_tabular(db_session, member_user)

    op = await client.get("/api/v1/tabular/executions", headers=_bearer(operator_user))
    assert op.status_code == 200
    assert str(ex.id) not in {r["id"] for r in op.json()}

    admin = await client.get("/api/v1/tabular/executions", headers=_bearer(org_admin_user))
    assert admin.status_code == 200
    assert str(ex.id) in {r["id"] for r in admin.json()}, (
        "org-admin must still see all (regression)"
    )


@pytest.mark.integration
async def test_operator_cross_user_tabular_detail_is_404(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    operator_user: User,
) -> None:
    """Operator reading ANOTHER user's execution is 404 (existence rule),
    never 403 — while the org-admin (regression) can read it."""
    ex = await _member_tabular(db_session, member_user)
    resp = await client.get(f"/api/v1/tabular/executions/{ex.id}", headers=_bearer(operator_user))
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# §E — legacy autonomous mutations: viewer role gate AND opt-in flag both hold
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_autonomous_mutation_stacks_role_gate_and_opt_in(
    client: AsyncClient,
    db_session: AsyncSession,
    viewer_user: User,
    member_user: User,
) -> None:
    """`get_autonomous_enabled_user` stacks on MutatingUser (§E): a viewer is
    rejected on ROLE (before the opt-in check); an opted-OUT member is
    rejected on the opt-in flag; an opted-IN member clears both gates and
    reaches the 404 owner lookup."""
    path = f"/api/v1/autonomous/memory/{uuid.uuid4()}"

    viewer = await client.delete(path, headers=_bearer(viewer_user))
    assert viewer.status_code == 403
    assert "read-only" in viewer.json()["detail"]["message"]

    opted_out = await client.delete(path, headers=_bearer(member_user))
    assert opted_out.status_code == 403
    assert "Autonomous Layer" in opted_out.json()["detail"]["message"]

    member_user.autonomous_enabled = True
    await db_session.flush()
    opted_in = await client.delete(path, headers=_bearer(member_user))
    assert opted_in.status_code == 404, opted_in.text


# ---------------------------------------------------------------------------
# §E — chat receipts: operator excluded + cross-user 404 (was a 403
# existence leak; recon §6 gap, fixed on lead review)
# ---------------------------------------------------------------------------


async def _member_chat(db_session: AsyncSession, owner: User):
    from app.models.chat import Chat

    chat = Chat(owner_id=owner.id, title="Member chat")
    db_session.add(chat)
    await db_session.flush()
    return chat


@pytest.mark.integration
async def test_operator_cross_user_receipts_is_404(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    operator_user: User,
) -> None:
    chat = await _member_chat(db_session, member_user)
    resp = await client.get(f"/api/v1/chats/{chat.id}/receipts", headers=_bearer(operator_user))
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
async def test_org_admin_cross_user_receipts_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    org_admin_user: User,
) -> None:
    chat = await _member_chat(db_session, member_user)
    resp = await client.get(f"/api/v1/chats/{chat.id}/receipts", headers=_bearer(org_admin_user))
    assert resp.status_code == 200, resp.text


@pytest.mark.integration
async def test_non_owner_member_receipts_is_404_not_403(
    client: AsyncClient,
    db_session: AsyncSession,
    member_user: User,
    org_admin_user: User,
) -> None:
    """The pre-§E code returned 403-after-fetch — an existence leak. A
    non-owner non-admin now gets the same 404 as a missing chat."""
    chat = await _member_chat(db_session, org_admin_user)
    other = await _make_user(db_session, role="member", is_admin=False)
    resp = await client.get(f"/api/v1/chats/{chat.id}/receipts", headers=_bearer(other))
    assert resp.status_code == 404, resp.text
