"""create knowledge_bases and knowledge_base_files — Task C6

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-08

Adds the `knowledge_bases` and `knowledge_base_files` tables per
docs/db-schema.md §`knowledge_bases`. C6's hybrid retrieval path
queries `document_chunks` filtered to chunks whose ``file_id`` is in a
KB's join table; the indexes on `document_chunks` (vector + GIN) were
landed in C5's migration 0005.

Notes:
- `owner_id` ON DELETE RESTRICT — a KB outlives its owner's
  soft-delete; an owner with KBs cannot be hard-deleted until D6's
  per-user export+delete path lands the cascade.
- `project_id` ON DELETE SET NULL — chats outlive their projects, KBs
  outlive their projects (operator may dissolve a project but keep its
  research artifacts).
- `hybrid_alpha` is a real (float) constrained to [0, 1] via CHECK.
  The default 0.5 weights vector and FTS scores equally; per-query
  callers may override.
- Composite-PK join `(kb_id, file_id)` plus an inverse `(file_id)`
  index so the embed-on-write trigger can ask "which KBs contain
  this file?" cheaply.
- The C5 column-comment on ``document_chunks.embedding`` referenced
  C6's backfill; this migration doesn't touch that column (the
  vector(1536) declaration is still correct per ADR 0008).

Reversible: downgrade drops both tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # knowledge_bases
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_bases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_knowledge_bases_owner_id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL", name="fk_knowledge_bases_project_id"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Hybrid alpha: 0 => vector-only; 1 => FTS-only; 0.5 => balanced.
        # Stored as REAL (single-precision float). The CHECK constraint
        # is the safety net; the API also clamps to [0, 1] at the
        # request boundary.
        sa.Column(
            "hybrid_alpha",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
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
            "hybrid_alpha >= 0.0 AND hybrid_alpha <= 1.0",
            name="chk_knowledge_bases_alpha_range",
        ),
        sa.CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_knowledge_bases_name_len",
        ),
    )

    # Listing index — partial on archived_at IS NULL so the active-KB
    # listing query (the most-common pattern) doesn't pay the index-
    # scan cost on archived rows.
    op.execute(
        "CREATE INDEX idx_kbs_owner_active "
        "ON knowledge_bases (owner_id, created_at DESC) "
        "WHERE archived_at IS NULL"
    )
    # Project filter index — partial on project_id IS NOT NULL so the
    # cross-project lookup is cheap when project scoping is asked.
    op.execute(
        "CREATE INDEX idx_kbs_project ON knowledge_bases (project_id) WHERE project_id IS NOT NULL"
    )

    # Reuse the A1 set_updated_at() trigger function so updated_at
    # auto-maintains. Same pattern used by users / projects / chats.
    op.execute(
        "CREATE TRIGGER trg_knowledge_bases_updated_at "
        "BEFORE UPDATE ON knowledge_bases "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # ------------------------------------------------------------------
    # knowledge_base_files (composite-PK join)
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_base_files",
        sa.Column(
            "kb_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "knowledge_bases.id",
                ondelete="CASCADE",
                name="fk_kb_files_kb_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "files.id",
                ondelete="CASCADE",
                name="fk_kb_files_file_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("kb_id", "file_id", name="pk_knowledge_base_files"),
    )

    # Inverse index: "which KBs contain this file?" The
    # embed-on-write trigger needs this when a chunk is embedded so
    # the affected KBs (if any) can be informed.
    op.execute("CREATE INDEX idx_kb_files_file_id ON knowledge_base_files (file_id)")


def downgrade() -> None:
    op.drop_table("knowledge_base_files")
    op.execute("DROP TRIGGER IF EXISTS trg_knowledge_bases_updated_at ON knowledge_bases")
    op.drop_table("knowledge_bases")
