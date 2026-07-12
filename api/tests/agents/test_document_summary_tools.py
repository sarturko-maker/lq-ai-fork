"""WORKSPACE-1 document-summary + duplicate-awareness tests (ADR-F082).

Drives, through the real test DB:

* the grant set (one tool; DISJOINT from every other matter + domain grant — confinement),
* the auto-write path (validate → resolve the named file under matter+owner scope → write the
  summary in place with run id + timestamp),
* reject-not-truncate (over-cap / blank rejected, the file's summary UNCHANGED),
* unknown / foreign / soft-deleted file → fix-and-retry, nothing written,
* ``duplicate_of_map`` — exact-byte dedup computed from ``hash_sha256`` (never agent-asserted):
  canonical = earliest, soft-deleted excluded, and NO cross-matter / cross-owner leak,
* the enriched ``_inventory`` renders the summary and the ``(duplicate of X)`` marker.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.assessment_tools import ASSESSMENT_TOOL_NAMES
from app.agents.commercial_tools import COMMERCIAL_TOOL_NAMES
from app.agents.composition import render_memory_tiers
from app.agents.document_summary_tools import (
    DOCUMENT_SUMMARY_TOOL_NAMES,
    MATTER_DOCUMENTS_INJECT_LIMIT,
    _record_document_summary,
    build_document_summary_tools,
    load_matter_documents_block,
)
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.ropa_tools import ROPA_TOOL_NAMES
from app.agents.tools import (
    MatterBinding,
    _inventory,
    duplicate_of_map,
    resolve_matter_file_by_name,
)
from app.models.agent_run import AgentRun, AgentThread
from app.models.document import Document
from app.models.file import File
from app.models.project import Project
from app.models.user import User
from app.schemas.document_summary import DOCUMENT_SUMMARY_MAX_CHARS
from app.security import hash_password

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_user_and_matter(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        user = User(
            email=f"ds-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Doc Summary User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Summary Matter",
            slug=f"ds-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
        )
        db.add(project)
        await db.commit()
        return user.id, project.id


async def _seed_file(
    factory: async_sessionmaker[AsyncSession],
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID | None,
    filename: str,
    hash_sha256: str,
    ingested: bool = False,
    summary: str | None = None,
    summary_author: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    is_snapshot: bool = False,
    parent_file_id: uuid.UUID | None = None,
    deleted: bool = False,
) -> uuid.UUID:
    async with factory() as db:
        file = File(
            owner_id=owner_id,
            project_id=project_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=123,
            hash_sha256=hash_sha256,
            storage_path=uuid.uuid4().hex,
            ingestion_status="ready" if ingested else "pending",
            summary=summary,
            summary_author=(summary_author or ("agent" if summary else None)),
            summary_updated_at=datetime.now(tz=UTC) if summary else None,
            created_at=created_at or datetime.now(tz=UTC),
            updated_at=updated_at,
            is_snapshot=is_snapshot,
            parent_file_id=parent_file_id,
            deleted_at=datetime.now(tz=UTC) if deleted else None,
        )
        db.add(file)
        await db.flush()
        if ingested:
            db.add(
                Document(
                    file_id=file.id,
                    parser="test",
                    page_count=2,
                    character_count=1_000,
                )
            )
        await db.commit()
        return file.id


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="Summary Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


async def _seed_run(
    factory: async_sessionmaker[AsyncSession], *, user_id: uuid.UUID, project_id: uuid.UUID
) -> uuid.UUID:
    """A real agent run — ``files.summary_run_id`` FK-references ``agent_runs`` (provenance)."""
    async with factory() as db:
        thread = AgentThread(user_id=user_id, project_id=project_id, title="doc summary run")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user_id,
            thread_id=thread.id,
            project_id=project_id,
            status="running",
            prompt="summarise",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()
        return run.id


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    user_id, project_id = await _seed_user_and_matter(commit_factory)
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            # documents CASCADE on the file delete; delete files before the user (RESTRICT FK).
            await db.execute(delete(File).where(File.owner_id == user_id))
            await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
            await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


# --------------------------------------------------------------------------- #
# Grant set / confinement
# --------------------------------------------------------------------------- #


def test_build_grants_exactly_one_tool() -> None:
    tools = build_document_summary_tools(
        async_sessionmaker(), run_id=uuid.uuid4(), binding=_binding(uuid.uuid4(), uuid.uuid4())
    )
    assert [t.__name__ for t in tools] == ["record_document_summary"]
    assert sorted(DOCUMENT_SUMMARY_TOOL_NAMES) == ["record_document_summary"]


def test_grant_set_disjoint_from_other_grants() -> None:
    assert DOCUMENT_SUMMARY_TOOL_NAMES.isdisjoint(MATTER_MEMORY_TOOL_NAMES)
    assert DOCUMENT_SUMMARY_TOOL_NAMES.isdisjoint(ROPA_TOOL_NAMES)
    assert DOCUMENT_SUMMARY_TOOL_NAMES.isdisjoint(ASSESSMENT_TOOL_NAMES)
    assert DOCUMENT_SUMMARY_TOOL_NAMES.isdisjoint(COMMERCIAL_TOOL_NAMES)


# --------------------------------------------------------------------------- #
# Auto-write the summary
# --------------------------------------------------------------------------- #


async def test_records_summary_against_the_named_file(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    file_id = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Cirrus MSA.pdf",
        hash_sha256="a" * 64,
        ingested=True,
    )
    run_id = await _seed_run(commit_factory, user_id=user_id, project_id=project_id)
    async with commit_factory() as db:
        out = await _record_document_summary(
            db,
            _binding(user_id, project_id),
            run_id=run_id,
            # Case-insensitive resolution — the SAME rule read_document uses (review fix,
            # PR #271): the agent that just read "Cirrus MSA.pdf" as "cirrus msa.pdf" must
            # not get a spurious not-found from the summary write.
            document_name="cirrus msa.pdf",
            summary="Master services agreement between us (buyer) and Cirrus; 12-month liability cap.",
        )
        await db.commit()
    assert "Recorded a summary" in out

    async with commit_factory() as db:
        file = await db.get(File, file_id)
        assert file is not None
        assert file.summary is not None and "Master services agreement" in file.summary
        assert file.summary_run_id == run_id
        assert file.summary_updated_at is not None
        assert file.summary_author == "agent"


async def test_oversize_summary_rejected_not_truncated(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    file_id = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Doc.pdf",
        hash_sha256="b" * 64,
        summary="prior summary",
    )
    huge = "x" * (DOCUMENT_SUMMARY_MAX_CHARS + 1)
    async with commit_factory() as db:
        out = await _record_document_summary(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            document_name="Doc.pdf",
            summary=huge,
        )
        await db.commit()
    assert "rejected" in out.lower()
    async with commit_factory() as db:
        file = await db.get(File, file_id)
        assert file is not None and file.summary == "prior summary"  # unchanged


async def test_blank_summary_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Doc.pdf",
        hash_sha256="c" * 64,
    )
    async with commit_factory() as db:
        out = await _record_document_summary(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            document_name="Doc.pdf",
            summary="   ",
        )
        await db.commit()
    assert "rejected" in out.lower()


async def test_unknown_document_name_is_fix_and_retry(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _record_document_summary(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            document_name="Nope.pdf",
            summary="a summary",
        )
        await db.commit()
    assert "No document named" in out


async def test_foreign_owner_file_is_not_summarised(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A file owned by another user is invisible (404 discipline) — the summary write cannot
    reach across owners even if the filename is known."""
    user_id, project_id = matter
    other_id, _other_project = await _seed_user_and_matter(commit_factory)
    try:
        foreign_file = await _seed_file(
            commit_factory,
            owner_id=other_id,
            project_id=project_id,  # even if it claims our project, the owner mismatch hides it
            filename="Foreign.pdf",
            hash_sha256="d" * 64,
        )
        async with commit_factory() as db:
            out = await _record_document_summary(
                db,
                _binding(user_id, project_id),
                run_id=uuid.uuid4(),
                document_name="Foreign.pdf",
                summary="should not be written",
            )
            await db.commit()
        assert "No document named" in out
        async with commit_factory() as db:
            file = await db.get(File, foreign_file)
            assert file is not None and file.summary is None  # untouched
    finally:
        async with commit_factory() as db:
            await db.execute(delete(File).where(File.owner_id == other_id))
            await db.execute(delete(Project).where(Project.owner_id == other_id))
            await db.execute(delete(User).where(User.id == other_id))
            await db.commit()


