"""SavedPrompt ORM model — Task D7.

Backs the ``saved_prompts`` table per migration 0011. Per-user saved
prompt fragments (PRD §9 DE-013 / Issue 04) — a lighter-weight
alternative to skills for personal text reuse.

Ownership is by ``user_id`` with ``ON DELETE CASCADE`` — when a user
account is deleted, their saved prompts go with it (no orphan rows in
audit-log territory). Matches the GDPR Article 17 deletion path
implemented in D6.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SavedPrompt(Base):
    """A user's saved prompt fragment — name + body + optional tags."""

    __tablename__ = "saved_prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_saved_prompts_user"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("ARRAY[]::text[]"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<SavedPrompt id={self.id} user_id={self.user_id} "
            f"name={self.name!r} updated_at={self.updated_at}>"
        )
