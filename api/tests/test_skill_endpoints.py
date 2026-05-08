"""Integration tests for the C1 skill HTTP endpoints.

Covers the wire-shape side of the C1 surface:

* ``GET /api/v1/skills`` — list summaries; tag filter; scope filter;
  401 without auth; 403 with B2 must-change-password gate.
* ``GET /api/v1/skills/{name}`` — full detail (body + frontmatter +
  reference/example files); 404 for unknown name; auth gates.

The tests use the same DB-backed conftest pattern other integration
tests in this suite use (SAVEPOINT-rolled-back per test). The skill
registry is injected directly into ``app.state`` for each test (the
ASGI in-process client doesn't trigger lifespan, by design — this is
how every integration test in the suite handles process-global state).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.security import create_access_token, hash_password
from app.skills import load_registry
from app.skills.registry import MutableSkillRegistry

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"skill-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Skill Test User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def gated_user(db_session: AsyncSession) -> User:
    """User with must_change_password=True — should hit the B2 gate."""

    user = User(
        email=f"skill-gated-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Gated Test User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """In-process AsyncClient with the fixture-skills registry installed."""

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


def _bearer(user: User) -> str:
    return create_access_token(user.id, user.email, is_admin=user.is_admin)


# --- /api/v1/skills (list) ---------------------------------------------------


@pytest.mark.integration
async def test_list_skills_unauthenticated_returns_401(client: AsyncClient) -> None:
    """No bearer token → 401, with the standard WWW-Authenticate header."""

    resp = await client.get("/api/v1/skills")
    assert resp.status_code == 401
    assert "Bearer" in resp.headers.get("www-authenticate", "")


@pytest.mark.integration
async def test_list_skills_must_change_password_gate(client: AsyncClient, gated_user: User) -> None:
    """`must_change_password=True` → 403 with `password_change_required`."""

    token = _bearer(gated_user)
    resp = await client.get("/api/v1/skills", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["code"] == "password_change_required"


@pytest.mark.integration
async def test_list_skills_happy_path(client: AsyncClient, db_user: User) -> None:
    """Returns every fixture skill, sorted by name, with summary fields."""

    token = _bearer(db_user)
    resp = await client.get("/api/v1/skills", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    names = [item["name"] for item in body]
    assert names == sorted(names)
    assert set(names) >= {"alpha-test-skill", "beta-minimal", "gamma-tagged"}

    # Spot-check the alpha skill's summary fields.
    alpha = next(item for item in body if item["name"] == "alpha-test-skill")
    assert alpha["scope"] == "builtin"
    assert alpha["title"] == "Alpha Test Skill"
    assert alpha["version"] == "1.0.0"
    assert alpha["jurisdiction"] == "agnostic"
    assert alpha["minimum_inference_tier"] == 2
    assert "test" in alpha["tags"]
    # Body / frontmatter content is NOT in the summary.
    assert "content_md" not in alpha
    assert "content_yaml" not in alpha


@pytest.mark.integration
async def test_list_skills_filters_by_tag(client: AsyncClient, db_user: User) -> None:
    """`?tag=` selects only skills whose frontmatter tags include the value."""

    token = _bearer(db_user)
    resp = await client.get(
        "/api/v1/skills?tag=special-tag",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [item["name"] for item in body] == ["gamma-tagged"]


@pytest.mark.integration
async def test_list_skills_scope_user_returns_empty(client: AsyncClient, db_user: User) -> None:
    """User-scope is empty until DB-backed forks land (post-C1)."""

    token = _bearer(db_user)
    resp = await client.get(
        "/api/v1/skills?scope=user",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
async def test_list_skills_scope_invalid_rejected(client: AsyncClient, db_user: User) -> None:
    """An out-of-enum `scope` returns 422 (FastAPI's pattern enforcement)."""

    token = _bearer(db_user)
    resp = await client.get(
        "/api/v1/skills?scope=junk",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_list_skills_omits_empty_optional_fields(client: AsyncClient, db_user: User) -> None:
    """Sparse-frontmatter skills omit `tags` / `jurisdiction` from the wire shape."""

    token = _bearer(db_user)
    resp = await client.get("/api/v1/skills", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    beta = next(item for item in body if item["name"] == "beta-minimal")
    # `beta-minimal` has no lq_ai namespace — empty/None optional fields
    # should be dropped from the response.
    assert "tags" not in beta
    assert "jurisdiction" not in beta
    assert "minimum_inference_tier" not in beta
    # The contract-required fields are still present.
    assert beta["name"] == "beta-minimal"
    assert beta["scope"] == "builtin"
    assert beta["version"] == "unversioned"
    assert beta["title"]  # humanised


# --- /api/v1/skills/{name} (detail) -----------------------------------------


@pytest.mark.integration
async def test_get_skill_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/skills/alpha-test-skill")
    assert resp.status_code == 401


@pytest.mark.integration
async def test_get_skill_must_change_password_gate(client: AsyncClient, gated_user: User) -> None:
    token = _bearer(gated_user)
    resp = await client.get(
        "/api/v1/skills/alpha-test-skill",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "password_change_required"


@pytest.mark.integration
async def test_get_skill_happy_path(client: AsyncClient, db_user: User) -> None:
    """Returns the full Skill shape: summary fields + content + lazy files."""

    token = _bearer(db_user)
    resp = await client.get(
        "/api/v1/skills/alpha-test-skill",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "alpha-test-skill"
    assert body["version"] == "1.0.0"
    assert body["scope"] == "builtin"

    # Body markdown is present.
    assert "Alpha Test Skill" in body["content_md"]
    assert "Workflow" in body["content_md"]

    # Verbatim YAML frontmatter is present.
    assert "name: alpha-test-skill" in body["content_yaml"]
    assert "minimum_inference_tier" in body["content_yaml"]

    # Reference files are loaded lazily.
    ref_paths = {f["path"] for f in body["reference_files"]}
    assert "reference/note.md" in ref_paths
    note = next(f for f in body["reference_files"] if f["path"] == "reference/note.md")
    assert "synthetic reference file" in note["content"]

    # Example files are loaded lazily.
    ex_paths = {f["path"] for f in body["example_files"]}
    assert "examples/basic.md" in ex_paths


@pytest.mark.integration
async def test_get_skill_unknown_name_returns_404(client: AsyncClient, db_user: User) -> None:
    """Unknown skill name → 404 with the structured `not_found` error envelope."""

    token = _bearer(db_user)
    resp = await client.get(
        "/api/v1/skills/never-existed",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "not_found"
    assert body["detail"]["details"]["skill_name"] == "never-existed"


@pytest.mark.integration
async def test_get_skill_minimal_skill_has_empty_reference_lists(
    client: AsyncClient, db_user: User
) -> None:
    """Skills with no reference/ or examples/ folders return empty lists."""

    token = _bearer(db_user)
    resp = await client.get(
        "/api/v1/skills/beta-minimal",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # The lazy-loader returns empty lists for missing subfolders rather
    # than omitting the fields — that matches the OpenAPI shape.
    assert body.get("reference_files", []) == []
    assert body.get("example_files", []) == []
