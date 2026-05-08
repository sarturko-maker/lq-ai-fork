"""create projects + project_files + project_skills; add files.project_id FK — Task C7

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-08

Adds the matter-scoped Project resource per docs/db-schema.md §`projects`
and PRD §3.11. Three new tables plus an ALTER on `files` to wire the
deferred FK constraint that 0003 left dangling.

What lands:

- `projects` — owner-scoped matter container with `name`, `slug`,
  `context_md` (free-form markdown), `privileged` (bool), and
  `minimum_inference_tier` (1-5). The `privileged` flag carries a
  CHECK constraint enforcing that `privileged=true` implies a non-NULL
  `minimum_inference_tier` (the API also validates this; the DB
  constraint is defense-in-depth). Soft-delete via `archived_at`.
- `project_files` — composite-PK join table linking projects to files.
  Both ends are `ON DELETE CASCADE`: dropping a project removes its
  attachments; dropping a file removes any join rows referencing it
  (the file's own row is what carries owner/audit ties).
- `project_skills` — composite-PK join table linking projects to skill
  *names* (text, no FK — skills are filesystem-canonical per ADR 0004).
- `files.project_id` FK constraint added: `fk_files_project_id
  REFERENCES projects(id) ON DELETE SET NULL`. The column itself was
  added in 0003 (nullable, no FK) so 0003 stays standalone-clean.

Per A2's choice (and the deferred UUIDv7 migration item) we use
`gen_random_uuid()` (UUIDv4) — `pgcrypto` is already enabled by 0001.
The schema doc shows `uuid_generate_v7()` aspirationally; the migrations
land what we run today.

Indexes:

- `idx_projects_owner_active` on `(owner_id, archived_at)` — listing
  endpoint's primary read shape.
- `idx_projects_slug_owner` on `(owner_id, slug)` UNIQUE WHERE
  `archived_at IS NULL` — slugs are unique-per-owner within the active
  set so a user can reuse a slug after archiving.
- `idx_project_files_file` on `(file_id)` — supports the future
  "which projects is this file in" query (D-phase / portfolio views).
- `idx_project_skills_skill` on `(skill_name)` — supports the future
  "which projects use this skill" query.

`updated_at` is maintained by the existing `set_updated_at()` trigger
function (created in 0001); we just attach a trigger to `projects`.

Reversible: downgrade drops the FK on files, then drops the three
tables in reverse dependency order. The `project_id` column on `files`
remains in place (its presence belongs to 0003).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # projects
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_projects_owner_id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("context_md", sa.Text(), nullable=True),
        sa.Column(
            "privileged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("minimum_inference_tier", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "minimum_inference_tier IS NULL OR (minimum_inference_tier BETWEEN 1 AND 5)",
            name="chk_projects_tier_range",
        ),
        sa.CheckConstraint(
            "(privileged = false) OR (minimum_inference_tier IS NOT NULL)",
            name="chk_projects_privileged_implies_tier",
        ),
        sa.CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_projects_name_len",
        ),
        sa.CheckConstraint(
            "char_length(slug) > 0 AND char_length(slug) <= 80",
            name="chk_projects_slug_len",
        ),
    )

    # Active-listing index — owner's non-archived projects, newest first.
    op.execute(
        """
        CREATE INDEX idx_projects_owner_active
            ON projects (owner_id, created_at DESC)
            WHERE archived_at IS NULL
        """
    )

    # Slug uniqueness scoped to (owner, active). Archived projects are
    # invisible to the slug check so a user can reuse the slug after
    # archiving.
    op.execute(
        """
        CREATE UNIQUE INDEX idx_projects_slug_owner_active
            ON projects (owner_id, slug)
            WHERE archived_at IS NULL
        """
    )

    # updated_at trigger reuses the function created in 0001.
    op.execute(
        """
        CREATE TRIGGER trg_projects_set_updated_at
            BEFORE UPDATE ON projects
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at()
        """
    )

    # ------------------------------------------------------------------
    # project_files (join: project ↔ file)
    # ------------------------------------------------------------------
    op.create_table(
        "project_files",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_project_files_project_id"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE", name="fk_project_files_file_id"),
            nullable=False,
        ),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("project_id", "file_id", name="pk_project_files"),
    )

    op.execute("CREATE INDEX idx_project_files_file ON project_files (file_id)")

    # ------------------------------------------------------------------
    # project_skills (join: project ↔ skill name)
    # ------------------------------------------------------------------
    # `skill_name` is *text*, not a FK — skills are filesystem-canonical
    # per ADR 0004; there is no `skills` SQL table.
    op.create_table(
        "project_skills",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_project_skills_project_id"),
            nullable=False,
        ),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("project_id", "skill_name", name="pk_project_skills"),
        sa.CheckConstraint(
            "char_length(skill_name) > 0 AND char_length(skill_name) <= 200",
            name="chk_project_skills_name_len",
        ),
    )

    op.execute("CREATE INDEX idx_project_skills_skill ON project_skills (skill_name)")

    # ------------------------------------------------------------------
    # Close the C4 deferred item: add the FK on files.project_id.
    # ------------------------------------------------------------------
    # 0003 left the column nullable without an FK because `projects`
    # didn't exist yet. Now it does. ON DELETE SET NULL because losing
    # a project shouldn't lose the files (the files are independently
    # owned and may be in other projects).
    op.create_foreign_key(
        constraint_name="fk_files_project_id",
        source_table="files",
        referent_table="projects",
        local_cols=["project_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop the FK on files.project_id first; the column itself stays
    # (it belongs to 0003).
    op.drop_constraint("fk_files_project_id", "files", type_="foreignkey")

    op.execute("DROP TRIGGER IF EXISTS trg_projects_set_updated_at ON projects")

    # Drop in reverse FK-dependency order.
    op.drop_table("project_skills")
    op.drop_table("project_files")
    op.drop_table("projects")
