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
        CheckConstraint(
            "default_budget_profile IS NULL "
            "OR default_budget_profile IN ('economy', 'balanced', 'generous')",
            name="chk_practice_areas_budget_profile",
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
    # SETUP-5a (ADR-F063): the area's default budget_profile for new runs.
    # NULL = no area default (inherit the deployment default / balanced).
    default_budget_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # HITL-1 (ADR-F071, migration 0093): the area's stop-and-ask policy —
    # ``{"<granted tool name>": true}`` compiled at composition into deepagents'
    # ``interrupt_on`` (intersected with the run's actual grant set). Mirrors
    # ``agent_config`` exactly; the default ``{}`` is the zero-config invariant (no
    # HITL middleware attached). No API write surface yet (HITL-3 adds the admin card
    # + a 422 unknown-name guard); no model CheckConstraint (the shape is validated at
    # write time, not by the DB).
    hitl_policy: Mapped[dict[str, Any]] = mapped_column(
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
    — the deep agent reuses only the playbook DATA (the company's preferred positions),
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


class PracticeAreaKnowledgeBase(Base):
    """Many-to-many join: practice area ↔ knowledge collection (availability binding) —
    ADR-F067 D1, migration 0092.

    Mirrors :class:`PracticeAreaPlaybook`: ``knowledge_base_id`` IS a real FK (knowledge
    collections are SQL rows). A collection bound here is AVAILABLE to the area's runs
    ONLY if it is also adopted into the Org Library (kind ``knowledge``,
    ``org_library_entries``) — the same ``build_area_inventory`` intersection every
    other kind goes through (ADR-F065 D3, no second resolution path). Unlike a skill or
    playbook, a knowledge collection's content never becomes instructions: it reaches
    the model only as fenced RETRIEVED-DATA through the guarded ``search_knowledge``
    tool, so adoption + binding IS the entire control (D1 — no propose/approve harness
    needed for this kind). Hard-deleting a knowledge base CASCADE-drops its bindings; a
    soft-delete (``archived_at``) leaves the binding in place but the inventory skips
    archived collections at resolve time (same drift-drop posture as a deleted
    playbook).
    """

    __tablename__ = "practice_area_knowledge_bases"
    __table_args__ = (
        PrimaryKeyConstraint(
            "practice_area_id", "knowledge_base_id", name="pk_practice_area_knowledge_bases"
        ),
    )

    practice_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "practice_areas.id",
            ondelete="CASCADE",
            name="fk_practice_area_knowledge_bases_area_id",
        ),
        nullable=False,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "knowledge_bases.id",
            ondelete="CASCADE",
            name="fk_practice_area_knowledge_bases_kb_id",
        ),
        nullable=False,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<PracticeAreaKnowledgeBase area_id={self.practice_area_id} "
            f"knowledge_base_id={self.knowledge_base_id}>"
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


class OrgLibraryEntry(Base):
    """One capability the organisation has ADOPTED — the Org Library (ADR-F065, STORE-1).

    Replaces the Level-0 disable-only ``DeploymentCapabilityToggle`` (ADR-F062, superseded).
    Adopt-in polarity: a capability (``skill`` name / ``tool`` group key /
    ``playbook_id::text`` / ``knowledge_base_id::text``) is AVAILABLE to any area's runs
    ONLY if a row here adopts it — absence is the single off-state ("not in your
    Library"). ``build_area_inventory`` intersects an area's bindings with Library
    membership at the one fail-closed chokepoint (D3); bind-time validation rejects
    binding a non-adopted capability (D4). Grants stay CODE — the ADR-F062 invariant is
    untouched; the Library only NARROWS availability, adopt-in instead of disable-out
    (D1). ``knowledge`` (migration 0092, ADR-F067 D1) is the fourth kind — a knowledge
    collection needs no propose/approve harness of its own since its content is fenced
    RETRIEVED-DATA, never instructions; adoption + binding is the entire control.

    ``enabled`` is intentionally ABSENT (unlike the toggle it replaces): membership IS the
    state, so ``GET /admin/capabilities`` reports ``enabled`` as a deprecated alias for
    ``in_library`` during the transition. ``adopted_by`` records the admin who adopted it
    (SET NULL on user delete — it is the org's state, not the individual's). ``capability_key``
    is TEXT, validated against the registry/DB at the adopt boundary so no dead row lands.
    """

    __tablename__ = "org_library_entries"
    __table_args__ = (
        PrimaryKeyConstraint("capability_kind", "capability_key", name="pk_org_library_entries"),
        CheckConstraint(
            "capability_kind IN ('skill', 'tool', 'playbook', 'knowledge')",
            name="chk_org_library_entries_kind",
        ),
        CheckConstraint(
            "char_length(capability_key) BETWEEN 1 AND 200",
            name="chk_org_library_entries_key_len",
        ),
    )

    capability_kind: Mapped[str] = mapped_column(Text, nullable=False)
    capability_key: Mapped[str] = mapped_column(Text, nullable=False)
    adopted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_org_library_entries_adopted_by"),
        nullable=True,
    )
    adopted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<OrgLibraryEntry kind={self.capability_kind!r} key={self.capability_key!r}>"
