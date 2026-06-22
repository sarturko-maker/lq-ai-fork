"""Commercial surgical-redline craft: bind skill + refresh redline doctrine — C8 (fork, ADR-F041)

Two pure-data changes to the Commercial practice area; no schema change.

1. **Bind the ``surgical-redline`` curated skill** (``skills/surgical-redline/SKILL.md``)
   to the Commercial area by default (``practice_area_skills`` m2m, ADR-F016 — a
   by-name reference into the one in-memory registry, content never copied). The
   ``NOT EXISTS`` guard (0056 precedent) makes a re-run a no-op and never disturbs
   an operator-attached skill.

2. **Refresh the now-stale tail of the Commercial ``profile_md`` redline doctrine.**
   The 0066 doctrine closed its "Redline surgically" section with "a tracked-changes
   tool … lands in a later slice" — C4 shipped that tool (``apply_redline``), so this
   replaces that one paragraph with a pointer to the ``surgical-redline`` skill and
   the ``preview_redline`` / ``apply_redline`` tools plus the decompose-into-narrow-
   edits craft. **Never-clobber:** the ``REPLACE`` fires only where the verbatim 0066
   paragraph is still present (an operator edit to that paragraph is preserved); a
   re-run is a no-op (the paragraph now holds the new text).

Revision ID: 0067
Revises: 0066
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

_AREA_KEY = "commercial"
_SKILL_NAME = "surgical-redline"

# The verbatim 0066 closing paragraph of the "Redline surgically" section (the
# stored form, with the source's line-continuations resolved). ASCII-only, so it
# reproduces byte-exactly. If it is ever edited, REPLACE matches nothing and the
# refresh is a safe no-op (caught loudly by the doctrine-present test).
_OLD_REDLINE_TAIL = (
    "At this stage you propose redline language as text for the supervising lawyer to "
    "apply. A tracked-changes tool with an enforced surgical-edit gate lands in a "
    "later slice; the discipline above is how you propose edits now."
)

# The C8 replacement: point at the shipped tools + the surgical-redline skill and
# the decompose-into-narrow-edits craft (the §8 lesson).
_NEW_REDLINE_TAIL = (
    "Make these edits as native tracked changes with the surgical-redline skill and "
    "the preview_redline / apply_redline tools: decompose each clause into several "
    "narrow edits (swap a party, narrow a trigger, insert a carve-out) rather than "
    "striking and retyping the clause, keep recognisable boilerplate (verb phrases, "
    "defined terms) bare, and preview the rendered tracked changes before you apply. "
    "You propose; the supervising lawyer reviews and accepts each change."
)


def upgrade() -> None:
    conn = op.get_bind()
    _bind_surgical_redline_skill(conn)
    _refresh_redline_doctrine(conn)


def _bind_surgical_redline_skill(conn: sa.engine.Connection) -> None:
    """Insert the (commercial, surgical-redline) binding if absent (0056 pattern)."""
    conn.execute(
        sa.text(
            "INSERT INTO practice_area_skills (practice_area_id, skill_name) "
            "SELECT pa.id, CAST(:skill AS VARCHAR) FROM practice_areas pa "
            "WHERE pa.key = :key AND NOT EXISTS ("
            "  SELECT 1 FROM practice_area_skills s "
            "  WHERE s.practice_area_id = pa.id AND s.skill_name = CAST(:skill AS VARCHAR)"
            ")"
        ),
        {"skill": _SKILL_NAME, "key": _AREA_KEY},
    )


def _refresh_redline_doctrine(conn: sa.engine.Connection) -> None:
    """Replace the stale 0066 redline tail with the C8 tools/skill pointer.

    Module-level (not inlined) so the never-clobber contract is unit-testable. The
    ``POSITION`` guard means the UPDATE only touches a row still carrying the
    verbatim 0066 paragraph — an operator edit is preserved and a re-run is a no-op.
    """
    conn.execute(
        sa.text(
            "UPDATE practice_areas "
            "SET profile_md = REPLACE(profile_md, CAST(:old AS TEXT), CAST(:new AS TEXT)) "
            "WHERE key = :key AND POSITION(CAST(:old AS TEXT) IN profile_md) > 0"
        ),
        {"old": _OLD_REDLINE_TAIL, "new": _NEW_REDLINE_TAIL, "key": _AREA_KEY},
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Restore the 0066 tail for rows still carrying the C8 text verbatim.
    conn.execute(
        sa.text(
            "UPDATE practice_areas "
            "SET profile_md = REPLACE(profile_md, CAST(:new AS TEXT), CAST(:old AS TEXT)) "
            "WHERE key = :key AND POSITION(CAST(:new AS TEXT) IN profile_md) > 0"
        ),
        {"old": _OLD_REDLINE_TAIL, "new": _NEW_REDLINE_TAIL, "key": _AREA_KEY},
    )
    # Remove only the binding this migration seeds (a user binding survives).
    conn.execute(
        sa.text(
            "DELETE FROM practice_area_skills "
            "WHERE skill_name = :skill AND practice_area_id = ("
            "  SELECT id FROM practice_areas WHERE key = :key"
            ")"
        ),
        {"skill": _SKILL_NAME, "key": _AREA_KEY},
    )
