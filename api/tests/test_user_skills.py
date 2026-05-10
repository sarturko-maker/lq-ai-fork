"""Integration tests for Task D8 — DB-backed user skills (ADR 0012).

Covers the new ``/api/v1/user-skills`` CRUD surface and the merge /
shadow / fork extensions to ``/api/v1/skills``:

* POST/GET/PATCH/DELETE on the user-scope row; cross-user 404 isolation.
* Slug-collision rules: same-user-same-slug → 409; user-slug-shadows-
  built-in → 201 OK (the deliberate shadow case per ADR 0012).
* Soft-delete via ``archived_at``: re-create at same slug after delete
  succeeds; double-delete returns 410.
* Merged ``GET /skills`` listing: user-scope first, built-in second,
  user shadow dedupes its matching built-in.
* ``GET /skills/{slug}`` returns the shadow when present, falls back
  to the built-in otherwise.
* ``POST /skills/{slug}/fork`` copies a built-in into user scope;
  ``scope=team`` returns 400 (deferred to D8.1).
* Audit rows land on every state-changing call; the PATCH version-bump
  path records ``version_before`` / ``version_after``.
* Migration 0013 schema invariants: CHECK constraints, partial UNIQUE
  indexes, FK to users with CASCADE.

Tests follow the project's SAVEPOINT-rolled-back integration pattern;
the skill registry is injected via ``app.state.skill_registry``
(matches ``test_skill_endpoints.py``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models import AuditLog, User, UserSkill
from app.security import create_access_token, hash_password
from app.skills import load_registry
from app.skills.registry import MutableSkillRegistry

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


async def _make_user(db_session: AsyncSession, *, suffix: str = "") -> User:
    user = User(
        email=f"user-skill-{suffix or uuid.uuid4().hex[:8]}@example.com",
        display_name=f"User Skill Test {suffix}".strip(),
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="a")


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="b")


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


def _bearer(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


def _post_body(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "slug": "personal-nda",
        "display_name": "Personal NDA",
        "description": "My NDA workflow",
        "body": "You review NDAs with attention to noncompetes.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# /user-skills: create + list + get
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_user_skill_returns_201_and_persists(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    resp = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["scope"] == "user"
    assert body["slug"] == "personal-nda"
    assert body["owner_user_id"] == str(user_a.id)
    assert body["version"] == "1.0.0"
    assert body["archived_at"] is None

    row = await db_session.get(UserSkill, uuid.UUID(body["id"]))
    assert row is not None
    assert row.owner_user_id == user_a.id


@pytest.mark.integration
async def test_list_user_skills_is_owner_scoped_and_newest_first(
    client: AsyncClient, db_session: AsyncSession, user_a: User, user_b: User
) -> None:
    """A's list shows only A's rows in updated_at DESC order; B's row never appears."""

    # Insert via the API so updated_at is set by the trigger-friendly path.
    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="alpha-skill", display_name="A1"),
    )
    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="beta-skill", display_name="A2"),
    )
    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_b),
        json=_post_body(slug="alpha-skill", display_name="B1"),
    )

    resp = await client.get("/api/v1/user-skills", headers=_bearer(user_a))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert {r["slug"] for r in rows} == {"alpha-skill", "beta-skill"}
    # Both rows owned by A; no B rows leaked.
    assert all(r["owner_user_id"] == str(user_a.id) for r in rows)


@pytest.mark.integration
async def test_get_user_skill_returns_404_for_non_owner(
    client: AsyncClient, user_a: User, user_b: User
) -> None:
    resp = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    skill_id = resp.json()["id"]

    cross = await client.get(
        f"/api/v1/user-skills/{skill_id}", headers=_bearer(user_b)
    )
    assert cross.status_code == 404


# ---------------------------------------------------------------------------
# /user-skills: slug collision (own + built-in shadow)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_collides_with_own_slug_returns_409(
    client: AsyncClient, user_a: User
) -> None:
    first = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    assert second.status_code == 409


@pytest.mark.integration
async def test_create_collides_with_builtin_slug_is_allowed(
    client: AsyncClient, user_a: User
) -> None:
    """Slug shadowing a filesystem built-in is the deliberate fork case (ADR 0012)."""

    resp = await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="alpha-test-skill", display_name="My Alpha"),
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# /user-skills: PATCH semantics + version-bump audit
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_patch_partial_update_writes_audit_row(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    created = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    skill_id = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/user-skills/{skill_id}",
        headers=_bearer(user_a),
        json={"display_name": "Renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Renamed"

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user_skill.updated",
                AuditLog.resource_id == skill_id,
            )
        )
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].details["changed_fields"] == ["display_name"]


