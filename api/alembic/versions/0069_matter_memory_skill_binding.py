"""Bind the matter-memory skill to every practice area — C3a (fork, ADR-F042)

Pure-data: bind the ``matter-memory`` curated skill (``skills/matter-memory/SKILL.md``)
to every standard practice area by default (``practice_area_skills`` m2m, ADR-F016 — a
by-name reference into the one in-memory registry; content never copied). Matter memory
is area-agnostic (the agent auto-maintains a matter wiki for every area — "deal context"
in Commercial, "Programme memory" in Privacy), so the curation skill that teaches *how*
to keep that wiki belongs to all of them.

Idempotent (0056/0067 precedent): the ``NOT EXISTS`` guard makes a re-run a no-op and
never disturbs an operator-attached skill. Downgrade removes only the pairs this
migration seeds; a user-attached binding survives.

Revision ID: 0069
Revises: 0068
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

_SKILL_NAME = "matter-memory"
# Every standard area (migrations 0053/0054). Matter memory is area-agnostic.
_AREA_KEYS = ("commercial", "privacy", "m-and-a", "disputes", "employment")


def upgrade() -> None:
    conn = op.get_bind()
    for key in _AREA_KEYS:
        conn.execute(
            sa.text(
                # CAST(:skill AS VARCHAR): the param is both projected into
                # skill_name and compared in NOT EXISTS — without the cast asyncpg
                # deduces conflicting types for the one placeholder (0056 note).
                "INSERT INTO practice_area_skills (practice_area_id, skill_name) "
                "SELECT pa.id, CAST(:skill AS VARCHAR) FROM practice_areas pa "
                "WHERE pa.key = :key AND NOT EXISTS ("
                "  SELECT 1 FROM practice_area_skills s "
                "  WHERE s.practice_area_id = pa.id AND s.skill_name = CAST(:skill AS VARCHAR)"
                ")"
            ),
            {"skill": _SKILL_NAME, "key": key},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key in _AREA_KEYS:
        conn.execute(
            sa.text(
                "DELETE FROM practice_area_skills "
                "WHERE skill_name = :skill AND practice_area_id = ("
                "  SELECT id FROM practice_areas WHERE key = :key"
                ")"
            ),
            {"skill": _SKILL_NAME, "key": key},
        )
