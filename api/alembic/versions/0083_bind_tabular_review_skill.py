"""Bind the ``tabular-review`` craft skill to Commercial — F2 Tabular T3 (ADR-F055)

The T1/T2 grid capability is discoverable only through the standing
``TABULAR_FILL_DOCTRINE`` prose. T3 adds a craft skill (``skills/tabular-review/``,
ADR-F041) that teaches the agent to PROACTIVELY offer a grid, map natural language
onto ``start_tabular_review`` columns, carry column templates, and — as importantly
— stay quiet when a grid does not fit. Binding it to Commercial makes it a
per-matter capability (default-on, toggleable via ADR-F054); the skill *content*
lives in the one registry (by-name reference, no duplication).

Idempotent (0056 precedent): the (commercial, tabular-review) pair is inserted
ONLY when absent, so a re-run never duplicates and an operator-attached skill is
never disturbed. Downgrade removes only this exact pair.

Revision ID: 0083
Revises: 0082
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

_AREA_KEY = "commercial"
_SKILL_NAME = "tabular-review"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            # CAST(:skill AS VARCHAR): the param is projected into skill_name AND
            # compared in NOT EXISTS — without the cast asyncpg deduces conflicting
            # types for the one placeholder and refuses to prepare (0056 note).
            "INSERT INTO practice_area_skills (practice_area_id, skill_name) "
            "SELECT pa.id, CAST(:skill AS VARCHAR) FROM practice_areas pa "
            "WHERE pa.key = :key AND NOT EXISTS ("
            "  SELECT 1 FROM practice_area_skills s "
            "  WHERE s.practice_area_id = pa.id AND s.skill_name = CAST(:skill AS VARCHAR)"
            ")"
        ),
        {"skill": _SKILL_NAME, "key": _AREA_KEY},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM practice_area_skills "
            "WHERE skill_name = :skill AND practice_area_id = ("
            "  SELECT id FROM practice_areas WHERE key = :key"
            ")"
        ),
        {"skill": _SKILL_NAME, "key": _AREA_KEY},
    )
