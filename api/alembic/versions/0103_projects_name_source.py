"""INTAKE-5a.1 — who named this matter: projects.name_source (ADR-F042 / ADR-F086)

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

Reversible: the downgrade drops the CHECK and the column (the naming provenance is
re-derivable only for intake rows, which is why the upgrade is the interesting
direction).

Revision ID: 0103
Revises: 0102
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

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
    # title. Everything else stays 'human' (see the module docstring).
    op.execute("UPDATE projects SET name_source = 'subject' WHERE intake_state = 'candidate'")
    op.create_check_constraint(
        "chk_projects_name_source",
        "projects",
        f"name_source IN ({_SQL_NAME_SOURCES})",
    )


def downgrade() -> None:
    op.drop_constraint("chk_projects_name_source", "projects", type_="check")
    op.drop_column("projects", "name_source")
