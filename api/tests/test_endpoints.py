"""Endpoint scaffold tests — every still-stub /api/v1 route returns the canonical 501 body.

A4 registered every endpoint from `docs/api/backend-openapi.yaml` as a stub
returning HTTP 501 with a structured body that names the implementing M1
task. As tasks land, their endpoints leave the stub set; the remaining
stubs continue to honor the contract:

    {
      "error": {
        "code": "not_implemented",
        "message": "Endpoint scaffold; full implementation lands in Task ...",
        "endpoint": "<METHOD /path>",
        "next_task": "<task ID — task title>"
      }
    }

This test enumerates the registered routes via `app.routes` and exercises
every one EXCEPT those whose implementing task has shipped (tracked in
`IMPLEMENTED_ROUTES` below). Implemented routes have their own dedicated
test files (e.g., `test_auth.py` for B1, `test_change_password.py` for B2).

Most stub routers are mounted under the `ActiveUser` dependency since
Task B2 — they require a valid bearer token whose user has cleared the
must-change-password gate. Tests therefore mint a JWT for an inserted
test user (with `must_change_password=False`) and pass it on every
request.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.security import create_access_token, hash_password

# Substitution table for path parameters when exercising stubs.
# Any UUID-shaped parameter gets a fixed UUID v4; named params get a
# safe identifier.
_DUMMY_UUID = "00000000-0000-4000-8000-000000000000"
_PARAM_VALUES: dict[str, str] = {
    "project_id": _DUMMY_UUID,
    "chat_id": _DUMMY_UUID,
    "message_id": _DUMMY_UUID,
    "file_id": _DUMMY_UUID,
    "kb_id": _DUMMY_UUID,
    "prompt_id": _DUMMY_UUID,
    "skill_name": "nda-review",
}


def _materialise(path: str) -> str:
    """Replace `{param}` placeholders with concrete values for the request."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in _PARAM_VALUES:
            raise AssertionError(
                f"Path parameter '{name}' has no test value — "
                f"add it to _PARAM_VALUES in test_endpoints.py"
            )
        return _PARAM_VALUES[name]

    return re.sub(r"\{([^}]+)\}", repl, path)


# Routes whose implementing task has landed. These are exercised by their
# own dedicated test files; this scaffold-test must skip them or the
# now-implemented handler returns 200/204/etc. and fails the 501 assertion.
# Format: (METHOD, registered_path).
IMPLEMENTED_ROUTES: set[tuple[str, str]] = {
    # B1 — User model + auth endpoints (backend)
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/users/me"),
    # B2 — first-run admin + forced password change
    ("POST", "/api/v1/auth/change-password"),
    # D6 — GDPR Article 17 + 20 surface
    ("POST", "/api/v1/users/me/export"),
    ("GET", "/api/v1/users/me/export/{job_id}"),
    ("POST", "/api/v1/users/me/delete"),
    ("POST", "/api/v1/users/me/delete/cancel"),
    # B5 + C3 — backend chats + messages with persistence; SSE streaming.
    ("POST", "/api/v1/chats"),
    ("GET", "/api/v1/chats"),
    ("GET", "/api/v1/chats/{chat_id}"),
    ("PATCH", "/api/v1/chats/{chat_id}"),
    ("DELETE", "/api/v1/chats/{chat_id}"),
    ("GET", "/api/v1/chats/{chat_id}/messages"),
    ("POST", "/api/v1/chats/{chat_id}/messages"),
    ("GET", "/api/v1/chats/{chat_id}/messages/{message_id}/citations"),
    # C1 — Skill Service: filesystem loading
    ("GET", "/api/v1/skills"),
    ("GET", "/api/v1/skills/{skill_name}"),
    # C2 — gateway-facing internal skills endpoint (X-LQ-AI-Gateway-Key auth)
    ("GET", "/api/v1/internal/skills/{skill_name}"),
    # C4 — file upload + storage
    ("POST", "/api/v1/files"),
    ("GET", "/api/v1/files/{file_id}"),
    ("GET", "/api/v1/files/{file_id}/content"),
    ("DELETE", "/api/v1/files/{file_id}"),
    # C7 — Project service
    ("POST", "/api/v1/projects"),
    ("GET", "/api/v1/projects"),
    ("GET", "/api/v1/projects/{project_id}"),
    ("PATCH", "/api/v1/projects/{project_id}"),
    ("DELETE", "/api/v1/projects/{project_id}"),
    ("POST", "/api/v1/projects/{project_id}/files"),
    ("DELETE", "/api/v1/projects/{project_id}/files/{file_id}"),
    ("POST", "/api/v1/projects/{project_id}/skills"),
    ("DELETE", "/api/v1/projects/{project_id}/skills/{skill_name}"),
    # D0 — Model availability (proxy to gateway /v1/models)
    ("GET", "/api/v1/models"),
    # D0.5 — Admin alias CRUD proxy
    ("GET", "/api/v1/admin/aliases"),
    ("GET", "/api/v1/admin/aliases/{name}"),
    ("POST", "/api/v1/admin/aliases"),
    ("PATCH", "/api/v1/admin/aliases/{name}"),
    ("DELETE", "/api/v1/admin/aliases/{name}"),
    ("GET", "/api/v1/admin/config"),
    # C6 — Knowledge bases
    ("POST", "/api/v1/knowledge-bases"),
    ("GET", "/api/v1/knowledge-bases"),
    ("GET", "/api/v1/knowledge-bases/{kb_id}"),
    ("PATCH", "/api/v1/knowledge-bases/{kb_id}"),
    ("DELETE", "/api/v1/knowledge-bases/{kb_id}"),
    ("POST", "/api/v1/knowledge-bases/{kb_id}/files"),
    ("DELETE", "/api/v1/knowledge-bases/{kb_id}/files/{file_id}"),
    ("POST", "/api/v1/knowledge-bases/{kb_id}/query"),
}


