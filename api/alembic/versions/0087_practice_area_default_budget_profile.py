"""practice_areas.default_budget_profile — per-area budget default (ADR-F063, SETUP-5a)

One additive nullable column: the practice area's default ``budget_profile`` for
new agent runs. Resolution order at run create (ADR-F063): run-explicit >
area default (this column) > deployment default (``RUN_DEFAULT_BUDGET_PROFILE``)
> ``balanced``. NULL = "no area default — inherit the deployment default".
Mirrors the ``default_tier_floor`` per-area-default precedent (0054): nullable,
named CHECK, no server default, no index (the table is a bounded curated set).

**Additive and non-destructive.** No existing column/row is touched; every
existing area stays NULL (inherits) until an admin sets a default.

Migration numbering: chains off ``0086`` (main head). The AIC branches carry
their own incompatible migrations on a different lineage — they renumber on
rebase; do not reconcile.

Revision ID: 0087
Revises: 0086
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE practice_areas
        ADD COLUMN default_budget_profile TEXT,
        ADD CONSTRAINT chk_practice_areas_budget_profile CHECK (
            default_budget_profile IS NULL
            OR default_budget_profile IN ('economy', 'balanced', 'generous')
        )
        """
    )


def downgrade() -> None:
    # Dropping the column drops its CHECK constraint with it.
    op.execute("ALTER TABLE practice_areas DROP COLUMN IF EXISTS default_budget_profile")
