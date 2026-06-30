"""agent_runs.budget_profile — per-run cost/effort envelope (ADR-F053, Slice O)

Persists the run's chosen budget profile (economy / balanced / generous) so the
worker — which is enqueued with only the run id and reads ``agent_runs`` columns
directly — can resolve the four-brake envelope (token budget, fan-out quota, max
steps, wall clock) at composition time. **Additive and non-destructive:** a single
nullable ``TEXT`` column; legacy rows stay NULL and are treated as ``balanced`` by
``app.agents.budget.resolve_envelope``.

Revision ID: 0080
Revises: 0079
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs ADD COLUMN budget_profile TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS budget_profile")
