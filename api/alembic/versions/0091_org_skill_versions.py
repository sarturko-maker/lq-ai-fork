"""org_skill_versions — org-authored skill propose/approve harness (ADR-F067 D2/D3, B-2a)

One table carries BOTH the proposal state machine AND the immutable approved snapshots
the runtime reads. A propose action synthesizes canonical ``SKILL.md`` content (frontmatter +
body) from the author's own ``user_skills`` row and inserts a ``proposed`` row here; an admin
approve flips it to ``approved`` (superseding any prior approved version of the same slug);
reject/revoke are the other terminal/derived transitions. Content columns
(``slug, raw_yaml, body, frontmatter, content_hash, version_no, author_user_id,
source_user_skill_id``) are written once at INSERT and never updated — only the
state/review/revoke columns transition, so an "approved" row is byte-for-byte the content that
was reviewed (ADR-F067 D2 "approval pins bytes, not a row" — no post-approval edit can silently
bypass the gate).

Implementer's-call (per the B-2a build contract): proposal state lives HERE, on this new table
— ``user_skills`` is left completely untouched by this migration. The live user/team shadow
resolution path (``api/app/api/skills.py``, ``api/app/api/internal.py``) keeps reading
``user_skills`` exactly as it does today; propose is a one-way, read-only-of-``user_skills``
snapshot action, so there is zero risk to that live path from this table's existence or from
any state this table's rows go through.

Design notes:

* ``state`` carries ``('proposed','approved','rejected','superseded','revoked')`` in the CHECK
  (``chk_org_skill_versions_state``). Legal transitions: ``proposed -> approved | rejected``;
  ``approved -> revoked | superseded`` (``superseded`` is set ONLY by a newer approval of the
  same slug — there is no "supersede" endpoint). Every other transition is a 409 at the API
  layer; this migration only enforces the state vocabulary, not the transition graph.
* The two partial unique indexes are the concurrency-safety backbone: at most one ``proposed``
  row per slug (``ux_org_skill_versions_slug_proposed`` — "duplicate open proposal" 409s via an
  IntegrityError race guard) and at most one ``approved`` row per slug
  (``ux_org_skill_versions_slug_approved`` — the approve transaction must supersede the prior
  approved row of the same slug BEFORE inserting/flipping the new one, in the same transaction,
  or this index raises).
* ``uq_org_skill_versions_slug_version`` backs the ``version_no = COALESCE(MAX(version_no), 0) +
  1`` per-slug numbering the propose endpoint computes; a concurrent double-propose racing that
  read collides here (also caught as an IntegrityError -> 409).
* ``source_user_skill_id`` / ``author_user_id`` / ``reviewed_by`` / ``revoked_by`` are all
  ``ON DELETE SET NULL`` — a version's provenance survives the referenced user's (or the source
  skill row's) deletion; the harness degrades to "unknown author" labels rather than losing the
  approved snapshot or its audit trail. This mirrors ``org_library_entries.adopted_by`` (0088)
  and ``deployment_branding.updated_by`` (0090): it is the org's approved artifact, not the
  individual's.
* ``frontmatter`` (JSONB) is a parsed-dict copy of what ``raw_yaml`` encodes — kept alongside so
  admin listing / capability-panel reads never re-parse YAML on the hot path; ``raw_yaml`` stays
  the source of truth re-served verbatim (via ``reconstruct_skill_md``) to the runtime.
* ``idx_org_skill_versions_state`` backs the admin queue's ``GET /admin/org-skills?state=``
  filter and the runtime's ``WHERE state = 'approved'`` snapshot load — both are concrete query
  shapes now (locked Phase-A deferred-index pattern: no other index is added speculatively).

Revision ID: 0091
Revises: 0090
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_skill_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("raw_yaml", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("frontmatter", JSONB, nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "source_user_skill_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "user_skills.id",
                ondelete="SET NULL",
                name="fk_org_skill_versions_source",
            ),
            nullable=True,
        ),
        sa.Column(
            "author_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_org_skill_versions_author",
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
                name="fk_org_skill_versions_reviewer",
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
                name="fk_org_skill_versions_revoker",
            ),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_org_skill_versions"),
        sa.CheckConstraint(
            "state IN ('proposed','approved','rejected','superseded','revoked')",
            name="chk_org_skill_versions_state",
        ),
        sa.CheckConstraint(
            "char_length(slug) BETWEEN 1 AND 80",
            name="chk_org_skill_versions_slug_len",
        ),
        sa.CheckConstraint(
            "version_no >= 1",
            name="chk_org_skill_versions_version_no",
        ),
    )

    # One row per (slug, version_no) — backs the per-slug version numbering.
    op.create_index(
        "uq_org_skill_versions_slug_version",
        "org_skill_versions",
        ["slug", "version_no"],
        unique=True,
    )
    # At most one OPEN proposal per slug (ADR-F067 D3 — duplicate propose is a 409).
    op.create_index(
        "ux_org_skill_versions_slug_proposed",
        "org_skill_versions",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("state = 'proposed'"),
    )
    # At most one LIVE approved version per slug — the runtime's snapshot source of truth
    # (ADR-F067 D2 "approval pins bytes, not a row").
    op.create_index(
        "ux_org_skill_versions_slug_approved",
        "org_skill_versions",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("state = 'approved'"),
    )
    # Backs the admin queue's state filter and the runtime's approved-snapshot load.
    op.create_index(
        "idx_org_skill_versions_state",
        "org_skill_versions",
        ["state"],
    )


def downgrade() -> None:
    op.drop_index("idx_org_skill_versions_state", table_name="org_skill_versions")
    op.drop_index("ux_org_skill_versions_slug_approved", table_name="org_skill_versions")
    op.drop_index("ux_org_skill_versions_slug_proposed", table_name="org_skill_versions")
    op.drop_index("uq_org_skill_versions_slug_version", table_name="org_skill_versions")
    op.drop_table("org_skill_versions")
