"""Integration tests for the org-skills harness endpoints (B-2a, ADR-F067 D2/D3).

Covers the FULL propose -> approve/reject/revoke -> catalog -> bind surface added across
``api/app/api/user_skills.py`` (author side), ``api/app/api/admin.py`` (review queue +
catalog/inventory extension), ``api/app/api/library.py`` (member-readable Library extension)
and ``api/app/api/practice_areas.py`` (bind acceptance). The pure synthesis/validation core
is covered separately in ``tests/test_org_skill_proposal.py``; the migration-level schema
invariants are in ``tests/test_migrations.py``.

Fixtures/style mirror ``tests/test_deployment_capabilities_api.py`` (client/user/admin
fixtures, the ``app.state.skill_registry`` install/restore pattern) and
``tests/test_practice_areas.py`` (bind acceptance flow, seeded area keys).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.org_skill import OrgSkillVersion
from app.models.practice_area import OrgLibraryEntry
from app.models.user import User
from app.models.user_skill import UserSkill
from app.skills import load_registry
from app.skills.org_proposal import synthesize_org_skill
from app.skills.registry import MutableSkillRegistry
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

# The alpha/beta/gamma test-fixture skill corpus (NOT the real shipped skills/ tree) — used to
# stand up a registry so the propose no-shadowing + bind registry-miss branches are exercised.
_FIXTURE_SKILLS_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="org-skill-author")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="org-skill-other")


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="org-skill-admin")
    u.is_admin = True
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def operator(db_session: AsyncSession) -> User:
    """The platform operator — an is_admin superset (passes AdminUser) but role='operator', so
    ADR-F064 excludes it from tenant-authored content like the org-skills queue."""
    u = await _make_user(db_session, suffix="org-skill-operator")
    u.is_admin = True
    u.role = "operator"
    await db_session.flush()
    return u


@pytest_asyncio.fixture(autouse=True)
async def _fixture_registry() -> AsyncIterator[None]:
    """Install the alpha/beta/gamma fixture skill registry for every test in this module.

    Propose now fails CLOSED without a registry (ADR-F067 D2 no-shadowing — the collision check
    is a security control that must never be skipped; see ``_require_skill_registry``), and the
    bind path's ``_registry(request)`` also needs one present so the registry-MISS branch is the
    one exercised. The fixture names collide with no proposed slug here EXCEPT the deliberate
    shipped-collision test (which proposes ``alpha-test-skill``)."""
    prior = getattr(app.state, "skill_registry", None)
    app.state.skill_registry = MutableSkillRegistry(load_registry(_FIXTURE_SKILLS_DIR))
    try:
        yield
    finally:
        if prior is None:
            delattr(app.state, "skill_registry")
        else:
            app.state.skill_registry = prior


async def _make_user_skill(
    db: AsyncSession,
    *,
    owner: User | None = None,
    owner_team_id: uuid.UUID | None = None,
    slug: str,
    scope: str = "user",
    display_name: str = "Harness Test Skill",
    description: str = "A skill proposed for org-wide adoption.",
    body: str = "# Harness Test Skill\n\nDo the thing, carefully.",
    tags: list[str] | None = None,
    frontmatter_extra: dict[str, object] | None = None,
    archived: bool = False,
) -> UserSkill:
    from datetime import UTC, datetime

    row = UserSkill(
        scope=scope,
        owner_user_id=owner.id if scope == "user" and owner is not None else None,
        owner_team_id=owner_team_id if scope == "team" else None,
        slug=slug,
        display_name=display_name,
        description=description,
        version="1.0.0",
        tags=tags or [],
        frontmatter_extra=frontmatter_extra or {},
        body=body,
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(row)
    await db.flush()
    return row


async def _propose(client: AsyncClient, actor: User, skill_id: uuid.UUID) -> dict:
    resp = await client.post(f"/api/v1/user-skills/{skill_id}/propose", headers=_bearer(actor))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _approve(client: AsyncClient, admin: User, version_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/admin/org-skills/{version_id}/approve", headers=_bearer(admin)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _latest_audit(db: AsyncSession, *, action: str, resource_id: str) -> AuditLog:
    row = (
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.action == action, AuditLog.resource_id == resource_id)
                .order_by(AuditLog.timestamp.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None, f"no audit row for action={action!r} resource_id={resource_id!r}"
    return row


# ---------------------------------------------------------------------------
# Propose — author side
# ---------------------------------------------------------------------------


async def test_propose_happy_path_matches_synthesis(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="propose-happy-path")
    body = await _propose(client, user, row.id)

    assert body["slug"] == "propose-happy-path"
    assert body["version_no"] == 1
    assert body["state"] == "proposed"
    assert body["reviewed_at"] is None
    assert body["revoked_at"] is None

    version = await db_session.get(OrgSkillVersion, uuid.UUID(body["id"]))
    assert version is not None
    expected = synthesize_org_skill(row)
    assert version.raw_yaml == expected.raw_yaml
    assert version.body == expected.body
    assert version.content_hash == expected.content_hash == body["content_hash"]
    assert body["size_bytes"] == expected.size_bytes
    assert version.author_user_id == user.id
    assert version.source_user_skill_id == row.id


async def test_propose_404_non_owner(
    client: AsyncClient, user: User, other_user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="propose-non-owner")
    resp = await client.post(f"/api/v1/user-skills/{row.id}/propose", headers=_bearer(other_user))
    assert resp.status_code == 404


async def test_propose_404_team_scope_row(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    """v1 is user-scope-only (ADR-F067 D2 "their own artifact") — a team-scope row 404s
    here exactly like a non-owned row, even for the row's own team-admin."""
    from app.models.team import Team, TeamMember

    team = Team(slug="org-skill-team", name="Org Skill Team", created_by_user_id=user.id)
    db_session.add(team)
    await db_session.flush()
    db_session.add(
        TeamMember(team_id=team.id, user_id=user.id, role="admin", added_by_user_id=user.id)
    )
    await db_session.flush()

    row = await _make_user_skill(
        db_session, owner_team_id=team.id, slug="propose-team-scope", scope="team"
    )

    resp = await client.post(f"/api/v1/user-skills/{row.id}/propose", headers=_bearer(user))
    assert resp.status_code == 404


