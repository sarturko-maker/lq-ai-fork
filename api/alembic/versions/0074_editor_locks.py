"""editor_locks — WOPI lock state for the in-app Word editor (Slice 2, ADR-F047)

One row per file an in-app editor session has locked, holding the opaque WOPI
lock string and its expiry. Backs the lock family (LOCK / GET_LOCK / REFRESH_LOCK
/ UNLOCK / UNLOCK_AND_RELOCK) the WOPI host implements in ``app.api.wopi``.

* PK is ``file_id`` — one lock per document (the lock is on the file, not the
  user; an UNLOCK may arrive on a different access token than the LOCK did).
* ``ON DELETE CASCADE`` on the files FK so deleting a file never strands a lock.
* ``lock_value`` is ``Text`` — opaque ASCII up to 1024 chars
  (``SupportsExtendedLockLength``), stored + compared verbatim.
* ``expires_at`` persists the protocol's lock timeout; an expired row is treated
  as "no lock" by the handler, so a stale row never blocks a fresh open.

Additive only: no existing table touched, no backfill. Mirrors
``app.models.editor_lock.EditorLock``.

Revision ID: 0074
Revises: 0073
Create Date: 2026-06-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editor_locks",
        sa.Column(
            "file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE", name="fk_editor_locks_file_id"),
            primary_key=True,
        ),
        sa.Column("lock_value", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("editor_locks")
