"""Migration 0020 — messages.kind discriminator.

Verifies the LQ.AI-specific ``messages.kind`` column exists, is NOT NULL
TEXT, is gated by a CHECK constraint over ``{user, ai, refusal, system}``,
and is covered by an index.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"mk-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Messages Kind Test User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def sample_chat(db_session: AsyncSession, db_user: User) -> Chat:
    chat = Chat(owner_id=db_user.id, title="kind discriminator test chat")
    db_session.add(chat)
    await db_session.flush()
    return chat


async def test_kind_column_exists_with_check_constraint(db_session: AsyncSession) -> None:
    """Column exists, is non-nullable text."""
    result = await db_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name='messages' AND column_name='kind'"
        )
    )
    row = result.first()
    assert row is not None, "messages.kind column should exist"
    assert row.data_type == "text"
    assert row.is_nullable == "NO"


async def test_kind_check_constraint_rejects_bogus(
    db_session: AsyncSession, sample_chat: Chat
) -> None:
    """Inserting an out-of-enum kind value raises a CHECK violation."""
    with pytest.raises(Exception):  # CheckViolation wraps into IntegrityError
        await db_session.execute(
            text(
                "INSERT INTO messages (chat_id, role, kind, content) "
                "VALUES (:cid, 'user', 'bogus', 'x')"
            ),
            {"cid": str(sample_chat.id)},
        )
        await db_session.flush()


async def test_kind_index_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname='idx_messages_kind'")
    )
    assert result.scalar() == 1
