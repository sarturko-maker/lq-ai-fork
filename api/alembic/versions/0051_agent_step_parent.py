"""agent_run_steps.parent_step_id — F0-S7 (fork, ADR-F002/F004)

Subagent identity for deep-agent steps: a step that ran underneath a
tool invocation (the deepagents ``task`` subagent tool, or any
tool-wrapped middleware graph) points at the settled ``tool_call`` step
row of its innermost ancestor tool. Root-loop steps stay NULL.

The runner has computed this ancestry since F0-S2 (``parent_ids`` on
astream_events v2) but only used it to decide finality and DROPPED it at
persist time — so fan-out rendered as an undifferentiated flat stream,
F1's subagent tree had no data, and S9's subagent eval nothing
observable (agentic-UX audit, 2026-06-11).

No backfill: pre-S7 rows keep NULL honestly — their ancestry was never
recorded, and inventing one from event-order heuristics would violate
the settled-rows-decide contract (ADR-F004).

Revision ID: 0051
Revises: 0050
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_run_steps",
        sa.Column(
            "parent_step_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "agent_run_steps.id",
                ondelete="CASCADE",
                name="fk_agent_run_steps_parent_step_id",
            ),
            nullable=True,
        ),
    )
    # Subagent-tree reads: children of one dispatch. Partial — the
    # common root-loop rows don't pay for it.
    op.create_index(
        "idx_agent_run_steps_parent",
        "agent_run_steps",
        ["parent_step_id"],
        postgresql_where=sa.text("parent_step_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_agent_run_steps_parent", table_name="agent_run_steps")
    op.drop_column("agent_run_steps", "parent_step_id")
