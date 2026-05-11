"""Extend users table with 4 personalization preference columns.

Adds:
- featured_tools    TEXT NOT NULL DEFAULT 'prominent'   (prominent | inline)
- workspace_layout  TEXT NOT NULL DEFAULT 'three_pane'  (three_pane | two_pane | one_pane)
- trust_pills       TEXT NOT NULL DEFAULT 'labels'       (labels | dots)
- provenance_pills  TEXT NOT NULL DEFAULT 'always'       (always | collapsed)

Each column ships with a DB-level CHECK constraint (``chk_users_<field>_enum``)
that mirrors the Pydantic Literal enforcement in the API layer. This is the same
defense-in-depth pattern introduced in migration 0015 for ``reasoning_visibility``.

Spec reference: frontend design §4.3 (Wave B v2), PRD §3.2.1.
Revision: 0019 | Previous: 0018
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users.featured_tools ------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "featured_tools",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'prominent'"),
        ),
    )
    op.create_check_constraint(
        "chk_users_featured_tools_enum",
        "users",
        "featured_tools IN ('prominent', 'inline')",
    )

    # --- users.workspace_layout ----------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "workspace_layout",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'three_pane'"),
        ),
    )
    op.create_check_constraint(
        "chk_users_workspace_layout_enum",
        "users",
        "workspace_layout IN ('three_pane', 'two_pane', 'one_pane')",
    )

    # --- users.trust_pills ---------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "trust_pills",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'labels'"),
        ),
    )
    op.create_check_constraint(
        "chk_users_trust_pills_enum",
        "users",
        "trust_pills IN ('labels', 'dots')",
    )

    # --- users.provenance_pills ----------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "provenance_pills",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'always'"),
        ),
    )
    op.create_check_constraint(
        "chk_users_provenance_pills_enum",
        "users",
        "provenance_pills IN ('always', 'collapsed')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_users_provenance_pills_enum", "users", type_="check")
    op.drop_column("users", "provenance_pills")

    op.drop_constraint("chk_users_trust_pills_enum", "users", type_="check")
    op.drop_column("users", "trust_pills")

    op.drop_constraint("chk_users_workspace_layout_enum", "users", type_="check")
    op.drop_column("users", "workspace_layout")

    op.drop_constraint("chk_users_featured_tools_enum", "users", type_="check")
    op.drop_column("users", "featured_tools")
