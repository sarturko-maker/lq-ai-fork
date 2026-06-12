"""WorkProductAttribution ORM model — PRD §3.3 (Wave C).

One row per model-generated artifact (assistant message). Captures
the chain-of-custody metadata the in-house legal context requires:
who asked, when, what tier the request routed to, which provider /
model answered, what skills were in scope, and a SHA-256 of the
output content for tamper-evidence.

Included in the GDPR Article 20 export bundle per PRD §5.3 so the
user can hand the chain of custody to a third party (e.g., trial
counsel, an auditor).

Schema enforced by migration 0017:
* ``message_id`` UNIQUE — exactly one attribution per assistant message.
* CASCADE on user/chat/message delete (GDPR Article 17).
* SET NULL on project delete (the attribution survives the project's
  removal — the trail is what matters; the project context can be
  reconstructed from the chat link).
* CHECK constraint on routed_inference_tier ∈ [1,5] or null.
* Indexes on (user_id, timestamp DESC) for the "my work product"
  surface and on (chat_id) for the per-chat lookup the citation
  panel will need in M2.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkProductAttribution(Base):
    """One assistant-message attribution row — see PRD §3.3 data model."""

    __tablename__ = "work_product_attribution"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "messages.id",
            ondelete="CASCADE",
            name="fk_work_product_attribution_message",
        ),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_work_product_attribution_user",
        ),
        nullable=False,
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chats.id",
            ondelete="CASCADE",
            name="fk_work_product_attribution_chat",
        ),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_work_product_attribution_project",
        ),
        nullable=True,
    )

    routed_inference_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Free-form model-version string. M1 typically mirrors ``model``
    (the providers we route to don't surface a separate version per
    request); a future task may pull a provider-side version stamp."""

    skill_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    """Skill names (slugs) applied during prompt assembly for this
    message. Empty when no skill was attached."""

    playbook_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    """Reserved for M3 Playbook execution. Always null in M1."""

    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    """SHA-256 (hex) of the assistant message content at the moment of
    persistence. Tamper-evidence — a future M2+ cryptographic
    timestamping layer chains these into a Merkle log."""

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<WorkProductAttribution id={self.id} message={self.message_id} "
            f"user={self.user_id} tier={self.routed_inference_tier}>"
        )


__all__ = ["WorkProductAttribution"]
