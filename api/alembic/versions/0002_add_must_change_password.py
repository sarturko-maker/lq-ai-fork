"""add must_change_password column to users — Task B2

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07

Adds `users.must_change_password BOOLEAN NOT NULL DEFAULT FALSE`. The
first-run admin (created on initial API startup per Task B2) is inserted
with `must_change_password = TRUE`; the corresponding `/auth/change-password`
endpoint flips it to FALSE once the operator sets a permanent password.

Reversible: downgrade drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
