"""capability panel — area↔playbook availability + per-matter capability toggles (ADR-F054)

Two additive tables for the cockpit capability panel (Phase 1):

* ``practice_area_playbooks`` — area↔playbook AVAILABILITY binding (mirrors
  ``practice_area_skills``; ``playbook_id`` is a real FK since playbooks are SQL rows).
  The area curates which playbooks (the firm's preferred positions) are available.
* ``matter_capability_toggles`` — the per-matter on/off the LAWYER writes. SPARSE:
  a row exists only where the lawyer diverged from the capability's ``default_enabled``
  (all available capabilities default ON except the MCP placeholder). Absence = default,
  so any untouched matter stays byte-identical to today and a newly-available capability
  is auto-on with no backfill.

Tool availability is deliberately NOT a table — tools are code-canonical (the
``*_TOOL_NAMES`` frozensets + the per-area group map in ``app.agents.capabilities`` are
the source of truth); a table would force a seed that must byte-match the grants forever.

**Additive and non-destructive.** No existing column/row is touched. No playbook binding
is seeded (there is no guaranteed built-in playbook to bind; binding is an admin action),
so existing matters get no new behaviour until an admin attaches a playbook AND a lawyer
leaves it on — preserving the byte-identical default path.

Revision ID: 0081
Revises: 0080
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FK constraints are NAMED to match the ORM models (PracticeAreaPlaybook,
    # MatterCapabilityToggle) so the DB and the model agree. No standalone index on
    # matter_capability_toggles.project_id: the PK btree
    # (project_id, capability_kind, capability_key) already serves every
    # "WHERE project_id = ?" read via its leftmost prefix.
    op.execute(
        """
        CREATE TABLE practice_area_playbooks (
            practice_area_id UUID NOT NULL,
            playbook_id UUID NOT NULL,
            attached_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_practice_area_playbooks
                PRIMARY KEY (practice_area_id, playbook_id),
            CONSTRAINT fk_practice_area_playbooks_area_id
                FOREIGN KEY (practice_area_id) REFERENCES practice_areas(id) ON DELETE CASCADE,
            CONSTRAINT fk_practice_area_playbooks_playbook_id
                FOREIGN KEY (playbook_id) REFERENCES playbooks(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE matter_capability_toggles (
            project_id UUID NOT NULL,
            capability_kind TEXT NOT NULL,
            capability_key TEXT NOT NULL,
            enabled BOOLEAN NOT NULL,
            set_by UUID,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_matter_capability_toggles
                PRIMARY KEY (project_id, capability_kind, capability_key),
            CONSTRAINT fk_matter_capability_toggles_project_id
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CONSTRAINT fk_matter_capability_toggles_set_by
                FOREIGN KEY (set_by) REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT chk_matter_capability_toggles_kind
                CHECK (capability_kind IN ('skill', 'tool', 'playbook')),
            CONSTRAINT chk_matter_capability_toggles_key_len
                CHECK (char_length(capability_key) BETWEEN 1 AND 200)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS matter_capability_toggles")
    op.execute("DROP TABLE IF EXISTS practice_area_playbooks")
