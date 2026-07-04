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


class PracticeAreaPlaybook(Base):
    """Many-to-many join: practice area ↔ playbook (availability binding) — ADR-F054.

    Mirrors :class:`PracticeAreaSkill`, but ``playbook_id`` IS a real FK (playbooks
    are SQL rows, unlike filesystem-canonical skills). A playbook bound here is
    AVAILABLE to matters under the area; the lawyer toggles it on/off per matter via
    ``matter_capability_toggles``. The legacy playbook EXECUTOR is frozen (CLAUDE.md)
    — the deep agent reuses only the playbook DATA (the firm's preferred positions),
    injected read-only as the "Practice Playbook" memory tier. Hard-deleting a
    playbook CASCADE-drops its bindings (and a soft-delete hides it from the
    inventory), so no dead toggle rows accumulate.
    """

    __tablename__ = "practice_area_playbooks"
    __table_args__ = (
        PrimaryKeyConstraint("practice_area_id", "playbook_id", name="pk_practice_area_playbooks"),
    )

    practice_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "practice_areas.id", ondelete="CASCADE", name="fk_practice_area_playbooks_area_id"
        ),
        nullable=False,
    )
    playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "playbooks.id", ondelete="CASCADE", name="fk_practice_area_playbooks_playbook_id"
        ),
        nullable=False,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<PracticeAreaPlaybook area_id={self.practice_area_id} playbook_id={self.playbook_id}>"
        )


class PracticeAreaToolGroup(Base):
    """Many-to-many join: practice area ↔ tool-group NAME (ADR-F062, SETUP-4a).

    The area↔tool-group AVAILABILITY binding (config-hierarchy Level 1). ``group_key``
    is TEXT, not a FK — a tool group is CODE-canonical (an entry in
    ``app.agents.capabilities.TOOL_GROUP_REGISTRY``; its grant set is the group's
    ``*_TOOL_NAMES`` frozenset). This row names ONLY *which* group is available to an
    area; what the name resolves to (the grant set, the builder, the ledger, the
    doctrine) stays code. A row naming a group absent from the registry is dropped at
    resolve time (registry is source of truth — the same drift posture as
    ``PracticeAreaSkill``), so no dead row can ever mint a grant. Supersedes ADR-F054
    D1 (tool availability was a code map; SETUP-4a makes it DATA while keeping grants
    code). Mirrors :class:`PracticeAreaSkill`; the composition point iterates the
    REGISTRY order filtered by this area's rows, so ordering stays code-canonical.
    """

    __tablename__ = "practice_area_tool_groups"
    __table_args__ = (
        PrimaryKeyConstraint("practice_area_id", "group_key", name="pk_practice_area_tool_groups"),
        CheckConstraint(
            "char_length(group_key) BETWEEN 1 AND 200",
            name="chk_practice_area_tool_groups_key_len",
        ),
    )

    practice_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "practice_areas.id", ondelete="CASCADE", name="fk_practice_area_tool_groups_area_id"
        ),
        nullable=False,
    )
    group_key: Mapped[str] = mapped_column(Text, nullable=False)
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<PracticeAreaToolGroup area_id={self.practice_area_id} group_key={self.group_key!r}>"
        )


class DeploymentCapabilityToggle(Base):
    """Deployment-wide (Level 0) capability on/off — org-admin owned (ADR-F062, SETUP-4a).

    The top of the config hierarchy: the org-admin narrows what the whole deployment
    offers. Mirrors :class:`~app.models.project.MatterCapabilityToggle` MINUS
    ``project_id`` (this is not per-matter). SPARSE — a row exists ONLY where the admin
    disabled a capability; ``enabled=true`` rows are inert (absence already means
    available), so there is NO seed.

    Level 0 only ever **narrows**: an ``enabled=false`` row removes that capability
    (``skill`` / ``tool`` group / ``playbook``) from EVERY area's AVAILABLE set at the one
    ``build_area_inventory`` chokepoint — the panel never shows it, composition never
    builds it, skills never wire, the playbook tier never renders. ``capability_key`` is
    TEXT (skill name / tool-group key / ``playbook_id::text``), validated against the
    registry/DB at the PATCH boundary so no dead row lands. ``set_by`` records the human
    who last set it (SET NULL on user delete — it is the deployment's state, not the
    individual's).
    """

    __tablename__ = "deployment_capability_toggles"
    __table_args__ = (
        PrimaryKeyConstraint(
            "capability_kind", "capability_key", name="pk_deployment_capability_toggles"
        ),
        CheckConstraint(
            "capability_kind IN ('skill', 'tool', 'playbook')",
            name="chk_deployment_capability_toggles_kind",
        ),
        CheckConstraint(
            "char_length(capability_key) BETWEEN 1 AND 200",
            name="chk_deployment_capability_toggles_key_len",
        ),
    )

    capability_kind: Mapped[str] = mapped_column(Text, nullable=False)
    capability_key: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    set_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_deployment_capability_toggles_set_by"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<DeploymentCapabilityToggle kind={self.capability_kind!r} "
            f"key={self.capability_key!r} enabled={self.enabled}>"
        )
