"""files.parent_file_id / files.is_snapshot — document lineage columns (ADR-F066, mig 0089)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.user import User


def _file(owner_id: uuid.UUID, filename: str, **extra: Any) -> File:
    return File(
        owner_id=owner_id,
        filename=filename,
        mime_type="application/octet-stream",
        size_bytes=1,
        hash_sha256="0" * 64,
        storage_path=f"lineage-{filename}",
        **extra,
    )


@pytest.mark.integration
async def test_file_lineage_defaults_no_parent_not_snapshot(db_session: AsyncSession) -> None:
    """An original upload carries no lineage: parent NULL, is_snapshot false."""
    user = User(email="lineage-default@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    row = _file(user.id, "original.docx")
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)
    assert row.parent_file_id is None
    assert row.is_snapshot is False


@pytest.mark.integration
async def test_file_lineage_round_trip(db_session: AsyncSession) -> None:
    """parent_file_id + is_snapshot persist and read back (ADR-F066)."""
    user = User(email="lineage-rt@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    parent = _file(user.id, "contract.docx")
    db_session.add(parent)
    await db_session.flush()
    child = _file(user.id, "contract (redlined).docx", parent_file_id=parent.id)
    snap = _file(user.id, "contract (agent draft).docx", parent_file_id=parent.id, is_snapshot=True)
    db_session.add_all([child, snap])
    await db_session.flush()

    fetched_child = (await db_session.execute(select(File).where(File.id == child.id))).scalar_one()
    assert fetched_child.parent_file_id == parent.id
    assert fetched_child.is_snapshot is False

    fetched_snap = (await db_session.execute(select(File).where(File.id == snap.id))).scalar_one()
    assert fetched_snap.parent_file_id == parent.id
    assert fetched_snap.is_snapshot is True
