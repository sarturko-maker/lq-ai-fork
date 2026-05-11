"""User and session models — per docs/db-schema.md §`users`, §`user_sessions`."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """A LQ.AI user. Auth-owning per ADR 0002.

    `email` is CITEXT (case-insensitive) so login is not surprised by case.
    `recovery_codes` are bcrypt-hashed (the hashes, not the plaintext codes).
    `deletion_scheduled_at` supports the GDPR Article 17 grace-period delete
    flow per PRD §5.3.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # B2 — first-run admin is created with must_change_password=TRUE; the
    # `/auth/change-password` endpoint flips it back to FALSE once the
    # operator sets a permanent password. See docs/M1-IMPLEMENTATION-ORDER.md
    # Task B2 and migration 0002.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    totp_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    recovery_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # PRD §3.2 — Enhance Prompt reasoning visibility. ``disclosure`` is the
    # spec default (reasoning collapsed behind a "why these changes?"
    # toggle). ``always_show`` makes reasoning visible by default;
    # ``on_request`` hides it until the user opens the skill inspector.
    # The CHECK constraint enforces the enum at the DB layer.
    reasoning_visibility: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'disclosure'")
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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class UserSession(Base):
    """Refresh token session. Access tokens are stateless JWTs (not stored).

    `refresh_token_hash` stores the bcrypt hash of the refresh token. The
    token itself is returned to the client at login/refresh time and never
    persisted in the clear.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_sessions_user_id"),
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id} revoked={self.revoked_at is not None}>"
