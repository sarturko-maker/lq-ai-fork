"""user_sessions absolute + idle timeout columns — M-Sec.1

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-11

PRD §5.1 promises configurable absolute (8h default) and idle (30m
default) session timeouts. JWT TTLs alone can't carry the absolute
clock across refresh-token rotations — each rotation creates a fresh
``user_sessions`` row whose ``created_at`` resets the clock. To
enforce the absolute timeout we stash the original-login deadline on
the session row and copy it forward on refresh; to enforce the idle
timeout we stamp ``last_active_at`` and re-check it at refresh time.

Why "at refresh time only" and not "on every authenticated request":

Access tokens are short-lived (15 min default). An idle user's
access token expires within the idle window anyway; if they come
back after 30 min they need to refresh, which is where we check
idle. This keeps the JWT path stateless and avoids the per-request
Postgres hit a "check session on every API call" model would
require. Documented trade-off — operators who want stricter
enforcement can shorten the access-token TTL.

Two additive columns:

1. ``user_sessions.absolute_expires_at`` — copied verbatim across
   refresh rotations so the original login's clock is preserved.
   Backfilled to ``created_at + 8h`` for existing rows.
2. ``user_sessions.last_active_at`` — updated on every refresh.
   Backfilled to ``created_at`` for existing rows.

Reversible: ``downgrade()`` drops both columns. No data lost on
upgrade; no data lost on downgrade either (the columns just go away).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- absolute_expires_at -------------------------------------------------
    # Add NULLABLE first so the migration can run on a populated table;
    # backfill from created_at + 8h; then ALTER to NOT NULL. The default
    # mirrors PRD §5.1's 8-hour absolute-timeout floor.
    op.add_column(
        "user_sessions",
        sa.Column(
            "absolute_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE user_sessions "
        "SET absolute_expires_at = created_at + interval '8 hours' "
        "WHERE absolute_expires_at IS NULL"
    )
    op.alter_column("user_sessions", "absolute_expires_at", nullable=False)

    # --- last_active_at ------------------------------------------------------
    # Backfilled to created_at so existing sessions get a sane idle clock.
    # No server_default — the app stamps it explicitly on insert so the
    # column's source of truth is application code, not the DB clock.
    op.add_column(
        "user_sessions",
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE user_sessions "
        "SET last_active_at = created_at "
        "WHERE last_active_at IS NULL"
    )
    op.alter_column("user_sessions", "last_active_at", nullable=False)


def downgrade() -> None:
    op.drop_column("user_sessions", "last_active_at")
    op.drop_column("user_sessions", "absolute_expires_at")
