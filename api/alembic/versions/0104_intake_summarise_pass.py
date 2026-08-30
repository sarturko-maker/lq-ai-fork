"""INTAKE-5a.1 — the human-asked summarise pass: intake_threads.summarise_pass_run_id (ADR-F086)

The maintainer's UAT of the Inbox found threads that will never get a summary: they
were concluded before ``record_intake_outcome`` carried one (INTAKE-5a), or their run
safe-failed. "Summarise now" gives the lawyer a way to ask for one — a READ-ONLY
conclude pass over the conversation the agent already has.

That pass is an ordinary agent run, so the composition root has to be able to tell it
apart from an ordinary intake run WITHOUT trusting anything the model or the payload
says. This column is that fact, and it does two jobs at once:

* it MARKS the run as summarise-only, so composition builds the run with no
  ``draft_email_reply`` tool (nothing this run does can reach a counterparty) and the
  summarise doctrine instead of the intake doctrine;
* it BINDS the run to its thread. A summarise pass claims no inbound message, and one
  conversation can hold several intake threads (ADR-F088), so without an explicit
  link the binder would have to guess — the same class of bug fix D repairs for
  resumes.

Written by the worker through the run's own enqueue seam, BEFORE the agent-run job is
queued, so the row is durable before anything can read it. ``SET NULL`` on run delete:
losing the run costs the marker, never the thread.

Reversible: the downgrade drops the FK and the column.

Revision ID: 0104
Revises: 0103
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intake_threads",
        sa.Column("summarise_pass_run_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_intake_threads_summarise_pass_run_id",
        "intake_threads",
        "agent_runs",
        ["summarise_pass_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_intake_threads_summarise_pass_run_id", "intake_threads", type_="foreignkey"
    )
    op.drop_column("intake_threads", "summarise_pass_run_id")
