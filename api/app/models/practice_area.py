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
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PracticeArea(Base):
    """One practice area — the cockpit's left-rail unit AND the agent
    identity record (ADR-F002).

    F1-S3 (ADR-F004/F010) adds the config vocabulary: ``profile_md``
    (folded into the agent system prompt), ``default_tier_floor`` (combined
    with the matter floor via ``min()`` — the gateway enforces it), and
    ``agent_config`` — declarative shape data consumed by ONE renderer:
    ``subagents`` (declarative SubAgent specs; per ADR-F010 they NEVER carry
    a ``model`` key — that would bypass the gateway), plus by-reference
    ``playbooks``/``mcp_servers`` (ids/names only, NO credentials —
    NORTH-STAR invariant 3; recorded for forward config, not consumed yet).
    """

    __tablename__ = "practice_areas"
    __table_args__ = (
        CheckConstraint(
            "default_tier_floor IS NULL OR (default_tier_floor BETWEEN 1 AND 5)",
            name="chk_practice_areas_tier_range",
        ),
    )

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
    configured: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # F1-S3 config vocabulary.
    profile_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_tier_floor: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    agent_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<PracticeArea key={self.key!r} configured={self.configured}>"


class PracticeAreaSkill(Base):
    """Many-to-many join: practice area ↔ skill name.

    ``skill_name`` is text, not a FK — skills are filesystem-canonical per
    ADR-0004 (no ``skills`` SQL table). The admin handler validates the name
    exists in the in-memory registry before insert; the renderer skips any
    name the registry no longer knows (registry is source of truth). Mirrors
    ``project_skills``.
    """

    __tablename__ = "practice_area_skills"
    __table_args__ = (
        PrimaryKeyConstraint("practice_area_id", "skill_name", name="pk_practice_area_skills"),
        CheckConstraint(
            "char_length(skill_name) > 0 AND char_length(skill_name) <= 200",
            name="chk_practice_area_skills_name_len",
        ),
    )

    practice_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practice_areas.id", ondelete="CASCADE", name="fk_practice_area_skills_area_id"),
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(String, nullable=False)
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<PracticeAreaSkill area_id={self.practice_area_id} skill_name={self.skill_name!r}>"
