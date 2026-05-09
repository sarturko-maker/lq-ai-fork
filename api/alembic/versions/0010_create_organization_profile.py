"""create organization_profile singleton — Task D4

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-09

PRD §3.12 calls the Organization Profile a "singleton skill" — same
SKILL.md format, same inspectability, treated as a singleton by the
Skill Service. ADR 0004 keeps built-in skills filesystem-canonical
(no ``skills`` SQL table for M1), so D4 can't simply add a
``is_organization_profile`` column to that nonexistent table.

Instead, this migration adds a focused single-row ``organization_profile``
table that backs the GET/PUT API. The gateway-side prompt-assembler
(C2) fetches the row's content via the backend's internal-skills
plumbing and prepends it to every attached skill whose frontmatter
does not opt out (``use_organization_profile: false``).

Singleton enforcement: ``CREATE UNIQUE INDEX ... ON organization_profile
((true))`` — the Postgres "at most one row" pattern. ``true`` is the
expression and ``UNIQUE`` collapses every row's index value to the
same literal; the second insert violates the index and 23505s.

Reversible: ``downgrade()`` drops the table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_profile",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("content_md", sa.Text(), nullable=False, server_default=sa.text("''")),
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
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_org_profile_updated_by"),
            nullable=True,
        ),
    )

    # Singleton enforcement — at most one row.
    op.execute(
        "CREATE UNIQUE INDEX idx_organization_profile_singleton ON organization_profile ((true))"
    )

    # Auto-maintain updated_at via the existing trigger function.
    op.execute(
        "CREATE TRIGGER trg_organization_profile_updated_at "
        "BEFORE UPDATE ON organization_profile "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_organization_profile_updated_at ON organization_profile")
    op.drop_index("idx_organization_profile_singleton", table_name="organization_profile")
    op.drop_table("organization_profile")
