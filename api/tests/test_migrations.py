"""Smoke tests for the Phase A1 migration (0001_initial).

Verifies:
- Migration applies cleanly to a fresh DB
- All four expected tables exist
- CITEXT email column behaves case-insensitively
- CHECK constraints fire correctly
- Partial indexes are created
- Per-test transaction rollback fixture works (data inserted in one test
  doesn't leak to the next)
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, KnowledgeBase, User


@pytest.mark.integration
async def test_phase_a1_tables_exist(db_session: AsyncSession) -> None:
    """All four Phase A1 tables exist after the migration runs."""
    expected = {"users", "user_sessions", "audit_log", "inference_routing_log"}
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
async def test_users_email_is_citext(db_session: AsyncSession) -> None:
    """users.email is case-insensitive: inserting two cases collides."""
    user1 = User(email="kevin@example.com", hashed_password="hash1")
    db_session.add(user1)
    await db_session.flush()

    # Same email different case should violate UNIQUE
    user2 = User(email="KEVIN@example.com", hashed_password="hash2")
    db_session.add(user2)

    with pytest.raises(Exception):  # IntegrityError or its asyncpg flavor
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_audit_log_privilege_check_constraint(db_session: AsyncSession) -> None:
    """privilege_marked=true requires privilege_basis to be set."""
    bad = AuditLog(
        action="test.action",
        resource_type="test",
        privilege_marked=True,
        privilege_basis=None,  # CHECK constraint should reject this
    )
    db_session.add(bad)
    with pytest.raises(Exception):
        await db_session.flush()
    await db_session.rollback()

    # Same row with privilege_basis populated should succeed
    good = AuditLog(
        action="test.action",
        resource_type="test",
        privilege_marked=True,
        privilege_basis="matter_attorney_directive",
    )
    db_session.add(good)
    await db_session.flush()
    assert good.id is not None


@pytest.mark.integration
async def test_inference_log_tier_range_check(db_session: AsyncSession) -> None:
    """routed_inference_tier must be 1-5."""
    from app.models import InferenceRoutingLog

    out_of_range = InferenceRoutingLog(
        routed_provider="test-provider",
        routed_model="test-model",
        routed_inference_tier=6,  # invalid
    )
    db_session.add(out_of_range)
    with pytest.raises(Exception):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_partial_indexes_exist(db_session: AsyncSession) -> None:
    """Verify the partial indexes specified in db-schema.md were created."""
    expected_partials = {
        "idx_users_email_active",
        "idx_users_deletion_scheduled",
        # idx_user_sessions_token_hash (bcrypt partial index) was dropped in
        # migration 0084 (ADR-F059) — refresh now uses a full UNIQUE index on
        # refresh_token_hmac (ix_user_sessions_refresh_token_hmac), not partial.
        "idx_audit_log_privileged",
        "idx_audit_log_tier",
        "idx_inference_log_user",
        "idx_inference_log_refused",
    }
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(:names)"
        ),
        {"names": list(expected_partials)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected_partials, f"missing indexes: {expected_partials - found}"


@pytest.mark.integration
async def test_updated_at_trigger_on_users(db_session: AsyncSession) -> None:
    """users.updated_at is bumped by the trigger on UPDATE."""
    user = User(email=f"trigger-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()
    initial_updated_at = user.updated_at

    # Use a raw SQL UPDATE to bypass the ORM and prove the DB-level trigger fires
    await db_session.execute(
        text("UPDATE users SET display_name = 'Triggered' WHERE id = :id"),
        {"id": user.id},
    )
    await db_session.flush()
    await db_session.refresh(user)
    assert user.updated_at >= initial_updated_at


@pytest.mark.integration
async def test_per_test_isolation_left_over_data(db_session: AsyncSession) -> None:
    """First half of a paired test: inserts a row that should NOT survive."""
    user = User(email="isolation-canary@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()
    # No commit. Teardown should roll back.


@pytest.mark.integration
async def test_per_test_isolation_canary_gone(db_session: AsyncSession) -> None:
    """Second half: the canary row from the previous test must be absent."""
    result = await db_session.execute(
        text("SELECT id FROM users WHERE email = 'isolation-canary@example.com'")
    )
    assert result.first() is None, "previous test's row leaked across test boundary"


# ---------------------------------------------------------------------------
# C4 — files table (migration 0003)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_files_table_exists(db_session: AsyncSession) -> None:
    """`files` table exists after the C4 migration runs."""
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'files'")
    )
    assert result.scalar_one_or_none() == "files"


@pytest.mark.integration
async def test_files_indexes_exist(db_session: AsyncSession) -> None:
    """The four indexes on `files` from migration 0003 are created."""
    expected = {
        "idx_files_owner_active",
        "idx_files_project",
        "idx_files_status",
        "idx_files_hash",
    }
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
async def test_files_ingestion_status_check(db_session: AsyncSession) -> None:
    """files.ingestion_status accepts only the four valid states."""
    from sqlalchemy.exc import IntegrityError

    from app.models import File, User

    user = User(email=f"file-chk-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()

    bad = File(
        owner_id=user.id,
        filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        hash_sha256="0" * 64,
        storage_path="abc",
        ingestion_status="invalid_state",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_files_size_nonneg_check(db_session: AsyncSession) -> None:
    """files.size_bytes >= 0 (CHECK constraint)."""
    from sqlalchemy.exc import IntegrityError

    from app.models import File, User

    user = User(email=f"file-neg-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()

    bad = File(
        owner_id=user.id,
        filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=-1,
        hash_sha256="0" * 64,
        storage_path="abc",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# C7 — projects + project_files + project_skills (migration 0004)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_projects_tables_exist(db_session: AsyncSession) -> None:
    """`projects`, `project_files`, `project_skills` exist after 0004."""

    expected = {"projects", "project_files", "project_skills"}
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
async def test_projects_indexes_exist(db_session: AsyncSession) -> None:
    """The expected indexes from migration 0004 are present."""

    expected = {
        "idx_projects_owner_active",
        "idx_projects_slug_owner_active",
        "idx_project_files_file",
        "idx_project_skills_skill",
    }
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
async def test_files_project_id_fk_exists(db_session: AsyncSession) -> None:
    """The C4-deferred FK on files.project_id was added by 0004."""

    result = await db_session.execute(
        text("SELECT conname FROM pg_constraint WHERE conname = 'fk_files_project_id'")
    )
    assert result.scalar_one_or_none() == "fk_files_project_id"


@pytest.mark.integration
async def test_projects_privileged_implies_tier_check(db_session: AsyncSession) -> None:
    """privileged=true requires minimum_inference_tier IS NOT NULL (DB-layer)."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Project, User

    user = User(email=f"proj-chk-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()

    # privileged=true with no tier → CHECK violation.
    bad = Project(
        owner_id=user.id,
        name="bad",
        slug="bad",
        privileged=True,
        minimum_inference_tier=None,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_projects_tier_range_check(db_session: AsyncSession) -> None:
    """minimum_inference_tier must be NULL or in 1-5 (DB-layer)."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Project, User

    user = User(email=f"proj-tier-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()

    bad = Project(
        owner_id=user.id,
        name="bad",
        slug="bad-tier",
        privileged=False,
        minimum_inference_tier=7,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_files_project_fk_set_null_on_delete(
    db_session: AsyncSession,
) -> None:
    """ON DELETE SET NULL: deleting a project nulls files.project_id."""
    from app.models import File, Project, User

    user = User(email=f"fk-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()

    project = Project(
        owner_id=user.id,
        name="P",
        slug=f"p-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(project)
    await db_session.flush()

    f = File(
        owner_id=user.id,
        project_id=project.id,
        filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        hash_sha256="0" * 64,
        storage_path="abc",
    )
    db_session.add(f)
    await db_session.flush()
    assert f.project_id == project.id

    # Delete the project; the FK should NULL out files.project_id.
    await db_session.delete(project)
    await db_session.flush()
    await db_session.refresh(f)
    assert f.project_id is None


# ---------------------------------------------------------------------------
# C5 — documents and document_chunks tables (migration 0005)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_documents_table_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename = 'documents'"
        )
    )
    assert result.scalar_one_or_none() == "documents"


@pytest.mark.integration
async def test_document_chunks_table_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename = 'document_chunks'"
        )
    )
    assert result.scalar_one_or_none() == "document_chunks"


@pytest.mark.integration
async def test_pgvector_extension_installed(db_session: AsyncSession) -> None:
    """The pgvector extension is enabled by migration 0005."""
    result = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    )
    assert result.scalar_one_or_none() == "vector"


@pytest.mark.integration
async def test_documents_unique_file_id(db_session: AsyncSession) -> None:
    """Only one Document row per file."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Document, File, User

    user = User(email=f"doc-uq-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()

    file_row = File(
        owner_id=user.id,
        filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        hash_sha256="0" * 64,
        storage_path="abc",
    )
    db_session.add(file_row)
    await db_session.flush()

    db_session.add(Document(file_id=file_row.id, parser="pymupdf"))
    await db_session.flush()

    db_session.add(Document(file_id=file_row.id, parser="pymupdf"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_document_chunks_offset_check_constraints(
    db_session: AsyncSession,
) -> None:
    """char_offset_end >= char_offset_start; both >= 0."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Document, DocumentChunk, File, User

    user = User(
        email=f"chunk-chk-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="h",
    )
    db_session.add(user)
    await db_session.flush()
    file_row = File(
        owner_id=user.id,
        filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        hash_sha256="0" * 64,
        storage_path="abc",
    )
    db_session.add(file_row)
    await db_session.flush()

    doc = Document(file_id=file_row.id, parser="pymupdf")
    db_session.add(doc)
    await db_session.flush()

    # char_offset_start < 0 → CHECK violation
    bad = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="hi",
        char_offset_start=-1,
        char_offset_end=10,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_document_chunks_unique_index_pair(db_session: AsyncSession) -> None:
    """(document_id, chunk_index) is UNIQUE."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Document, DocumentChunk, File, User

    user = User(
        email=f"chunk-unq-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="h",
    )
    db_session.add(user)
    await db_session.flush()
    file_row = File(
        owner_id=user.id,
        filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        hash_sha256="0" * 64,
        storage_path="abc",
    )
    db_session.add(file_row)
    await db_session.flush()
    doc = Document(file_id=file_row.id, parser="pymupdf")
    db_session.add(doc)
    await db_session.flush()

    db_session.add(
        DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            content="a",
            char_offset_start=0,
            char_offset_end=1,
        )
    )
    await db_session.flush()

    db_session.add(
        DocumentChunk(
            document_id=doc.id,
            chunk_index=0,  # duplicate index
            content="b",
            char_offset_start=2,
            char_offset_end=3,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_documents_cascade_delete_via_file(db_session: AsyncSession) -> None:
    """Hard-deleting a file cascades to document and chunks."""
    from app.models import Document, DocumentChunk, File, User

    user = User(email=f"cascade-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()
    file_row = File(
        owner_id=user.id,
        filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        hash_sha256="0" * 64,
        storage_path="abc",
    )
    db_session.add(file_row)
    await db_session.flush()
    doc = Document(file_id=file_row.id, parser="pymupdf")
    db_session.add(doc)
    await db_session.flush()
    db_session.add(
        DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            content="content",
            char_offset_start=0,
            char_offset_end=7,
        )
    )
    await db_session.flush()

    # Hard-delete the file (DELETE FROM files WHERE id = ...).
    await db_session.execute(text("DELETE FROM files WHERE id = :id"), {"id": file_row.id})
    await db_session.flush()

    # The document and its chunks should be gone.
    docs_remaining = await db_session.execute(
        text("SELECT count(*) FROM documents WHERE file_id = :id"),
        {"id": file_row.id},
    )
    assert docs_remaining.scalar_one() == 0

    chunks_remaining = await db_session.execute(
        text("SELECT count(*) FROM document_chunks WHERE document_id = :id"),
        {"id": doc.id},
    )
    assert chunks_remaining.scalar_one() == 0


# ---------------------------------------------------------------------------
# Task C3 — chats + messages migration (0006)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_chats_and_messages_tables_exist(db_session: AsyncSession) -> None:
    """C3: ``chats`` and ``messages`` tables exist after migration 0006."""

    expected = {"chats", "messages"}
    result = await db_session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = ANY(:names)"
        ),
        {"names": list(expected)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected


@pytest.mark.integration
async def test_chats_indexes_exist(db_session: AsyncSession) -> None:
    """C3: the active-listing and project-active partial indexes exist
    plus the ordered messages index."""

    expected = {
        "idx_chats_owner_active",
        "idx_chats_project_active",
        "idx_messages_chat_created",
    }
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(:names)"
        ),
        {"names": list(expected)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected


@pytest.mark.integration
async def test_messages_role_check_fires(db_session: AsyncSession) -> None:
    """C3: inserting a message with a bogus role violates the CHECK."""

    from app.models.chat import Chat
    from app.models.user import User

    user = User(
        email=f"role-check-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()
    chat = Chat(owner_id=user.id, title="x")
    db_session.add(chat)
    await db_session.flush()

    with pytest.raises(Exception):
        await db_session.execute(
            text("INSERT INTO messages (chat_id, role, content) VALUES (:cid, 'bogus_role', 'x')"),
            {"cid": chat.id},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_messages_cascade_delete_on_chat(db_session: AsyncSession) -> None:
    """C3: deleting a chat cascades to its messages."""

    from app.models.chat import Chat
    from app.models.user import User

    user = User(
        email=f"cascade-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()
    chat = Chat(owner_id=user.id, title="x")
    db_session.add(chat)
    await db_session.flush()
    chat_id = chat.id

    await db_session.execute(
        text(
            "INSERT INTO messages (chat_id, role, content) "
            "VALUES (:cid, 'user', 'a'), (:cid, 'assistant', 'b')"
        ),
        {"cid": chat_id},
    )
    await db_session.flush()

    # Hard-delete the chat.
    await db_session.execute(text("DELETE FROM chats WHERE id = :cid"), {"cid": chat_id})
    await db_session.flush()

    rows = await db_session.execute(
        text("SELECT count(*) FROM messages WHERE chat_id = :cid"),
        {"cid": chat_id},
    )
    assert rows.scalar_one() == 0


# Note: previous tests at this position verified ON DELETE SET NULL behavior
# for inference_routing_log.chat_id and .message_id (the FK constraints
# closed C3's deferred A2 item). Migration 0008
# (drop_inference_routing_log_message_fks) intentionally dropped both FKs to
# fix the gateway/backend write-order race (the gateway writes the
# routing-log row at end-of-call before the backend persists the message
# row; the FK rejected the insert and B4's "never raise" invariant silently
# swallowed every audit row). Per that migration's docstring, the
# NULL-on-delete behavior "was not load-bearing because the messages row
# carries the same routing metadata (routed_inference_tier, provider,
# model, tokens, cost) on its own." The two tests were retired alongside
# the constraint.


@pytest.mark.integration
async def test_messages_applied_skills_default_empty_array(db_session: AsyncSession) -> None:
    """C3: ``applied_skills`` defaults to an empty text[] when omitted."""

    from app.models.chat import Chat
    from app.models.user import User

    user = User(
        email=f"applied-skills-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    db_session.add(user)
    await db_session.flush()
    chat = Chat(owner_id=user.id, title="x")
    db_session.add(chat)
    await db_session.flush()

    # Insert via raw SQL omitting applied_skills.
    msg_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO messages (id, chat_id, role, content) VALUES (:mid, :cid, 'user', 'hi')"),
        {"mid": msg_id, "cid": chat.id},
    )
    await db_session.flush()

    rows = await db_session.execute(
        text("SELECT applied_skills FROM messages WHERE id = :mid"),
        {"mid": msg_id},
    )
    value = rows.scalar_one()
    # Postgres returns the text[] as a Python list.
    assert value == []


# ---------------------------------------------------------------------------
# 0026 — paraphrase_judge enum + partial column on message_citations (M2-C1)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_message_citations_accepts_paraphrase_judge_method(
    db_session: AsyncSession,
) -> None:
    """The widened enum accepts the new ``'paraphrase_judge'`` method value.

    The 0026 migration replaces the M2-A2 CHECK constraint to add
    ``'paraphrase_judge'``. Without the migration the INSERT below
    would fail the constraint.
    """

    # Need a real chat + message + file to satisfy the FKs.
    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    message_id = uuid.uuid4()
    file_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO users (id, email, display_name, hashed_password) "
            "VALUES (:uid, :email, 'M2-C1 Test', 'x')"
        ),
        {"uid": user_id, "email": f"c1-{uuid.uuid4().hex[:6]}@example.com"},
    )
    await db_session.execute(
        text("INSERT INTO chats (id, owner_id, title) VALUES (:cid, :uid, 't')"),
        {"cid": chat_id, "uid": user_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, role, content) "
            "VALUES (:mid, :cid, 'assistant', 'x')"
        ),
        {"mid": message_id, "cid": chat_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO files (id, owner_id, filename, mime_type, size_bytes, "
            "hash_sha256, storage_path) VALUES "
            "(:fid, :uid, 'f.pdf', 'application/pdf', 1, "
            "'a' || repeat('0', 63), 's3://k')"
        ),
        {"fid": file_id, "uid": user_id},
    )
    await db_session.flush()

    await db_session.execute(
        text(
            "INSERT INTO message_citations "
            "(message_id, source_file_id, source_offset_start, source_offset_end, "
            "source_text, verified, verification_method, verification_confidence, "
            "partial) "
            "VALUES (:mid, :fid, 0, 5, 'hello', true, 'paraphrase_judge', "
            "0.90, true)"
        ),
        {"mid": message_id, "fid": file_id},
    )
    await db_session.flush()

    row = (
        await db_session.execute(
            text(
                "SELECT verification_method, partial FROM message_citations WHERE message_id = :mid"
            ),
            {"mid": message_id},
        )
    ).one()
    assert row[0] == "paraphrase_judge"
    assert row[1] is True


@pytest.mark.integration
async def test_message_citations_partial_default_false(
    db_session: AsyncSession,
) -> None:
    """``partial`` defaults to ``false`` so M2-A2 / M2-B1 callers stay correct.

    The Stage 1 / Stage 2 verifiers don't write ``partial`` explicitly;
    the default keeps their rows readable as fully-verified.
    """

    user_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    message_id = uuid.uuid4()
    file_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO users (id, email, display_name, hashed_password) "
            "VALUES (:uid, :email, 'C1 Default', 'x')"
        ),
        {"uid": user_id, "email": f"c1-{uuid.uuid4().hex[:6]}@example.com"},
    )
    await db_session.execute(
        text("INSERT INTO chats (id, owner_id, title) VALUES (:cid, :uid, 't')"),
        {"cid": chat_id, "uid": user_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, role, content) "
            "VALUES (:mid, :cid, 'assistant', 'x')"
        ),
        {"mid": message_id, "cid": chat_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO files (id, owner_id, filename, mime_type, size_bytes, "
            "hash_sha256, storage_path) VALUES "
            "(:fid, :uid, 'f.pdf', 'application/pdf', 1, "
            "'a' || repeat('0', 63), 's3://k')"
        ),
        {"fid": file_id, "uid": user_id},
    )
    await db_session.flush()

    # Omit ``partial`` — the column default should populate it.
    await db_session.execute(
        text(
            "INSERT INTO message_citations "
            "(message_id, source_file_id, source_offset_start, source_offset_end, "
            "source_text, verified, verification_method, verification_confidence) "
            "VALUES (:mid, :fid, 0, 5, 'hello', true, 'exact_match', 1.0)"
        ),
        {"mid": message_id, "fid": file_id},
    )
    await db_session.flush()

    row = (
        await db_session.execute(
            text("SELECT partial FROM message_citations WHERE message_id = :mid"),
            {"mid": message_id},
        )
    ).one()
    assert row[0] is False


# ---------------------------------------------------------------------------
# SETUP-3a — user_auth_tokens + users.disabled_at/email_verified_at + operator
# role (migration 0085, ADR-F061)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_user_auth_tokens_table_exists(db_session: AsyncSession) -> None:
    """The 0085 user_auth_tokens table + its unique HMAC index exist."""
    cols = (
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'user_auth_tokens'"
                )
            )
        )
        .scalars()
        .all()
    )
    expected = {
        "id",
        "purpose",
        "email",
        "user_id",
        "role",
        "token_hmac",
        "created_by",
        "created_at",
        "expires_at",
        "consumed_at",
        "revoked_at",
    }
    assert expected.issubset(set(cols)), f"missing columns: {expected - set(cols)}"

    idx = (
        await db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'ix_user_auth_tokens_token_hmac'"
            )
        )
    ).scalar_one_or_none()
    assert idx == "ix_user_auth_tokens_token_hmac"