async def test_propose_404_archived_row(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="propose-archived", archived=True)
    resp = await client.post(f"/api/v1/user-skills/{row.id}/propose", headers=_bearer(user))
    assert resp.status_code == 404


async def test_propose_422_denied_frontmatter_key(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(
        db_session,
        owner=user,
        slug="propose-denied-key",
        frontmatter_extra={"allowed-tools": ["redlining"]},
    )
    resp = await client.post(f"/api/v1/user-skills/{row.id}/propose", headers=_bearer(user))
    assert resp.status_code == 422
    assert "lq_ai.allowed-tools" in resp.json()["detail"]


async def test_propose_422_oversize(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="propose-oversize", body="A" * 40_000)
    resp = await client.post(f"/api/v1/user-skills/{row.id}/propose", headers=_bearer(user))
    assert resp.status_code == 422
    assert "32768" in resp.json()["detail"] or "bytes" in resp.json()["detail"]


async def test_propose_409_shipped_slug_collision(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    # 'alpha-test-skill' IS a name in the (autouse-installed) fixture registry → shipped wins.
    row = await _make_user_skill(db_session, owner=user, slug="alpha-test-skill")
    resp = await client.post(f"/api/v1/user-skills/{row.id}/propose", headers=_bearer(user))
    assert resp.status_code == 409


async def test_propose_409_duplicate_open_proposal(
    client: AsyncClient, user: User, other_user: User, db_session: AsyncSession
) -> None:
    """The one-open-proposal-per-slug rule is slug-global, not per-author."""
    row_a = await _make_user_skill(db_session, owner=user, slug="propose-dup-slug")
    await _propose(client, user, row_a.id)

    row_b = await _make_user_skill(db_session, owner=other_user, slug="propose-dup-slug")
    resp = await client.post(f"/api/v1/user-skills/{row_b.id}/propose", headers=_bearer(other_user))
    assert resp.status_code == 409


async def test_propose_version_no_increments_after_reject_and_repropose(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="propose-reject-repropose")
    first = await _propose(client, user, row.id)
    assert first["version_no"] == 1

    resp = await client.post(
        f"/api/v1/admin/org-skills/{first['id']}/reject",
        headers=_bearer(admin),
        json={"note": "not ready"},
    )
    assert resp.status_code == 200

    second = await _propose(client, user, row.id)
    assert second["version_no"] == 2


async def test_propose_audit_row_is_content_free(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(
        db_session,
        owner=user,
        slug="propose-audit-content-free",
        description="A very specific description string that must never leak into audit.",
        body="# Body\n\nA distinctive body sentence that must never leak into audit rows.",
    )
    body = await _propose(client, user, row.id)

    audit = await _latest_audit(db_session, action="library.propose", resource_id=body["id"])
    details = audit.details or {}
    assert set(details.keys()) <= {"kind", "key", "version", "content_hash", "size_bytes"}
    serialized = json.dumps(details)
    assert "distinctive body sentence" not in serialized
    assert row.body not in serialized
    assert row.description not in serialized


# ---------------------------------------------------------------------------
# Admin review — approve / reject / revoke
# ---------------------------------------------------------------------------


async def test_approve_flips_state_and_records_reviewer(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="approve-happy-path")
    proposal = await _propose(client, user, row.id)
    approved = await _approve(client, admin, proposal["id"])

    assert approved["state"] == "approved"
    assert approved["reviewed_at"] is not None
    # B-2b, D3.5 wire gap: approver_email mirrors author_email's resolution technique.
    assert approved["approver_email"] == admin.email

    version = await db_session.get(OrgSkillVersion, uuid.UUID(proposal["id"]))
    assert version is not None
    assert version.state == "approved"
    assert version.reviewed_by == admin.id


async def test_approve_supersedes_prior_approved_version(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="approve-supersede")
    v1 = await _propose(client, user, row.id)
    await _approve(client, admin, v1["id"])

    v2 = await _propose(client, user, row.id)
    assert v2["version_no"] == 2
    await _approve(client, admin, v2["id"])

    stale = await db_session.get(OrgSkillVersion, uuid.UUID(v1["id"]))
    assert stale is not None
    assert stale.state == "superseded"

    fresh = await db_session.get(OrgSkillVersion, uuid.UUID(v2["id"]))
    assert fresh is not None
    assert fresh.state == "approved"


async def test_approve_409_on_already_approved(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="approve-already-approved")
    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])

    resp = await client.post(
        f"/api/v1/admin/org-skills/{proposal['id']}/approve", headers=_bearer(admin)
    )
    assert resp.status_code == 409


async def test_approve_409_on_rejected(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="approve-rejected")
    proposal = await _propose(client, user, row.id)
    await client.post(
        f"/api/v1/admin/org-skills/{proposal['id']}/reject",
        headers=_bearer(admin),
        json={},
    )
    resp = await client.post(
        f"/api/v1/admin/org-skills/{proposal['id']}/approve", headers=_bearer(admin)
    )
    assert resp.status_code == 409


async def test_approve_audit_row_content_free_with_superseded(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="approve-audit-superseded")
    v1 = await _propose(client, user, row.id)
    await _approve(client, admin, v1["id"])
    v2 = await _propose(client, user, row.id)
    await _approve(client, admin, v2["id"])

    audit = await _latest_audit(db_session, action="library.approve", resource_id=v2["id"])
    details = audit.details or {}
    assert details["superseded_version"] == 1
    assert set(details.keys()) <= {
        "kind",
        "key",
        "version",
        "content_hash",
        "size_bytes",
        "superseded_version",
    }


async def test_reject_stores_note_and_audits_has_note_only(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="reject-note")
    proposal = await _propose(client, user, row.id)

    note_text = "Please tighten the description before resubmitting."
    resp = await client.post(
        f"/api/v1/admin/org-skills/{proposal['id']}/reject",
        headers=_bearer(admin),
        json={"note": note_text},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "rejected"
    assert body["review_note"] == note_text
    # A reject ALSO sets reviewed_by (it is a review outcome, not just an approval one) —
    # approver_email resolves it exactly like an approve's.
    assert body["approver_email"] == admin.email

    audit = await _latest_audit(db_session, action="library.reject", resource_id=proposal["id"])
    details = audit.details or {}
    assert details["has_note"] is True
    assert "note" not in details
    assert note_text not in json.dumps(details)


async def test_revoke_happy_path(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="revoke-happy-path")
    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])

    resp = await client.post(
        f"/api/v1/admin/org-skills/{proposal['id']}/revoke", headers=_bearer(admin)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "revoked"
    assert body["revoked_at"] is not None
    # revoke does NOT touch reviewed_by (ADR-F067 D3.8) — the approving admin's
    # approver_email survives the revoke transition untouched.
    assert body["approver_email"] == admin.email


async def test_revoke_409_on_proposed(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="revoke-still-proposed")
    proposal = await _propose(client, user, row.id)

    resp = await client.post(
        f"/api/v1/admin/org-skills/{proposal['id']}/revoke", headers=_bearer(admin)
    )
    assert resp.status_code == 409


async def test_admin_org_skills_routes_require_admin_and_auth(
    client: AsyncClient, user: User
) -> None:
    resp = await client.get("/api/v1/admin/org-skills", headers=_bearer(user))
    assert resp.status_code == 403

    resp = await client.get("/api/v1/admin/org-skills")
    assert resp.status_code == 401


async def test_operator_excluded_from_org_skill_list(client: AsyncClient, operator: User) -> None:
    """ADR-F064: the operator passes the AdminUser gate but is excluded from tenant-authored
    content — 403 on the org-skills review queue."""
    resp = await client.get("/api/v1/admin/org-skills", headers=_bearer(operator))
    assert resp.status_code == 403


async def test_operator_excluded_from_org_skill_approve(
    client: AsyncClient, user: User, operator: User, db_session: AsyncSession
) -> None:
    """ADR-F064: the operator cannot approve a tenant-authored proposal — 403."""
    row = await _make_user_skill(db_session, owner=user, slug="operator-excluded-approve")
    proposal = await _propose(client, user, row.id)
    resp = await client.post(
        f"/api/v1/admin/org-skills/{proposal['id']}/approve", headers=_bearer(operator)
    )
    assert resp.status_code == 403


async def test_list_org_skill_versions_rejects_unknown_state(
    client: AsyncClient, admin: User
) -> None:
    resp = await client.get(
        "/api/v1/admin/org-skills", params={"state": "bogus"}, headers=_bearer(admin)
    )
    assert resp.status_code == 422


async def test_list_org_skill_versions_includes_approver_email(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    """The review-queue GET (B-2b's data source) carries author_email AND
    approver_email per row — None on a still-proposed row, resolved once reviewed."""
    row = await _make_user_skill(db_session, owner=user, slug="list-approver-email")
    proposal = await _propose(client, user, row.id)

    resp = await client.get("/api/v1/admin/org-skills", headers=_bearer(admin))
    assert resp.status_code == 200
    row_before = next(v for v in resp.json()["versions"] if v["id"] == proposal["id"])
    assert row_before["author_email"] == user.email
    assert row_before["approver_email"] is None

    await _approve(client, admin, proposal["id"])

    resp = await client.get("/api/v1/admin/org-skills", headers=_bearer(admin))
    assert resp.status_code == 200
    row_after = next(v for v in resp.json()["versions"] if v["id"] == proposal["id"])
    assert row_after["approver_email"] == admin.email


# ---------------------------------------------------------------------------
# Catalog / capabilities / member Library read
# ---------------------------------------------------------------------------


async def test_adopt_org_skill_422_before_approval_204_after(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="catalog-adopt-flow")

    resp = await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "skill", "key": "catalog-adopt-flow"},
    )
    assert resp.status_code == 422

    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])

    resp = await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "skill", "key": "catalog-adopt-flow"},
    )
    assert resp.status_code == 204