def _api_v1_routes() -> list[tuple[str, str, str]]:
    """Return (method, registered_path, materialised_path) for every still-stub /api/v1 route."""
    rows: list[tuple[str, str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            if (method, route.path) in IMPLEMENTED_ROUTES:
                continue
            rows.append((method, route.path, _materialise(route.path)))
    return rows


# Materialised once at import time so pytest reports the route in the parametrize id.
ROUTES = _api_v1_routes()


@pytest.mark.unit
async def test_route_inventory_is_nonempty() -> None:
    """Sanity: stub routes still exist under /api/v1.

    The bound is intentionally loose — as tasks land, they migrate
    routes from this 501-stub set into ``IMPLEMENTED_ROUTES``. The
    primary purpose of this assertion is to catch the failure mode
    of accidentally dropping all the include_router calls. After D5/D6
    landed (4 MFA + 4 GDPR endpoints), the remaining stub count drops
    into the single digits; lowered to ``>= 5`` so the bound continues
    to fire as a sanity check through wave-2 (D2, D3, D4, D7) without
    needing to re-tune on every task.
    """
    assert len(ROUTES) >= 5


@pytest_asyncio.fixture
async def stub_test_user(db_session: AsyncSession) -> User:
    """Insert a user with must_change_password=False so stub tests can pass the B2 gate."""
    user = User(
        email=f"stub-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Stub Test User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def stub_client(
    db_session: AsyncSession, stub_test_user: User
) -> AsyncIterator[tuple[AsyncClient, str]]:
    """Async HTTP client + a bearer token good for the stub tests' authenticated routers."""

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    token = create_access_token(
        stub_test_user.id, stub_test_user.email, is_admin=stub_test_user.is_admin
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, token
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path_template", "path"),
    ROUTES,
    ids=[f"{m} {p}" for (m, p, _) in ROUTES],
)
async def test_endpoint_returns_canonical_501_body(
    stub_client: tuple[AsyncClient, str],
    method: str,
    path_template: str,
    path: str,
) -> None:
    """Every /api/v1 endpoint returns HTTP 501 with the documented body shape.

    Authenticated routers (most of them since B2) are exercised with a
    bearer token whose user has `must_change_password=False`, so the gate
    passes and the request reaches the stub handler. Unauthenticated
    endpoints (auth/login etc.) ignore the header.
    """
    client, token = stub_client
    response = await client.request(method, path, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 501, (
        f"{method} {path} returned {response.status_code}, expected 501"
    )
    body = response.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == "not_implemented"
    # Endpoint label is the (template) METHOD + path the stub was registered for.
    # We don't assert exact equality on the verb because the stub helper formats
    # it as a method+path label.
    assert path_template in err["endpoint"]
    assert err["next_task"]
    assert err["message"].startswith("Endpoint scaffold")