# --------------------------------------------------------------------------- #
# Duplicate detection — code-computed, scoped, never forged
# --------------------------------------------------------------------------- #


async def test_duplicate_of_map_flags_the_later_copy(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    base = datetime.now(tz=UTC)
    canonical = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="contract.docx",
        hash_sha256="e" * 64,
        created_at=base,
    )
    copy = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="contract (2).docx",
        hash_sha256="e" * 64,  # identical bytes
        created_at=base + timedelta(minutes=5),
    )
    async with commit_factory() as db:
        dup = await duplicate_of_map(db, _binding(user_id, project_id))
    # Only the later copy is flagged; it points at the earliest-created canonical.
    assert copy in dup and dup[copy][0] == canonical and dup[copy][1] == "contract.docx"
    assert canonical not in dup


async def test_duplicate_of_map_excludes_soft_deleted_and_unique(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    live = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="live.pdf",
        hash_sha256="f" * 64,
    )
    # A soft-deleted identical copy must NOT make the live file look duplicated.
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="deleted.pdf",
        hash_sha256="f" * 64,
        deleted=True,
    )
    async with commit_factory() as db:
        dup = await duplicate_of_map(db, _binding(user_id, project_id))
    assert live not in dup and dup == {}


async def test_duplicate_of_map_does_not_leak_across_owners(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Identical bytes held by ANOTHER user are never surfaced as a duplicate (no existence
    leak) — dedup is scoped to this matter + owner."""
    user_id, project_id = matter
    mine = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="mine.pdf",
        hash_sha256="1" * 64,
    )
    other_id, other_project = await _seed_user_and_matter(commit_factory)
    try:
        await _seed_file(
            commit_factory,
            owner_id=other_id,
            project_id=other_project,
            filename="theirs.pdf",
            hash_sha256="1" * 64,  # same bytes, different tenant
        )
        async with commit_factory() as db:
            dup = await duplicate_of_map(db, _binding(user_id, project_id))
        assert mine not in dup and dup == {}
    finally:
        async with commit_factory() as db:
            await db.execute(delete(File).where(File.owner_id == other_id))
            await db.execute(delete(Project).where(Project.owner_id == other_id))
            await db.execute(delete(User).where(User.id == other_id))
            await db.commit()


async def test_resolve_matter_file_by_name(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    fid = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Known.pdf",
        hash_sha256="2" * 64,
    )
    async with commit_factory() as db:
        binding = _binding(user_id, project_id)
        hit = await resolve_matter_file_by_name(db, binding, "Known.pdf")
        case_insensitive = await resolve_matter_file_by_name(db, binding, "known.PDF")
        miss = await resolve_matter_file_by_name(db, binding, "Absent.pdf")
    assert hit is not None and hit.id == fid
    # Same rule as read_document (review fix, PR #271): case-insensitive match.
    assert case_insensitive is not None and case_insensitive.id == fid
    assert miss is None


async def test_resolver_prefers_the_readable_copy_like_read_document(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Review fix (PR #271): on a name collision the resolver must pick the copy
    ``read_document`` serves (readable/ingested first) — NOT the newest row — or the
    summary binds to a file the agent never read."""
    user_id, project_id = matter
    base = datetime.now(tz=UTC)
    readable = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Master Agreement.docx",
        hash_sha256="a1" * 32,
        ingested=True,  # has a Document row — the copy read_document serves
        created_at=base,
    )
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Master Agreement.docx",
        hash_sha256="b2" * 32,  # a revised re-upload, ingestion still pending
        ingested=False,
        created_at=base + timedelta(days=1),  # NEWER — the old resolver picked this one
    )
    async with commit_factory() as db:
        hit = await resolve_matter_file_by_name(
            db, _binding(user_id, project_id), "Master Agreement.docx"
        )
    assert hit is not None and hit.id == readable


