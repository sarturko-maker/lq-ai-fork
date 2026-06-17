"""Commercial document-researcher subagent — UX-B-4 (fork, ADR-F010/F015/F017)

Populate the first live declarative subagent. Commercial's ``agent_config``
(empty since F1-S3) gains ONE subagent — a general **document-researcher** the
lead agent fans out to on-demand for complex, multi-document matters. It is NOT
a pipeline stage: deepagents exposes a ``task`` tool and the lead model decides
when to delegate (read a single NDA directly; spawn researchers for a complex
RFQ across many documents — the Claude-Code-for-legal posture). The subagent:

* carries NO ``model`` key — it inherits the gateway-bound parent instance
  (ADR-F010; a provider string would bypass the Inference Gateway). The
  ``build_deep_agent`` seam re-asserts this.
* carries NO ``tools`` key — it inherits the parent's guarded matter tools
  (``search_documents``/``read_document``), each still mediated by the
  ``guarded_dispatch`` chokepoint.
* declares ``skills`` as NAMES, a subset of Commercial's bound skills (0056:
  ``contract-qa``/``nda-review``). At composition the wiring (ADR-F017) gives
  the subagent its OWN isolated virtual source exposing only that subset —
  deepagents' per-subagent skill isolation. No credentials anywhere
  (NORTH-STAR inv 3).

Idempotent (0055 check-before-write precedent): written ONLY where Commercial's
``agent_config`` is still empty (``'{}'``), so re-running never clobbers an
operator edit. The symmetric downgrade resets it to ``'{}'`` only while it still
equals the seeded value verbatim.

Revision ID: 0057
Revises: 0056
Create Date: 2026-06-17
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_COMMERCIAL_KEY = "commercial"

# The declarative subagent spec. Plain operator-editable data; the admin PATCH
# (shape-validated by the area renderer, ADR-F010/F017) can replace it.
_COMMERCIAL_AGENT_CONFIG: dict[str, object] = {
    "subagents": [
        {
            "name": "document-researcher",
            "description": (
                "Investigate a specific question across the matter's documents and report "
                "findings with citations. Delegate to this researcher when the matter has many "
                "documents or several independent questions, so investigations run in parallel "
                "and the main thread stays focused. For a single short document, read it "
                "directly instead."
            ),
            "system_prompt": (
                "You are a document researcher on a commercial legal matter. You are handed one "
                "focused question to investigate across the matter's documents. Use "
                "search_documents to find relevant passages and read_document to read a document "
                "in full. Quote what you find with the document name and page, and ground every "
                "statement in a tool result; if the documents do not answer the question, say so "
                "plainly rather than guessing. Report your findings concisely back to the lead "
                "agent — do NOT write the final client-facing answer or advice; that is the lead "
                "agent's job."
            ),
            "skills": ["contract-qa", "nda-review"],
        }
    ]
}


def upgrade() -> None:
    _seed_commercial_subagent(op.get_bind())


def _seed_commercial_subagent(conn: sa.engine.Connection) -> None:
    """Set Commercial's ``agent_config`` to the researcher spec — idempotently.

    Module-level (not inlined) so the idempotency contract is unit-testable
    (tests/test_practice_areas.py). Writes ONLY where ``agent_config`` is still
    the empty default ``'{}'``, so re-running on an operator-edited database
    never overwrites a deliberate change (0055 check-before-write precedent).
    """
    conn.execute(
        sa.text(
            "UPDATE practice_areas "
            "SET agent_config = CAST(:cfg AS jsonb) "
            "WHERE key = :key AND agent_config = '{}'::jsonb"
        ),
        {"cfg": json.dumps(_COMMERCIAL_AGENT_CONFIG), "key": _COMMERCIAL_KEY},
    )


def downgrade() -> None:
    # Reverse only if Commercial still carries the seeded spec verbatim — restore
    # the empty default, never silently dropping an operator edit.
    op.get_bind().execute(
        sa.text(
            "UPDATE practice_areas "
            "SET agent_config = '{}'::jsonb "
            "WHERE key = :key AND agent_config = CAST(:cfg AS jsonb)"
        ),
        {"cfg": json.dumps(_COMMERCIAL_AGENT_CONFIG), "key": _COMMERCIAL_KEY},
    )
