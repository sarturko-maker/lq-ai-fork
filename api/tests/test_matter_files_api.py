"""C7a matter-files read-surface tests (ADR-F046).

``GET /api/v1/matters/{project_id}/files`` is the listing the cockpit Documents tab
and the inline redline-download button read. These tests prove:

* the union scope — files attached via ``project_files`` AND files persisted with
  ``File.project_id`` (the redline-output path) both appear, newest-first;
* ``created_by_run_id`` provenance is surfaced (the run-timeline filter key);
* per-user isolation — a cross-user / archived matter is 404 (never 403);
* soft-deleted files and other matters' files are excluded;
* an empty-but-existing matter returns an empty list (not 404).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.agent_run import AgentRun, AgentThread
from app.models.file import File
from app.models.project import Project, ProjectFile
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
        email=f"mf-{tag}-{uuid.uuid4().hex[:8]}@example.com",
        display_name=f"Matter Files {tag}",
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
        name="Docs Matter",
        slug=f"docs-{uuid.uuid4().hex[:6]}",
        privileged=False,
        minimum_inference_tier=None,
    )
    db_session.add(project)
    await db_session.flush()
    if archived:
        project.archived_at = datetime.now(UTC)
        await db_session.flush()
    return project


async def _make_file(
    db_session: AsyncSession,
    owner: User,
    *,
    filename: str,
    project_id: uuid.UUID | None = None,
    created_by_run_id: uuid.UUID | None = None,
    deleted: bool = False,
    created_at: datetime | None = None,
    hash_sha256: str | None = None,
    summary: str | None = None,
) -> File:
    f = File(
        owner_id=owner.id,
        project_id=project_id,
        filename=filename,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=2048,
        # Unique per file by default — real uploads differ; a test that WANTS the
        # byte-identical case (ADR-F082 duplicate_of) passes an explicit shared hash.
        hash_sha256=hash_sha256 or (uuid.uuid4().hex + uuid.uuid4().hex),
        storage_path=str(uuid.uuid4()),
        ingestion_status="ready",
        created_by_run_id=created_by_run_id,
        summary=summary,
    )
    # ``now()`` is constant within a transaction, so set an explicit timestamp when a
    # test asserts the newest-first ordering (in production each file is created in its
    # own run/transaction, so ``created_at`` differs naturally).
    if created_at is not None:
        f.created_at = created_at
    if deleted:
        f.deleted_at = datetime.now(UTC)
    db_session.add(f)
    await db_session.flush()
    return f


async def _attach(db_session: AsyncSession, project_id: uuid.UUID, file_id: uuid.UUID) -> None:
    db_session.add(ProjectFile(project_id=project_id, file_id=file_id))
    await db_session.flush()


async def _make_run(db_session: AsyncSession, owner: User, project_id: uuid.UUID) -> uuid.UUID:
    thread = AgentThread(user_id=owner.id, project_id=project_id, title="redline")
    db_session.add(thread)
    await db_session.flush()
    run = AgentRun(user_id=owner.id, thread_id=thread.id, project_id=project_id, prompt="redline")
    db_session.add(run)
    await db_session.flush()
    return run.id


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "owner")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "other")


def _h(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, is_admin=False)}"}


def _url(project_id: uuid.UUID) -> str:
    return f"/api/v1/matters/{project_id}/files"


async def test_list_files_unauthenticated_401(client: AsyncClient) -> None:
    resp = await client.get(_url(uuid.uuid4()))
    assert resp.status_code == 401


async def test_list_files_unions_membership_and_project_id(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """An uploaded file (project_files membership) AND a redline output (File.project_id
    + created_by_run_id) both appear; newest-first; provenance surfaced."""
    project = await _make_project(db_session, db_user)
    uploaded = await _make_file(
        db_session,
        db_user,
        filename="contract.docx",
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )
    await _attach(db_session, project.id, uploaded.id)
    run_id = await _make_run(db_session, db_user, project.id)
    redlined = await _make_file(
        db_session,
        db_user,
        filename="contract (redlined).docx",
        project_id=project.id,
        created_by_run_id=run_id,
        created_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),  # newer than the upload
    )
    await db_session.commit()

    resp = await client.get(_url(project.id), headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == str(project.id)
    by_name = {f["filename"]: f for f in body["files"]}
    assert set(by_name) == {"contract.docx", "contract (redlined).docx"}
    # the redline output carries its run provenance; the upload does not.
    assert by_name["contract (redlined).docx"]["created_by_run_id"] == str(run_id)
    assert by_name["contract.docx"]["created_by_run_id"] is None
    # updated_at surfaces (ADR-F081 — the web keys its redline announce on it);
    # NULL until an in-place mutation lands.
    assert by_name["contract (redlined).docx"]["updated_at"] is None
    # newest-first: the redlined file was created after the upload.
    assert body["files"][0]["id"] == str(redlined.id)
    # metadata only — no bytes / storage_path / hash leak in the contract.
    # (`summary`/`summary_author`/`summary_stale` + `duplicate_of` are ADR-F082 workspace
    # awareness; `duplicate_of` is a computed {id, filename} ref, never the raw hash.)
    assert set(body["files"][0]) == {
        "id",
        "filename",
        "mime_type",
        "size_bytes",
        "ingestion_status",
        "created_at",
        "updated_at",
        "created_by_run_id",
        "summary",
        "summary_author",
        "summary_stale",
        "duplicate_of",
    }
    # Distinct bytes + never-read files: the awareness fields stay null/false.
    assert by_name["contract.docx"]["summary"] is None
    assert by_name["contract.docx"]["summary_author"] is None
    assert by_name["contract.docx"]["summary_stale"] is False
    assert by_name["contract.docx"]["duplicate_of"] is None


async def test_list_files_surfaces_summary_and_duplicate_of(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """ADR-F082 (WORKSPACE-3): a byte-identical later copy carries ``duplicate_of``
    pointing at the earliest file (never the raw hash); the agent-recorded summary
    passes through; canonical/unique files carry null."""
    project = await _make_project(db_session, db_user)
    shared = "e" * 64
    original = await _make_file(
        db_session,
        db_user,
        filename="msa.docx",
        hash_sha256=shared,
        summary="Two-year MSA with Cirrus; auto-renews.",
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )
    copy = await _make_file(
        db_session,
        db_user,
        filename="msa (2).docx",
        hash_sha256=shared,  # identical bytes → duplicate of the earlier upload
        created_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
    )
    await _attach(db_session, project.id, original.id)
    await _attach(db_session, project.id, copy.id)
    await db_session.commit()

    resp = await client.get(_url(project.id), headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    by_name = {f["filename"]: f for f in resp.json()["files"]}
    assert by_name["msa.docx"]["summary"] == "Two-year MSA with Cirrus; auto-renews."
    assert by_name["msa.docx"]["duplicate_of"] is None  # canonical (earliest) is never flagged
    assert by_name["msa (2).docx"]["duplicate_of"] == {
        "id": str(original.id),
        "filename": "msa.docx",
    }
    # The dup ref carries id + filename only — the content hash never leaves the API.
    assert "hash" not in str(by_name["msa (2).docx"]["duplicate_of"]).lower()


async def test_put_summary_human_write_clear_and_scoping(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """ADR-F082/F042 human-owns-after: the lawyer sets/clears a file's summary; the write is
    author-stamped 'human'; boundary rules match the agent's (422 on newline/reserved marker);
    a foreign/absent file is a 404 (no existence leak)."""
    project = await _make_project(db_session, db_user)
    f = await _make_file(db_session, db_user, filename="msa.docx")
    await _attach(db_session, project.id, f.id)
    await db_session.commit()
    url = f"{_url(project.id)}/{f.id}/summary"

    # Write: author-stamped human, stale False, run provenance NULL.
    resp = await client.put(url, headers=_h(db_user), json={"summary": "The lawyer's words."})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == "The lawyer's words."
    assert body["summary_author"] == "human"
    assert body["summary_stale"] is False

    # Boundary parity with the agent write: newline / reserved marker → 422.
    assert (
        await client.put(url, headers=_h(db_user), json={"summary": "two\nlines"})
    ).status_code == 422
    assert (
        await client.put(url, headers=_h(db_user), json={"summary": "x (duplicate of y.docx)"})
    ).status_code == 422

    # Clear: everything resets.
    resp = await client.put(url, headers=_h(db_user), json={"summary": None})
    assert resp.status_code == 200
    assert resp.json()["summary"] is None and resp.json()["summary_author"] is None

    # Absent file id under a real matter → 404, never 403.
    resp = await client.put(
        f"{_url(project.id)}/{uuid.uuid4()}/summary",
        headers=_h(db_user),
        json={"summary": "x"},
    )
    assert resp.status_code == 404


async def test_list_files_excludes_soft_deleted_and_other_matters(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    other = await _make_project(db_session, db_user)
    keep = await _make_file(db_session, db_user, filename="keep.docx", project_id=project.id)
    await _make_file(db_session, db_user, filename="gone.docx", project_id=project.id, deleted=True)
    await _make_file(db_session, db_user, filename="elsewhere.docx", project_id=other.id)
    await db_session.commit()

    resp = await client.get(_url(project.id), headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    names = {f["filename"] for f in resp.json()["files"]}
    assert names == {"keep.docx"}
    assert resp.json()["files"][0]["id"] == str(keep.id)


async def test_list_files_empty_matter_is_empty_list_not_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    await db_session.commit()
    resp = await client.get(_url(project.id), headers=_h(db_user))
    assert resp.status_code == 200
    assert resp.json()["files"] == []


async def test_list_files_cross_user_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User, other_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    await _make_file(db_session, db_user, filename="private.docx", project_id=project.id)
    await db_session.commit()
    # other_user does not own the matter → 404, never 403 (no existence leak).
    resp = await client.get(_url(project.id), headers=_h(other_user))
    assert resp.status_code == 404


async def test_list_files_archived_matter_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user, archived=True)
    await db_session.commit()
    resp = await client.get(_url(project.id), headers=_h(db_user))
    assert resp.status_code == 404
