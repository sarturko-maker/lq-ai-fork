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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents import commercial_tools
from app.agents.commercial_tools import (
    COMMERCIAL_TOOL_NAMES,
    _apply_redline,
    build_commercial_tools,
)
from app.agents.redline_render import reconstruct_redline_text
from app.agents.redline_service import RedlineService
from app.agents.tools import MatterBinding
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


def test_build_commercial_tools_grants_only_apply_redline() -> None:
    factory = async_sessionmaker()  # not used; the closure captures it
    tools = build_commercial_tools(
        factory,
        run_id=uuid.uuid4(),
        binding=_binding(uuid.uuid4(), uuid.uuid4()),
        redline_service=RedlineService(),
    )
    assert [t.__name__ for t in tools] == ["apply_redline"]
    assert sorted(COMMERCIAL_TOOL_NAMES) == ["apply_redline"]


async def test_apply_redline_rejects_noop_edit(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, project_id, _ = await _make_matter_file(commit_factory)
    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[{"target_text": "the claim", "new_text": "the claim"}],
            service=RedlineService(),
        )
    assert "rejected" in out.lower()
    assert "no change" in out.lower()


async def test_apply_redline_document_in_another_matter_not_found(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, _project_id, _ = await _make_matter_file(commit_factory)
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
        )
    assert "No document named" in out  # matter-scope: invisible across matters


async def test_apply_redline_happy_path_persists_redlined_file(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, project_id, _ = await _make_matter_file(commit_factory)
    captured = _patch_storage(monkeypatch, source=_docx_bytes(CAP))

    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
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

        # audit receipt: counts/types/IDs only, never clause text
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(AuditLog.action == "commercial.redline_applied")
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1
        details = str(audit[0].details)
        assert "twelve" not in details and "three" not in details
