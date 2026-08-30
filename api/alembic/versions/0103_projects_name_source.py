"""INTAKE-5a.1 — projects.name_source + agent_runs.resumed_from_run_id (ADR-F042/F086/F087)

The maintainer's UAT of the Inbox (INTAKE-5a, PR #299) found every intake-born
matter carrying the raw email subject as its name ("RE: FW: quick question"). The
agent now summarises the matter's essence into its NAME
(``record_intake_outcome(matter_title=…)``), which raises the one question every
auto-write-then-correct tier has to answer (ADR-F042): what happens when the human
has already said what this thing is called?

``name_source`` is that answer, as data rather than as a guess:

* ``'subject'`` — the eager intake row was named from the email subject at ingest.
  A placeholder; the agent may replace it.
* ``'agent'`` — the agent named it from what the thread turned out to be. Still
  the agent's, so a later run may improve it.
* ``'human'`` — a person renamed it (``PATCH /projects/{id}`` with ``name``).
  **Pins win**: no agent write ever overwrites this, exactly as a pinned matter
  correction outranks the agent's own wiki.

NOT NULL DEFAULT ``'human'`` is the conservative default for the whole existing
estate: every matter that predates this column was created by a person through the
cockpit, so treating it as human-named means the new agent write can never surprise
an owner by renaming a matter they typed the name of themselves. The backfill then
marks the intake-born rows (``intake_state = 'candidate'``) ``'subject'``, because
that is literally where their names came from
(``app.api.intake_emails._derive_project_name``).

## ``agent_runs.resumed_from_run_id`` — the resume's parent link (fix D)

A second, unrelated-looking column, and a P1: a resumed HITL run is a NEW
``agent_runs`` row with no inbound message stamped on it, so
``load_intake_thread_for_run`` fell through to its layer-2 heuristic ("the newest
inbound processed by ANY run on this conversation") and — on a conversation holding
several intake threads (ADR-F088 layer 2/3) — bound the resume to the WRONG thread.
Seen twice on dev: an approved draft on the thread that was paused was refused by
the delivered-row guard because the binding had landed on a sibling thread that had
already replied. Two lawyer approvals were consumed and nothing was sent.

The fix is a fact instead of a guess: the resume endpoint records WHICH run it is
resuming, and the binder follows that link (through a chain of resumes) to the
message its ancestor actually claimed. ``SET NULL`` on delete — losing the parent
row costs the link, never the run. No backfill: historic resumes stay NULL and fall
through to the legacy heuristic exactly as before.

Reversible: the downgrade drops the CHECK, the FK and both columns (the naming
provenance is re-derivable only for intake rows, which is why the upgrade is the
interesting direction).

Revision ID: 0103
Revises: 0102
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

_NAME_SOURCES = ("subject", "agent", "human")
_SQL_NAME_SOURCES = ",".join(f"'{value}'" for value in _NAME_SOURCES)


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "name_source",
            sa.String(length=16),
            nullable=False,
            server_default="human",
        ),
    )
    # The intake-born rows were named from the email subject at ingest — that is
    # their provenance, and it is what makes them replaceable by the agent's own
    # title. Everything else stays 'human' (see the module docstring). Known and
    # accepted (N10): an intake-born matter a human renamed BEFORE this column
    # existed is indistinguishable from one still carrying its subject, so it is
    # marked 'subject' and the thread's next run may overwrite that name once. There
    # is no record anywhere of who typed those names; a later human rename re-pins
    # it permanently.
    op.execute("UPDATE projects SET name_source = 'subject' WHERE intake_state = 'candidate'")
    op.create_check_constraint(
        "chk_projects_name_source",
        "projects",
        f"name_source IN ({_SQL_NAME_SOURCES})",
    )

    # --- fix D: the resume's parent link -----------------------------------
    op.add_column(
        "agent_runs",
        sa.Column("resumed_from_run_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_resumed_from_run_id",
        "agent_runs",
        "agent_runs",
        ["resumed_from_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # The binder walks this link on EVERY intake run's composition (and the safe-fail
    # hook walks it again), and a self-referential FK gets no index for free. Small
    # and mostly NULL, so it costs nothing to keep.
    op.create_index("ix_agent_runs_resumed_from_run_id", "agent_runs", ["resumed_from_run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_resumed_from_run_id", table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_resumed_from_run_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "resumed_from_run_id")
    op.drop_constraint("chk_projects_name_source", "projects", type_="check")
    op.drop_column("projects", "name_source")
