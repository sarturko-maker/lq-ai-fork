"""create user_skills table — Task D8 (DB-backed user skills per ADR 0012)

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-10

ADR 0012 lands user-scope skill storage as a shadow layer over the
filesystem-canonical built-ins (ADR 0004). One row per
``(scope, owner, slug)``; user shadows built-in on slug collision when
resolved for that user's chats; ``archived_at`` is the soft-delete
mechanism so accidental deletes are recoverable via a follow-on
unarchive (not implemented in D8 — DE candidate).

Scope columns ship in this migration even though only ``scope='user'``
is exercised by D8's CRUD endpoints. The empty ``team`` slot is what
D8.1 fills (adding the ``teams`` table + the FK constraint pointing at
it + the team-scope branch in resolution). The ``CHECK`` clause and
the partial UNIQUE index for team scope are valid SQL today against an
empty row set; no rows can be inserted at ``scope='team'`` until the
FK target exists, but the constraint shape is in place.

Indexes:

* ``idx_user_skills_owner_user`` — owner-scoped listing query; partial
  on ``scope='user' AND archived_at IS NULL`` because that's the only
  branch hot in D8.
* ``idx_user_skills_owner_team`` — symmetric, awaits D8.1.
* Two partial ``UNIQUE`` constraints enforce slug uniqueness within an
  owner *for non-archived rows*. Archiving a row and creating a new
  one at the same slug succeeds — that's the soft-delete reuse
  pattern, deliberate.

The ``updated_at`` trigger reuses the ``set_updated_at()`` function
created in migration 0001 (canonical across all entity tables).

Reversible: ``downgrade()`` drops the trigger, indexes, and table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_skills",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "scope",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_skills_user"),
            nullable=True,
        ),
        # No FK constraint on owner_team_id in this migration — the
        # ``teams`` target table lands in D8.1. The column shape + the
        # CHECK + the partial UNIQUE index are all valid SQL today
        # against an empty team-scope row set; D8.1's only schema
        # change is adding the FK constraint pointing at teams.id.
        sa.Column(
            "owner_team_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'1.0.0'"),
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "frontmatter_extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
        sa.CheckConstraint(
            "scope IN ('user', 'team')",
            name="ck_user_skills_scope_enum",
        ),
        sa.CheckConstraint(
            "(scope = 'user' AND owner_user_id IS NOT NULL AND owner_team_id IS NULL) "
            "OR (scope = 'team' AND owner_team_id IS NOT NULL AND owner_user_id IS NULL)",
            name="ck_user_skills_scope_owner_consistency",
        ),
    )

    # Partial UNIQUE constraints — slug is unique within an owner only
    # for non-archived rows. Archiving frees the slug; a user can create
    # a new skill at the same slug after archiving the prior one.
    op.execute(
        "CREATE UNIQUE INDEX ux_user_skills_user_slug "
        "ON user_skills (owner_user_id, slug) "
        "WHERE scope = 'user' AND archived_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_user_skills_team_slug "
        "ON user_skills (owner_team_id, slug) "
        "WHERE scope = 'team' AND archived_at IS NULL"
    )

    # Listing-by-owner — partial on the alive-row branch so the index
    # stays small even after many archives.
    op.execute(
        "CREATE INDEX idx_user_skills_owner_user ON user_skills "
        "(owner_user_id, updated_at DESC) "
        "WHERE scope = 'user' AND archived_at IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_user_skills_owner_team ON user_skills "
        "(owner_team_id, updated_at DESC) "
        "WHERE scope = 'team' AND archived_at IS NULL"
    )

    op.execute(
        "CREATE TRIGGER trg_user_skills_updated_at "
        "BEFORE UPDATE ON user_skills "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_user_skills_updated_at ON user_skills")
    op.execute("DROP INDEX IF EXISTS idx_user_skills_owner_team")
    op.execute("DROP INDEX IF EXISTS idx_user_skills_owner_user")
    op.execute("DROP INDEX IF EXISTS ux_user_skills_team_slug")
    op.execute("DROP INDEX IF EXISTS ux_user_skills_user_slug")
    op.drop_table("user_skills")
