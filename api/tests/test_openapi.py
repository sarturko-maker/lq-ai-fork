"""OpenAPI surface tests.

The OpenAPI sketch at `docs/api/backend-openapi.yaml` is the contract.
Task A4 registers every path from the sketch as a 501-returning stub so
the OpenAPI document FastAPI generates matches the contract from day
one. This test pins that match.

When the sketch is updated, this test should be updated in the same PR.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

EXPECTED_PATHS: frozenset[str] = frozenset(
    {
        # auth
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/refresh",
        "/api/v1/auth/mfa/setup",
        "/api/v1/auth/mfa/verify",
        "/api/v1/auth/change-password",  # B2
        # users
        "/api/v1/users/me",
        "/api/v1/users/me/export",
        "/api/v1/users/me/delete",
        # projects
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/skills",
        # C7 — detach skill by name (extends the sketch).
        "/api/v1/projects/{project_id}/skills/{skill_name}",
        "/api/v1/projects/{project_id}/files",
        # C7 — detach file by id (extends the sketch).
        "/api/v1/projects/{project_id}/files/{file_id}",
        # chats + messages
        "/api/v1/chats",
        "/api/v1/chats/{chat_id}",
        "/api/v1/chats/{chat_id}/messages",
        "/api/v1/chats/{chat_id}/messages/{message_id}/citations",
        # skills
        "/api/v1/skills",
        "/api/v1/skills/{skill_name}",
        "/api/v1/skills/{skill_name}/fork",
        # internal (gateway → backend, ADR 0006 / C2)
        "/api/v1/internal/skills/{skill_name}",
        # files
        "/api/v1/files",
        "/api/v1/files/{file_id}",
        "/api/v1/files/{file_id}/content",
        # knowledge bases (C6)
        "/api/v1/knowledge-bases",
        "/api/v1/knowledge-bases/{kb_id}",
        "/api/v1/knowledge-bases/{kb_id}/files",
        "/api/v1/knowledge-bases/{kb_id}/files/{file_id}",
        "/api/v1/knowledge-bases/{kb_id}/query",
        # organization profile
        "/api/v1/organization-profile",
        # saved prompts
        "/api/v1/saved-prompts",
        "/api/v1/saved-prompts/{prompt_id}",
        # admin
        "/api/v1/admin/audit-log",
        "/api/v1/admin/tier-policy",
    }
)


@pytest.mark.unit
async def test_openapi_paths_match_sketch() -> None:
    """All paths from `backend-openapi.yaml` are registered.

    Counts: 30 from A4 + 1 from B2 (change-password) + 2 from C7
    (project file/skill detach by id) = 33 total.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    actual = {p for p in spec["paths"] if p.startswith("/api/v1")}
    assert actual == EXPECTED_PATHS, (
        f"OpenAPI surface drift. Missing: {EXPECTED_PATHS - actual}, "
        f"Extra: {actual - EXPECTED_PATHS}"
    )
    # 36 distinct /api/v1 paths: prior 34 (A4 base + B2 + C7 + C2)
    # plus C6's two new KB routes (/files and /files/{file_id} attach
    # surface; /search → /query rename keeps the count; +2 net).
    assert len(actual) == 36


@pytest.mark.unit
async def test_openapi_includes_health_and_ready() -> None:
    """Liveness and readiness are also documented in the spec."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    spec = response.json()
    assert "/health" in spec["paths"]
    assert "/ready" in spec["paths"]


@pytest.mark.unit
async def test_openapi_version_is_3_1() -> None:
    """We declare OpenAPI 3.1 — FastAPI emits this by default on recent versions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
    spec = response.json()
    # FastAPI >= 0.99 emits OpenAPI 3.1.x by default.
    assert spec["openapi"].startswith("3.1.")
