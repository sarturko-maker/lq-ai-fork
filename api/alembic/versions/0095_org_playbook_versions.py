"""org_playbook_versions — org-authored playbook propose/approve harness (ADR-F067 D2/D3, B-4)

The playbook twin of ``org_skill_versions`` (migration 0091). One table carries BOTH the
proposal state machine AND the immutable approved snapshots the runtime reads. A propose action
FREEZES the author's own ``playbooks`` row + its ordered ``playbook_positions`` into a canonical
positions payload and inserts a ``proposed`` row here; an admin approve flips it to ``approved``
(superseding any prior approved version of the same playbook), reject/revoke are the other
terminal/derived transitions. Content columns
(``playbook_id, version_no, name, contract_type, description, playbook_version, positions,
content_hash, source_playbook_id, author_user_id``) are written once at INSERT and never updated
— only the state/review/revoke columns transition, so an "approved" row is byte-for-byte the
positions that were reviewed (ADR-F067 D2 "approval pins bytes, not a row").

B-4 governance is FULL SKILLS PARITY: the runtime resolves an adopted+bound org playbook from
the ``state = 'approved'`` snapshot keyed by ``playbook_id``, INDEPENDENT of the live
``playbooks`` row — so an author soft-deleting their source playbook cannot yank an admin-approved
capability (only an admin revoke removes it). This is why ``playbook_id`` is a PLAIN column, not a
FK: like ``org_skill_versions.slug``, the snapshot's adoption key must survive the source row's
deletion. ``source_playbook_id`` is the separate ``ON DELETE SET NULL`` provenance FK.

Design notes (mirroring 0091):

* ``state`` carries ``('proposed','approved','rejected','superseded','revoked')``. Legal
  transitions: ``proposed -> approved | rejected``; ``approved -> revoked | superseded``
  (``superseded`` is set ONLY by a newer approval of the same playbook). Enforced at the API
  layer; this migration only enforces the vocabulary.
* Two partial unique indexes are the concurrency backbone: at most one ``proposed`` row per
  ``playbook_id`` (duplicate open proposal 409s via an IntegrityError race guard) and at most one
  ``approved`` row per ``playbook_id`` (the approve transaction must supersede the prior approved
  row BEFORE flipping the new one, in the same transaction, or this index raises — the two-step
  flush).
* ``uq_org_playbook_versions_playbook_version`` backs the per-playbook ``version_no =
  COALESCE(MAX,0)+1`` numbering; a concurrent double-propose collides here (also -> 409).
* ``positions`` (JSONB) is the CANONICAL frozen positions array — full fidelity (issue /
  description / standard_language / fallback_tiers / redline_strategy / severity_if_missing /
  detection_keywords / detection_examples / position_order), serialized deterministically so
  ``content_hash`` (sha256 over the canonical positions+header JSON) is stable across re-proposes
  of unchanged content.
* ``source_playbook_id`` / ``author_user_id`` / ``reviewed_by`` / ``revoked_by`` are all
  ``ON DELETE SET NULL`` — provenance degrades to "unknown" labels rather than losing the approved
  snapshot (mirrors 0091 / ``org_library_entries.adopted_by``).

The ``org_library_entries`` kind CHECK is NOT touched — ``playbook`` has been an allowed Library
kind since migration 0088; adopt/bind/toggle/remove already work for kind=playbook.

Revision ID: 0095
Revises: 0094
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_playbook_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # PLAIN column, NOT an FK — the stable adoption key. Survives live-playbook deletion
        # exactly as org_skill_versions.slug survives, so the Library adopt key str(pb.id) stays
        # resolvable (full-parity resolution).
        sa.Column("playbook_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        # Frozen header snapshot (the capability label the read models render).
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("contract_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("playbook_version", sa.Text(), nullable=False, server_default="1.0.0"),
        # The canonical frozen positions array (full fidelity).
        sa.Column("positions", JSONB, nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "source_playbook_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "playbooks.id",
                ondelete="SET NULL",
                name="fk_org_playbook_versions_source",
            ),
            nullable=True,
        ),
        sa.Column(
            "author_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_org_playbook_versions_author",
            ),
            nullable=True,
        ),
        sa.Column(
            "state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'proposed'"),
        ),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "reviewed_by",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_org_playbook_versions_reviewer",
            ),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "revoked_by",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_org_playbook_versions_revoker",
            ),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_org_playbook_versions"),
        sa.CheckConstraint(
            "state IN ('proposed','approved','rejected','superseded','revoked')",
            name="chk_org_playbook_versions_state",
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200",
            name="chk_org_playbook_versions_name_len",
        ),
        sa.CheckConstraint(
            "version_no >= 1",
            name="chk_org_playbook_versions_version_no",
        ),
    )

    # One row per (playbook_id, version_no) — backs the per-playbook version numbering.
    op.create_index(
        "uq_org_playbook_versions_playbook_version",
        "org_playbook_versions",
        ["playbook_id", "version_no"],
        unique=True,
    )
    # At most one OPEN proposal per playbook (ADR-F067 D3 — duplicate propose is a 409).
    op.create_index(
        "ux_org_playbook_versions_playbook_proposed",
        "org_playbook_versions",
        ["playbook_id"],
        unique=True,
        postgresql_where=sa.text("state = 'proposed'"),
    )
    # At most one LIVE approved version per playbook — the runtime's snapshot source of truth.
    op.create_index(
        "ux_org_playbook_versions_playbook_approved",
        "org_playbook_versions",
        ["playbook_id"],
        unique=True,
        postgresql_where=sa.text("state = 'approved'"),
    )
    # Backs the admin queue's state filter and the runtime's approved-snapshot load.
    op.create_index(
        "idx_org_playbook_versions_state",
        "org_playbook_versions",
        ["state"],
    )


def downgrade() -> None:
    op.drop_index("idx_org_playbook_versions_state", table_name="org_playbook_versions")
    op.drop_index("ux_org_playbook_versions_playbook_approved", table_name="org_playbook_versions")
    op.drop_index("ux_org_playbook_versions_playbook_proposed", table_name="org_playbook_versions")
    op.drop_index("uq_org_playbook_versions_playbook_version", table_name="org_playbook_versions")
    op.drop_table("org_playbook_versions")
