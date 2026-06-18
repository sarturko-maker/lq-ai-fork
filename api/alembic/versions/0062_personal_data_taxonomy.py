"""personal-data taxonomy — PRIV-6a (fork, ADR-F019)

Article 30(1)(c): the categories of data subjects and the categories of personal
data each processing activity processes. Two company-wide controlled-vocabulary
entities, each many-to-many to processing activities:

* ``data_subject_categories`` — classes of individuals ("Employees", "Customers").
* ``data_categories`` — classes of personal data ("Contact details", "Health data").

Pure labels: ``name`` (UNIQUE — the vocabulary is reused, not duplicated; the agent
write tool finds-or-creates by name) + provenance ``source_project_id``
(ON DELETE SET NULL; ADR-F019 deployment-global, not matter-owned). No
``updated_at`` — a label is immutable. The link tables mirror the existing
``processing_activity_systems`` / ``_vendors`` shape (composite PK, CASCADE both
ends). Closes the last Article 30(1) content gap.

Revision ID: 0062
Revises: 0061
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def _category_table(name: str, *, name_check: str, name_unique: str, fk_source: str) -> None:
    op.create_table(
        name,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL", name=fk_source),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name=name_check,
        ),
    )
    # Case-insensitive uniqueness (PRIV-6a): the agent write tool finds-or-creates
    # on lower(name), so the DB backstop is a UNIQUE index on lower(name) — a plain
    # UNIQUE(name) would let "Health data"/"Health Data" both persist.
    op.create_index(name_unique, name, [sa.text("lower(name)")], unique=True)


def _link_table(
    name: str, *, category_table: str, category_col: str, fk_pa: str, fk_cat: str
) -> None:
    op.create_table(
        name,
        sa.Column(
            "processing_activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_activities.id", ondelete="CASCADE", name=fk_pa),
            primary_key=True,
        ),
        sa.Column(
            category_col,
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{category_table}.id", ondelete="CASCADE", name=fk_cat),
            primary_key=True,
        ),
    )


def upgrade() -> None:
    _category_table(
        "data_subject_categories",
        name_check="chk_data_subject_categories_name_len",
        name_unique="uq_data_subject_categories_name",
        fk_source="fk_data_subject_categories_source_project_id",
    )
    _category_table(
        "data_categories",
        name_check="chk_data_categories_name_len",
        name_unique="uq_data_categories_name",
        fk_source="fk_data_categories_source_project_id",
    )
    _link_table(
        "processing_activity_data_subject_categories",
        category_table="data_subject_categories",
        category_col="data_subject_category_id",
        fk_pa="fk_pa_dsc_processing_activity_id",
        fk_cat="fk_pa_dsc_data_subject_category_id",
    )
    _link_table(
        "processing_activity_data_categories",
        category_table="data_categories",
        category_col="data_category_id",
        fk_pa="fk_pa_dc_processing_activity_id",
        fk_cat="fk_pa_dc_data_category_id",
    )


def downgrade() -> None:
    op.drop_table("processing_activity_data_categories")
    op.drop_table("processing_activity_data_subject_categories")
    op.drop_table("data_categories")
    op.drop_table("data_subject_categories")