@pytest.mark.integration
async def test_patch_version_bump_records_before_and_after_in_audit(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    created = await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(version="1.0.0"),
    )
    skill_id = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/user-skills/{skill_id}",
        headers=_bearer(user_a),
        json={"version": "1.1.0"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.1.0"

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user_skill.updated",
                AuditLog.resource_id == skill_id,
            )
        )
    ).scalar_one()
    assert audit.details["version_before"] == "1.0.0"
    assert audit.details["version_after"] == "1.1.0"


@pytest.mark.integration
async def test_patch_no_op_does_not_write_audit_row(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    created = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    skill_id = created.json()["id"]

    # PATCH with the same display_name → handler short-circuits without
    # an audit row to avoid log churn from idempotent UI re-saves.
    resp = await client.patch(
        f"/api/v1/user-skills/{skill_id}",
        headers=_bearer(user_a),
        json={"display_name": "Personal NDA"},
    )
    assert resp.status_code == 200

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user_skill.updated",
                AuditLog.resource_id == skill_id,
            )
        )
    ).scalars().all()
    assert audit == []


@pytest.mark.integration
async def test_patch_non_owner_returns_404(
    client: AsyncClient, user_a: User, user_b: User
) -> None:
    created = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    skill_id = created.json()["id"]
    cross = await client.patch(
        f"/api/v1/user-skills/{skill_id}",
        headers=_bearer(user_b),
        json={"display_name": "I am evil"},
    )
    assert cross.status_code == 404


# ---------------------------------------------------------------------------
# /user-skills: soft-delete + 410 + slug re-use
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_delete_soft_deletes_and_writes_audit(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    created = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    skill_id = created.json()["id"]

    resp = await client.delete(
        f"/api/v1/user-skills/{skill_id}", headers=_bearer(user_a)
    )
    assert resp.status_code == 204

    row = await db_session.get(UserSkill, uuid.UUID(skill_id))
    assert row is not None
    assert row.archived_at is not None

    # Default list excludes archived rows.
    listing = await client.get("/api/v1/user-skills", headers=_bearer(user_a))
    assert listing.json() == []

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user_skill.deleted",
                AuditLog.resource_id == skill_id,
            )
        )
    ).scalar_one()
    assert audit.details["slug"] == "personal-nda"


@pytest.mark.integration
async def test_delete_then_delete_returns_410(
    client: AsyncClient, user_a: User
) -> None:
    created = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    skill_id = created.json()["id"]
    first = await client.delete(
        f"/api/v1/user-skills/{skill_id}", headers=_bearer(user_a)
    )
    assert first.status_code == 204
    second = await client.delete(
        f"/api/v1/user-skills/{skill_id}", headers=_bearer(user_a)
    )
    assert second.status_code == 410


@pytest.mark.integration
async def test_recreate_at_same_slug_after_delete_succeeds(
    client: AsyncClient, user_a: User
) -> None:
    """Archiving a row frees the slug for a new creation."""

    first = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    await client.delete(
        f"/api/v1/user-skills/{first.json()['id']}", headers=_bearer(user_a)
    )
    second = await client.post(
        "/api/v1/user-skills", headers=_bearer(user_a), json=_post_body()
    )
    assert second.status_code == 201
    assert second.json()["slug"] == "personal-nda"


# ---------------------------------------------------------------------------
# /skills: merged listing with user shadow
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_merged_list_shows_user_rows_first(
    client: AsyncClient, user_a: User
) -> None:
    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="zeta-rare"),
    )
    resp = await client.get("/api/v1/skills", headers=_bearer(user_a))
    assert resp.status_code == 200
    rows = resp.json()
    # User-scope rows precede built-ins regardless of name ordering.
    assert rows[0]["scope"] == "user"
    assert rows[0]["name"] == "zeta-rare"


@pytest.mark.integration
async def test_merged_list_dedupes_built_in_on_user_shadow(
    client: AsyncClient, user_a: User
) -> None:
    """A user shadow at slug=alpha-test-skill hides the built-in for that user."""

    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="alpha-test-skill", display_name="My Alpha"),
    )
    resp = await client.get("/api/v1/skills", headers=_bearer(user_a))
    rows = resp.json()
    alpha_rows = [r for r in rows if r["name"] == "alpha-test-skill"]
    assert len(alpha_rows) == 1
    assert alpha_rows[0]["scope"] == "user"
    assert alpha_rows[0]["title"] == "My Alpha"


@pytest.mark.integration
async def test_merged_list_scope_filters_independently(
    client: AsyncClient, user_a: User
) -> None:
    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="alpha-test-skill"),
    )

    user_only = await client.get(
        "/api/v1/skills?scope=user", headers=_bearer(user_a)
    )
    assert all(r["scope"] == "user" for r in user_only.json())

    builtin_only = await client.get(
        "/api/v1/skills?scope=builtin", headers=_bearer(user_a)
    )
    # builtin scope does NOT apply the shadow dedup — operator-side
    # surfaces (e.g., the "as-shipped catalog" admin view) need the
    # raw view. The handler returns built-ins straight from the
    # registry.
    builtin_rows = builtin_only.json()
    assert all(r["scope"] == "builtin" for r in builtin_rows)
    assert any(r["name"] == "alpha-test-skill" for r in builtin_rows)

    team_only = await client.get(
        "/api/v1/skills?scope=team", headers=_bearer(user_a)
    )
    assert team_only.json() == []


