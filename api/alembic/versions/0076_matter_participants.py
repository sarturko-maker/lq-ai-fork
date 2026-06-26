"""matter_participants — the authorship roster (who-is-who) for a matter (ADR-F048)

A negotiation has MANY people redlining, not just two counsels. This table maps a
person's identity (display name + the author/email strings we MATCH against) to a
``side`` so the agent can tell whose tracked changes are whose. ``side`` drives
treatment: 'ours' (our team incl. our client) → adopt; 'counterparty' → a
negotiation position; 'unknown' → ask the user. ``trust`` distinguishes an
agent-inferred row ('inferred') from a human-confirmed one ('confirmed', which the
agent's auto-curation must never overwrite — the human owns the tier, ADR-F042).

* Matter-scoped via ``project_id`` (CASCADE) — the write blast radius is one matter.
* ``aliases`` is a JSONB array (the match set), matched Python-side, never via SQL.
* A removed participant is SOFT-retired (``superseded_at`` set; never deleted).
* CHECK literals mirror ``app.models.project`` (``_MATTER_PARTICIPANT_SIDES`` /
  ``_MATTER_PARTICIPANT_TRUST`` + the length caps) — keep the two in sync.

Additive only: no existing table touched, no backfill. Mirrors
``app.models.project.MatterParticipant``.

Revision ID: 0076
Revises: 0075
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

# The CHECK value sets — the SQL mirror of app.models.project's private tuples.
_SIDES = ("ours", "counterparty", "unknown")
_TRUST = ("inferred", "confirmed")
_NAME_MAX = 200
_ROLE_MAX = 200
_ORG_MAX = 200
_SOURCE_MAX = 500


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "matter_participants",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id", ondelete="CASCADE", name="fk_matter_participants_project_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_matter_participants_user_id"),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("aliases", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("organization", sa.Text(), nullable=True),
        sa.Column("role_label", sa.Text(), nullable=True),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("trust", sa.Text(), nullable=False, server_default=sa.text("'inferred'")),
        sa.Column("source_citation", sa.Text(), nullable=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_in_set("side", _SIDES), name="chk_matter_participants_side"),
        sa.CheckConstraint(_in_set("trust", _TRUST), name="chk_matter_participants_trust"),
        sa.CheckConstraint(
            f"char_length(display_name) BETWEEN 1 AND {_NAME_MAX}",
            name="chk_matter_participants_name_len",
        ),
        sa.CheckConstraint(
            f"organization IS NULL OR char_length(organization) BETWEEN 1 AND {_ORG_MAX}",
            name="chk_matter_participants_org_len",
        ),
        sa.CheckConstraint(
            f"role_label IS NULL OR char_length(role_label) BETWEEN 1 AND {_ROLE_MAX}",
            name="chk_matter_participants_role_len",
        ),
        sa.CheckConstraint(
            f"source_citation IS NULL OR char_length(source_citation) BETWEEN 1 AND {_SOURCE_MAX}",
            name="chk_matter_participants_source_len",
        ),
    )
    op.create_index(
        "ix_matter_participants_project_created",
        "matter_participants",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_matter_participants_project_created", table_name="matter_participants")
    op.drop_table("matter_participants")
