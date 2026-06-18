"""vendors + processing_activity_vendors — PRIV-5a (fork, ADR-F019)

The recipients half of Article 30(1)(e): vendors/third parties a processing
activity discloses personal data to.

* ``vendors`` — third parties (role, DPA status, country). Deployment-global
  (ADR-F019): not matter-owned; nullable ``source_project_id`` (ON DELETE SET
  NULL) is provenance only.
* ``processing_activity_vendors`` — M:N link (an activity discloses to several
  recipients; a vendor receives from several activities), same shape as
  ``processing_activity_systems``.

CHECK constraints on ``vendors`` mirror ``app.schemas.ropa.VendorInput`` (ADR-F018
code-validated writes) as the DB guard. Risk rating is deliberately not modelled
(assessment-track concept, PRIV-A1).

Revision ID: 0060
Revises: 0059
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_VENDOR_ROLES = (
    "processor",
    "sub_processor",
    "joint_controller",
    "separate_controller",
    "recipient",
)
_DPA_STATUSES = ("in_place", "pending", "not_required", "none")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_len(column: str, max_len: int) -> str:
    return f"{column} IS NULL OR char_length({column}) <= {max_len}"


def upgrade() -> None:
    op.create_table(
        "vendors",
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
                name="fk_vendors_source_project_id",
            ),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("vendor_role", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("dpa_status", sa.Text(), nullable=False),
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
            name="chk_vendors_name_len",
        ),
        sa.CheckConstraint(_in_set("vendor_role", _VENDOR_ROLES), name="chk_vendors_vendor_role"),
        sa.CheckConstraint(_in_set("dpa_status", _DPA_STATUSES), name="chk_vendors_dpa_status"),
        sa.CheckConstraint(_opt_len("description", 2000), name="chk_vendors_description_len"),
        sa.CheckConstraint(_opt_len("country", 200), name="chk_vendors_country_len"),
    )

    op.create_table(
        "processing_activity_vendors",
        sa.Column(
            "processing_activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "processing_activities.id",
                ondelete="CASCADE",
                name="fk_pa_vendors_processing_activity_id",
            ),
            primary_key=True,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "vendors.id",
                ondelete="CASCADE",
                name="fk_pa_vendors_vendor_id",
            ),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_processing_activity_vendors_vendor_id",
        "processing_activity_vendors",
        ["vendor_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processing_activity_vendors_vendor_id",
        table_name="processing_activity_vendors",
    )
    op.drop_table("processing_activity_vendors")
    op.drop_table("vendors")
