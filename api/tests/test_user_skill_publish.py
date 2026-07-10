"""Integration tests for the admin skill fast-path — POST /user-skills/{id}/publish.

The fast-path (ADR-F067 "Publish") collapses propose -> approve -> adopt into ONE atomic action
for a skill the ADMIN AUTHORED THEMSELVES. These tests cover the full matrix from the slice plan
(``docs/fork/plans/PUBLISH-admin-skill-fast-path.md``): the happy path (201 + frozen approved
snapshot + Library row + three content-free audit rows incl. ``fast_path: True``), the operator
fence (403), the AdminUser gate (403), owner-scoping (404), the write-time gate battery incl. the
injection battery (422 per denied frontmatter key) and the fail-closed registry check (500), and
the idempotency behaviours (unchanged re-publish -> 200 no-op; edited re-publish -> supersede with
no new adopt; already-in-library idempotent adopt).

Fixtures/style mirror ``tests/test_org_skill_harness_api.py`` — same ``app.state.skill_registry``
install/restore pattern and the same ``_make_user_skill`` / ``_propose`` / ``_approve`` /
``_latest_audit`` helpers, imported to avoid divergence.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.org_skill import OrgSkillVersion
from app.models.practice_area import OrgLibraryEntry
from app.models.user import User
from app.skills import load_registry
from app.skills.registry import MutableSkillRegistry
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db
from tests.test_org_skill_harness_api import (
    _latest_audit,
    _make_user_skill,
    _propose,
)

pytestmark = pytest.mark.integration

# The alpha/beta/gamma fixture skill corpus (NOT the real shipped skills/ tree) — stands up a
# registry so the no-shadowing collision + fail-closed branches are exercised.
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
    return await _make_user(db_session, suffix="publish-author")


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="publish-admin")
    u.is_admin = True
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def operator(db_session: AsyncSession) -> User:
    """The platform operator — an is_admin superset (passes AdminUser) but role='operator', so
    ADR-F064 excludes it from tenant-authored content like an approve/publish."""
    u = await _make_user(db_session, suffix="publish-operator")
    u.is_admin = True
    u.role = "operator"
    await db_session.flush()
    return u


@pytest_asyncio.fixture(autouse=True)
async def _fixture_registry() -> AsyncIterator[None]:
    """Install the alpha/beta/gamma fixture skill registry for every test in this module.

    Publish fails CLOSED without a registry (ADR-F067 D2 no-shadowing — the collision check is a
    security control that must never be skipped); the registry-absent test deletes it explicitly."""
    prior = getattr(app.state, "skill_registry", None)
    app.state.skill_registry = MutableSkillRegistry(load_registry(_FIXTURE_SKILLS_DIR))
    try:
        yield
    finally:
        if prior is None:
            if getattr(app.state, "skill_registry", None) is not None:
                delattr(app.state, "skill_registry")
        else:
            app.state.skill_registry = prior


async def _publish(
    client: AsyncClient, admin: User, skill_id: uuid.UUID, *, expect: int = 201
) -> dict:
    resp = await client.post(f"/api/v1/user-skills/{skill_id}/publish", headers=_bearer(admin))
    assert resp.status_code == expect, resp.text
    return resp.json()


async def _count_audits(db: AsyncSession, *, action: str, resource_id: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == action, AuditLog.resource_id == resource_id)
        )
    ).scalar_one()


async def _library_row(db: AsyncSession, slug: str) -> OrgLibraryEntry | None:
    return (
        await db.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "skill",
                OrgLibraryEntry.capability_key == slug,
            )
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_publish_happy_path_mints_approved_snapshot_and_adopts(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=admin, slug="publish-happy-path")
    body = await _publish(client, admin, row.id)

    # 201 + a frozen APPROVED snapshot authored AND approved by the admin (self-approval, D2).
    assert body["state"] == "approved"
    assert body["slug"] == "publish-happy-path"
    assert body["version_no"] == 1
    assert body["author_email"] == admin.email
    assert body["approver_email"] == admin.email
    assert body["reviewed_at"] is not None

    version = await db_session.get(OrgSkillVersion, uuid.UUID(body["id"]))
    assert version is not None
    assert version.state == "approved"
    assert version.reviewed_by == admin.id
    assert version.author_user_id == admin.id

    # Adopted into the Org Library.
    assert await _library_row(db_session, "publish-happy-path") is not None

    # Exactly THREE content-free audit actions: propose + approve (fast_path) + adopt.
    propose_audit = await _latest_audit(
        db_session, action="library.propose", resource_id=body["id"]
    )
    approve_audit = await _latest_audit(
        db_session, action="library.approve", resource_id=body["id"]
    )
    adopt_audit = await _latest_audit(
        db_session, action="library.adopt", resource_id="publish-happy-path"
    )
    assert approve_audit.details["fast_path"] is True
    assert approve_audit.details["superseded_version"] is None
    assert adopt_audit.details == {"kind": "skill", "key": "publish-happy-path"}

    total = (
        await db_session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action.in_(["library.propose", "library.approve", "library.adopt"]),
                AuditLog.resource_id.in_([body["id"], "publish-happy-path"]),
            )
        )
    ).scalar_one()
    assert total == 3

    # Content-free: no body/description bytes anywhere in the audit details.
    for audit in (propose_audit, approve_audit, adopt_audit):
        details = audit.details or {}
        serialized = json.dumps(details)
        assert row.body not in serialized
        assert row.description not in serialized
    assert set(propose_audit.details.keys()) <= {
        "kind",
        "key",
        "version",
        "content_hash",
        "size_bytes",
    }
    assert set(approve_audit.details.keys()) <= {
        "kind",
        "key",
        "version",
        "content_hash",
        "size_bytes",
        "superseded_version",
        "fast_path",
    }


# ---------------------------------------------------------------------------
# Authz — operator fence + AdminUser gate + owner-scoping
# ---------------------------------------------------------------------------


async def test_publish_operator_excluded_403(
    client: AsyncClient, operator: User, db_session: AsyncSession
) -> None:
    """ADR-F064: the operator passes the AdminUser gate but publish performs an approve of
    tenant-authored content — 403 on the INNER tenant_admin_visibility check."""
    row = await _make_user_skill(db_session, owner=operator, slug="publish-operator")
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(operator))
    assert resp.status_code == 403
    # Fence fires before any mutation.
    assert await _library_row(db_session, "publish-operator") is None


async def test_publish_non_admin_403(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=user, slug="publish-non-admin")
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(user))
    assert resp.status_code == 403


async def test_publish_404_non_owner(
    client: AsyncClient, admin: User, user: User, db_session: AsyncSession
) -> None:
    """An admin may publish ONLY a skill they themselves authored (D2 keystone) — another
    user's skill 404s (no existence leak)."""
    row = await _make_user_skill(db_session, owner=user, slug="publish-non-owner")
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(admin))
    assert resp.status_code == 404


