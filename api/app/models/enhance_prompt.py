"""EnhancePromptInteraction ORM model — PRD §3.2 (Wave A).

Telemetry table behind the Enhance Prompt UX. One row per invocation
of the Enhance Prompt skill — captured at the moment the model returns
its expansion, then updated post-hoc with ``used`` and
``edited_before_use`` once the user decides what to do with the
preview.

The row also carries the routed inference annotation (tier, provider,
model, tokens) so improvement work can identify which (model, tier)
combinations produce useful expansions and which produce skip
decisions or low-quality output.

Schema is enforced by migration 0015:
* ``user_id`` CASCADE on user delete (per GDPR Article 17 — D6).
* ``chat_id`` SET NULL on chat delete (telemetry survives the
  originating chat being archived).
* ``chk_enhance_prompt_skip_has_reason`` — if expansion was skipped
  (``expansion_applied=False``), ``skip_reason`` must be non-null.
* ``chk_enhance_prompt_tier_range`` — tier 1-5 or null.
* Index on ``(user_id, created_at DESC)`` for the "my recent
  enhancements" surface a future preferences page might need.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnhancePromptInteraction(Base):
    """One Enhance Prompt invocation — see :func:`app.api.enhance_prompt`."""

    __tablename__ = "enhance_prompt_interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_enhance_prompt_interactions_user",
        ),
        nullable=False,
    )
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chats.id",
            ondelete="SET NULL",
            name="fk_enhance_prompt_interactions_chat",
        ),
        nullable=True,
    )
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    expansion_applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expanded_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    """The expanded prompt the user sees in the review screen. Null when
    the skill returned a skip decision (``expansion_applied=False``)."""

    reasoning: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    """Array of plain-language bullets per the SKILL.md output schema.
    Empty list when skipped."""

    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    """The reason from the skill's skip-conditions list. Non-null when
    ``expansion_applied=False`` (enforced by DB CHECK)."""

    used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    """Updated when the user clicks Submit on the review screen (or when
    the application auto-submits an expansion the user didn't touch).
    Stays ``false`` if the user skips or backs out."""

    edited_before_use: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    """Updated when the user modifies ``expanded_output`` in the review
    screen before submitting. Used to surface which model/skill
    combinations produce expansions the user accepts versus rewrites."""

    routed_inference_tier: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    routed_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    routed_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<EnhancePromptInteraction id={self.id} user={self.user_id} "
            f"applied={self.expansion_applied} used={self.used}>"
        )


__all__ = ["EnhancePromptInteraction"]
