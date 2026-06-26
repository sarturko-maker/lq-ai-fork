"""Editor Slice 5 review_edited_document tests (ADR-F047).

The agent side of the editor hand-back: an area-agnostic tool that re-reads a
document the supervising lawyer edited and surfaces THEIR tracked changes/comments
in a trusted-supervisor frame, with the agent's own still-pending redline filtered
out (the naive single-author test — superseded by the future team-identity slice).

Covered:
* the grant set (one tool; DISJOINT from every other matter + domain grant),
* the author filter (``_lawyer_edits``) — excludes the agent's author, replies, and
  resolved threads — and the trusted-supervisor renderer (``_render_supervised_edits``),
  both as pure functions over a synthetic StateOfPlay,
* end-to-end over a real two-author ``.docx``: the lawyer's edits + comment are
  surfaced, the agent's own pending change is NOT, the clean view is shown,
* a cross-matter document is 404-conflated (not found),
* an agent-only doc reports "nothing of the lawyer's to incorporate" but still shows
  the current version,
* a parse failure is rejected (not a crash),
* the domain audit receipt carries counts only — never clause/comment text.
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

from app.agents import tools as agent_tools
from app.agents.assessment_tools import ASSESSMENT_TOOL_NAMES
from app.agents.commercial_tools import COMMERCIAL_TOOL_NAMES
from app.agents.matter_consolidation import MATTER_CONSOLIDATION_TOOL_NAMES
from app.agents.matter_fact_tools import MATTER_FACT_TOOL_NAMES
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.matter_read_tools import MATTER_READ_TOOL_NAMES
from app.agents.negotiation_service import CounterpartyComment, StateOfPlay, TrackedChange
from app.agents.redline_service import DEFAULT_AUTHOR
from app.agents.review_edited_document_tools import (
    REVIEW_EDITED_DOCUMENT_TOOL_NAMES,
    _lawyer_edits,
    _render_supervised_edits,
    _review_edited_document,
    build_review_edited_document_tools,
)
from app.agents.ropa_tools import ROPA_TOOL_NAMES
from app.agents.tools import MatterBinding
from app.models.audit import AuditLog
from app.models.file import File
from app.models.project import Project
from app.models.user import User
from app.pipeline.readers._base import OOXML_DOCX_MIME
from app.security import hash_password

pytestmark = pytest.mark.integration

LAWYER_AUTHOR = "Jane Lawyer (Acme LLP)"
_BASE = (
    "The Vendor shall indemnify the Customer for all losses arising from the Services. "
    "The term of this Agreement is three (3) years from the Effective Date. "
    "Liability is capped at fees paid in the prior twelve (12) months."
)


# --------------------------------------------------------------------------- #
# Synthetic StateOfPlay builders (pure tests)
# --------------------------------------------------------------------------- #


def _change(
    author: str, *, ref: str = "C1", kind: str = "modify", deleted: str = "x", inserted: str = "y"
) -> TrackedChange:
    return TrackedChange(
        ref=ref,
        kind=kind,
        deleted_text=deleted,
        inserted_text=inserted,
        author=author,
        context="… in some clause …",
        adeu_ids=(),
    )


def _comment(
    author: str,
    *,
    ref: str = "Com:1",
    parent_id: str | None = None,
    resolved: bool = False,
    is_ours: bool = False,
    text: str = "please fix this",
) -> CounterpartyComment:
    return CounterpartyComment(
        ref=ref, author=author, text=text, resolved=resolved, parent_id=parent_id, is_ours=is_ours
    )


def _state(
    changes: list[TrackedChange], comments: list[CounterpartyComment], *, clean: str = "CLEAN-TEXT"
) -> StateOfPlay:
    return StateOfPlay(
        changes=changes,
        comments=comments,
        clean_view=clean,
        marked_view="MARKED",
        clean_text_full=clean,
    )


# --------------------------------------------------------------------------- #
# Grant set / confinement
# --------------------------------------------------------------------------- #


def test_build_grants_exactly_the_review_tool() -> None:
    tools = build_review_edited_document_tools(
        async_sessionmaker(), run_id=uuid.uuid4(), binding=_binding(uuid.uuid4(), uuid.uuid4())
    )
    assert [t.__name__ for t in tools] == ["review_edited_document"]
    assert sorted(REVIEW_EDITED_DOCUMENT_TOOL_NAMES) == ["review_edited_document"]


def test_grant_set_disjoint_from_other_grants() -> None:
    """Confinement: the re-read tool shares no tool name with any other grant."""
    assert REVIEW_EDITED_DOCUMENT_TOOL_NAMES.isdisjoint(MATTER_MEMORY_TOOL_NAMES)
    assert REVIEW_EDITED_DOCUMENT_TOOL_NAMES.isdisjoint(MATTER_FACT_TOOL_NAMES)
    assert REVIEW_EDITED_DOCUMENT_TOOL_NAMES.isdisjoint(MATTER_CONSOLIDATION_TOOL_NAMES)
    assert REVIEW_EDITED_DOCUMENT_TOOL_NAMES.isdisjoint(MATTER_READ_TOOL_NAMES)
    assert REVIEW_EDITED_DOCUMENT_TOOL_NAMES.isdisjoint(ROPA_TOOL_NAMES)
    assert REVIEW_EDITED_DOCUMENT_TOOL_NAMES.isdisjoint(ASSESSMENT_TOOL_NAMES)
    assert REVIEW_EDITED_DOCUMENT_TOOL_NAMES.isdisjoint(COMMERCIAL_TOOL_NAMES)


# --------------------------------------------------------------------------- #
# Author filter + trusted renderer (pure)
# --------------------------------------------------------------------------- #


def test_lawyer_edits_filters_the_agent_author() -> None:
    state = _state(
        changes=[_change(DEFAULT_AUTHOR, ref="C1"), _change(LAWYER_AUTHOR, ref="C2")],
        comments=[
            _comment(DEFAULT_AUTHOR, ref="Com:1", is_ours=True),  # our prior reply
            _comment(LAWYER_AUTHOR, ref="Com:2", is_ours=False),  # the lawyer's
        ],
    )
    changes, comments = _lawyer_edits(state)
    assert [c.ref for c in changes] == ["C2"]
    assert [c.ref for c in comments] == ["Com:2"]


def test_lawyer_edits_excludes_replies_and_resolved() -> None:
    state = _state(
        changes=[],
        comments=[
            _comment(LAWYER_AUTHOR, ref="Com:1", resolved=True),  # resolved → excluded
            _comment(LAWYER_AUTHOR, ref="Com:2", parent_id="Com:1"),  # a reply (not root)
            _comment(LAWYER_AUTHOR, ref="Com:3"),  # open root → included
        ],
    )
    _changes, comments = _lawyer_edits(state)
    assert [c.ref for c in comments] == ["Com:3"]


def test_render_trusted_frame_lists_only_the_lawyer() -> None:
    state = _state(
        changes=[
            _change(DEFAULT_AUTHOR, ref="C1", inserted="twenty-four (24)"),
            _change(LAWYER_AUTHOR, ref="C2", deleted="three (3)", inserted="two (2)"),
        ],
        comments=[_comment(LAWYER_AUTHOR, ref="Com:1", text="tighten the term")],
        clean="THE-LAWYERS-CLEAN-VERSION",
    )
    changes, comments = _lawyer_edits(state)
    out = _render_supervised_edits("contract.docx", state, changes, comments)
    assert "provenance=your supervising lawyer" in out
    assert "TRUSTED" in out
    assert "THE-LAWYERS-CLEAN-VERSION" in out  # the current version is shown
    assert LAWYER_AUTHOR in out and "two (2)" in out  # the lawyer's edit is listed
    assert "tighten the term" in out  # the lawyer's comment is listed
    assert DEFAULT_AUTHOR not in out  # the agent's own pending redline is filtered out


def test_render_no_lawyer_edits_is_graceful_but_shows_current() -> None:
    state = _state(
        changes=[_change(DEFAULT_AUTHOR, ref="C1")],  # only the agent's own change
        comments=[],
        clean="ONLY-CLEAN-VERSION",
    )
    changes, comments = _lawyer_edits(state)
    out = _render_supervised_edits("contract.docx", state, changes, comments)
    assert "no one but you has tracked edits or open comments" in out
    assert "ONLY-CLEAN-VERSION" in out
    assert DEFAULT_AUTHOR not in out


# --------------------------------------------------------------------------- #
# End-to-end over a real .docx (DB + storage)
# --------------------------------------------------------------------------- #


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _redline(data: bytes, author: str, edits: list[object]) -> bytes:
    from adeu import RedlineEngine

    eng = RedlineEngine(io.BytesIO(data), author=author)
    eng.apply_edits(edits)
    out = eng.save_to_stream()
    return out.getvalue() if hasattr(out, "getvalue") else bytes(out)


def _two_author_docx() -> bytes:
    """The agent's still-pending redline (DEFAULT_AUTHOR) + the lawyer's edits on top."""
    from adeu import ModifyText

    mid = _redline(
        _docx_bytes(_BASE),
        DEFAULT_AUTHOR,
        [ModifyText(target_text="twelve (12)", new_text="twenty-four (24)")],
    )
    return _redline(
        mid,
        LAWYER_AUTHOR,
        [
            ModifyText(
                target_text="three (3)",
                new_text="two (2)",
                comment="Tighten the term to two years.",
            )
        ],
    )


def _agent_only_docx() -> bytes:
    from adeu import ModifyText

    return _redline(
        _docx_bytes(_BASE),
        DEFAULT_AUTHOR,
        [ModifyText(target_text="twelve (12)", new_text="twenty-four (24)")],
    )


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="Edited Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


async def _make_matter_file(
    factory: async_sessionmaker[AsyncSession], *, filename: str = "contract.docx"
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        user = User(
            email=f"red-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Review User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Edited Matter",
            slug=f"edited-{uuid.uuid4().hex[:6]}",
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
        return user.id, project.id


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    user_id, project_id = await _make_matter_file(commit_factory)
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(File).where(File.owner_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


def _patch_download(monkeypatch: pytest.MonkeyPatch, *, source: bytes) -> None:
    """Patch the SHARED storage module's stream_download (download_matter_docx reads it)."""

    @asynccontextmanager
    async def fake_download(*, storage_path: str) -> AsyncIterator[AsyncIterator[bytes]]:
        async def _gen() -> AsyncIterator[bytes]:
            yield source

        yield _gen()

    monkeypatch.setattr(agent_tools.storage, "stream_download", fake_download)


