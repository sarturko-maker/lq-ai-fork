"""create saved_prompts table — Task D7

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-09

PRD §9 DE-013 / Issue 04: per-user saved prompts complement skills the
way browser bookmarks complement Knowledge Bases — lighter than a full
skill (no folder, no frontmatter, no semver) for the "the way I always
ask for an executive summary" reuse case.

Schema mirrors ``docs/db-schema.md`` ("Saved prompts (per DE-013 /
Issue 04)") except ``id`` defaults to ``gen_random_uuid()`` (pgcrypto)
to match the rest of this codebase rather than the schema doc's
notional ``uuid_generate_v7()``. The schema doc describes intent; the
migrations are authoritative DDL.

Indexes:

* ``idx_saved_prompts_user`` on ``(user_id, updated_at DESC)`` —
  supports the dominant query (list-this-user's-prompts, newest first).
* ``idx_saved_prompts_tags`` on ``tags`` (gin) — supports future tag
  filtering. M1 doesn't expose tag filtering at the API yet but the
  index is cheap and lets the query land without a follow-on
  migration when DE-013's "tag filter" surface arrives.

The ``updated_at`` trigger reuses the ``set_updated_at()`` function
created in migration 0001, keeping the wall-clock-update behaviour
consistent across entity tables.

Reversible: ``downgrade()`` drops the trigger, indexes, and table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_prompts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_saved_prompts_user"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
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
    )

    op.create_index(
        "idx_saved_prompts_user",
        "saved_prompts",
        [sa.text("user_id"), sa.text("updated_at DESC")],
    )
    op.execute(
        "CREATE INDEX idx_saved_prompts_tags ON saved_prompts USING gin (tags)"
    )

    op.execute(
        "CREATE TRIGGER trg_saved_prompts_updated_at "
        "BEFORE UPDATE ON saved_prompts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_saved_prompts_updated_at ON saved_prompts")
    op.drop_index("idx_saved_prompts_tags", table_name="saved_prompts")
    op.drop_index("idx_saved_prompts_user", table_name="saved_prompts")
    op.drop_table("saved_prompts")
