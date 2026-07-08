"""agent_runs.resume_decision — the human's HITL resume choice on the follow-up run
(ADR-F071, HITL-2)

One additive, nullable column. A resume of a paused (``awaiting_input``) run is a NEW
``agent_runs`` row on the same thread (run-per-resume; the paused run keeps its intact lease
and stays ``awaiting_input``). The worker only ever receives ``run_id`` and reads everything
else from the row, so the human's decision must be DURABLE on that new row:

* ``resume_decision`` — JSONB, NULL for every ordinary run. Its PRESENCE is the "this run is
  a resume" flag the composition point keys off; its value is the closed-enum decision the
  endpoint validated: ``{"type": "approve"}`` or ``{"type": "reject", "message": <str|null>}``.
  The runner re-reads the paused thread's pending interrupt(s) from ``aget_state`` at resume
  time and fans this ONE decision across the interrupt's action_requests to build
  ``Command(resume=…)`` — it never stores a langgraph-internal interrupt id in our schema.

No CHECK (dict-typed at the ORM/schema boundary; a malformed value degrades the run to
``failed`` in the runner, never raises — mirrors HITL-1's ``hitl_policy`` posture). No index
(read only by the executing worker via the run's PK).

Downgrade: drop the column. Deliberately no data migration — a NULL-or-decision column
carries nothing the older schema cannot lose (any in-flight resume run simply loses its
decision and the orphan sweep / a fresh resume recovers it).

Revision ID: 0094
Revises: 0093
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADR-F071 (HITL-2): the human's resume choice on a run-per-resume follow-up row.
    # NULL for ordinary runs; presence marks the run as a resume (composition keys off it).
    op.execute("ALTER TABLE agent_runs ADD COLUMN resume_decision JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS resume_decision")