async def test_capabilities_lists_org_skill_with_source_and_in_library_flip(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(
        db_session,
        owner=user,
        slug="catalog-capabilities-flip",
        display_name="Capabilities Flip Skill",
        tags=["review"],
    )
    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])

    resp = await client.get("/api/v1/admin/capabilities", headers=_bearer(admin))
    assert resp.status_code == 200
    skills = {
        e["capability_key"]: e
        for e in next(s for s in resp.json()["sections"] if s["kind"] == "skill")["entries"]
    }
    entry = skills["catalog-capabilities-flip"]
    assert entry["source"] == "org"
    assert entry["label"] == "Capabilities Flip Skill"
    assert entry["author"] == user.email
    assert entry["version"] == "1.0.0"
    assert entry["in_library"] is False
    # B-2b, D3.5 wire gap: the catalog entry also carries the approver (reviewed_by
    # resolved to an email), additive alongside author.
    assert entry["approver"] == admin.email

    await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "skill", "key": "catalog-capabilities-flip"},
    )
    resp = await client.get("/api/v1/admin/capabilities", headers=_bearer(admin))
    skills = {
        e["capability_key"]: e
        for e in next(s for s in resp.json()["sections"] if s["kind"] == "skill")["entries"]
    }
    assert skills["catalog-capabilities-flip"]["in_library"] is True


