"""practice_areas table + standard-rows seed — F1-S2 (fork, ADR-F002)

ADR-F002: practice areas are backend entities from day one. This is the
MINIMAL F1-S2 shape (what the cockpit shell renders); the config
vocabulary — area profile, bound skills/playbooks/MCPs, tier floor,
``projects.practice_area_id`` — lands in F1-S3 as ADDITIVE migrations.

Seed (idempotent, 0033 data-migration precedent: check-before-insert,
safe to re-run on partially-seeded databases): the standard areas from
the fork charter — Commercial, Disputes, M&A, Privacy, Employment.
Only Commercial seeds ``configured = true`` — it fronts the existing
generic matter agent; the others render as INERT cards (no composer,
no matter creation) until S3 lets an admin configure them. Unit-of-work
nouns are data, not code (ADR-F004).

Operators may rename/extend rows later (S3 admin surface); the seed
never overwrites an existing key.

Revision ID: 0053
Revises: 0052
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


# (key, name, unit_label, configured, position) — frozen at S2; content
# changes ship as new migrations or via the S3 admin surface.
_STANDARD_AREAS: list[tuple[str, str, str, bool, int]] = [
    ("commercial", "Commercial", "Matter", True, 1),
    ("disputes", "Disputes", "Matter", False, 2),
    ("m-and-a", "M&A", "Deal", False, 3),
    ("privacy", "Privacy", "Programme", False, 4),
    ("employment", "Employment", "Matter", False, 5),
]


def upgrade() -> None:
    op.create_table(
        "practice_areas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit_label", sa.Text(), nullable=False),
        sa.Column("configured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer(), nullable=False),
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
    )

    _seed(op.get_bind())


def _seed(conn: sa.engine.Connection) -> None:
    """Insert any missing standard area; never overwrite an existing key.

    Module-level (not inlined in ``upgrade``) so the idempotency
    contract is directly testable — tests/test_practice_areas.py calls
    it against an already-seeded database and asserts no duplicates.
    """
    for key, name, unit_label, configured, position in _STANDARD_AREAS:
        exists = conn.execute(
            sa.text("SELECT 1 FROM practice_areas WHERE key = :key"),
            {"key": key},
        ).first()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO practice_areas (key, name, unit_label, configured, position) "
                "VALUES (:key, :name, :unit_label, :configured, :position)"
            ),
            {
                "key": key,
                "name": name,
                "unit_label": unit_label,
                "configured": configured,
                "position": position,
            },
        )


def downgrade() -> None:
    op.drop_table("practice_areas")
