"""files.summary / summary_updated_at / summary_run_id — per-document agent summaries
(WORKSPACE-1, ADR-F082)

Three additive, nullable columns on ``files``. After the agent reads a document it records a
short summary against the file (auto-write-then-correct, ADR-F042 discipline) so future runs —
and the lawyer, in the Documents panel — recognise a document by content, not just filename.

* ``summary`` — TEXT, NULL until the agent has read + summarised the file. Bounded at the write
  boundary (``app.schemas.document_summary.DOCUMENT_SUMMARY_MAX_CHARS``), not by a DB CHECK:
  reject-not-truncate lives in the Pydantic write boundary, mirroring the matter-wiki write.
* ``summary_updated_at`` — TIMESTAMPTZ, when the summary was last written.
* ``summary_run_id`` — the agent run that last wrote the summary; ``SET NULL`` on run delete keeps
  the summary (it outlives the run record, exactly like ``created_by_run_id``).

Exact-duplicate detection needs NO new column — it is computed at read time from the existing
``files.hash_sha256`` (grouped within a matter, owner-scoped), so a stored dup edge can never go
stale and the agent can never forge one.

Downgrade: drop the FK + the three columns. No data migration — a NULL-or-summary column carries
nothing the older schema cannot lose.

Revision ID: 0096
Revises: 0095
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # WORKSPACE-1 (ADR-F082): per-document agent summary + when/which-run wrote it.
    op.execute("ALTER TABLE files ADD COLUMN summary TEXT")
    op.execute("ALTER TABLE files ADD COLUMN summary_updated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE files ADD COLUMN summary_run_id UUID")
    op.execute(
        "ALTER TABLE files ADD CONSTRAINT fk_files_summary_run_id "
        "FOREIGN KEY (summary_run_id) REFERENCES agent_runs (id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE files DROP CONSTRAINT IF EXISTS fk_files_summary_run_id")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS summary_run_id")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS summary_updated_at")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS summary")
