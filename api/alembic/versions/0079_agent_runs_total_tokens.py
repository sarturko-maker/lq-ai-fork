"""agent_runs.total_tokens — per-run token usage (ADR-F051 follow-up, Slice G)

Persists the cumulative model-token total the runner already computes for the R4
per-run token-budget brake (ADR-F051), so a settled run's actual spend is queryable
(observability + calibrating ``run_token_budget``). **Additive and non-destructive:**
a single nullable ``INTEGER`` column; the existing ``cost_usd`` column (mig 0048, still
NULL — dollars need the gateway's per-call cost, a separate concern) is untouched.

Revision ID: 0079
Revises: 0078
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs ADD COLUMN total_tokens INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS total_tokens")
