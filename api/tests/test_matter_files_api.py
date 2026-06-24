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
) -> File:
    f = File(
        owner_id=owner.id,
        project_id=project_id,
        filename=filename,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=2048,
        hash_sha256="0" * 64,
        storage_path=str(uuid.uuid4()),
        ingestion_status="ready",
        created_by_run_id=created_by_run_id,
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
    # newest-first: the redlined file was created after the upload.
    assert body["files"][0]["id"] == str(redlined.id)
    # metadata only — no bytes / storage_path / hash leak in the contract.
    assert set(body["files"][0]) == {
        "id",
        "filename",
        "mime_type",
        "size_bytes",
        "ingestion_status",
        "created_at",
        "created_by_run_id",
    }


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
