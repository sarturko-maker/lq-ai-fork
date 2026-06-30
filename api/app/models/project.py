"""Project ORM models — per docs/db-schema.md §`projects` and PRD §3.11.

A Project is a user-curated container that scopes a set of files,
skills, and a free-form context document around a single matter
(deal, counterparty, regulatory question, policy refresh). Chats
inside a Project (C3) inherit the Project's attached files and skills;
Projects in M1 are file/skill containers with a context document and
the privileged-tier constraint.

Lifecycle (M1):

* Created on `POST /api/v1/projects` (Task C7).
* Files attached/detached via `POST/DELETE /api/v1/projects/{id}/files`.
* Skills attached/detached via `POST/DELETE /api/v1/projects/{id}/skills`.
  Skills are referenced by name (text) — there is no `skills` SQL
  table per ADR 0004 (skills are filesystem-canonical).
* Soft-deleted via `DELETE /api/v1/projects/{id}` — flips
  `archived_at` from NULL to `now()`. Hard-delete is D6 territory
  (per-user export+delete).

`privileged` and `minimum_inference_tier` carry a CHECK constraint at
the DB level (`chk_projects_privileged_implies_tier`) enforcing that
`privileged=true` implies a non-NULL `minimum_inference_tier`. The API
also validates this; defense-in-depth.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    """A matter-scoped container per PRD §3.11.

    `slug` is unique-per-owner within the active set (an archived
    project's slug can be reused). The DB enforces uniqueness via a
    partial UNIQUE index `idx_projects_slug_owner_active`.

    `context_md` is the free-form Markdown context document the user
    edits to capture matter knowledge ("we are the customer; counterparty
    is Acme; their counsel is Smith Crowell; we agreed to a 12-month
    liability cap last round").

    `archived_at` is the soft-delete column — set on `DELETE`, NULL
    means active.
    """

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "minimum_inference_tier IS NULL OR (minimum_inference_tier BETWEEN 1 AND 5)",
            name="chk_projects_tier_range",
        ),
        CheckConstraint(
            "(privileged = false) OR (minimum_inference_tier IS NOT NULL)",
            name="chk_projects_privileged_implies_tier",
        ),
        CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_projects_name_len",
        ),
        CheckConstraint(
            "char_length(slug) > 0 AND char_length(slug) <= 80",
            name="chk_projects_slug_len",
        ),
        # F1-S3: sandbox rows are not matters (the matters rollup excludes
        # them) — they must not file under a practice area.
        CheckConstraint(
            "NOT (is_sandbox AND practice_area_id IS NOT NULL)",
            name="chk_projects_sandbox_no_area",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_projects_owner_id"),
        nullable=False,
    )
    # F1-S3: which practice area this matter files under (ADR-F002). Nullable
    # — legacy/unfiled matters keep NULL (no backfill); SET NULL on area
    # delete so the matter survives. The CHECK above forbids it on sandboxes.
    practice_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practice_areas.id", ondelete="SET NULL", name="fk_projects_practice_area_id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    privileged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    minimum_inference_tier: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_sandbox: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    ensemble_verification: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
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
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Project id={self.id} owner_id={self.owner_id} "
            f"name={self.name!r} slug={self.slug!r} "
            f"privileged={self.privileged} archived={self.archived_at is not None}>"
        )


class ProjectFile(Base):
    """Many-to-many join: project ↔ file.

    Both ends `ON DELETE CASCADE` — dropping a project removes its
    attachments; dropping a file removes the join rows referencing it.
    The composite (project_id, file_id) is the primary key.
    """

    __tablename__ = "project_files"
    __table_args__ = (PrimaryKeyConstraint("project_id", "file_id", name="pk_project_files"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_project_files_project_id"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE", name="fk_project_files_file_id"),
        nullable=False,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return f"<ProjectFile project_id={self.project_id} file_id={self.file_id}>"


class ProjectSkill(Base):
    """Many-to-many join: project ↔ skill name.

    `skill_name` is text, not a FK — skills are filesystem-canonical
    per ADR 0004 (no `skills` SQL table). The handler validates the
    name exists in the in-memory registry before insert.
    """

    __tablename__ = "project_skills"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "skill_name", name="pk_project_skills"),
        CheckConstraint(
            "char_length(skill_name) > 0 AND char_length(skill_name) <= 200",
            name="chk_project_skills_name_len",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_project_skills_project_id"),
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(String, nullable=False)
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return f"<ProjectSkill project_id={self.project_id} skill_name={self.skill_name!r}>"


# C3a (ADR-F042): the unit-of-work memory tier — the auto-maintained "matter wiki".
# The wiki itself is the existing free-form ``projects.context_md`` (rewritten in
# place by the agent's ``update_matter_memory`` tool); THIS table is the durable
# spine around it: prior-version snapshots (undo substrate) and the
# human-authenticated pinned corrections the agent's auto-curation may never touch.
#
# Three ``kind``s share one table. C3b-1 added ``'fact'`` and the typed bi-temporal
# columns (author/source_citation/fact_type/valid_at/invalid_at/superseded_by) as
# additive-nullable with NO backfill: correction/snapshot rows keep ``body_md`` and
# leave the typed columns NULL; ``fact`` rows reuse ``body_md`` for the statement and
# populate the typed columns. The kinds:
#   * ``correction``    — a lawyer's correction. ``trust='human-pinned'``, written
#     ONLY through the authenticated human endpoint (``author`` = the session user).
#     No agent-granted tool mints one — an agent-asserted "the lawyer said X" is
#     forgeable by document/prompt injection (ADR-F042 §Decision; B2). The agent's
#     auto-curation is structurally unable to alter/drop these (it writes only
#     ``context_md`` + ``wiki_snapshot`` rows — the no-overwrite guarantee).
#   * ``wiki_snapshot`` — the prior ``context_md`` captured before an
#     ``update_matter_memory`` rewrite (undo; ``trust='normal'``; ``run_id`` = the
#     run that triggered the rewrite, provenance).
#   * ``fact``          — one entry in the agent's dated fact ledger (C3b-1;
#     ``author='agent'``, ``trust='normal'``). ``body_md`` is the statement;
#     ``valid_at``/``invalid_at`` are its WORLD-time validity window (supersede sets
#     ``invalid_at`` + ``superseded_by``, never deletes — "what did we believe at
#     signing"); ``source_citation`` is the prose source; ``fact_type`` the taxonomy.
#     The ``record_matter_fact`` tool writes only ``fact`` rows — never a correction,
#     never ``human-pinned`` (no-fabrication + no-overwrite carry over from C3a).
# The value sets are the single source of truth for the CHECK constraints below
# (mirrors app.models.assessment / app.models.ropa: private value tuples wired into
# the CHECK via ``_in_set``). The migration DDL holds the matching SQL literals.
# C3b-1 (ADR-F042): ``'fact'`` is the typed bi-temporal fact-ledger kind (the agent's
# dated, supersede-able facts) — additive on the C3a table; fact rows reuse ``body_md``
# for the statement and populate the nullable typed columns below.
_MATTER_MEMORY_KINDS = ("correction", "wiki_snapshot", "fact")
_MATTER_MEMORY_TRUST = ("normal", "human-pinned")
# C3b-1: who recorded a typed fact. ``'agent'`` for the auto-recorded ledger. The
# CHECK also admits ``'lawyer'``, reserved for a future pin-endpoint change — C3b-1
# does NOT populate it (existing correction rows keep ``author`` NULL; additive-
# nullable, no backfill). No agent path mints a ``'lawyer'`` row (B2 — an
# agent-asserted human author is forgeable).
_MATTER_MEMORY_AUTHORS = ("agent", "lawyer")
# C3b-1: a small, area-neutral fact taxonomy (start here; extend additively). Covers
# both a Commercial deal and a Privacy programme.
_MATTER_FACT_TYPES = ("party", "term", "date", "decision", "open_point", "fact")
# DB-level body cap (defense-in-depth; reject, don't truncate). Generous: a
# ``wiki_snapshot`` stores a prior ``context_md`` which the PATCH path caps at
# 100 KiB, so this must comfortably exceed that. The agent wiki write and the
# correction endpoint enforce their own (smaller) caps at the boundary.
MATTER_MEMORY_BODY_MAX_CHARS = 200_000
# C3b-1: the prose ``source_citation`` cap (kept in sync with the migration DDL and
# ``app.schemas.matter_memory``).
MATTER_FACT_SOURCE_MAX_CHARS = 500


def _in_set(column: str, values: tuple[str, ...]) -> str:
    """Render ``column IN ('a', 'b', …)`` for a CHECK (mirrors models.assessment)."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_in_set(column: str, values: tuple[str, ...]) -> str:
    """``column IS NULL OR column IN (…)`` for a nullable-enum CHECK (mirrors _opt_len)."""
    return f"{column} IS NULL OR {_in_set(column, values)}"


class MatterMemoryEntry(Base):
    """One durable matter-memory entry — a pinned correction, a wiki snapshot, or a
    typed fact (the C3b-1 fact ledger).

    See the module-level note above. The hot read is "the live pinned corrections
    of this matter" (injected every run) — covered by the
    ``(project_id, kind, created_at)`` index, which also serves the matter-scoped
    fact reads (tens of rows per matter). ``superseded_at`` is the C3a soft-supersede
    column for corrections; the C3b-1 ``valid_at``/``invalid_at``/``superseded_by``
    columns are the typed-fact bi-temporal supersede (set ``invalid_at``, never
    delete). Rows are matter-scoped via ``project_id`` (CASCADE) — the write blast
    radius is confined to the single matter (ADR-F042).
    """

    __tablename__ = "matter_memory_entries"
    __table_args__ = (
        CheckConstraint(
            _in_set("kind", _MATTER_MEMORY_KINDS),
            name="chk_matter_memory_entries_kind",
        ),
        CheckConstraint(
            _in_set("trust", _MATTER_MEMORY_TRUST),
            name="chk_matter_memory_entries_trust",
        ),
        CheckConstraint(
            f"char_length(body_md) BETWEEN 1 AND {MATTER_MEMORY_BODY_MAX_CHARS}",
            name="chk_matter_memory_entries_body_len",
        ),
        # C3b-1: nullable-enum + temporal + length guards on the typed-fact columns.
        CheckConstraint(
            _opt_in_set("author", _MATTER_MEMORY_AUTHORS),
            name="chk_matter_memory_entries_author",
        ),
        CheckConstraint(
            _opt_in_set("fact_type", _MATTER_FACT_TYPES),
            name="chk_matter_memory_entries_fact_type",
        ),
        CheckConstraint(
            "invalid_at IS NULL OR valid_at IS NULL OR invalid_at > valid_at",
            name="chk_matter_memory_entries_valid_window",
        ),
        CheckConstraint(
            "source_citation IS NULL OR "
            f"char_length(source_citation) BETWEEN 1 AND {MATTER_FACT_SOURCE_MAX_CHARS}",
            name="chk_matter_memory_entries_source_len",
        ),
        Index(
            "ix_matter_memory_entries_project_kind_created",
            "project_id",
            "kind",
            "created_at",
        ),
        Index("ix_matter_memory_entries_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_matter_memory_entries_project_id"),
        nullable=False,
    )
    # The author. For a correction this is the authenticated human; for a snapshot
    # it is the run's user. CASCADE is academic in practice (projects.owner_id is
    # RESTRICT, so a user with matters can't be deleted), but keeps the row from
    # outliving its author on a D6 hard-delete.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_matter_memory_entries_user_id"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    trust: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'normal'"))
    # Provenance: the run that wrote a snapshot. NULL for a human correction (no run).
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # C3b-1 (ADR-F042): typed bi-temporal fact columns (NULL for correction/snapshot
    # rows; populated for ``kind='fact'``). See the module note above.
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    fact_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # WORLD-time validity window (distinct from created_at = ingestion-time).
    valid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The explicit forward link to the fact that replaced this one (a plain UUID,
    # mirroring run_id — not a self-FK; the temporal window is the load-bearing part).
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<MatterMemoryEntry id={self.id} project_id={self.project_id} "
            f"kind={self.kind!r} trust={self.trust!r}>"
        )


# --- Authorship roster (fork, ADR-F048): a matter's who-is-who -----------------------
#
# A negotiation has MANY people redlining, not just two counsels (our lead + our
# associate + our client's GC, vs. their counsel + their client). The roster maps a
# person's identity (display name + the author/email strings we MATCH against) to a
# ``side``, so the agent can tell whose tracked changes are whose when it re-reads a
# document. ``side`` drives treatment: ``'ours'`` (our team incl. our client) → adopt
# as authoritative; ``'counterparty'`` → a negotiation position, never silently
# adopted; ``'other'`` (ADR-F048 Slice 2) → a known third party (escrow agent,
# lender's counsel) — weigh distinctly, never silently adopt; ``'unknown'`` → ask the
# user. Additive-extensible (the set grew from 3→4 in migration ``0077``), mirroring
# the ``_MATTER_FACT_TYPES`` convention. ``role_label`` is the free-text descriptor
# ("Lead counsel", "Client GC") that rides along for context.
_MATTER_PARTICIPANT_SIDES = ("ours", "counterparty", "other", "unknown")
# How a roster entry was set. ``'inferred'`` = the agent recorded it (auto-write,
# ADR-F042 / B2); ``'confirmed'`` = the supervising lawyer set or edited it. The human
# owns the tier: a ``'confirmed'`` entry is authoritative — the agent's auto-curation
# must never overwrite its side/role (B2 carries over, enforced by the tool).
_MATTER_PARTICIPANT_TRUST = ("inferred", "confirmed")
# Identity-field caps (defense-in-depth; reject-not-truncate at the schema boundary).
MATTER_PARTICIPANT_NAME_MAX_CHARS = 200
MATTER_PARTICIPANT_ROLE_MAX_CHARS = 200
MATTER_PARTICIPANT_ORG_MAX_CHARS = 200
MATTER_PARTICIPANT_ALIAS_MAX_CHARS = 200
MATTER_PARTICIPANT_MAX_ALIASES = 30
MATTER_PARTICIPANT_SOURCE_MAX_CHARS = 500


class MatterParticipant(Base):
    """One person on a matter's authorship roster (ADR-F048).

    Matter-scoped via ``project_id`` (CASCADE) — the write blast radius is the single
    matter (ADR-F042). ``aliases`` is the JSONB match set: the tracked-change author
    strings / emails this person writes under, matched Python-side (normalised
    lower/trim) against a document's author strings (never a SQL string built from
    untrusted input). ``side`` is the treatment driver (CHECK-bounded); ``trust``
    distinguishes an agent-inferred row from a human-confirmed one (the latter wins).
    A removed participant is SOFT-retired (``superseded_at`` set; the row is never
    deleted — active = ``superseded_at IS NULL``), mirroring the correction retire.
    """

    __tablename__ = "matter_participants"
    __table_args__ = (
        CheckConstraint(
            _in_set("side", _MATTER_PARTICIPANT_SIDES),
            name="chk_matter_participants_side",
        ),
        CheckConstraint(
            _in_set("trust", _MATTER_PARTICIPANT_TRUST),
            name="chk_matter_participants_trust",
        ),
        CheckConstraint(
            f"char_length(display_name) BETWEEN 1 AND {MATTER_PARTICIPANT_NAME_MAX_CHARS}",
            name="chk_matter_participants_name_len",
        ),
        CheckConstraint(
            "organization IS NULL OR "
            f"char_length(organization) BETWEEN 1 AND {MATTER_PARTICIPANT_ORG_MAX_CHARS}",
            name="chk_matter_participants_org_len",
        ),
        CheckConstraint(
            "role_label IS NULL OR "
            f"char_length(role_label) BETWEEN 1 AND {MATTER_PARTICIPANT_ROLE_MAX_CHARS}",
            name="chk_matter_participants_role_len",
        ),
        CheckConstraint(
            "source_citation IS NULL OR "
            f"char_length(source_citation) BETWEEN 1 AND {MATTER_PARTICIPANT_SOURCE_MAX_CHARS}",
            name="chk_matter_participants_source_len",
        ),
        Index(
            "ix_matter_participants_project_created",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_matter_participants_project_id"),
        nullable=False,
    )
    # The setter: the run's user for an agent-inferred row, the authenticated human for
    # a confirmed one. CASCADE keeps a row from outliving its user on a D6 hard-delete.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_matter_participants_user_id"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    # The match set (author strings + emails). Normalised + matched in code, not SQL.
    aliases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    organization: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    trust: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'inferred'"))
    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provenance: the run that recorded an inferred entry; NULL for a human-set one.
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Soft-remove: a retired participant drops off the active roster but stays on record.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
            f"<MatterParticipant id={self.id} project_id={self.project_id} "
            f"side={self.side!r} trust={self.trust!r}>"
        )


class MatterCapabilityToggle(Base):
    """Per-matter capability on/off override — ADR-F054 (capability panel).

    Two-layer scope: the practice AREA curates which capabilities are AVAILABLE
    (skills via ``practice_area_skills``; playbooks via ``practice_area_playbooks``;
    tools via a per-area CODE group map in ``app.agents.capabilities``); the LAWYER
    toggles a subset on/off here, persisted per matter (survives the matter's
    conversations). "System proposes, user owns."

    **Sparse override.** A row exists ONLY where the lawyer diverged from the
    capability's ``default_enabled`` (every available capability defaults ON except
    the MCP placeholder). Absence of a row = the default — so a matter the lawyer
    never touches stays byte-identical to today, and a newly-available area
    capability is auto-on with no backfill. ``enabled`` is stored (not "presence =
    off") so a lawyer can explicitly re-enable after a future default flip, and the
    direction is recorded in ``set_by``. A stale row for a removed/renamed
    capability is ignored at resolve time (the inventory is the source of truth).

    ``capability_key`` is TEXT (not a polymorphic FK), mirroring
    ``practice_area_skills.skill_name``: skills are filesystem-canonical, tool-group
    keys are code-canonical, and the playbook key is ``playbook_id::text`` —
    validated to resolve against the matter's AVAILABLE set at the PUT boundary so
    no dead rows accumulate.
    """

    __tablename__ = "matter_capability_toggles"
    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id",
            "capability_kind",
            "capability_key",
            name="pk_matter_capability_toggles",
        ),
        CheckConstraint(
            "capability_kind IN ('skill', 'tool', 'playbook')",
            name="chk_matter_capability_toggles_kind",
        ),
        CheckConstraint(
            "char_length(capability_key) BETWEEN 1 AND 200",
            name="chk_matter_capability_toggles_key_len",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id", ondelete="CASCADE", name="fk_matter_capability_toggles_project_id"
        ),
        nullable=False,
    )
    capability_kind: Mapped[str] = mapped_column(Text, nullable=False)
    capability_key: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Human provenance — who last set this toggle. SET NULL on user delete keeps
    # the override (it is the matter's state, not the individual's).
    set_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_matter_capability_toggles_set_by"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<MatterCapabilityToggle project_id={self.project_id} "
            f"kind={self.capability_kind!r} key={self.capability_key!r} enabled={self.enabled}>"
        )
