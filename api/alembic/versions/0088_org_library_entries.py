"""org library entries — adopt-in capability availability (ADR-F065, STORE-1)

Replaces the Level-0 disable-only ``deployment_capability_toggles`` (ADR-F062, superseded)
with an adopt-in **Org Library**. A capability (skill name / tool-group key /
``playbook_id::text``) is AVAILABLE to any practice area's runs ONLY if a row here adopts
it — absence is the single off-state ("not in your Library"). ``build_area_inventory``
intersects an area's bindings with Library membership at the one fail-closed chokepoint
(ADR-F065 D3); bind-time validation rejects binding a non-adopted capability (D4). Grants
stay CODE — the ADR-F062 invariant is untouched; the Library only NARROWS availability,
adopt-in instead of disable-out (D1).

Toggle supersession — DROP, not repurpose (implementer's call, ADR-F065 D2; recorded in the
F065 addendum). Repurposing saves nothing: the polarity inverts (a toggle row means
"disabled"; a Library row means "adopted") and the shape changes (no ``enabled`` column), so
no data carries over — a rename would leave every existing ``enabled=false`` row meaning the
OPPOSITE of a Library membership. The seed below reads the toggle table's disabled set once
(to preserve effective state), then ``upgrade()`` DROPs the table. ``downgrade()`` recreates
it EMPTY — this is LOSSY (the seeded Library does not round-trip back into disable rows;
there is deliberately no downgrade round-trip test) and drops ``org_library_entries``.

Seed-from-effective-state (ADR-F065 D2/D4) — the load-bearing subtlety:

* **Fresh deployment** (brand-new org): the Library starts EMPTY (maintainer decision 3).
  Discriminator: at THIS migration's execution time a fresh stack has ZERO rows in ``users``
  (first-run bootstrap mints the operator/admin in the app lifespan AFTER migrations run); an
  existing deployment upgrading always has users. So ``upgrade()`` gates on
  ``EXISTS (SELECT 1 FROM users)`` — empty ⇒ skip the seed; non-empty ⇒ run it.
* **Existing deployment** (upgrade day): the seed adopts exactly "bound anywhere ∧ not
  explicitly disabled" so nothing changes behaviour on upgrade day (maintainer decision 4) —
  every area's currently-resolving skills/tools/playbooks stay resolving. Sources are the
  binding tables ONLY (no tool-group registry knowledge — AIC adds a group on its branch, and
  a pure-SQL seed cannot read the code registry anyway); a bound name the registry no longer
  knows becomes a harmless ORPHAN Library row under the established drift-drop posture
  (``build_area_inventory`` drops it at resolve time), so the skipped registry intersection
  is deliberate and safe.

``_seed`` is module-level + idempotent (NOT-EXISTS inserts) so the test suite can call it
directly (conftest emulates an upgraded deployment; tests/test_practice_areas.py pins
idempotency). It is resilient to ``deployment_capability_toggles`` being ABSENT
(``to_regclass`` probe — when gone, treat as "nothing disabled") because it runs on a
fully-migrated DB where the table has already been dropped. Seeded rows carry
``adopted_by = NULL``.

Migration numbering: chains off ``0087`` (main head). The AIC branches carry their own
incompatible lineage — they renumber on rebase; do not reconcile.

Revision ID: 0088
Revises: 0087
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE org_library_entries (
            capability_kind TEXT NOT NULL,
            capability_key TEXT NOT NULL,
            adopted_by UUID,
            adopted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_org_library_entries
                PRIMARY KEY (capability_kind, capability_key),
            CONSTRAINT fk_org_library_entries_adopted_by
                FOREIGN KEY (adopted_by) REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT chk_org_library_entries_kind
                CHECK (capability_kind IN ('skill', 'tool', 'playbook')),
            CONSTRAINT chk_org_library_entries_key_len
                CHECK (char_length(capability_key) BETWEEN 1 AND 200)
        )
        """
    )
    conn = op.get_bind()
    # Users-empty gate: a fresh org (no users yet — bootstrap runs AFTER migrations) starts
    # with an EMPTY Library; an existing deployment (always has users) seeds from its current
    # effective state so upgrade day changes nothing (ADR-F065 D2, decisions 3 & 4).
    has_users = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM users)")).scalar()
    if has_users:
        _seed(conn)
    # Supersession: read the toggle table's disabled set in the seed above, THEN drop it.
    op.execute("DROP TABLE IF EXISTS deployment_capability_toggles")