async def test_publish_404_team_scope(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    from app.models.team import Team, TeamMember

    team = Team(slug="publish-team", name="Publish Team", created_by_user_id=admin.id)
    db_session.add(team)
    await db_session.flush()
    db_session.add(
        TeamMember(team_id=team.id, user_id=admin.id, role="admin", added_by_user_id=admin.id)
    )
    await db_session.flush()
    row = await _make_user_skill(
        db_session, owner_team_id=team.id, slug="publish-team-scope", scope="team"
    )
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(admin))
    assert resp.status_code == 404


async def test_publish_404_archived(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=admin, slug="publish-archived", archived=True)
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(admin))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Write-time gate battery — 409 conflicts, injection battery, fail-closed
# ---------------------------------------------------------------------------


async def test_publish_409_open_proposal_for_slug(
    client: AsyncClient, admin: User, user: User, db_session: AsyncSession
) -> None:
    """One-open-proposal-per-slug is slug-keyed across ALL authors: an in-flight proposal (even
    another user's) blocks the fast-path — the admin should review it, not race it."""
    other = await _make_user_skill(db_session, owner=user, slug="publish-open-proposal")
    await _propose(client, user, other.id)  # user's proposal is now open (state='proposed')

    mine = await _make_user_skill(db_session, owner=admin, slug="publish-open-proposal")
    resp = await client.post(f"/api/v1/user-skills/{mine.id}/publish", headers=_bearer(admin))
    assert resp.status_code == 409
    # No approved snapshot minted, no adopt.
    assert await _library_row(db_session, "publish-open-proposal") is None


async def test_publish_409_shipped_slug_collision(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    # 'alpha-test-skill' IS a name in the (autouse-installed) fixture registry → shipped wins.
    row = await _make_user_skill(db_session, owner=admin, slug="alpha-test-skill")
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(admin))
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "denied_key",
    [
        "allowed-tools",
        "minimum_inference_tier",
        "ensemble_verification",
        "self_improvement",
        "inputs",
    ],
)
async def test_publish_422_denied_frontmatter_key(
    client: AsyncClient, admin: User, db_session: AsyncSession, denied_key: str
) -> None:
    """The D3.3 CLOSED frontmatter allowlist is the sole write-time line of defense (no
    serve-time backstop) — every denied key 422s NAMING the offending dotted path. Author-supplied
    ``frontmatter_extra`` keys land under ``lq_ai``, so a denied key surfaces as ``lq_ai.<key>``."""
    row = await _make_user_skill(
        db_session,
        owner=admin,
        slug=f"publish-denied-{denied_key.replace('_', '-').replace('-', '')}",
        frontmatter_extra={denied_key: "malicious-value"},
    )
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(admin))
    assert resp.status_code == 422
    assert f"lq_ai.{denied_key}" in resp.json()["detail"]
    # Rejected before any mutation.
    assert await _library_row(db_session, row.slug) is None