async def test_review_surfaces_lawyer_edits_not_agent_changes(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    _patch_download(monkeypatch, source=_two_author_docx())
    async with commit_factory() as db:
        out = await _review_edited_document(
            db, _binding(user_id, project_id), document_name="contract.docx"
        )
        await db.commit()

    assert "provenance=your supervising lawyer" in out
    assert "TRUSTED" in out
    assert LAWYER_AUTHOR in out  # the lawyer's edit is attributed
    assert "two (2)" in out  # the lawyer's inserted text
    assert "Tighten the term" in out  # the lawyer's comment
    assert DEFAULT_AUTHOR not in out  # the agent's own pending redline is filtered out


async def test_review_audit_carries_counts_only(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    _patch_download(monkeypatch, source=_two_author_docx())
    async with commit_factory() as db:
        await _review_edited_document(
            db, _binding(user_id, project_id), document_name="contract.docx"
        )
        await db.commit()

    async with commit_factory() as db:
        rows = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "review.edited_document",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    details = str(rows[0].details)
    assert "lawyer_changes" in details and "changes" in details
    assert "Tighten the term" not in details  # no comment text
    assert "two (2)" not in details  # no clause text


async def test_review_cross_matter_is_not_found(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, _project_id = matter
    _patch_download(monkeypatch, source=_two_author_docx())
    # A binding to a matter this user's file is not in → 404-conflated absence.
    async with commit_factory() as db:
        out = await _review_edited_document(
            db, _binding(user_id, uuid.uuid4()), document_name="contract.docx"
        )
    assert "No document named" in out


async def test_review_agent_only_doc_reports_nothing_to_incorporate(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    _patch_download(monkeypatch, source=_agent_only_docx())
    async with commit_factory() as db:
        out = await _review_edited_document(
            db, _binding(user_id, project_id), document_name="contract.docx"
        )
    assert "no one but you has tracked edits or open comments" in out
    assert "twenty-four (24)" in out  # the current (accept-all) version is still shown
    assert DEFAULT_AUTHOR not in out


async def test_review_parse_failure_is_rejected_not_crash(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    _patch_download(monkeypatch, source=_two_author_docx())
    import app.agents.review_edited_document_tools as mod

    def _boom(*_a: object, **_k: object) -> StateOfPlay:
        raise ValueError("unparseable")

    monkeypatch.setattr(mod, "read_state_of_play", _boom)
    async with commit_factory() as db:
        out = await _review_edited_document(
            db, _binding(user_id, project_id), document_name="contract.docx"
        )
    assert "could not be read as a tracked-changes document" in out
