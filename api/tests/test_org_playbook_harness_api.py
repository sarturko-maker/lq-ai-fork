"""Integration tests for the org-playbooks harness endpoints (B-4, ADR-F067 D2/D3).

The playbook twin of ``tests/test_org_skill_harness_api.py``: propose (author) ->
approve/reject/revoke (admin) -> catalog gating + provenance -> member Library provenance. The
pure freeze/canonicalize core is covered in ``tests/test_org_playbook_proposal.py``; the
composition seam (snapshot-not-live, revoke fail-close, full parity) in
``tests/agents/test_org_playbook_composition.py``.

Fixtures/style mirror the org-skill harness test (client/user/admin/operator + the
``tests.agents.test_agent_runs_api`` helpers). Playbooks need NO skill-registry fixture — there
is no filesystem registry for them (the built-in-vs-org split is ``created_by``).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.org_playbook_version import OrgPlaybookVersion
from app.models.playbook import Playbook, PlaybookPosition
from app.models.user import User
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def author(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="org-pb-author")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="org-pb-other")


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="org-pb-admin")
    u.is_admin = True
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def operator(db_session: AsyncSession) -> User:
    """The platform operator — passes AdminUser but role='operator', so ADR-F064 excludes it
    from tenant-authored content like the org-playbooks queue."""
    u = await _make_user(db_session, suffix="org-pb-operator")
    u.is_admin = True
    u.role = "operator"
    await db_session.flush()
    return u


async def _make_playbook(
    db: AsyncSession,
    *,
    created_by: object,
    name: str = "House NDA",
    standard: str = "Each party keeps the other's info secret.",
    n_positions: int = 1,
) -> Playbook:
    pb = Playbook(
        name=name,
        contract_type="NDA",
        description="Preferred NDA positions.",
        version="1.0.0",
        created_by=created_by,
    )
    for i in range(n_positions):
        pb.positions.append(
            PlaybookPosition(
                issue=f"Issue {i}",
                standard_language=standard,
                severity_if_missing="high",
                fallback_tiers=[],
                position_order=i,
            )
        )
    db.add(pb)
    await db.flush()
    return pb


async def _propose(client: AsyncClient, actor: User, playbook_id: object) -> dict:
    resp = await client.post(f"/api/v1/playbooks/{playbook_id}/propose", headers=_bearer(actor))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _approve(client: AsyncClient, admin: User, version_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/admin/org-playbooks/{version_id}/approve", headers=_bearer(admin)
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
    assert row is not None, f"no audit row for {action!r} resource_id={resource_id!r}"
    return row


# ---------------------------------------------------------------------------
# Propose — author side
# ---------------------------------------------------------------------------


async def test_propose_happy_path(
    client: AsyncClient, author: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    body = await _propose(client, author, pb.id)
    assert body["playbook_id"] == str(pb.id)
    assert body["state"] == "proposed"
    assert body["version_no"] == 1
    assert body["position_count"] == 1
    assert len(body["content_hash"]) == 64
    assert body["size_bytes"] > 0


async def test_propose_audit_row_is_content_free(
    client: AsyncClient, author: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(
        db_session, created_by=author.id, standard="A distinctive clause that must never leak."
    )
    body = await _propose(client, author, pb.id)
    audit = await _latest_audit(db_session, action="library.propose", resource_id=body["id"])
    details = audit.details or {}
    assert set(details.keys()) == {
        "kind",
        "key",
        "version",
        "content_hash",
        "size_bytes",
        "position_count",
    }
    assert details["kind"] == "playbook" and details["key"] == str(pb.id)
    assert "distinctive clause" not in json.dumps(details)


async def test_propose_non_owned_404(
    client: AsyncClient, author: User, other_user: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=other_user.id)
    resp = await client.post(f"/api/v1/playbooks/{pb.id}/propose", headers=_bearer(author))
    assert resp.status_code == 404


async def test_propose_builtin_404(
    client: AsyncClient, author: User, db_session: AsyncSession
) -> None:
    """A built-in (created_by IS NULL) is not proposable — 404 (no existence leak)."""
    pb = await _make_playbook(db_session, created_by=None)
    resp = await client.post(f"/api/v1/playbooks/{pb.id}/propose", headers=_bearer(author))
    assert resp.status_code == 404


async def test_propose_size_cap_422(
    client: AsyncClient, author: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id, standard="x" * 40_000)
    resp = await client.post(f"/api/v1/playbooks/{pb.id}/propose", headers=_bearer(author))
    assert resp.status_code == 422


async def test_propose_one_open_proposal_409(
    client: AsyncClient, author: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    await _propose(client, author, pb.id)
    resp = await client.post(f"/api/v1/playbooks/{pb.id}/propose", headers=_bearer(author))
    assert resp.status_code == 409
    assert "open proposal already exists" in resp.text


async def test_proposals_list_author_only(
    client: AsyncClient, author: User, other_user: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    await _propose(client, author, pb.id)
    ok = await client.get(f"/api/v1/playbooks/{pb.id}/proposals", headers=_bearer(author))
    assert ok.status_code == 200 and len(ok.json()) == 1
    denied = await client.get(f"/api/v1/playbooks/{pb.id}/proposals", headers=_bearer(other_user))
    assert denied.status_code == 404


async def test_version_no_increments_after_reject_and_repropose(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    first = await _propose(client, author, pb.id)
    assert first["version_no"] == 1
    resp = await client.post(
        f"/api/v1/admin/org-playbooks/{first['id']}/reject",
        headers=_bearer(admin),
        json={"note": "not ready"},
    )
    assert resp.status_code == 200
    second = await _propose(client, author, pb.id)
    assert second["version_no"] == 2


# ---------------------------------------------------------------------------
# Admin review — approve / reject / revoke
# ---------------------------------------------------------------------------


async def test_approve_pins_snapshot_and_carries_positions(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id, n_positions=2)
    proposed = await _propose(client, author, pb.id)
    approved = await _approve(client, admin, proposed["id"])
    assert approved["state"] == "approved"
    assert approved["approver_email"] == admin.email
    assert approved["author_email"] == author.email
    assert approved["position_count"] == 2
    assert len(approved["positions"]) == 2  # the review surface carries the frozen positions


async def test_reapprove_supersedes_prior(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    v1 = await _propose(client, author, pb.id)
    await _approve(client, admin, v1["id"])
    # a second proposal + approval supersedes v1 (one approved per playbook_id holds).
    v2 = await _propose(client, author, pb.id)
    await _approve(client, admin, v2["id"])
    states = {
        v.version_no: v.state
        for v in (
            await db_session.execute(
                select(OrgPlaybookVersion).where(OrgPlaybookVersion.playbook_id == pb.id)
            )
        )
        .scalars()
        .all()
    }
    assert states == {1: "superseded", 2: "approved"}


async def test_reject_sets_note_and_audit_has_note_only(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    proposed = await _propose(client, author, pb.id)
    resp = await client.post(
        f"/api/v1/admin/org-playbooks/{proposed['id']}/reject",
        headers=_bearer(admin),
        json={"note": "secret reviewer reasoning that must not be audited"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "rejected"
    audit = await _latest_audit(db_session, action="library.reject", resource_id=proposed["id"])
    assert audit.details["has_note"] is True
    assert "secret reviewer reasoning" not in json.dumps(audit.details)


async def test_revoke_leaves_library_and_binding_rows(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    proposed = await _propose(client, author, pb.id)
    await _approve(client, admin, proposed["id"])
    # adopt it, then revoke — the Library row must survive (D3.8 fail-close at build, not delete).
    adopt = await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "playbook", "key": str(pb.id)},
    )
    assert adopt.status_code == 204
    resp = await client.post(
        f"/api/v1/admin/org-playbooks/{proposed['id']}/revoke", headers=_bearer(admin)
    )
    assert resp.status_code == 200 and resp.json()["state"] == "revoked"
    lib = await client.get("/api/v1/library", headers=_bearer(admin))
    assert any(e["key"] == str(pb.id) for e in lib.json()["entries"])  # dangling, not vanished


# ---------------------------------------------------------------------------
# Operator exclusion (ADR-F064)
# ---------------------------------------------------------------------------


async def test_operator_excluded_from_list(client: AsyncClient, operator: User) -> None:
    resp = await client.get("/api/v1/admin/org-playbooks", headers=_bearer(operator))
    assert resp.status_code == 403


async def test_operator_excluded_from_approve(
    client: AsyncClient, author: User, operator: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    proposed = await _propose(client, author, pb.id)
    resp = await client.post(
        f"/api/v1/admin/org-playbooks/{proposed['id']}/approve", headers=_bearer(operator)
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Catalog gating + provenance (full parity)
# ---------------------------------------------------------------------------


def _playbook_entry(catalog: dict, key: str) -> dict | None:
    section = next(s for s in catalog["sections"] if s["kind"] == "playbook")
    return {e["capability_key"]: e for e in section["entries"]}.get(key)


async def test_adopt_org_playbook_422_before_approval_204_after(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    """Full parity: an un-approved org playbook is NOT adoptable (422); adoptable after approve."""
    pb = await _make_playbook(db_session, created_by=author.id)
    before = await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "playbook", "key": str(pb.id)},
    )
    assert before.status_code == 422
    proposed = await _propose(client, author, pb.id)
    await _approve(client, admin, proposed["id"])
    after = await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "playbook", "key": str(pb.id)},
    )
    assert after.status_code == 204


async def test_catalog_shows_org_playbook_with_provenance(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id)
    proposed = await _propose(client, author, pb.id)
    await _approve(client, admin, proposed["id"])
    cat = await client.get("/api/v1/admin/capabilities", headers=_bearer(admin))
    assert cat.status_code == 200
    entry = _playbook_entry(cat.json(), str(pb.id))
    assert entry is not None
    assert entry["source"] == "org"
    assert entry["author"] == author.email
    assert entry["approver"] == admin.email
    assert entry["version"] == "1.0.0"


async def test_catalog_hides_unapproved_org_playbook(
    client: AsyncClient, author: User, admin: User, db_session: AsyncSession
) -> None:
    """A created_by-set playbook that was never proposed does NOT appear in the catalog (it is
    neither a shipped built-in nor an approved org playbook)."""
    pb = await _make_playbook(db_session, created_by=author.id, name="Never Proposed")
    cat = await client.get("/api/v1/admin/capabilities", headers=_bearer(admin))
    assert _playbook_entry(cat.json(), str(pb.id)) is None


async def test_builtin_playbook_shows_in_catalog_without_source(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=None, name="Shipped Built-in")
    cat = await client.get("/api/v1/admin/capabilities", headers=_bearer(admin))
    entry = _playbook_entry(cat.json(), str(pb.id))
    assert entry is not None and entry["source"] is None


async def test_member_library_shows_org_playbook_provenance(
    client: AsyncClient, author: User, other_user: User, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session, created_by=author.id, name="Member Read NDA")
    proposed = await _propose(client, author, pb.id)
    await _approve(client, admin, proposed["id"])
    await client.post(
        "/api/v1/admin/library",
        headers=_bearer(admin),
        json={"kind": "playbook", "key": str(pb.id)},
    )
    lib = await client.get("/api/v1/library", headers=_bearer(other_user))
    assert lib.status_code == 200
    entry = next(e for e in lib.json()["entries"] if e["key"] == str(pb.id))
    assert entry["source"] == "org"
    assert entry["author"] is None  # member surface exposes no author identity
    assert entry["approver"] == admin.email
