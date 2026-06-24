"""C4 commercial_tools integration tests (ADR-F031/F035).

Drives ``_apply_redline`` through a real test DB with a real ``RedlineService``
(Adeu) and storage monkeypatched to a known ``.docx`` — covering the orchestration
(validate → fetch → gate → dry-run → apply → persist), the matter-scope boundary
(a document in another matter is not found — 404-conflated), and the audit receipt
(counts/types/IDs, never clause text).
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents import commercial_tools
from app.agents.commercial_tools import (
    COMMERCIAL_TOOL_NAMES,
    _apply_redline,
    _preview_redline,
    build_commercial_tools,
)
from app.agents.redline_render import reconstruct_redline_text
from app.agents.redline_service import (
    ProposedEdit,
    RedlineApplyResult,
    RedlinePreview,
    RedlineService,
)
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.file import File
from app.models.project import Project
from app.models.user import User
from app.pipeline.readers._base import OOXML_DOCX_MIME
from app.security import hash_password

pytestmark = pytest.mark.integration

CAP = (
    "The Vendor's aggregate liability arising out of or in connection with this "
    "Agreement shall not exceed the total fees paid by the Customer in the three (3) "
    "months preceding the claim."
)
_RATIONALE = (
    "Align the cap measurement period to the house twelve-month fee floor so the "
    "customer's standard liability position is preserved across this deal."
)


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _make_matter_file(
    factory: async_sessionmaker[AsyncSession], *, filename: str = "contract.docx"
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a user + matter + a .docx File (no Document — the tool falls back to
    DocxReader). Returns (user_id, project_id, file_id)."""
    async with factory() as db:
        user = User(
            email=f"comm-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Commercial User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="SecureScan Deal",
            slug=f"deal-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
        )
        db.add(project)
        await db.flush()
        file = File(
            owner_id=user.id,
            project_id=project.id,
            filename=filename,
            mime_type=OOXML_DOCX_MIME,
            size_bytes=1234,
            hash_sha256="0" * 64,
            storage_path=str(uuid.uuid4()),
            ingestion_status="ready",
        )
        db.add(file)
        await db.commit()
        return user.id, project.id, file.id


async def _make_run(
    factory: async_sessionmaker[AsyncSession], *, user_id: uuid.UUID, project_id: uuid.UUID
) -> uuid.UUID:
    """Seed a thread + run so a redlined File can carry a valid ``created_by_run_id``
    FK (ADR-F046). Returns the run id."""
    async with factory() as db:
        thread = AgentThread(user_id=user_id, project_id=project_id, title="redline")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user_id,
            thread_id=thread.id,
            project_id=project_id,
            prompt="redline the MSA",
        )
        db.add(run)
        await db.commit()
        return run.id


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="SecureScan Deal",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


def _patch_storage(monkeypatch: pytest.MonkeyPatch, *, source: bytes) -> dict[str, object]:
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_download(*, storage_path: str) -> AsyncIterator[AsyncIterator[bytes]]:
        async def _gen() -> AsyncIterator[bytes]:
            yield source

        yield _gen()

    async def fake_upload(*, storage_path: str, body: bytes, content_type: str) -> None:
        captured["path"] = storage_path
        captured["body"] = body
        captured["content_type"] = content_type

    monkeypatch.setattr(commercial_tools.storage, "stream_download", fake_download)
    monkeypatch.setattr(commercial_tools.storage, "upload_bytes", fake_upload)
    return captured


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """A committed user+matter+.docx File, torn down after the test.

    commit_factory bypasses the per-test rollback, so these rows MUST be cleaned
    up or they leak into the shared DB (File.owner_id is ON DELETE RESTRICT, so a
    leftover file breaks other tests' user deletes + row-count assertions).
    """
    user_id, project_id, _ = await _make_matter_file(commit_factory)
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(File).where(File.owner_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


def test_build_commercial_tools_grants_redline_tools() -> None:
    factory = async_sessionmaker()  # not used; the closure captures it
    tools = build_commercial_tools(
        factory,
        run_id=uuid.uuid4(),
        binding=_binding(uuid.uuid4(), uuid.uuid4()),
        redline_service=RedlineService(),
    )
    assert [t.__name__ for t in tools] == ["apply_redline", "preview_redline"]
    assert sorted(COMMERCIAL_TOOL_NAMES) == ["apply_redline", "preview_redline"]


async def test_apply_redline_rejects_noop_edit(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[{"target_text": "the claim", "new_text": "the claim"}],
            service=RedlineService(),
            run_id=uuid.uuid4(),  # rejected → no File row → FK never exercised
        )
    assert "rejected" in out.lower()
    assert "no change" in out.lower()


async def test_apply_redline_document_in_another_matter_not_found(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, _project_id = matter
    other_project = uuid.uuid4()  # a matter that doesn't own the file
    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, other_project),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
            run_id=uuid.uuid4(),  # not found → no File row → FK never exercised
        )
    assert "No document named" in out  # matter-scope: invisible across matters


