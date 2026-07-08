"""practice_area_knowledge_bases — knowledge-collection binding join + org_library_entries
'knowledge' kind (ADR-F067 D1, B-3)

D1 adds **knowledge collection** as the fourth Library kind: unlike skill/playbook it
authors nothing new and needs no propose/approve harness — a knowledge collection's
content reaches the model only as fenced RETRIEVED-DATA through a guarded read tool
(the B-3 ``search_knowledge`` tool group), never as instructions, so adoption + binding
IS the control (D1 "Two boundary calls", second bullet). This migration lands the two
additive pieces of schema that decision requires:

* ``practice_area_knowledge_bases`` — area <-> knowledge-collection AVAILABILITY
  binding. A straight clone of ``practice_area_playbooks`` (``0081``,
  ``app/models/practice_area.py:142-181``): composite PK
  ``(practice_area_id, knowledge_base_id)``, both FKs ``ON DELETE CASCADE`` (dropping
  an area drops its bindings; hard-deleting a KB — D6 territory, not exercised by the
  existing soft-delete-only API — drops the binding rather than leaving a dangling
  row), ``attached_at`` defaulting ``now()``. No CHECK beyond the FKs/PK: unlike
  ``practice_area_tool_groups``/``practice_area_skills`` the referenced id is a real
  FK, so there is no free-text key to length-bound.
* ``org_library_entries.chk_org_library_entries_kind`` (``0088``, ADR-F065) widens
  from ``('skill', 'tool', 'playbook')`` to include ``'knowledge'`` — the Library's
  adopt-in gate now recognises the new kind. The key stored for a knowledge entry is
  ``knowledge_bases.id::text`` (mirrors the playbook convention — the UUID PK cast to
  the existing free-text ``capability_key`` column, no schema change needed there).
* ``matter_capability_toggles.chk_matter_capability_toggles_kind`` (``0081``,
  ADR-F054) widens identically — the lawyer's per-matter panel toggles the new kind
  like any other, so the sparse-override table must admit ``'knowledge'`` rows
  (capability_key = ``knowledge_bases.id::text``). Mirrored in the
  ``MatterCapabilityToggle`` model's ``__table_args__``.

Downgrade posture (documented per the B-3 build contract's requirement — pick one):
this migration's ``downgrade()`` DELETES any ``org_library_entries`` rows with
``capability_kind = 'knowledge'`` before re-narrowing the CHECK to the 0088 three-kind
set, and any ``matter_capability_toggles`` rows with ``capability_kind = 'knowledge'``
before re-narrowing that table's CHECK to the 0081 three-kind set. This is
deliberately LOSSY (mirrors 0088's own downgrade posture, which drops
``org_library_entries`` outright) rather than raising: a downgrade that instead
refused whenever a knowledge row existed would just move the identical data-loss
decision onto whoever runs the downgrade, with no round-trip possible either way (a
'knowledge' row cannot be represented once the CHECK no longer admits it). Deleting
keeps the downgrade path mechanical and matches the established "downgrade is lossy,
not preserved" convention on this table. There is deliberately no downgrade
round-trip test (same posture as 0088).

Migration numbering: chains off ``0091`` (head at branch time, B-2a's
``org_skill_versions``).

Revision ID: 0092
Revises: 0091
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

_CHK_KIND_KNOWLEDGE = "CHECK (capability_kind IN ('skill', 'tool', 'playbook', 'knowledge'))"
_CHK_KIND_PRE_0092 = "CHECK (capability_kind IN ('skill', 'tool', 'playbook'))"

# Constraint names verbatim from 0088 (org_library_entries) and 0081
# (matter_capability_toggles) — reused so the ORM models and the DB stay in agreement.
_CHK_LIBRARY_KIND = "chk_org_library_entries_kind"
_CHK_TOGGLE_KIND = "chk_matter_capability_toggles_kind"


def upgrade() -> None:
    # Named constraints match the ORM model (PracticeAreaKnowledgeBase) so the DB and
    # the model agree — house convention (mirrors 0081's practice_area_playbooks).
    op.execute(
        """
        CREATE TABLE practice_area_knowledge_bases (
            practice_area_id UUID NOT NULL,
            knowledge_base_id UUID NOT NULL,
            attached_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_practice_area_knowledge_bases
                PRIMARY KEY (practice_area_id, knowledge_base_id),
            CONSTRAINT fk_practice_area_knowledge_bases_area_id
                FOREIGN KEY (practice_area_id) REFERENCES practice_areas(id) ON DELETE CASCADE,
            CONSTRAINT fk_practice_area_knowledge_bases_kb_id
                FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(f"ALTER TABLE org_library_entries DROP CONSTRAINT {_CHK_LIBRARY_KIND}")
    op.execute(
        f"ALTER TABLE org_library_entries ADD CONSTRAINT {_CHK_LIBRARY_KIND} {_CHK_KIND_KNOWLEDGE}"
    )
    # Widen the per-matter toggle CHECK identically (0081's constraint name verbatim) —
    # the lawyer's panel toggles kind='knowledge' like any other capability.
    op.execute(f"ALTER TABLE matter_capability_toggles DROP CONSTRAINT {_CHK_TOGGLE_KIND}")
    op.execute(
        f"ALTER TABLE matter_capability_toggles ADD CONSTRAINT {_CHK_TOGGLE_KIND} "
        f"{_CHK_KIND_KNOWLEDGE}"
    )


def downgrade() -> None:
    # Lossy narrowing (see module docstring): a 'knowledge' row cannot satisfy the
    # restored 3-kind CHECKs, so any such rows are deleted first rather than the
    # downgrade raising on their presence.
    op.execute("DELETE FROM matter_capability_toggles WHERE capability_kind = 'knowledge'")
    op.execute(f"ALTER TABLE matter_capability_toggles DROP CONSTRAINT {_CHK_TOGGLE_KIND}")
    op.execute(
        f"ALTER TABLE matter_capability_toggles ADD CONSTRAINT {_CHK_TOGGLE_KIND} "
        f"{_CHK_KIND_PRE_0092}"
    )
    op.execute("DELETE FROM org_library_entries WHERE capability_kind = 'knowledge'")
    op.execute(f"ALTER TABLE org_library_entries DROP CONSTRAINT {_CHK_LIBRARY_KIND}")
    op.execute(
        f"ALTER TABLE org_library_entries ADD CONSTRAINT {_CHK_LIBRARY_KIND} {_CHK_KIND_PRE_0092}"
    )
    op.execute("DROP TABLE IF EXISTS practice_area_knowledge_bases")
