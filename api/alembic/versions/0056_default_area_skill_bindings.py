"""Default practice-area skill bindings — UX-B-3 (fork, ADR-F015/F016)

Bind a small, focused set of relevant skills to each standard area by default,
so an area's Deep Agent lands with the skills its work calls for (the maintainer
steer: "relevant skills land in each area agent by default; users are free to
add more"). The skill *content* is never copied — these are by-name references
into the one in-memory skill registry (``practice_area_skills`` m2m, ADR-F016:
one library, no duplication). At run time the composition point exposes ONLY the
area's bound subset to the agent through a read-only registry-backed backend
(``app/agents/skill_backend.py``); a bound name the registry no longer knows is
simply dropped (drift).

Focused on purpose: an agent shown the *whole* library gets confused (maintainer
note), so each area gets the few skills that match its unit of work — not the
catalogue. Cross-cutting/meta skills (``enhance-prompt``, ``skill-creator``,
``playbook-easy-extract``, the ``*-snapshot`` grids, ``comms-improver``) stay
**user-attachable**, not seeded.

Idempotent (0053/0054/0055 check-before-write precedent): each (area, skill) pair
is inserted ONLY when absent, so re-running never duplicates and an
operator-attached skill is never disturbed. Downgrade removes only the exact
pairs this migration seeds — a user-attached skill survives a downgrade.

Revision ID: 0056
Revises: 0055
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


# area key -> default bound skill names (must exist as skill directories under
# skills/; the registry validates at attach time, the backend filters at run
# time). Kept deliberately small per area (avoid "too many skills" confusion).
_DEFAULT_BINDINGS: dict[str, tuple[str, ...]] = {
    "commercial": (
        "msa-review-commercial-purchase",
        "msa-review-saas",
        "contract-qa",
        "nda-review",
    ),
    "privacy": (
        "dpa-checklist-review",
        "vendor-privacy-policy-first-pass",
        "contract-qa",
    ),
    "m-and-a": (
        "nda-review",
        "contract-qa",
        "contract-snapshot",
    ),
    "disputes": (
        "contract-qa",
        "action-items-from-client-alert",
    ),
    "employment": (
        "contract-qa",
        "nda-review",
        "action-items-from-client-alert",
    ),
}


def upgrade() -> None:
    _seed_default_area_skill_bindings(op.get_bind())


def _seed_default_area_skill_bindings(conn: sa.engine.Connection) -> None:
    """Insert each default (area, skill) binding that is not already present.

    Module-level (not inlined) so the idempotency contract is unit-testable
    (tests/test_practice_areas.py). The ``NOT EXISTS`` guard makes a re-run a
    no-op and never overwrites an operator-attached skill; the join on ``key``
    resolves the area id, so a missing area key simply inserts nothing.
    """
    for key, skills in _DEFAULT_BINDINGS.items():
        for skill in skills:
            conn.execute(
                sa.text(
                    # CAST(:skill AS VARCHAR): the param is both projected into
                    # skill_name and compared in NOT EXISTS — without the cast
                    # asyncpg deduces conflicting types (text vs varchar) for
                    # the one placeholder and refuses to prepare the statement.
                    "INSERT INTO practice_area_skills (practice_area_id, skill_name) "
                    "SELECT pa.id, CAST(:skill AS VARCHAR) FROM practice_areas pa "
                    "WHERE pa.key = :key AND NOT EXISTS ("
                    "  SELECT 1 FROM practice_area_skills s "
                    "  WHERE s.practice_area_id = pa.id AND s.skill_name = CAST(:skill AS VARCHAR)"
                    ")"
                ),
                {"skill": skill, "key": key},
            )


def downgrade() -> None:
    # Remove only the pairs this migration seeds; a user-attached skill (any
    # pair not in _DEFAULT_BINDINGS) is untouched.
    conn = op.get_bind()
    for key, skills in _DEFAULT_BINDINGS.items():
        for skill in skills:
            conn.execute(
                sa.text(
                    "DELETE FROM practice_area_skills "
                    "WHERE skill_name = :skill AND practice_area_id = ("
                    "  SELECT id FROM practice_areas WHERE key = :key"
                    ")"
                ),
                {"skill": skill, "key": key},
            )
