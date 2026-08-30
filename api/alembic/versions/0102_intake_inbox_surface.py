"""INTAKE-5a — the inbox surface: thread summary, read indexes, enum narrowing (ADR-F086)

Three unrelated-looking changes that together make the lawyer's Inbox possible
(``docs/fork/plans/INTAKE-5-plan.md`` rulings 6 + 7):

1. ``intake_threads.summary`` (JSONB, nullable) + ``intake_threads.summary_run_id``
   (FK ``agent_runs`` ``SET NULL``). Ruling 7 — "summary over chain": the thread
   detail opens on the agent's own ≤5-bullet account of the thread so far, and the
   raw email chain stays collapsed. ``record_intake_outcome`` REWRITES the whole
   list on every call (the same call that already ends every intake run), so
   ``summary_run_id`` names the run whose account this is — that is what makes
   "the agent's last run did not finish, so this may be out of date" computable.
   Shape (a JSON array of ``{"title", "text"}`` objects, ≤5 items, title ≤40 chars,
   text ≤300 chars, plain text) is bounded at the Pydantic write boundary
   (``app.schemas.intake.IntakeSummaryItem``), NOT by a DB CHECK: it is a
   structured document, and a CHECK over JSONB shape would be a second, drifting
   copy of the schema. ``SET NULL`` on run delete keeps the summary — it outlives
   the run record, exactly like ``files.summary_run_id`` (ADR-F082).

2. Two read indexes. ``intake_threads`` had none beyond its PK and the
   ``(mailbox_id, provider_thread_id)`` unique: the Inbox's two access paths are
   "this matter's threads" and "the attention queue, newest inbound first", and
   both were sequential scans.

3. The ``projects.intake_state`` CHECK narrows from
   ``NULL|candidate|promoted|dismissed`` to ``NULL|candidate``. ADR-F086
   Amendment A1 made ``intake_state`` PROVENANCE ("born from email") rather than a
   lifecycle — every intake thread IS a matter, so there is no promotion step and
   nothing has ever written the other two values. Narrowing now stops a future
   writer inventing a lifecycle the code does not have. The upgrade REFUSES loudly
   if any row carries a dead value rather than silently dropping the constraint:
   such a row would mean a lifecycle exists somewhere this migration cannot see.

Reversible: the downgrade restores the wide CHECK, drops the indexes and drops
both columns (the summaries themselves are agent-rewritable on the next run).

Revision ID: 0102
Revises: 0101
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

# The dead lifecycle values retired by ADR-F086 Amendment A1.
_DEAD_INTAKE_STATES = ("promoted", "dismissed")


def upgrade() -> None:
    # --- ruling 7: the agent's summary of the thread so far -----------------
    op.add_column(
        "intake_threads",
        sa.Column("summary", JSONB, nullable=True),
    )
    op.add_column("intake_threads", sa.Column("summary_run_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_intake_threads_summary_run_id",
        "intake_threads",
        "agent_runs",
        ["summary_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- ruling 6: the two read paths the Inbox actually takes --------------
    # "this matter's threads" (the matter-level Inbox tab, and the owner fence's
    # project join).
    op.create_index("ix_intake_threads_project_id", "intake_threads", ["project_id"])
    # "the attention queue" — filtered by status, ordered newest inbound first.
    op.execute(
        "CREATE INDEX ix_intake_threads_status_last_inbound "
        "ON intake_threads (status, last_inbound_at DESC)"
    )

    # --- ruling 6: retire the dead enum values ------------------------------
    conn = op.get_bind()
    stuck = conn.execute(
        sa.text(
            "SELECT count(*) FROM projects WHERE intake_state = ANY(:dead)",
        ),
        {"dead": list(_DEAD_INTAKE_STATES)},
    ).scalar_one()
    if stuck:
        # Loud, not lenient: a row carrying one of these means something wrote a
        # lifecycle ADR-F086 Amendment A1 says does not exist. Fix the writer (and
        # the rows) before narrowing — never widen the vocabulary back.
        raise RuntimeError(
            f"{stuck} projects row(s) carry a retired intake_state "
            f"({'/'.join(_DEAD_INTAKE_STATES)}); ADR-F086 Amendment A1 admits only "
            "NULL or 'candidate'. Migration 0102 refuses to narrow the CHECK while "
            "such rows exist."
        )
    op.drop_constraint("chk_projects_intake_state", "projects", type_="check")
    op.create_check_constraint(
        "chk_projects_intake_state",
        "projects",
        "intake_state IS NULL OR intake_state IN ('candidate')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_projects_intake_state", "projects", type_="check")
    op.create_check_constraint(
        "chk_projects_intake_state",
        "projects",
        "intake_state IS NULL OR intake_state IN ('candidate','promoted','dismissed')",
    )
    op.drop_index("ix_intake_threads_status_last_inbound", table_name="intake_threads")
    op.drop_index("ix_intake_threads_project_id", table_name="intake_threads")
    op.drop_constraint("fk_intake_threads_summary_run_id", "intake_threads", type_="foreignkey")
    op.drop_column("intake_threads", "summary_run_id")
    op.drop_column("intake_threads", "summary")
