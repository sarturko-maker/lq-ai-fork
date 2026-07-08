"""agent_runs awaiting_input + agent_run_steps hitl_request + practice_areas.hitl_policy
(ADR-F071, HITL-1)

Substrate for the B-6 human-in-the-loop pause. Three additive schema changes, each
mirroring an established pattern:

* ``chk_agent_runs_status`` (``0048``) widens to admit ``'awaiting_input'`` — the new
  SETTLED state a run parks in when a deepagents ``interrupt_on`` policy stops it BEFORE
  a gated tool executes (ADR-F071). It is written through the existing ``settle_run``
  fence, is sweep-exempt (the orphan rules only touch ``'running'``), and — in HITL-1 —
  the thread is LOCKED: a follow-up on it 409s until HITL-2 adds resume.
* ``chk_agent_run_steps_kind`` (``0048``) widens to admit ``'hitl_request'`` — the one
  step row that records the ask (the pending tool name + a display-only args digest);
  ADR-F004 "settled rows decide, streams animate".
* ``practice_areas.hitl_policy`` — a JSONB column mirroring ``agent_config`` (``0054``):
  ``NOT NULL DEFAULT '{}'``. The area's stop-and-ask policy (exact granted tool names ->
  ``true``), compiled at composition into ``interrupt_on`` intersected with the run's
  actual grant set. The shipped default ``{}`` IS the zero-config invariant: an
  unconfigured area attaches NO HITL middleware and its agent graph is byte-identical to
  today's. No write surface exists yet (HITL-3 adds the admin card + a 422 unknown-name
  guard); HITL-1 lands the column so the runner's pause detection ships together with the
  first possible policy write (a pause detected before this slice would mis-settle
  ``completed`` with a NULL answer, then the next run's repair would destroy it).

The two CHECKs re-add with 0048's exact IN-list formatting (no space after commas).

Downgrade posture (documented, deliberately LOSSY — mirrors 0092/0088): a row cannot
carry a value the re-narrowed CHECK forbids. Before re-narrowing we UPDATE any
``agent_runs`` at ``'awaiting_input'`` to ``'failed'`` (NOT delete — a run row's history +
its steps are audit-adjacent; deleting would cascade them) and DELETE the now-meaningless
``'hitl_request'`` step rows, then drop the column. There is deliberately no downgrade
round-trip test (same posture as 0092).

Migration numbering: chains off ``0092`` (head at branch time, B-3's
``practice_area_knowledge_bases``).

Revision ID: 0093
Revises: 0092
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

# Constraint names verbatim from 0048 (agent_runs / agent_run_steps) — reused so the DB
# and the AgentRunStatus / AgentRunStepKind StrEnums (schemas/agent_runs.py) stay in
# agreement. 0048's IN-lists have no space after commas; preserved on re-add.
_CHK_STATUS = "chk_agent_runs_status"
_CHK_STATUS_HITL = (
    "CHECK (status IN ('running','completed','failed','cancelled','cap_exceeded','awaiting_input'))"
)
_CHK_STATUS_PRE_0093 = (
    "CHECK (status IN ('running','completed','failed','cancelled','cap_exceeded'))"
)
_CHK_KIND = "chk_agent_run_steps_kind"
_CHK_KIND_HITL = "CHECK (kind IN ('model_turn','tool_call','tool_result','hitl_request'))"
_CHK_KIND_PRE_0093 = "CHECK (kind IN ('model_turn','tool_call','tool_result'))"


def upgrade() -> None:
    op.execute(f"ALTER TABLE agent_runs DROP CONSTRAINT {_CHK_STATUS}")
    op.execute(f"ALTER TABLE agent_runs ADD CONSTRAINT {_CHK_STATUS} {_CHK_STATUS_HITL}")
    op.execute(f"ALTER TABLE agent_run_steps DROP CONSTRAINT {_CHK_KIND}")
    op.execute(f"ALTER TABLE agent_run_steps ADD CONSTRAINT {_CHK_KIND} {_CHK_KIND_HITL}")
    # ADR-F071: the area's stop-and-ask policy. Mirrors agent_config (0054): JSONB NOT NULL
    # DEFAULT '{}'. The default '{}' IS the zero-config invariant (no HITL middleware).
    op.execute(
        "ALTER TABLE practice_areas ADD COLUMN hitl_policy JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE practice_areas DROP COLUMN IF EXISTS hitl_policy")
    # Lossy narrowing (see docstring): an 'awaiting_input' run cannot satisfy the restored
    # CHECK, so it is failed in place (never deleted — preserve the run + its steps), and
    # the now-unrepresentable 'hitl_request' step rows are dropped.
    op.execute(
        "UPDATE agent_runs SET status='failed', "
        "error='downgraded: awaiting_input no longer representable' "
        "WHERE status='awaiting_input'"
    )
    op.execute(f"ALTER TABLE agent_runs DROP CONSTRAINT {_CHK_STATUS}")
    op.execute(f"ALTER TABLE agent_runs ADD CONSTRAINT {_CHK_STATUS} {_CHK_STATUS_PRE_0093}")
    op.execute("DELETE FROM agent_run_steps WHERE kind='hitl_request'")
    op.execute(f"ALTER TABLE agent_run_steps DROP CONSTRAINT {_CHK_KIND}")
    op.execute(f"ALTER TABLE agent_run_steps ADD CONSTRAINT {_CHK_KIND} {_CHK_KIND_PRE_0093}")
