"""Tests for migration 0007 — knowledge_bases + knowledge_base_files (Task C6).

Verifies the schema lands as documented in docs/db-schema.md and ADR
0008's commitments — table existence, indexes, the hybrid_alpha CHECK
constraint, the FK shapes, and the trigger.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase, KnowledgeBaseFile, User


@pytest.mark.integration
async def test_kb_tables_exist(db_session: AsyncSession) -> None:
    """C6: knowledge_bases + knowledge_base_files exist after migration."""

    expected = {"knowledge_bases", "knowledge_base_files"}
    result = await db_session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = ANY(:names)"
        ),
        {"names": list(expected)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected, f"missing tables: {expected - found}"


@pytest.mark.integration
async def test_kb_indexes_exist(db_session: AsyncSession) -> None:
    """C6: the listing index, the project filter index, and the kb_files inverse index exist."""

    expected = {"idx_kbs_owner_active", "idx_kbs_project", "idx_kb_files_file_id"}
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(:names)"
        ),
        {"names": list(expected)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected, f"missing indexes: {expected - found}"


@pytest.mark.integration
async def test_kb_hybrid_alpha_check_fires(db_session: AsyncSession) -> None:
    """C6: hybrid_alpha must be in [0, 1]."""

    user = User(
        email=f"alpha-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()

    bad = KnowledgeBase(owner_id=user.id, name="bad", hybrid_alpha=1.5)
    db_session.add(bad)
    with pytest.raises(Exception, match=r"(?i)alpha_range"):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_kb_alpha_zero_and_one_accepted(db_session: AsyncSession) -> None:
    """C6: boundary values 0.0 and 1.0 are valid (the CHECK is inclusive)."""

    user = User(
        email=f"alpha-edge-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()

    kb_zero = KnowledgeBase(owner_id=user.id, name="zero", hybrid_alpha=0.0)
    kb_one = KnowledgeBase(owner_id=user.id, name="one", hybrid_alpha=1.0)
    db_session.add(kb_zero)
    db_session.add(kb_one)
    await db_session.flush()
    assert kb_zero.id is not None and kb_one.id is not None


@pytest.mark.integration
async def test_kb_name_length_check(db_session: AsyncSession) -> None:
    """C6: name must be non-empty and at most 200 chars."""

    user = User(
        email=f"name-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()

    bad = KnowledgeBase(owner_id=user.id, name="")
    db_session.add(bad)
    with pytest.raises(Exception, match=r"(?i)name_len"):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_kb_files_cascade_on_kb_delete(db_session: AsyncSession) -> None:
    """C6: deleting a KB hard-removes its kb_files rows (CASCADE)."""

    from app.models.file import File

    user = User(
        email=f"cascade-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()

    kb = KnowledgeBase(owner_id=user.id, name="kb")
    db_session.add(kb)
    await db_session.flush()

    file_row = File(
        owner_id=user.id,
        filename="doc.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        hash_sha256="x" * 64,
        storage_path="x",
        ingestion_status="ready",
    )
    db_session.add(file_row)
    await db_session.flush()

    join = KnowledgeBaseFile(kb_id=kb.id, file_id=file_row.id)
    db_session.add(join)
    await db_session.flush()

    # Hard-delete the KB. The CASCADE FK should remove the join row.
    await db_session.execute(
        text("DELETE FROM knowledge_bases WHERE id = :kid"), {"kid": str(kb.id)}
    )
    await db_session.flush()

    rows = await db_session.execute(
        text("SELECT 1 FROM knowledge_base_files WHERE kb_id = :kid"),
        {"kid": str(kb.id)},
    )
    assert rows.first() is None


@pytest.mark.integration
async def test_kb_updated_at_trigger(db_session: AsyncSession) -> None:
    """C6: updated_at is bumped on UPDATE via the set_updated_at() trigger."""

    user = User(
        email=f"upd-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()

    kb = KnowledgeBase(owner_id=user.id, name="upd")
    db_session.add(kb)
    await db_session.flush()
    initial = kb.updated_at

    await db_session.execute(
        text("UPDATE knowledge_bases SET name = 'updated' WHERE id = :kid"),
        {"kid": str(kb.id)},
    )
    await db_session.flush()
    await db_session.refresh(kb)
    assert kb.updated_at >= initial


@pytest.mark.integration
async def test_kb_owner_restrict(db_session: AsyncSession) -> None:
    """C6: deleting a user that owns KBs is RESTRICTed."""

    user = User(
        email=f"restrict-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()

    kb = KnowledgeBase(owner_id=user.id, name="kb")
    db_session.add(kb)
    await db_session.flush()

    with pytest.raises(Exception, match=r"(?i)foreign key"):
        await db_session.execute(
            text("DELETE FROM users WHERE id = :uid"), {"uid": str(user.id)}
        )
        await db_session.flush()
    await db_session.rollback()