async def test_library_read_shows_label_and_source_after_adoption(
    client: AsyncClient, user: User, other_user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(
        db_session,
        owner=user,
        slug="library-read-org-skill",
        display_name="Library Read Org Skill",
    )
    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])
    await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "skill", "key": "library-read-org-skill"},
    )

    # Member-readable: any active user, not just the admin (transparency, CLAUDE.md).
    resp = await client.get("/api/v1/library", headers=_bearer(other_user))
    assert resp.status_code == 200
    entry = next(e for e in resp.json()["entries"] if e["key"] == "library-read-org-skill")
    assert entry["label"] == "Library Read Org Skill"
    assert entry["source"] == "org"
    # The member-readable Library surface carries no cross-user identifiers (module
    # docstring) — author is admin/audit territory only (GET /admin/capabilities).
    assert entry["author"] is None
    # approver DOES surface here (B-2b, D3.5) — "an admin reviewed and approved this"
    # is not the same disclosure as "who wrote it".
    assert entry["approver"] == admin.email


async def test_revoked_slug_disappears_from_capabilities_but_adopted_row_dangles(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="catalog-revoke-dangling")
    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])
    await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "skill", "key": "catalog-revoke-dangling"},
    )

    await client.post(f"/api/v1/admin/org-skills/{proposal['id']}/revoke", headers=_bearer(admin))

    resp = await client.get("/api/v1/admin/capabilities", headers=_bearer(admin))
    skill_keys = {
        e["capability_key"]
        for e in next(s for s in resp.json()["sections"] if s["kind"] == "skill")["entries"]
    }
    assert "catalog-revoke-dangling" not in skill_keys

    # The Library row itself is untouched (ADR-F067 D3.8 — revoke does NOT delete it);
    # the member read shows it dangling (label=None) per today's read-model contract.
    library_row = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "skill",
                OrgLibraryEntry.capability_key == "catalog-revoke-dangling",
            )
        )
    ).scalar_one_or_none()
    assert library_row is not None

    resp = await client.get("/api/v1/library", headers=_bearer(admin))
    entry = next(e for e in resp.json()["entries"] if e["key"] == "catalog-revoke-dangling")
    assert entry["label"] is None
    assert entry["source"] is None