@pytest.mark.integration
async def test_user_auth_tokens_purpose_check(db_session: AsyncSession) -> None:
    """purpose is constrained to invite|password_reset."""
    with pytest.raises(Exception):
        await db_session.execute(
            text(
                "INSERT INTO user_auth_tokens (purpose, email, role, token_hmac, expires_at) "
                "VALUES ('bogus', 'x@example.com', 'member', 'h', now())"
            )
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_users_disable_and_verify_columns_exist(db_session: AsyncSession) -> None:
    """users.disabled_at + users.email_verified_at were added by 0085."""
    cols = (
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' "
                    "AND column_name IN ('disabled_at', 'email_verified_at')"
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(cols) == {"disabled_at", "email_verified_at"}


@pytest.mark.integration
async def test_users_role_check_admits_operator(db_session: AsyncSession) -> None:
    """The 0085-widened role CHECK admits 'operator' and still rejects garbage."""
    ok = User(
        email=f"operator-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="h",
        role="operator",
        is_admin=True,
    )
    db_session.add(ok)
    await db_session.flush()  # must NOT raise

    bad = User(
        email=f"bad-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="h",
        role="wizard",
    )
    db_session.add(bad)
    with pytest.raises(Exception):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# SETUP-4a (ADR-F062) — tool-group registry data + deployment capability
# toggles (migration 0086)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_practice_area_tool_groups_table_and_seed(db_session: AsyncSession) -> None:
    """The 0086 practice_area_tool_groups table exists, has the expected columns, and is
    seeded (names only) from today's map: commercial → {redlining, tabular}, privacy →
    {ropa, assessment}."""
    cols = (
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'practice_area_tool_groups'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {"practice_area_id", "group_key", "attached_at"}.issubset(set(cols))

    seeded = (
        await db_session.execute(
            text(
                "SELECT pa.key, t.group_key FROM practice_area_tool_groups t "
                "JOIN practice_areas pa ON pa.id = t.practice_area_id "
                "ORDER BY pa.key, t.group_key"
            )
        )
    ).all()
    assert list(seeded) == [
        ("commercial", "redlining"),
        ("commercial", "tabular"),
        ("privacy", "assessment"),
        ("privacy", "ropa"),
    ]


@pytest.mark.integration
async def test_practice_area_tool_groups_key_len_check(db_session: AsyncSession) -> None:
    """group_key length is CHECK-bounded (1..200) — an empty key is rejected."""
    area_id = (
        await db_session.execute(text("SELECT id FROM practice_areas WHERE key = 'commercial'"))
    ).scalar_one()
    with pytest.raises(Exception):
        await db_session.execute(
            text(
                "INSERT INTO practice_area_tool_groups (practice_area_id, group_key) "
                "VALUES (:aid, '')"
            ),
            {"aid": area_id},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_practice_area_tool_groups_cascade_on_area_delete(db_session: AsyncSession) -> None:
    """Deleting a practice area CASCADE-drops its tool-group rows (FK ON DELETE CASCADE)."""
    await db_session.execute(
        text(
            "INSERT INTO practice_areas (key, name, unit_label, position) "
            "VALUES ('tg-cascade-test', 'TG Cascade', 'Matter', 999)"
        )
    )
    area_id = (
        await db_session.execute(
            text("SELECT id FROM practice_areas WHERE key = 'tg-cascade-test'")
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO practice_area_tool_groups (practice_area_id, group_key) "
            "VALUES (:aid, 'redlining')"
        ),
        {"aid": area_id},
    )
    await db_session.flush()
    await db_session.execute(text("DELETE FROM practice_areas WHERE id = :aid"), {"aid": area_id})
    await db_session.flush()
    remaining = (
        await db_session.execute(
            text("SELECT count(*) FROM practice_area_tool_groups WHERE practice_area_id = :aid"),
            {"aid": area_id},
        )
    ).scalar_one()
    assert remaining == 0
    await db_session.rollback()


@pytest.mark.integration
async def test_org_library_entries_table_exists(db_session: AsyncSession) -> None:
    """0088 (ADR-F065): the org_library_entries table exists with the expected columns."""
    cols = (
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'org_library_entries'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {"capability_kind", "capability_key", "adopted_by", "adopted_at"}.issubset(set(cols))
    # PK is (capability_kind, capability_key).
    pk = (
        (
            await db_session.execute(
                text(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = 'org_library_entries'::regclass AND i.indisprimary "
                    "ORDER BY a.attname"
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(pk) == {"capability_kind", "capability_key"}


@pytest.mark.integration
async def test_org_library_entries_kind_check(db_session: AsyncSession) -> None:
    """capability_kind is CHECK-constrained (0088; widened to admit 'knowledge' in 0092)."""
    await db_session.execute(
        text(
            "INSERT INTO org_library_entries (capability_kind, capability_key) "
            "VALUES ('tool', 'chk-probe-redlining')"
        )
    )
    await db_session.flush()  # a valid kind must NOT raise
    with pytest.raises(Exception):
        await db_session.execute(
            text(
                "INSERT INTO org_library_entries (capability_kind, capability_key) "
                "VALUES ('bogus', 'x')"
            )
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_org_library_entries_adopted_by_set_null_on_user_delete(
    db_session: AsyncSession,
) -> None:
    """adopted_by FK is ON DELETE SET NULL — deleting the adopting user keeps the org's
    Library entry (it is the org's state, not the individual's)."""
    admin = User(
        email=f"lib-fk-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Lib FK User",
        hashed_password="x",
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO org_library_entries (capability_kind, capability_key, adopted_by) "
            "VALUES ('tool', 'fk-probe-tabular', :uid)"
        ),
        {"uid": admin.id},
    )
    await db_session.flush()
    await db_session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": admin.id})
    await db_session.flush()
    adopted_by = (
        await db_session.execute(
            text(
                "SELECT adopted_by FROM org_library_entries WHERE capability_key = 'fk-probe-tabular'"
            )
        )
    ).scalar_one()
    assert adopted_by is None
    await db_session.rollback()


@pytest.mark.integration
async def test_deployment_capability_toggles_table_dropped(db_session: AsyncSession) -> None:
    """0088 supersedes ADR-F062: the deployment_capability_toggles table is DROPPED."""
    reg = (
        await db_session.execute(text("SELECT to_regclass('deployment_capability_toggles')"))
    ).scalar()
    assert reg is None


@pytest.mark.integration
async def test_org_library_fresh_org_starts_empty() -> None:
    """0088 (ADR-F065 decisions 3 & 4): on a FRESH (user-less) deployment the users-empty gate
    SKIPS the seed, so org_library_entries is EMPTY even though the binding tables ARE seeded
    (the 0086 tool-group seed is present). Migrated on a throwaway DB so the shared test DB's
    conftest seed (which emulates an EXISTING deployment) does not mask the fresh-org path."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from tests.conftest import API_DIR

    runtime_url = os.environ.get("DATABASE_URL")
    if not runtime_url:
        pytest.skip("DATABASE_URL not set")

    base, _orig = runtime_url.rsplit("/", 1)
    fresh_db = f"lq_ai_test_store1_{secrets.token_hex(4)}"
    admin_sync = f"{base.replace('postgresql+asyncpg://', 'postgresql://', 1)}/postgres"
    fresh_sync = f"{base.replace('postgresql+asyncpg://', 'postgresql://', 1)}/{fresh_db}"

    def _run() -> tuple[int, int]:
        admin_engine = create_engine(admin_sync, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{fresh_db}"'))
        admin_engine.dispose()
        saved = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = fresh_sync
        try:
            cfg = Config(str(API_DIR / "alembic.ini"))
            cfg.set_main_option("script_location", str(API_DIR / "alembic"))
            command.upgrade(cfg, "head")
            engine = create_engine(fresh_sync)
            with engine.connect() as conn:
                lib = conn.execute(text("SELECT count(*) FROM org_library_entries")).scalar_one()
                groups = conn.execute(
                    text("SELECT count(*) FROM practice_area_tool_groups")
                ).scalar_one()
            engine.dispose()
            return int(lib), int(groups)
        finally:
            if saved is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = saved
            admin_engine = create_engine(admin_sync, isolation_level="AUTOCOMMIT")
            with admin_engine.connect() as conn:
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :db AND pid <> pg_backend_pid()"
                    ),
                    {"db": fresh_db},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{fresh_db}"'))
            admin_engine.dispose()

    lib_count, group_count = await asyncio.to_thread(_run)
    assert lib_count == 0  # users-empty gate skipped the seed → fresh org starts empty
    assert group_count > 0  # binding tables WERE seeded — emptiness is the gate, not empty sources


@pytest.mark.integration
async def test_practice_areas_default_budget_profile_check(db_session: AsyncSession) -> None:
    """0087 (ADR-F063): default_budget_profile is NULL or economy|balanced|generous."""
    from sqlalchemy.exc import IntegrityError

    from app.models.practice_area import PracticeArea

    ok = PracticeArea(
        key=f"bp-ok-{uuid.uuid4().hex[:8]}",
        name="Budget OK",
        unit_label="Matter",
        position=901,
        default_budget_profile="economy",
    )
    db_session.add(ok)
    await db_session.flush()  # a valid profile (and the seeded NULLs) must NOT raise

    bad = PracticeArea(
        key=f"bp-bad-{uuid.uuid4().hex[:8]}",
        name="Budget Bad",
        unit_label="Matter",
        position=902,
        default_budget_profile="lavish",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# org_skill_versions — org-authored skill propose/approve harness (0091, ADR-F067 D2/D3, B-2a)
# ---------------------------------------------------------------------------

_MIN_ORG_SKILL_VERSION_SQL = (
    "INSERT INTO org_skill_versions "
    "(slug, version_no, raw_yaml, body, frontmatter, content_hash, state) "
    "VALUES (:slug, :version_no, 'name: x', 'body', '{}'::jsonb, :hash, :state)"
)


@pytest.mark.integration
async def test_org_skill_versions_table_exists(db_session: AsyncSession) -> None:
    """0091 (ADR-F067 D2/D3): the org_skill_versions table exists with the expected columns."""
    cols = (
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'org_skill_versions'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {
        "id",
        "slug",
        "version_no",
        "raw_yaml",
        "body",
        "frontmatter",
        "content_hash",
        "source_user_skill_id",
        "author_user_id",
        "state",
        "proposed_at",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "revoked_by",
        "revoked_at",
    }.issubset(set(cols))
    # PK is (id).
    pk = (
        (
            await db_session.execute(
                text(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = 'org_skill_versions'::regclass AND i.indisprimary"
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(pk) == {"id"}


@pytest.mark.integration
async def test_org_skill_versions_state_check(db_session: AsyncSession) -> None:
    """state is constrained to the F067 D2 state machine vocabulary (0091 CHECK)."""
    from sqlalchemy.exc import IntegrityError

    slug = f"chk-probe-{uuid.uuid4().hex[:8]}"
    await db_session.execute(
        text(_MIN_ORG_SKILL_VERSION_SQL),
        {"slug": slug, "version_no": 1, "hash": "hash-1", "state": "proposed"},
    )
    await db_session.flush()  # a valid state must NOT raise
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(_MIN_ORG_SKILL_VERSION_SQL),
            {"slug": slug, "version_no": 2, "hash": "hash-2", "state": "bogus"},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_org_skill_versions_one_proposed_per_slug(db_session: AsyncSession) -> None:
    """ux_org_skill_versions_slug_proposed: at most one OPEN proposal per slug (0091,
    ADR-F067 D3 — a duplicate open proposal is the endpoint's 409 source)."""
    from sqlalchemy.exc import IntegrityError

    slug = f"uniq-proposed-{uuid.uuid4().hex[:8]}"
    await db_session.execute(
        text(_MIN_ORG_SKILL_VERSION_SQL),
        {"slug": slug, "version_no": 1, "hash": "hash-1", "state": "proposed"},
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(_MIN_ORG_SKILL_VERSION_SQL),
            {"slug": slug, "version_no": 2, "hash": "hash-2", "state": "proposed"},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_org_skill_versions_one_approved_per_slug(db_session: AsyncSession) -> None:
    """ux_org_skill_versions_slug_approved: at most one LIVE approved version per slug (0091,
    ADR-F067 D2 "approval pins bytes, not a row" — a prior approved row must be superseded
    in the SAME transaction as the new approval, or this index raises)."""
    from sqlalchemy.exc import IntegrityError

    slug = f"uniq-approved-{uuid.uuid4().hex[:8]}"
    await db_session.execute(
        text(_MIN_ORG_SKILL_VERSION_SQL),
        {"slug": slug, "version_no": 1, "hash": "hash-1", "state": "approved"},
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(_MIN_ORG_SKILL_VERSION_SQL),
            {"slug": slug, "version_no": 2, "hash": "hash-2", "state": "approved"},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_org_skill_versions_user_fks_set_null_on_user_delete(
    db_session: AsyncSession,
) -> None:
    """author_user_id / reviewed_by / revoked_by are all ON DELETE SET NULL — a version's
    provenance survives the referenced user's deletion (mirrors
    test_org_library_entries_adopted_by_set_null_on_user_delete; it is the org's approved
    artifact, not the individual's)."""
    user = User(
        email=f"org-skill-fk-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Org Skill FK User",
        hashed_password="x",
        is_admin=True,
    )
    db_session.add(user)
    await db_session.flush()

    slug = f"fk-probe-{uuid.uuid4().hex[:8]}"
    await db_session.execute(
        text(
            "INSERT INTO org_skill_versions "
            "(slug, version_no, raw_yaml, body, frontmatter, content_hash, state, "
            " author_user_id, reviewed_by, revoked_by) "
            "VALUES (:slug, 1, 'name: x', 'body', '{}'::jsonb, 'hash-1', 'revoked', "
            " :uid, :uid, :uid)"
        ),
        {"slug": slug, "uid": user.id},
    )
    await db_session.flush()
    await db_session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})
    await db_session.flush()

    row = (
        await db_session.execute(
            text(
                "SELECT author_user_id, reviewed_by, revoked_by FROM org_skill_versions "
                "WHERE slug = :slug"
            ),
            {"slug": slug},
        )
    ).one()
    assert row.author_user_id is None
    assert row.reviewed_by is None
    assert row.revoked_by is None
    await db_session.rollback()


# ---------------------------------------------------------------------------
# practice_area_knowledge_bases + org_library_entries 'knowledge' kind
# (0092, ADR-F067 D1, B-3)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_practice_area_knowledge_bases_table_exists(db_session: AsyncSession) -> None:
    """0092 (ADR-F067 D1): practice_area_knowledge_bases exists with the expected columns
    and a composite PK of (practice_area_id, knowledge_base_id) — mirrors
    test_practice_area_tool_groups_table_and_seed's shape for practice_area_playbooks'
    sibling join table."""
    cols = (
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'practice_area_knowledge_bases'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {"practice_area_id", "knowledge_base_id", "attached_at"}.issubset(set(cols))
    pk = (
        (
            await db_session.execute(
                text(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = 'practice_area_knowledge_bases'::regclass "
                    "AND i.indisprimary"
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(pk) == {"practice_area_id", "knowledge_base_id"}


@pytest.mark.integration
async def test_practice_area_knowledge_bases_cascade_on_area_delete(
    db_session: AsyncSession,
) -> None:
    """Deleting a practice area CASCADE-drops its knowledge-base bindings (FK ON DELETE
    CASCADE) — mirrors test_practice_area_tool_groups_cascade_on_area_delete."""
    owner = User(
        email=f"kb-area-cascade-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
    )
    db_session.add(owner)
    await db_session.flush()
    kb = KnowledgeBase(owner_id=owner.id, name="area-cascade-kb")
    db_session.add(kb)
    await db_session.flush()

    await db_session.execute(
        text(
            "INSERT INTO practice_areas (key, name, unit_label, position) "
            "VALUES ('kb-area-cascade-test', 'KB Area Cascade', 'Matter', 999)"
        )
    )
    area_id = (
        await db_session.execute(
            text("SELECT id FROM practice_areas WHERE key = 'kb-area-cascade-test'")
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO practice_area_knowledge_bases (practice_area_id, knowledge_base_id) "
            "VALUES (:aid, :kid)"
        ),
        {"aid": area_id, "kid": kb.id},
    )
    await db_session.flush()
    await db_session.execute(text("DELETE FROM practice_areas WHERE id = :aid"), {"aid": area_id})
    await db_session.flush()
    remaining = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM practice_area_knowledge_bases WHERE practice_area_id = :aid"
            ),
            {"aid": area_id},
        )
    ).scalar_one()
    assert remaining == 0
    await db_session.rollback()


@pytest.mark.integration
async def test_practice_area_knowledge_bases_cascade_on_kb_delete(
    db_session: AsyncSession,
) -> None:
    """Deleting a knowledge base CASCADE-drops its area bindings (FK ON DELETE CASCADE) —
    the join table's other FK, not exercised by the area-delete cascade test above."""
    owner = User(
        email=f"kb-kb-cascade-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
    )
    db_session.add(owner)
    await db_session.flush()
    kb = KnowledgeBase(owner_id=owner.id, name="kb-cascade-kb")
    db_session.add(kb)
    await db_session.flush()

    await db_session.execute(
        text(
            "INSERT INTO practice_areas (key, name, unit_label, position) "
            "VALUES ('kb-kb-cascade-test', 'KB KB Cascade', 'Matter', 999)"
        )
    )
    area_id = (
        await db_session.execute(
            text("SELECT id FROM practice_areas WHERE key = 'kb-kb-cascade-test'")
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO practice_area_knowledge_bases (practice_area_id, knowledge_base_id) "
            "VALUES (:aid, :kid)"
        ),
        {"aid": area_id, "kid": kb.id},
    )
    await db_session.flush()
    await db_session.execute(text("DELETE FROM knowledge_bases WHERE id = :kid"), {"kid": kb.id})
    await db_session.flush()
    remaining = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM practice_area_knowledge_bases WHERE knowledge_base_id = :kid"
            ),
            {"kid": kb.id},
        )
    ).scalar_one()
    assert remaining == 0
    await db_session.rollback()


@pytest.mark.integration
async def test_org_library_entries_kind_check_admits_knowledge(
    db_session: AsyncSession,
) -> None:
    """0092 widens chk_org_library_entries_kind to admit 'knowledge' (ADR-F067 D1) while
    still rejecting an unknown kind — mirrors test_org_library_entries_kind_check for the
    post-0092 CHECK definition."""
    from sqlalchemy.exc import IntegrityError

    await db_session.execute(
        text(
            "INSERT INTO org_library_entries (capability_kind, capability_key) "
            "VALUES ('knowledge', 'chk-probe-knowledge')"
        )
    )
    await db_session.flush()  # 'knowledge' must NOT raise post-0092
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO org_library_entries (capability_kind, capability_key) "
                "VALUES ('bogus', 'chk-probe-bogus-2')"
            )
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_matter_capability_toggles_kind_check_admits_knowledge(
    db_session: AsyncSession,
) -> None:
    """0092 widens chk_matter_capability_toggles_kind to admit 'knowledge' (ADR-F067 D1,
    B-3 — the lawyer's per-matter panel toggles the new kind) while still rejecting an
    unknown kind — mirrors test_org_library_entries_kind_check_admits_knowledge."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Project

    user = User(email=f"kb-toggle-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()
    project = Project(
        owner_id=user.id, name="kb-toggle-chk-probe", slug=f"kbtog-{uuid.uuid4().hex[:6]}"
    )
    db_session.add(project)
    await db_session.flush()
    project_id = project.id
    await db_session.execute(
        text(
            "INSERT INTO matter_capability_toggles "
            "(project_id, capability_kind, capability_key, enabled) "
            "VALUES (:pid, 'knowledge', 'chk-probe-knowledge', true)"
        ),
        {"pid": project_id},
    )
    await db_session.flush()  # 'knowledge' must NOT raise post-0092
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO matter_capability_toggles "
                "(project_id, capability_kind, capability_key, enabled) "
                "VALUES (:pid, 'bogus', 'chk-probe-bogus', true)"
            ),
            {"pid": project_id},
        )
        await db_session.flush()
    await db_session.rollback()
