"""agent_threads + agent_runs.thread_id — F0-S5 (fork, ADR-F008)

Conversation identity for multi-turn deep-agent runs: one
``agent_threads`` row per conversation; every ``agent_runs`` row belongs
to exactly one thread. The thread id doubles as the langgraph
checkpointer's ``configurable.thread_id`` (AsyncPostgresSaver — its own
tables are created by the library's versioned ``setup()``, deliberately
NOT alembic-managed; alembic owns only OUR schema).

The thread owns the Matter binding (``project_id``, SET NULL like the
runs' snapshot column); ``title`` is the bounded first prompt until
auto-titling lands (F1/F2); ``last_run_at`` orders the conversation
list.

Backfill: pre-S5 runs become one-run threads with ``thread_id = run id``
(UUID collision-free, keeps the backfill a single INSERT..SELECT +
UPDATE), then ``thread_id`` goes NOT NULL — every run belongs to a
thread, no special cases downstream. Backfilled threads have no
checkpoint state; the API refuses follow-ups on them at runtime (a
checkpoint-existence check, ADR-F008) rather than pretending the agent
remembers a conversation that was never persisted.

``uq_agent_runs_thread_running`` (partial unique) is the DB-level brake:
at most ONE running run per thread — two concurrent follow-ups cannot
both start, however the API races (the handler maps the integrity error
to 409).

Revision ID: 0050
Revises: 0049
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_threads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_agent_threads_user_id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL", name="fk_agent_threads_project_id"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Conversation list: the caller's threads, newest activity first.
    op.create_index(
        "idx_agent_threads_user_activity",
        "agent_threads",
        ["user_id", sa.text("last_run_at DESC")],
    )

    op.add_column(
        "agent_runs",
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_threads.id", ondelete="CASCADE", name="fk_agent_runs_thread_id"),
            nullable=True,
        ),
    )

    # Backfill: one thread per pre-S5 run, thread id = run id.
    op.execute(
        """
        INSERT INTO agent_threads (id, user_id, project_id, title, created_at, last_run_at)
        SELECT id, user_id, project_id, left(prompt, 120), started_at, started_at
        FROM agent_runs
        """
    )
    op.execute("UPDATE agent_runs SET thread_id = id WHERE thread_id IS NULL")
    op.alter_column("agent_runs", "thread_id", nullable=False)

    # Runs of a thread in conversation order.
    op.create_index(
        "idx_agent_runs_thread_started",
        "agent_runs",
        ["thread_id", "started_at"],
    )
    # The one-running-run-per-thread brake (ADR-F008).
    op.create_index(
        "uq_agent_runs_thread_running",
        "agent_runs",
        ["thread_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_agent_runs_thread_running", table_name="agent_runs")
    op.drop_index("idx_agent_runs_thread_started", table_name="agent_runs")
    op.drop_column("agent_runs", "thread_id")
    op.drop_index("idx_agent_threads_user_activity", table_name="agent_threads")
    op.drop_table("agent_threads")