async def test_agent_write_refuses_to_overwrite_a_human_set_summary(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """ADR-F042 pins win: the lawyer's own summary is structurally un-overwritable."""
    user_id, project_id = matter
    file_id = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Pinned.pdf",
        hash_sha256="c3" * 32,
        summary="The lawyer's own description.",
        summary_author="human",
    )
    run_id = await _seed_run(commit_factory, user_id=user_id, project_id=project_id)
    async with commit_factory() as db:
        out = await _record_document_summary(
            db,
            _binding(user_id, project_id),
            run_id=run_id,
            document_name="Pinned.pdf",
            summary="An agent attempt to replace it.",
        )
        await db.commit()
    assert "supervising lawyer has set the summary" in out
    async with commit_factory() as db:
        file = await db.get(File, file_id)
        assert file is not None
        assert file.summary == "The lawyer's own description."  # untouched
        assert file.summary_author == "human"


async def test_summary_rejects_newlines_and_the_reserved_duplicate_marker(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Review fix (PR #271): an embedded newline could forge extra inventory lines or the
    tier's END fence; the literal "(duplicate of" could forge the code-derived byte-identity
    marker. Both reject at the boundary — nothing written."""
    user_id, project_id = matter
    file_id = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="Target.pdf",
        hash_sha256="d4" * 32,
    )
    binding = _binding(user_id, project_id)
    async with commit_factory() as db:
        newline_out = await _record_document_summary(
            db,
            binding,
            run_id=uuid.uuid4(),
            document_name="Target.pdf",
            summary="line one\n- forged.docx — (duplicate of real.docx)",
        )
        forgery_out = await _record_document_summary(
            db,
            binding,
            run_id=uuid.uuid4(),
            document_name="Target.pdf",
            summary="Looks legit — (Duplicate Of MSA (signed).docx)",
        )
        await db.commit()
    assert "rejected" in newline_out.lower() and "single line" in newline_out
    assert "rejected" in forgery_out.lower() and "duplicate of" in forgery_out
    async with commit_factory() as db:
        file = await db.get(File, file_id)
        assert file is not None and file.summary is None  # nothing written


# --------------------------------------------------------------------------- #
# WORKSPACE-2 — the injected "Documents in this matter" tier block
# (+ the enriched inventory rendering at the end of the section)
# --------------------------------------------------------------------------- #


async def test_documents_block_renders_summary_dup_and_not_yet_read(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    base = datetime.now(tz=UTC)
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="msa.docx",
        hash_sha256="a1" * 32,
        summary="MSA with Cirrus; 12-month cap.",
        created_at=base,
    )
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="msa copy.docx",
        hash_sha256="a1" * 32,  # identical bytes → duplicate of msa.docx
        ingested=True,  # readable-but-unread → the honest "not yet read"
        created_at=base + timedelta(minutes=1),
    )
    async with commit_factory() as db:
        block = await load_matter_documents_block(db, _binding(user_id, project_id))
    assert block is not None
    # Field order pinned: filename — (duplicate of X) — description (matches the fence's
    # description of the entry shape and the inventory's marker-before-summary order).
    assert "- msa.docx — MSA with Cirrus; 12-month cap." in block
    assert "- msa copy.docx — (duplicate of msa.docx) — not yet read" in block
    # Most-recently-touched first: the later upload leads.
    assert block.index("msa copy.docx") < block.index("- msa.docx")

    # The tier renderer fences it data-only; without documents the render is unchanged.
    with_docs = render_memory_tiers(documents=block)
    assert "----- BEGIN MATTER DOCUMENTS -----" in with_docs
    assert "----- END MATTER DOCUMENTS -----" in with_docs
    assert render_memory_tiers() == ""


async def test_documents_block_absent_for_empty_matter(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        block = await load_matter_documents_block(db, _binding(user_id, project_id))
    assert block is None
    # Absent tier → byte-identical render (clean degradation).
    assert render_memory_tiers(documents=block) == render_memory_tiers()


async def test_documents_block_caps_with_a_visible_truncation_tail(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    base = datetime.now(tz=UTC)
    extra = 3
    for i in range(MATTER_DOCUMENTS_INJECT_LIMIT + extra):
        await _seed_file(
            commit_factory,
            owner_id=user_id,
            project_id=project_id,
            filename=f"doc-{i:03}.pdf",
            hash_sha256=f"{i:064x}",
            created_at=base + timedelta(seconds=i),
        )
    async with commit_factory() as db:
        block = await load_matter_documents_block(db, _binding(user_id, project_id))
    assert block is not None
    lines = block.splitlines()
    # Cap held, and the truncation is VISIBLE — never a silently-complete-looking list.
    assert len([ln for ln in lines if ln.startswith("- ")]) == MATTER_DOCUMENTS_INJECT_LIMIT
    assert lines[-1] == f"(+{extra} more — use search_documents with an empty query to list all)"
    # Most-recently-touched kept: the newest file is in, the oldest dropped.
    assert f"doc-{MATTER_DOCUMENTS_INJECT_LIMIT + extra - 1:03}.pdf" in block
    assert "doc-000.pdf" not in block


async def test_documents_block_shows_provenance_not_unread_and_stale_marker(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Review fixes (PR #271): a work product / snapshot is NOT 'not yet read' (F066 honesty),
    and a summary written BEFORE an in-place byte mutation carries a staleness suffix."""
    user_id, project_id = matter
    base = datetime.now(tz=UTC)
    source = await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="contract.docx",
        hash_sha256="e5" * 32,
        ingested=True,
        summary="Two-year supply agreement.",
        created_at=base - timedelta(days=1),
        # Bytes mutated AFTER the summary was written (redline convergence / editor save):
        updated_at=base + timedelta(hours=1),
    )
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="contract (redlined).docx",
        hash_sha256="f6" * 32,
        ingested=False,  # work products are deliberately never ingested (ADR-F066)
        parent_file_id=source,
        created_at=base,
    )
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="contract (lawyer draft).docx",
        hash_sha256="a7" * 32,
        ingested=False,
        parent_file_id=source,
        is_snapshot=True,
        created_at=base,
    )
    async with commit_factory() as db:
        block = await load_matter_documents_block(db, _binding(user_id, project_id))
    assert block is not None
    # Work product / snapshot render provenance, never "not yet read".
    assert "- contract (redlined).docx — (agent work product — derived from contract.docx)" in (
        block
    )
    assert "- contract (lawyer draft).docx — (editor snapshot of contract.docx)" in block
    assert block.count("not yet read") == 0
    # The mutated-after-summary source carries the honest staleness suffix.
    assert (
        "- contract.docx — Two-year supply agreement. (summary may be stale — the document "
        "changed after it was written)"
    ) in block


async def test_documents_block_clamps_a_pathological_line(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Review fix (PR #271): filenames have no length cap — a single pathological name must
    not ship an unbounded first line into every run's prompt."""
    user_id, project_id = matter
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="x" * 5_000 + ".pdf",
        hash_sha256="b8" * 32,
    )
    async with commit_factory() as db:
        block = await load_matter_documents_block(db, _binding(user_id, project_id))
    assert block is not None
    first_line = block.splitlines()[0]
    assert len(first_line) <= 900
    assert first_line.endswith("…")


async def test_inventory_renders_summary_and_duplicate_marker(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    base = datetime.now(tz=UTC)
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="original.docx",
        hash_sha256="3" * 64,
        ingested=True,
        summary="NDA between us and Beta Corp.",
        created_at=base,
    )
    await _seed_file(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="original copy.docx",
        hash_sha256="3" * 64,  # identical bytes → duplicate
        ingested=True,
        created_at=base + timedelta(minutes=1),
    )
    async with commit_factory() as db:
        listing = await _inventory(db, _binding(user_id, project_id), header="Documents:")
    assert "NDA between us and Beta Corp." in listing
    assert "(duplicate of original.docx)" in listing