async def test_publish_422_oversize(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(
        db_session, owner=admin, slug="publish-oversize", body="A" * 40_000
    )
    resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(admin))
    assert resp.status_code == 422
    assert "32768" in resp.json()["detail"] or "bytes" in resp.json()["detail"]


async def test_publish_fail_closed_when_registry_absent(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """Mirrors propose: if the skill registry is unavailable the no-shadowing collision check
    cannot run, so publish FAILS CLOSED (500) rather than silently proceeding."""
    row = await _make_user_skill(db_session, owner=admin, slug="publish-registry-absent")
    prior = getattr(app.state, "skill_registry", None)
    delattr(app.state, "skill_registry")
    try:
        resp = await client.post(f"/api/v1/user-skills/{row.id}/publish", headers=_bearer(admin))
    finally:
        if prior is not None:
            app.state.skill_registry = prior
    assert resp.status_code == 500
    # Fail-closed leaves no partial writes.
    assert await _library_row(db_session, "publish-registry-absent") is None


# ---------------------------------------------------------------------------
# Idempotency — unchanged no-op, edited supersede, already-in-library
# ---------------------------------------------------------------------------


async def test_republish_unchanged_is_200_noop(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=admin, slug="publish-noop")
    first = await _publish(client, admin, row.id)

    # Re-publish with NO edit → 200 no-op returning the SAME approved version.
    second = await _publish(client, admin, row.id, expect=200)
    assert second["id"] == first["id"]
    assert second["state"] == "approved"

    # No new snapshot minted.
    versions = (
        await db_session.execute(
            select(func.count())
            .select_from(OrgSkillVersion)
            .where(OrgSkillVersion.slug == "publish-noop")
        )
    ).scalar_one()
    assert versions == 1

    # No new audit rows from the no-op (still exactly one of each of the three actions).
    assert await _count_audits(db_session, action="library.propose", resource_id=first["id"]) == 1
    assert await _count_audits(db_session, action="library.approve", resource_id=first["id"]) == 1
    assert await _count_audits(db_session, action="library.adopt", resource_id="publish-noop") == 1


async def test_republish_after_edit_supersedes_without_new_adopt(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    row = await _make_user_skill(db_session, owner=admin, slug="publish-supersede")
    v1 = await _publish(client, admin, row.id)

    # Edit the source skill so the synthesized content_hash changes.
    row.body = "# Edited\n\nA materially different body for version two."
    await db_session.flush()

    v2 = await _publish(client, admin, row.id)
    assert v2["id"] != v1["id"]
    assert v2["version_no"] == 2
    assert v2["state"] == "approved"

    stale = await db_session.get(OrgSkillVersion, uuid.UUID(v1["id"]))
    assert stale is not None and stale.state == "superseded"

    # The second approve records the superseded version, with fast_path.
    approve_audit = await _latest_audit(db_session, action="library.approve", resource_id=v2["id"])
    assert approve_audit.details["superseded_version"] == 1
    assert approve_audit.details["fast_path"] is True

    # Already in the Library → NO second adopt row/audit (ON CONFLICT DO NOTHING).
    adopt_count = await _count_audits(
        db_session, action="library.adopt", resource_id="publish-supersede"
    )
    assert adopt_count == 1


async def test_publish_idempotent_adopt_when_slug_already_in_library(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """A slug already adopted into the Library (an 'adopted-but-no-approved-version' strand)
    publishes cleanly: the approved snapshot heals the strand and the adopt is a no-op (no new
    Library row, no adopt audit) — the ON CONFLICT DO NOTHING path."""
    other = await _make_user(db_session, suffix="publish-preadopter")
    db_session.add(
        OrgLibraryEntry(
            capability_kind="skill",
            capability_key="publish-preadopted",
            adopted_by=other.id,
        )
    )
    await db_session.flush()

    row = await _make_user_skill(db_session, owner=admin, slug="publish-preadopted")
    body = await _publish(client, admin, row.id)
    assert body["state"] == "approved"

    # No new/duplicate Library row; the pre-existing adopter is untouched.
    entry = await _library_row(db_session, "publish-preadopted")
    assert entry is not None
    assert entry.adopted_by == other.id

    # Only propose + approve audits; the adopt was a no-op so NO adopt audit exists.
    assert await _count_audits(db_session, action="library.propose", resource_id=body["id"]) == 1
    assert await _count_audits(db_session, action="library.approve", resource_id=body["id"]) == 1
    assert (
        await _count_audits(db_session, action="library.adopt", resource_id="publish-preadopted")
        == 0
    )
