"""tool-group registry data + deployment capability toggles (ADR-F062, SETUP-4a)

Two additive tables for the config hierarchy Levels 0/1:

* ``practice_area_tool_groups`` — the area↔tool-group AVAILABILITY binding (Level 1),
  by group NAME. What a name RESOLVES to (the grant set, the builder, the ledger, the
  doctrine) stays CODE — the ``TOOL_GROUP_REGISTRY`` in ``app.agents.capabilities`` plus
  the per-group ``*_TOOL_NAMES`` frozensets are the source of truth. A table for the
  *grants* was rejected (ADR-F054 D1 rejected-option-2: it would force a seed that must
  byte-match today's grants forever). SETUP-4a (ADR-F062) supersedes F054-D1 by making
  tool *availability* DATA (so an admin-created area can be granted domain tools) while
  keeping grants/builders/ledgers CODE. Seeded (NAMES ONLY, idempotent) from today's map:
  ``commercial → {redlining, tabular}``, ``privacy → {ropa, assessment}``.

* ``deployment_capability_toggles`` — the deployment-wide (Level 0) on/off the org-admin
  writes. SPARSE (mirrors ``matter_capability_toggles`` minus ``project_id``): a row
  exists ONLY where the admin disabled a deployment capability; ``enabled=true`` rows are
  inert (absence already means available), so there is NO seed. Level 0 only NARROWS: an
  ``enabled=false`` row removes the capability from every area's AVAILABLE set at the one
  ``build_area_inventory`` chokepoint (panel, composition, skills, playbook tier).

**Additive and non-destructive.** No existing column/row is touched. FK constraints are
NAMED to match the ORM models (``PracticeAreaToolGroup`` / ``DeploymentCapabilityToggle``).
No standalone index on ``practice_area_tool_groups.practice_area_id``: the composite PK
btree ``(practice_area_id, group_key)`` already serves every "WHERE practice_area_id = ?"
read via its leftmost prefix (0081 reasoning).

Migration numbering: chains off ``0085`` (main head). The AIC branches carry their own
incompatible ``0086`` on a different lineage — they renumber on rebase; do not reconcile.

Revision ID: 0086
Revises: 0085
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


# area key -> the tool-group NAMES available to that area by default. NAMES ONLY — each
# must be an entry in ``app.agents.capabilities.TOOL_GROUP_REGISTRY`` (the code resolves a
# name to its grant set/builder/ledger). This reproduces the pre-slice per-area code map.
_SEED_TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "commercial": ("redlining", "tabular"),
    "privacy": ("ropa", "assessment"),
}


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE practice_area_tool_groups (
            practice_area_id UUID NOT NULL,
            group_key TEXT NOT NULL,
            attached_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_practice_area_tool_groups
                PRIMARY KEY (practice_area_id, group_key),
            CONSTRAINT fk_practice_area_tool_groups_area_id
                FOREIGN KEY (practice_area_id) REFERENCES practice_areas(id) ON DELETE CASCADE,
            CONSTRAINT chk_practice_area_tool_groups_key_len
                CHECK (char_length(group_key) BETWEEN 1 AND 200)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE deployment_capability_toggles (
            capability_kind TEXT NOT NULL,
            capability_key TEXT NOT NULL,
            enabled BOOLEAN NOT NULL,
            set_by UUID,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_deployment_capability_toggles
                PRIMARY KEY (capability_kind, capability_key),
            CONSTRAINT fk_deployment_capability_toggles_set_by
                FOREIGN KEY (set_by) REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT chk_deployment_capability_toggles_kind
                CHECK (capability_kind IN ('skill', 'tool', 'playbook')),
            CONSTRAINT chk_deployment_capability_toggles_key_len
                CHECK (char_length(capability_key) BETWEEN 1 AND 200)
        )
        """
    )
    _seed(op.get_bind())


def _seed(conn: sa.engine.Connection) -> None:
    """Insert each default (area, tool-group) binding that is not already present.

    Module-level (not inlined) so the idempotency contract is unit-testable
    (tests/test_practice_areas.py). The ``NOT EXISTS`` guard makes a re-run a no-op and
    never overwrites an admin-attached group; the join on ``key`` resolves the area id, so
    a missing area key simply inserts nothing (0053/0056 check-before-write precedent).
    """
    for key, groups in _SEED_TOOL_GROUPS.items():
        for group in groups:
            conn.execute(
                sa.text(
                    # CAST(:group AS VARCHAR): the param is both projected into group_key
                    # and compared in NOT EXISTS — without the cast asyncpg deduces
                    # conflicting types (text vs varchar) for the one placeholder and
                    # refuses to prepare the statement (0056 trap).
                    "INSERT INTO practice_area_tool_groups (practice_area_id, group_key) "
                    "SELECT pa.id, CAST(:group AS VARCHAR) FROM practice_areas pa "
                    "WHERE pa.key = :key AND NOT EXISTS ("
                    "  SELECT 1 FROM practice_area_tool_groups t "
                    "  WHERE t.practice_area_id = pa.id AND t.group_key = CAST(:group AS VARCHAR)"
                    ")"
                ),
                {"group": group, "key": key},
            )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deployment_capability_toggles")
    op.execute("DROP TABLE IF EXISTS practice_area_tool_groups")
