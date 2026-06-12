"""agent_runs lease + heartbeat columns — F1-S1 (fork, ADR-F009)

Run-lifecycle durability: agent runs execute on the arq worker at-most-once;
liveness is a positive signal (heartbeat) and every worker write is fenced by
a per-claim lease token, so the orphan sweep and the cancel endpoint can
settle a run with first-writer-wins semantics and a zombie worker's late
writes are rejected by SQL.

* ``claimed_by``   — informational worker tag (host:pid:boot-uuid) for ops.
* ``claimed_at``   — when the worker claimed the run (DB clock). NULL +
  stale ``started_at`` = lost enqueue / dead-before-claim → swept.
* ``lease_token``  — the fencing value, new uuid per claim; heartbeat and
  terminal UPDATEs carry ``WHERE lease_token = :mine``.
* ``heartbeat_at`` — touched (throttled) from inside the stream loop and at
  the guarded_tool_call chokepoint; stale = orphaned → swept FAILED.

No backfill: pre-S1 rows keep NULLs honestly — the sweep's unclaimed-grace
rule settles any legacy ``running`` rows on first pass (they have no live
runner by construction: BackgroundTasks died with their api process).

The partial index serves the sweep's scan (the ``running`` set is small but
the table grows unboundedly).

Revision ID: 0052
Revises: 0051
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("claimed_by", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "idx_agent_runs_running_sweep",
        "agent_runs",
        ["heartbeat_at"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("idx_agent_runs_running_sweep", table_name="agent_runs")
    op.drop_column("agent_runs", "heartbeat_at")
    op.drop_column("agent_runs", "lease_token")
    op.drop_column("agent_runs", "claimed_at")
    op.drop_column("agent_runs", "claimed_by")
