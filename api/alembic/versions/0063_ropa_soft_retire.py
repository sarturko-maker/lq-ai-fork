"""ROPA soft-retire — PRIV-8a (fork, ADR-F023)

The Privacy agent gains *change* verbs (retire / unlink), not only *add*. A
register row is never destroyed — it is **soft-retired** so the change stays
auditable (ADR-F018/F019: append-only, audited, deployment-global). Each of the
four MUTABLE register entities (the two label vocabularies are immutable) gains:

* ``retired_at`` — TIMESTAMPTZ, NULL = live; set to ``now()`` on retire. Reads
  exclude retired rows by default (``?include_retired=true`` shows them); the
  agent's ``list_*`` tools hide them so a retired vendor is never re-linked.
* ``retirement_reason`` — optional free text (≤1000), the maintainer/agent's note
  ("superseded by Hotjar").

Additive + nullable, so existing rows are live by construction (no backfill).

Revision ID: 0063
Revises: 0062
Create Date: 2026-06-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

# The four mutable register entities (the data_* label vocabularies are immutable
# — Article 30(1)(c) tags, no retire). Kept as a literal so upgrade/downgrade and
# the reason-length CHECK stay in lockstep.
_TABLES = ("processing_activities", "systems", "vendors", "transfers")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("retirement_reason", sa.Text(), nullable=True),
        )
        # Optional free text: NULL or within bound (mirrors the _opt_len CHECK
        # style of the existing descriptive columns).
        op.create_check_constraint(
            f"chk_{table}_retirement_reason_len",
            table,
            "retirement_reason IS NULL OR char_length(retirement_reason) <= 1000",
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"chk_{table}_retirement_reason_len", table, type_="check")
        op.drop_column(table, "retirement_reason")
        op.drop_column(table, "retired_at")