async def test_preview_redline_renders_without_persisting(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """preview_redline returns the rendered tracked changes but writes nothing —
    no upload, no new File row (the self-review primitive, ADR-F041)."""
    user_id, project_id = matter
    captured = _patch_storage(monkeypatch, source=_docx_bytes(CAP))

    async with commit_factory() as db:
        out = await _preview_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
        )
        await db.commit()

    # the rendered tracked changes come back to the agent...
    assert "[+twelve" in out and "[-three" in out
    assert "NOTHING has been saved" in out
    # ...but nothing was uploaded and no redlined File was created.
    assert "body" not in captured
    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx"}


async def test_preview_redline_rejects_noop_edit(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _preview_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[{"target_text": "the claim", "new_text": "the claim"}],
            service=RedlineService(),
        )
    assert "rejected" in out.lower()
    assert "no change" in out.lower()


class _DryRunRaises(RedlineService):
    def dry_run(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlinePreview:
        raise RuntimeError("simulated editor failure")


class _ApplyRaises(RedlineService):
    def apply(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlineApplyResult:
        raise RuntimeError("simulated editor failure")


async def test_apply_redline_editor_exception_is_rejected_not_propagated(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """If the Adeu editor raises on a pathological edit (a real batch CAN — e.g. a
    zero-width insertion), the tool returns fix-and-retry guidance and persists
    nothing — never propagates the exception (untrusted input, ADR-F041)."""
    user_id, project_id = matter
    _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    valid = [{"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}]

    for svc in (_DryRunRaises(), _ApplyRaises()):
        async with commit_factory() as db:
            out = await _apply_redline(
                db,
                _binding(user_id, project_id),
                document_name="contract.docx",
                edits=valid,
                service=svc,
                run_id=uuid.uuid4(),  # editor failure → no File row → FK never exercised
            )
            await db.commit()
        assert "could not be placed by the editor" in out

    # neither attempt persisted a redlined file
    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx"}


async def test_apply_redline_happy_path_persists_redlined_file(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    captured = _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)

    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
            run_id=run_id,
        )
        await db.commit()

    assert "Applied" in out and "redlined" in out.lower()

    # the redlined .docx was uploaded + carries native tracked changes
    body = captured["body"]
    assert isinstance(body, bytes)
    redline = reconstruct_redline_text(body)
    assert "[+twelve" in redline and "[-three" in redline

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        names = {f.filename for f in files}
        assert "contract.docx" in names
        assert "contract (redlined).docx" in names
        redlined = next(f for f in files if f.filename == "contract (redlined).docx")
        assert redlined.project_id == project_id
        assert redlined.mime_type == OOXML_DOCX_MIME
        assert redlined.ingestion_status == "ready"
        # work-product provenance (ADR-F046): the output is tied to the run
        assert redlined.created_by_run_id == run_id

        # audit receipt: counts/types/IDs only, never clause text
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "commercial.redline_applied",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1
        details = str(audit[0].details)
        assert "twelve" not in details and "three" not in details
