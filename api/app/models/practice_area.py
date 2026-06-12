"""Practice-area ORM model — F1-S2 (fork, ADR-F002).

ADR-F002 makes practice areas **backend entities from day one**
(frontend-only grouping was explicitly rejected: memory scoping, agent
config, audit slicing, and tool grants need a row to hang off). F1-S2
ships the MINIMAL shape the cockpit shell renders — identity, display
name, unit-of-work noun, honest configured state, ordering — seeded with
the standard areas by migration ``0053_practice_areas.py``.

The real config vocabulary (area profile markdown, bound skills /
playbooks / MCP servers, default tier floor, ``projects.practice_area_id``,
admin API) is F1-S3 scope; it EXTENDS this table rather than replacing it.

``configured`` is the F002 inert-card switch: unconfigured areas render
as inert cards in the cockpit (no composer, no rail, no matter creation
under them — the demo-tool rule applies to UI). In S2 it is seed data —
Commercial is configured because it fronts the existing generic matter
agent; S3 derives it from real area config.

``key`` is the stable machine identifier (used in cockpit URL state,
audit slicing later). It is presentation-plus-config identity — per the
MILESTONES pre-F1 guard it must never be written into other stored rows
until S3's ``projects.practice_area_id`` FK exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PracticeArea(Base):
    """One practice area — the cockpit's left-rail unit (ADR-F002)."""

    __tablename__ = "practice_areas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # The unit-of-work noun the UI renders ("Matter" / "Programme" / "Deal")
    # — data, not code, per ADR-F004 (declarative area shapes, one renderer).
    unit_label: Mapped[str] = mapped_column(Text, nullable=False)
    configured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<PracticeArea key={self.key!r} configured={self.configured}>"
