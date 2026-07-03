"""Single-use user-lifecycle tokens — SETUP-3a (ADR-F061), migration 0085.

One table backs both the invite and password-reset flows (``purpose``). Only
the domain-separated HMAC-SHA256 verifier is stored (``token_hmac``); the
opaque plaintext is returned once (in the email link / invite-create response)
and never persisted (ADR-F059 token-at-rest pattern). Single-use is enforced by
an atomic ``consumed_at`` write under ``SELECT ... FOR UPDATE`` in
``app.auth_tokens``; ``revoked_at`` supports resend/revoke.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserAuthToken(Base):
    """A single-use, TTL-bounded lifecycle token (invite or password reset).

    ``purpose`` selects the flow. For ``invite`` the target is ``email`` +
    ``role``; for ``password_reset`` the target is ``user_id``. The DB CHECK
    ``chk_user_auth_tokens_shape`` enforces that shape. ``token_hmac`` is the
    only representation of the secret at rest.
    """

    __tablename__ = "user_auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_auth_tokens_user_id"),
        nullable=True,
    )
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_user_auth_tokens_created_by"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<UserAuthToken id={self.id} purpose={self.purpose!r} "
            f"consumed={self.consumed_at is not None} revoked={self.revoked_at is not None}>"
        )
