"""Bind the ``adversarial-review`` craft skill to Commercial — ADV-1 (ADR-F084)

The hostile-reader tool (``adversarial_review``) rides the redlining tool group, so its
AVAILABILITY needs no data change. This migration ships the CRAFT half: the
``skills/adversarial-review`` skill (when to OFFER the pass, how to weigh its findings) is bound to
Commercial the way every shipped Commercial skill is (0067/0072/0083 pattern), and — post-Library
(ADR-F065) — adopted into ``org_library_entries`` for an EXISTING deployment so the binding is not
inert on upgrade day (the G13 failure class: bound-but-not-adopted = silent capability loss). A
fresh org (no users at migrate time — the 0088 gate) starts with an empty Library and gets both the
binding and the adoption from the Commercial profile apply (B-7a), which reads the same manifest
this slice updates.

Idempotent (0056/0083 precedent): NOT-EXISTS inserts, so a re-run never duplicates and an
operator-removed adoption is re-added only by re-running the migration (not by app code).
Downgrade removes only this exact pair + this exact Library row.

Revision ID: 0097
Revises: 0096
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

_AREA_KEY = "commercial"
_SKILL_NAME = "adversarial-review"


def upgrade() -> None:
    conn = op.get_bind()
    # Bind to Commercial (only where the seeded area exists; CAST — the 0056 asyncpg
    # one-placeholder-two-types trap).
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
    # Users-empty gate (0088 posture): an existing deployment adopts the shipped skill so
    # the new binding resolves on upgrade day; a fresh org's Library stays empty (profile
    # apply adopts it there).
    has_users = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM users)")).scalar()
    if has_users:
        conn.execute(
            sa.text(
                "INSERT INTO org_library_entries (capability_kind, capability_key) "
                "SELECT 'skill', CAST(:skill AS TEXT) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM org_library_entries e "
                "  WHERE e.capability_kind = 'skill' "
                "    AND e.capability_key = CAST(:skill AS TEXT)"
                ")"
            ),
            {"skill": _SKILL_NAME},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM org_library_entries "
            "WHERE capability_kind = 'skill' AND capability_key = :skill"
        ),
        {"skill": _SKILL_NAME},
    )
    conn.execute(
        sa.text(
            "DELETE FROM practice_area_skills "
            "WHERE skill_name = :skill AND practice_area_id = ("
            "  SELECT id FROM practice_areas WHERE key = :key"
            ")"
        ),
        {"skill": _SKILL_NAME, "key": _AREA_KEY},
    )
