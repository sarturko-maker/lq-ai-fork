"""systems + processing_activity_systems; re-scope ROPA global — PRIV-3 (fork, ADR-F019)

The Privacy module's relational, deployment-global inventory graph:

* ``systems`` — IT systems/assets where personal data lives (the "where").
* ``processing_activity_systems`` — M:N link (a processing activity composes the
  systems it uses; OneTrust/TrustArc "Business Process composes Systems").
* re-scope ``processing_activities`` to the **company-wide** register (ADR-F019):
  drop the matter-ownership ``project_id`` (added in 0058) and add a nullable
  ``source_project_id`` (ON DELETE SET NULL) for provenance only.

Safe to drop ``project_id``: no environment holds ``processing_activities`` data
yet (0058 unshipped to any DB with rows). CHECK constraints on ``systems`` mirror
``app.schemas.ropa.SystemInput`` (ADR-F018 code-validated writes) as the DB guard.

Revision ID: 0059
Revises: 0058
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

_SYSTEM_TYPES = (
    "database",
    "analytics",
    "crm",
    "support",
    "email_marketing",
    "logs",
    "backup",
    "third_party_processor",
    "other",
)


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_len(column: str, max_len: int) -> str:
    return f"{column} IS NULL OR char_length({column}) <= {max_len}"


def upgrade() -> None:
    # --- systems (the "where personal data lives" half of the graph) ---
    op.create_table(
        "systems",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="SET NULL",
                name="fk_systems_source_project_id",
            ),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("system_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("hosting_location", sa.Text(), nullable=True),
        sa.Column("retention", sa.Text(), nullable=True),
        sa.Column("security_measures", sa.Text(), nullable=True),
        sa.Column(
            "ai_usage",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_systems_name_len",
        ),
        sa.CheckConstraint(_in_set("system_type", _SYSTEM_TYPES), name="chk_systems_system_type"),
        sa.CheckConstraint(_opt_len("description", 2000), name="chk_systems_description_len"),
        sa.CheckConstraint(_opt_len("owner", 200), name="chk_systems_owner_len"),
        sa.CheckConstraint(
            _opt_len("hosting_location", 200), name="chk_systems_hosting_location_len"
        ),
        sa.CheckConstraint(_opt_len("retention", 1000), name="chk_systems_retention_len"),
        sa.CheckConstraint(
            _opt_len("security_measures", 2000), name="chk_systems_security_measures_len"
        ),
    )

    # --- M:N link processing_activities <-> systems ---
    op.create_table(
        "processing_activity_systems",
        sa.Column(
            "processing_activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "processing_activities.id",
                ondelete="CASCADE",
                name="fk_pa_systems_processing_activity_id",
            ),
            primary_key=True,
        ),
        sa.Column(
            "system_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "systems.id",
                ondelete="CASCADE",
                name="fk_pa_systems_system_id",
            ),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_processing_activity_systems_system_id",
        "processing_activity_systems",
        ["system_id"],
    )

    # --- re-scope processing_activities to the global register (ADR-F019) ---
    # Drop the matter-ownership project_id (the column drop cascades its FK), then
    # add the nullable source_project_id (provenance only).
    op.drop_index("ix_processing_activities_project_id", table_name="processing_activities")
    op.drop_column("processing_activities", "project_id")
    op.add_column(
        "processing_activities",
        sa.Column(
            "source_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="SET NULL",
                name="fk_processing_activities_source_project_id",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Best-effort reverse: matter ownership cannot be reconstructed once global,
    # so project_id comes back nullable (re-add NOT NULL would fail on real rows).
    op.drop_column("processing_activities", "source_project_id")
    op.add_column(
        "processing_activities",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="CASCADE",
                name="fk_processing_activities_project_id",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_processing_activities_project_id",
        "processing_activities",
        ["project_id"],
    )
    op.drop_index(
        "ix_processing_activity_systems_system_id",
        table_name="processing_activity_systems",
    )
    op.drop_table("processing_activity_systems")
    op.drop_table("systems")