# ---------------------------------------------------------------------------
# /skills/{slug}: shadow resolution
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_skill_returns_shadow_when_present(
    client: AsyncClient, user_a: User
) -> None:
    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="alpha-test-skill", body="my custom body"),
    )
    resp = await client.get(
        "/api/v1/skills/alpha-test-skill", headers=_bearer(user_a)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "user"
    assert body["content_md"] == "my custom body"


@pytest.mark.integration
async def test_get_skill_falls_back_to_builtin_when_no_shadow(
    client: AsyncClient, user_a: User
) -> None:
    resp = await client.get(
        "/api/v1/skills/alpha-test-skill", headers=_bearer(user_a)
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "builtin"


@pytest.mark.integration
async def test_get_skill_shadow_is_per_user(
    client: AsyncClient, user_a: User, user_b: User
) -> None:
    """A's shadow does not affect B's resolution."""

    await client.post(
        "/api/v1/user-skills",
        headers=_bearer(user_a),
        json=_post_body(slug="alpha-test-skill", body="A's body"),
    )
    b_resp = await client.get(
        "/api/v1/skills/alpha-test-skill", headers=_bearer(user_b)
    )
    assert b_resp.status_code == 200
    body = b_resp.json()
    assert body["scope"] == "builtin"
    assert "A's body" not in body["content_md"]


# ---------------------------------------------------------------------------
# /skills/{slug}/fork
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_fork_copies_built_in_into_user_scope(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    resp = await client.post(
        "/api/v1/skills/alpha-test-skill/fork",
        headers=_bearer(user_a),
        json={"new_name": "my-alpha", "scope": "user"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["scope"] == "user"
    assert body["name"] == "my-alpha"
    # Tier and other extension keys carried through frontmatter_extra.
    assert body.get("minimum_inference_tier") == 2

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "user_skill.created")
        )
    ).scalars().all()
    assert any(a.details.get("forked_from") == "alpha-test-skill" for a in audit)


@pytest.mark.integration
async def test_fork_team_scope_returns_400(
    client: AsyncClient, user_a: User
) -> None:
    resp = await client.post(
        "/api/v1/skills/alpha-test-skill/fork",
        headers=_bearer(user_a),
        json={"new_name": "team-alpha", "scope": "team"},
    )
    assert resp.status_code == 400
    assert "D8.1" in resp.json()["detail"]


@pytest.mark.integration
async def test_fork_unknown_source_returns_404(
    client: AsyncClient, user_a: User
) -> None:
    resp = await client.post(
        "/api/v1/skills/does-not-exist/fork",
        headers=_bearer(user_a),
        json={"new_name": "x", "scope": "user"},
    )
    assert resp.status_code == 404


@pytest.mark.integration
async def test_fork_default_slug_creates_same_name_shadow(
    client: AsyncClient, user_a: User
) -> None:
    """Omitting ``new_name`` → forked row inherits the source slug, which
    is the natural "I want my own version of nda-review" shadow case."""

    resp = await client.post(
        "/api/v1/skills/alpha-test-skill/fork",
        headers=_bearer(user_a),
        json={"scope": "user"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "alpha-test-skill"
    assert resp.json()["scope"] == "user"


# ---------------------------------------------------------------------------
# Migration 0013 invariants
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_user_skills_check_constraints(
    db_session: AsyncSession, user_a: User
) -> None:
    """The scope/owner-consistency CHECK rejects mismatched rows."""

    bad = UserSkill(
        scope="user",
        owner_user_id=None,  # violates CHECK
        slug="bad",
        display_name="bad",
        description="bad",
        body="bad",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_user_skills_partial_unique_index(
    db_session: AsyncSession, user_a: User
) -> None:
    """Two non-archived rows for the same (user, slug) violate uniqueness."""

    first = UserSkill(
        scope="user",
        owner_user_id=user_a.id,
        slug="dup",
        display_name="first",
        description="first",
        body="first",
    )
    db_session.add(first)
    await db_session.flush()

    second = UserSkill(
        scope="user",
        owner_user_id=user_a.id,
        slug="dup",
        display_name="second",
        description="second",
        body="second",
    )
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_user_skills_table_indexes_exist(db_session: AsyncSession) -> None:
    expected = {
        "idx_user_skills_owner_user",
        "idx_user_skills_owner_team",
        "ux_user_skills_user_slug",
        "ux_user_skills_team_slug",
    }
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(:names)"
        ),
        {"names": list(expected)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected, f"missing: {expected - found}"
