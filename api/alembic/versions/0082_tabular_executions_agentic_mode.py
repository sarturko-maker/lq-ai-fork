"""tabular executions — agentic mode + matter scope + run provenance + fill mode (ADR-F055)

Additive columns on ``tabular_executions`` so the SAME table backs both the frozen
linear executor (M3-C2) and the new agentic "grids" tool (F2 Tabular T1). No existing
column/row is touched; every default keeps the linear path byte-identical.

* ``mode`` — 'linear' (the frozen ARQ executor) | 'agentic' (the deepagents tool).
  DEFAULT 'linear', so every existing row + every ``POST /tabular/execute`` row is
  unchanged. Agentic grids are created in-run by the tool; the frozen worker refuses
  an 'agentic' row defensively (it is only ever enqueued for linear ids).
* ``project_id`` — the matter an agentic grid belongs to (ADR-F035 matter scope; the
  Grids-tab listing keys off it). NULL for linear rows (upstream scopes them by
  user + ``document_ids``). ON DELETE SET NULL — never cascade-delete a work product.
* ``created_by_run_id`` — the agent run that produced an agentic grid (provenance,
  ADR-F046; mirrors ``files.created_by_run_id``). NULL for linear rows.
* ``fill_mode`` — 'fanout' (one subagent per doc) | 'retrieval' (batched-row retrieval):
  which engine filled an agentic grid (ADR-F055 crossover). NULL for linear rows.

Revision ID: 0082
Revises: 0081
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FK constraints are NAMED to match the ORM (TabularExecution) so DB and model agree.
    op.execute(
        """
        ALTER TABLE tabular_executions
            ADD COLUMN mode TEXT NOT NULL DEFAULT 'linear',
            ADD COLUMN project_id UUID,
            ADD COLUMN created_by_run_id UUID,
            ADD COLUMN fill_mode TEXT,
            ADD CONSTRAINT chk_tabular_executions_mode
                CHECK (mode IN ('linear', 'agentic')),
            ADD CONSTRAINT chk_tabular_executions_fill_mode
                CHECK (fill_mode IS NULL OR fill_mode IN ('fanout', 'retrieval')),
            ADD CONSTRAINT fk_tabular_executions_project_id
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            ADD CONSTRAINT fk_tabular_executions_created_by_run_id
                FOREIGN KEY (created_by_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL
        """
    )
    # Partial index for the per-matter Grids listing (agentic rows only) — keeps the
    # frozen linear read paths untouched (they never filter on project_id).
    op.execute(
        """
        CREATE INDEX ix_tabular_executions_agentic_project
            ON tabular_executions (project_id)
            WHERE mode = 'agentic'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tabular_executions_agentic_project")
    op.execute(
        """
        ALTER TABLE tabular_executions
            DROP CONSTRAINT IF EXISTS fk_tabular_executions_created_by_run_id,
            DROP CONSTRAINT IF EXISTS fk_tabular_executions_project_id,
            DROP CONSTRAINT IF EXISTS chk_tabular_executions_fill_mode,
            DROP CONSTRAINT IF EXISTS chk_tabular_executions_mode,
            DROP COLUMN IF EXISTS fill_mode,
            DROP COLUMN IF EXISTS created_by_run_id,
            DROP COLUMN IF EXISTS project_id,
            DROP COLUMN IF EXISTS mode
        """
    )