def _seed(conn: sa.engine.Connection) -> None:
    """Adopt every capability that is bound anywhere and not explicitly disabled.

    Idempotent (NOT-EXISTS guards make a re-run a no-op) and resilient to the superseded
    ``deployment_capability_toggles`` table being ABSENT — the ``to_regclass`` probe means the
    disabled-exclusion clause is emitted only while the table exists (during ``upgrade()`` it
    still does; on a fully-migrated DB it has been dropped, so "nothing disabled"). No bound
    parameters are used: kinds are SQL literals and keys come from the binding tables, so the
    asyncpg conflicting-type deduction (the 0086 CAST trap) cannot arise here.
    """
    toggles_present = (
        conn.execute(sa.text("SELECT to_regclass('deployment_capability_toggles')")).scalar()
        is not None
    )

    def _not_disabled(kind: str, key_expr: str) -> str:
        if not toggles_present:
            return ""
        return (
            " AND NOT EXISTS ("
            "  SELECT 1 FROM deployment_capability_toggles d"
            f"  WHERE d.capability_kind = '{kind}' AND d.capability_key = {key_expr}"
            "    AND d.enabled = false"
            ")"
        )

    # Skills — every distinct name bound via practice_area_skills.
    conn.execute(
        sa.text(
            "INSERT INTO org_library_entries (capability_kind, capability_key) "
            "SELECT 'skill', src.skill_name "
            "FROM (SELECT DISTINCT skill_name FROM practice_area_skills) src "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM org_library_entries e "
            "  WHERE e.capability_kind = 'skill' AND e.capability_key = src.skill_name"
            ")" + _not_disabled("skill", "src.skill_name")
        )
    )

    # Tool groups — every distinct group_key bound via practice_area_tool_groups.
    conn.execute(
        sa.text(
            "INSERT INTO org_library_entries (capability_kind, capability_key) "
            "SELECT 'tool', src.group_key "
            "FROM (SELECT DISTINCT group_key FROM practice_area_tool_groups) src "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM org_library_entries e "
            "  WHERE e.capability_kind = 'tool' AND e.capability_key = src.group_key"
            ")" + _not_disabled("tool", "src.group_key")
        )
    )

    # Playbooks — every distinct non-deleted playbook bound via practice_area_playbooks;
    # the key is the UUID rendered AS TEXT (matching build_area_inventory's str(pb.id)).
    conn.execute(
        sa.text(
            "INSERT INTO org_library_entries (capability_kind, capability_key) "
            "SELECT 'playbook', src.pid "
            "FROM ("
            "  SELECT DISTINCT pap.playbook_id::text AS pid "
            "  FROM practice_area_playbooks pap "
            "  JOIN playbooks pb ON pb.id = pap.playbook_id AND pb.deleted_at IS NULL"
            ") src "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM org_library_entries e "
            "  WHERE e.capability_kind = 'playbook' AND e.capability_key = src.pid"
            ")" + _not_disabled("playbook", "src.pid")
        )
    )


def downgrade() -> None:
    # Drop the Library; recreate the superseded toggle table EMPTY (lossy — the seeded Library
    # does not round-trip; see the module docstring). Byte-matches 0086's DDL so a re-upgrade
    # to 0088 finds the table exactly as before.
    op.execute("DROP TABLE IF EXISTS org_library_entries")
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
