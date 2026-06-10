"""agent runs + steps — F0-S2 (fork)

Creates the two tables that persist deep-agent runs (ADR-F002 "glass
cockpit"; ADR-F004 render-deterministic UI):

* ``agent_runs`` — one row per deep-agent run: prompt, model alias,
  interim caps (``max_steps``; the wall-clock timeout lives in the
  runner), terminal status, final answer.
* ``agent_run_steps`` — one row per loop step (model turn / tool call /
  tool result), appended and committed as each step completes so a
  poller sees progress live. ``summary`` is a bounded digest — tool
  args/results are truncated before persisting; no raw secrets.

``agent_runs.user_id`` FKs ``users`` with ``ON DELETE CASCADE`` — agent
runs are hard per-user isolated, matching the autonomous layer
(migration 0039). Steps cascade from their run.

``status='cancelled'`` is RESERVED in the CHECK for the cancel endpoint
(later slice); nothing sets it in F0-S2. ``cost_usd`` stays NULL until
the F1 guarded_tool_call/R4 integration aggregates per-run gateway cost.

Revision ID: 0048
Revises: 0047
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # agent_runs — one row per deep-agent run
    # ---------------------------------------------------------------
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_agent_runs_user_id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column(
            "model_alias",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'smart'"),
        ),
        sa.Column(
            "purpose",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'agent_loop'"),
        ),
        sa.Column(
            "max_steps",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("20"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','cancelled','cap_exceeded')",
            name="chk_agent_runs_status",
        ),
        sa.CheckConstraint(
            "max_steps >= 1",
            name="chk_agent_runs_max_steps_positive",
        ),
    )
    # "My recent runs" view for the UI (list endpoint: newest first).
    op.create_index(
        "idx_agent_runs_user_started",
        "agent_runs",
        ["user_id", sa.text("started_at DESC")],
    )

    # ---------------------------------------------------------------
    # agent_run_steps — one row per loop step, committed live
    # ---------------------------------------------------------------
    op.create_table(
        "agent_run_steps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE", name="fk_agent_run_steps_run_id"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "kind IN ('model_turn','tool_call','tool_result')",
            name="chk_agent_run_steps_kind",
        ),
        # The unique constraint's backing index also serves the
        # poller's ordered (run_id, seq) read — no separate index.
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_run_steps_run_seq"),
    )


def downgrade() -> None:
    op.drop_table("agent_run_steps")

    op.drop_index("idx_agent_runs_user_started", table_name="agent_runs")
    op.drop_table("agent_runs")
