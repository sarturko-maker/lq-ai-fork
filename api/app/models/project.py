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
from sqlalchemy.dialects.postgresql import UUID
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
# Two ``kind``s share one table (additive-nullable so C3b layers typed bi-temporal
# fact columns — valid_at/invalid_at/superseded_by/value/author/source_citation/type
# — with NO backfill; correction/snapshot rows keep ``body_md``, typed-fact rows
# will populate the new columns):
#   * ``correction``    — a lawyer's correction. ``trust='human-pinned'``, written
#     ONLY through the authenticated human endpoint (``author`` = the session user).
#     No agent-granted tool mints one — an agent-asserted "the lawyer said X" is
#     forgeable by document/prompt injection (ADR-F042 §Decision; B2). The agent's
#     auto-curation is structurally unable to alter/drop these (it writes only
#     ``context_md`` + ``wiki_snapshot`` rows — the no-overwrite guarantee).
#   * ``wiki_snapshot`` — the prior ``context_md`` captured before an
#     ``update_matter_memory`` rewrite (undo; ``trust='normal'``; ``run_id`` = the
#     run that triggered the rewrite, provenance).
# The value sets are the single source of truth for the CHECK constraints below
# (mirrors app.models.assessment / app.models.ropa: private value tuples wired into
# the CHECK via ``_in_set``). The migration DDL holds the matching SQL literals.
_MATTER_MEMORY_KINDS = ("correction", "wiki_snapshot")
_MATTER_MEMORY_TRUST = ("normal", "human-pinned")
# DB-level body cap (defense-in-depth; reject, don't truncate). Generous: a
# ``wiki_snapshot`` stores a prior ``context_md`` which the PATCH path caps at
# 100 KiB, so this must comfortably exceed that. The agent wiki write and the
# correction endpoint enforce their own (smaller) caps at the boundary.
MATTER_MEMORY_BODY_MAX_CHARS = 200_000


def _in_set(column: str, values: tuple[str, ...]) -> str:
    """Render ``column IN ('a', 'b', …)`` for a CHECK (mirrors models.assessment)."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class MatterMemoryEntry(Base):
    """One durable matter-memory entry — a pinned correction or a wiki snapshot.

    See the module-level note above. The hot read is "the live pinned corrections
    of this matter" (injected every run) — covered by the
    ``(project_id, kind, created_at)`` index. ``superseded_at`` is the C3a soft-
    supersede column (set when a correction is retired; C3b adds the richer
    bi-temporal columns). Rows are matter-scoped via ``project_id`` (CASCADE) — the
    write blast radius is confined to the single matter (ADR-F042).
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