# ---------------------------------------------------------------------------
# Bind — practice-area skill attachment
# ---------------------------------------------------------------------------


async def test_bind_approved_and_adopted_org_skill_succeeds(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="bind-approved-adopted")
    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])
    await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "skill", "key": "bind-approved-adopted"},
    )

    resp = await client.post(
        "/api/v1/practice-areas/commercial/skills",
        headers=_bearer(admin),
        json={"skill_name": "bind-approved-adopted"},
    )
    assert resp.status_code == 204


async def test_bind_merely_proposed_org_skill_is_404(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="bind-merely-proposed")
    await _propose(client, user, row.id)

    resp = await client.post(
        "/api/v1/practice-areas/commercial/skills",
        headers=_bearer(admin),
        json={"skill_name": "bind-merely-proposed"},
    )
    assert resp.status_code == 404


async def test_bind_approved_but_unadopted_org_skill_is_422(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="bind-approved-unadopted")
    proposal = await _propose(client, user, row.id)
    await _approve(client, admin, proposal["id"])

    resp = await client.post(
        "/api/v1/practice-areas/commercial/skills",
        headers=_bearer(admin),
        json={"skill_name": "bind-approved-unadopted"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /user-skills/{id}/proposals — author version history
# ---------------------------------------------------------------------------


async def test_list_proposals_returns_authors_history_newest_first(
    client: AsyncClient, user: User, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="proposals-history")
    v1 = await _propose(client, user, row.id)
    await client.post(
        f"/api/v1/admin/org-skills/{v1['id']}/reject", headers=_bearer(admin), json={}
    )
    v2 = await _propose(client, user, row.id)

    resp = await client.get(f"/api/v1/user-skills/{row.id}/proposals", headers=_bearer(user))
    assert resp.status_code == 200
    items = resp.json()
    assert [i["version_no"] for i in items] == [2, 1]
    assert items[0]["id"] == v2["id"]
    assert items[1]["state"] == "rejected"


async def test_list_proposals_404_for_non_owner(
    client: AsyncClient, user: User, other_user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="proposals-non-owner")
    resp = await client.get(f"/api/v1/user-skills/{row.id}/proposals", headers=_bearer(other_user))
    assert resp.status_code == 404
