"""C3a matter-memory pin endpoint tests (ADR-F042).

The ``POST /api/v1/matters/{project_id}/memory/corrections`` endpoint is the ONLY
writer of a ``trust='human-pinned'`` correction. These tests prove:

* the pin is written with ``author`` (``user_id``) from the SESSION — not from any
  request field (B2: the trust label is structurally true, not claimed),
* per-user isolation — a cross-user / archived matter is 404 (never 403),
* reject-at-the-boundary — blank/oversize bodies are 422 (never a DB 500),
* the audit row (``matter_memory.pin``) carries IDs/counts only — never the body.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.matter_memory import CORRECTION_MAX_CHARS
from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.project import MatterMemoryEntry, Project
from app.models.user import User
from app.security import create_access_token, hash_password

pytestmark = pytest.mark.integration


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


async def _make_user(db_session: AsyncSession, tag: str) -> User:
    user = User(
        email=f"mm-{tag}-{uuid.uuid4().hex[:8]}@example.com",
        display_name=f"Matter Memory {tag}",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_project(
    db_session: AsyncSession, owner: User, *, archived: bool = False
) -> Project:
    project = Project(
        owner_id=owner.id,
        name="Pin Matter",
        slug=f"pin-{uuid.uuid4().hex[:6]}",
        privileged=False,
        minimum_inference_tier=None,
    )
    db_session.add(project)
    await db_session.flush()
    if archived:
        from datetime import UTC, datetime

        project.archived_at = datetime.now(UTC)
        await db_session.flush()
    return project


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "owner")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "other")


def _h(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, is_admin=False)}"}


def _url(project_id: uuid.UUID) -> str:
    return f"/api/v1/matters/{project_id}/memory/corrections"


async def test_pin_unauthenticated_401(client: AsyncClient) -> None:
    # The router-level ActiveUser gate fires before the handler — no project needed.
    resp = await client.post(_url(uuid.uuid4()), json={"body_md": "x"})
    assert resp.status_code == 401


async def test_pin_creates_human_pinned_with_session_author(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(
        _url(project.id),
        json={"body_md": "  We are the BUYER; counterparty counsel is Smith Crowell.  "},
        headers=_h(db_user),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["trust"] == "human-pinned"
    assert body["project_id"] == str(project.id)
    # str_strip_whitespace trimmed the body before persist.
    assert body["body_md"] == "We are the BUYER; counterparty counsel is Smith Crowell."

    row = (
        await db_session.execute(
            select(MatterMemoryEntry).where(MatterMemoryEntry.project_id == project.id)
        )
    ).scalar_one()
    assert row.kind == "correction"
    assert row.trust == "human-pinned"
    # Author comes from the session, NOT from any request field (B2).
    assert row.user_id == db_user.id
    assert row.run_id is None


async def test_pin_cross_user_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User, other_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    # other_user does not own the matter → 404, never 403 (no existence leak).
    resp = await client.post(_url(project.id), json={"body_md": "sneaky"}, headers=_h(other_user))
    assert resp.status_code == 404
    # Nothing written.
    rows = (
        (
            await db_session.execute(
                select(MatterMemoryEntry).where(MatterMemoryEntry.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


async def test_pin_archived_matter_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user, archived=True)
    resp = await client.post(
        _url(project.id), json={"body_md": "for an archived matter"}, headers=_h(db_user)
    )
    assert resp.status_code == 404


async def test_pin_blank_body_is_422(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(_url(project.id), json={"body_md": "   "}, headers=_h(db_user))
    assert resp.status_code == 422


async def test_pin_oversize_body_is_422(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(
        _url(project.id),
        json={"body_md": "x" * (CORRECTION_MAX_CHARS + 1)},
        headers=_h(db_user),
    )
    assert resp.status_code == 422


async def test_pin_audit_carries_no_body(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    marker = "QUOKKA-secret-clause-text"
    resp = await client.post(
        _url(project.id), json={"body_md": f"Pinned fact: {marker}"}, headers=_h(db_user)
    )
    assert resp.status_code == 201, resp.text

    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "matter_memory.pin", AuditLog.user_id == db_user.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    details = str(audit[0].details)
    assert "entry_id" in details and "body_chars" in details
    assert marker not in details  # the correction body never reaches the audit row


# --------------------------------------------------------------------------- #
# C3c-1 (ADR-F044): the read surface (GET) + the human-authenticated wiki revert
# --------------------------------------------------------------------------- #


def _memory_url(project_id: uuid.UUID) -> str:
    return f"/api/v1/matters/{project_id}/memory"


def _revert_url(project_id: uuid.UUID) -> str:
    return f"/api/v1/matters/{project_id}/memory/wiki/revert"


async def _add_entry(
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    kind: str,
    body_md: str,
    trust: str = "normal",
    **kw: object,
) -> MatterMemoryEntry:
    entry = MatterMemoryEntry(
        project_id=project_id, user_id=user_id, kind=kind, body_md=body_md, trust=trust, **kw
    )
    db.add(entry)
    await db.flush()
    return entry


async def test_get_memory_unauthenticated_401(client: AsyncClient) -> None:
    resp = await client.get(_memory_url(uuid.uuid4()))
    assert resp.status_code == 401


async def test_get_memory_returns_composite(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    project.context_md = "Deal one-pager."
    await _add_entry(
        db_session,
        project.id,
        db_user.id,
        kind="fact",
        body_md="We act for the buyer.",
        author="agent",
        fact_type="party",
    )
    await _add_entry(
        db_session,
        project.id,
        db_user.id,
        kind="correction",
        body_md="Counsel is Smith Crowell.",
        trust="human-pinned",
    )
    await _add_entry(
        db_session, project.id, db_user.id, kind="wiki_snapshot", body_md="older one-pager"
    )
    await db_session.flush()

    resp = await client.get(_memory_url(project.id), headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == str(project.id)
    assert body["wiki"]["content_md"] == "Deal one-pager."
    assert body["wiki"]["version_count"] == 1  # one revertable wiki_snapshot
    assert [f["body_md"] for f in body["facts"]] == ["We act for the buyer."]
    assert [c["body_md"] for c in body["corrections"]] == ["Counsel is Smith Crowell."]
    assert sorted(e["kind"] for e in body["log"]) == ["correction", "fact", "wiki_snapshot"]
    assert body["log_total"] == 3


async def test_get_memory_excludes_superseded_facts(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """The live facts projection excludes a superseded fact (invalid_at set); it still
    appears in the append-only log (marked superseded)."""
    from datetime import UTC, datetime

    project = await _make_project(db_session, db_user)
    await _add_entry(
        db_session,
        project.id,
        db_user.id,
        kind="fact",
        body_md="cap 1 month (draft)",
        author="agent",
        fact_type="term",
        valid_at=datetime(2026, 1, 1, tzinfo=UTC),
        invalid_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    await _add_entry(
        db_session,
        project.id,
        db_user.id,
        kind="fact",
        body_md="cap 12 months",
        author="agent",
        fact_type="term",
        valid_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    await db_session.flush()

    resp = await client.get(_memory_url(project.id), headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [f["body_md"] for f in body["facts"]] == ["cap 12 months"]  # live only
    assert body["log_total"] == 2  # both kept in the log
    superseded = {e["body_preview"]: e["superseded"] for e in body["log"]}
    assert superseded["cap 1 month (draft)"] is True
    assert superseded["cap 12 months"] is False


async def test_get_memory_empty_matter_returns_empty_lists(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    await db_session.flush()
    resp = await client.get(_memory_url(project.id), headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["facts"] == [] and body["corrections"] == [] and body["log"] == []
    assert body["wiki"]["content_md"] == "" and body["wiki"]["version_count"] == 0
    assert body["log_total"] == 0


async def test_get_memory_cross_user_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User, other_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    await db_session.flush()
    resp = await client.get(_memory_url(project.id), headers=_h(other_user))
    assert resp.status_code == 404


async def test_get_memory_archived_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user, archived=True)
    await db_session.flush()
    resp = await client.get(_memory_url(project.id), headers=_h(db_user))
    assert resp.status_code == 404


async def test_revert_unauthenticated_401(client: AsyncClient) -> None:
    resp = await client.post(_revert_url(uuid.uuid4()), json={"snapshot_id": str(uuid.uuid4())})
    assert resp.status_code == 401


async def test_revert_restores_chosen_version_and_is_reversible(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    project.context_md = "current wiki v2"
    v1 = await _add_entry(
        db_session, project.id, db_user.id, kind="wiki_snapshot", body_md="wiki v1"
    )
    await db_session.flush()
    v1_id = v1.id

    resp = await client.post(
        _revert_url(project.id), json={"snapshot_id": str(v1_id)}, headers=_h(db_user)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reverted_to_snapshot_id"] == str(v1_id)
    assert body["snapshotted_prior"] is True
    assert body["wiki"]["content_md"] == "wiki v1"

    # The pre-revert state was snapshotted FIRST → the revert is itself reversible.
    snaps = (
        (
            await db_session.execute(
                select(MatterMemoryEntry).where(
                    MatterMemoryEntry.project_id == project.id,
                    MatterMemoryEntry.kind == "wiki_snapshot",
                )
            )
        )
        .scalars()
        .all()
    )
    assert sorted(s.body_md for s in snaps) == ["current wiki v2", "wiki v1"]
    refreshed = await db_session.get(Project, project.id)
    assert refreshed is not None and refreshed.context_md == "wiki v1"

    # Reverting to the freshly-snapshotted v2 restores it (reversibility proven).
    new_snap = next(s for s in snaps if s.body_md == "current wiki v2")
    resp2 = await client.post(
        _revert_url(project.id), json={"snapshot_id": str(new_snap.id)}, headers=_h(db_user)
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["wiki"]["content_md"] == "current wiki v2"


async def test_revert_unknown_snapshot_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    await db_session.flush()
    resp = await client.post(
        _revert_url(project.id), json={"snapshot_id": str(uuid.uuid4())}, headers=_h(db_user)
    )
    assert resp.status_code == 404


async def test_revert_non_snapshot_id_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """A fact / correction id is not a wiki_snapshot → 404 (kind scope), wiki untouched."""
    project = await _make_project(db_session, db_user)
    project.context_md = "untouched"
    fact = await _add_entry(
        db_session,
        project.id,
        db_user.id,
        kind="fact",
        body_md="a fact",
        author="agent",
        fact_type="fact",
    )
    await db_session.flush()
    resp = await client.post(
        _revert_url(project.id), json={"snapshot_id": str(fact.id)}, headers=_h(db_user)
    )
    assert resp.status_code == 404
    refreshed = await db_session.get(Project, project.id)
    assert refreshed is not None and refreshed.context_md == "untouched"


async def test_revert_cross_user_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User, other_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    v1 = await _add_entry(
        db_session, project.id, db_user.id, kind="wiki_snapshot", body_md="wiki v1"
    )
    await db_session.flush()
    resp = await client.post(
        _revert_url(project.id), json={"snapshot_id": str(v1.id)}, headers=_h(other_user)
    )
    assert resp.status_code == 404


async def test_revert_snapshot_of_other_matter_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """Same-user confused-deputy: a snapshot of matter A cannot be reverted into matter B
    (the triple-scoped lookup's project_id predicate) → 404, B untouched."""
    matter_a = await _make_project(db_session, db_user)
    matter_b = await _make_project(db_session, db_user)
    matter_b.context_md = "B untouched"
    snap_a = await _add_entry(
        db_session, matter_a.id, db_user.id, kind="wiki_snapshot", body_md="A's prior wiki"
    )
    await db_session.flush()
    resp = await client.post(
        _revert_url(matter_b.id), json={"snapshot_id": str(snap_a.id)}, headers=_h(db_user)
    )
    assert resp.status_code == 404
    refreshed = await db_session.get(Project, matter_b.id)
    assert refreshed is not None and refreshed.context_md == "B untouched"


async def test_revert_blank_current_wiki_writes_no_prior_snapshot(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """Reverting when the current wiki is blank: snapshotted_prior is False and no new
    wiki_snapshot row is written (only the original target remains) — the documented
    benign edge (ADR-F044)."""
    project = await _make_project(db_session, db_user)  # context_md is None (blank)
    v1 = await _add_entry(
        db_session, project.id, db_user.id, kind="wiki_snapshot", body_md="restore me"
    )
    await db_session.flush()
    resp = await client.post(
        _revert_url(project.id), json={"snapshot_id": str(v1.id)}, headers=_h(db_user)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["snapshotted_prior"] is False
    assert body["wiki"]["content_md"] == "restore me"
    # No new snapshot of the blank prior — only the original target remains.
    snaps = (
        (
            await db_session.execute(
                select(MatterMemoryEntry).where(
                    MatterMemoryEntry.project_id == project.id,
                    MatterMemoryEntry.kind == "wiki_snapshot",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(snaps) == 1 and snaps[0].id == v1.id


async def test_revert_audit_carries_no_body(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    project.context_md = "current"
    marker = "WALRUS-secret-wiki-text"
    v1 = await _add_entry(
        db_session, project.id, db_user.id, kind="wiki_snapshot", body_md=f"prior {marker}"
    )
    await db_session.flush()
    resp = await client.post(
        _revert_url(project.id), json={"snapshot_id": str(v1.id)}, headers=_h(db_user)
    )
    assert resp.status_code == 200, resp.text

    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "matter_memory.wiki_revert",
                    AuditLog.user_id == db_user.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    details = str(audit[0].details)
    assert "reverted_to_snapshot_id" in details and "new_chars" in details
    assert marker not in details  # the wiki body never reaches the audit row
