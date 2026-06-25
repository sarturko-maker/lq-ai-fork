"""EditorLock ORM model — WOPI lock state (libreoffice-editor Slice 2, ADR-F047).

One row per file that an in-app editor session has locked, holding the opaque
WOPI lock string and its expiry. The WOPI host (``app.api.wopi``) is the only
reader/writer; the lock state machine lives in ``app.schemas.wopi``.

WOPI semantics this row backs (per the protocol):

* **One lock per file** — the lock is on the document, not the user; an UNLOCK
  may legitimately arrive on a different access token than the LOCK did, so the
  natural primary key is ``file_id`` (no owner column).
* **TTL** — Collabora refreshes the lock periodically; a lock not refreshed
  within ``expires_at`` is treated as absent (the protocol's 30-minute timeout).
  We persist the timeout rather than rely on a sweep so a stale row never blocks
  a fresh open.
* **Lock value** — an opaque ASCII string up to 1024 chars
  (``SupportsExtendedLockLength``); stored verbatim and compared verbatim, never
  interpreted. Hence ``Text``.

``ON DELETE CASCADE`` on the file FK so soft-/hard-deleting a file never strands
its lock row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EditorLock(Base):
    """A WOPI lock held on a single file by an in-app editor session."""

    __tablename__ = "editor_locks"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE", name="fk_editor_locks_file_id"),
        primary_key=True,
    )
    lock_value: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<EditorLock file_id={self.file_id} "
            f"lock_value_len={len(self.lock_value)} expires_at={self.expires_at}>"
        )
