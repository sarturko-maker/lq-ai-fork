"""transfers — PRIV-5b (fork, ADR-F019)

The third-country-transfer half of Article 30(1)(e): a transfer of a processing
activity's personal data to a third country / international organisation, with
the Chapter V safeguard that legitimises it.

* ``transfers`` — child of one processing activity (required FK, ON DELETE
  CASCADE — Art 30 lists transfers within each record), optional recipient
  vendor (ON DELETE SET NULL). Deployment-global (ADR-F019): not matter-owned;
  nullable ``source_project_id`` (ON DELETE SET NULL) is provenance only.

The CHECK constraints mirror ``app.schemas.ropa.TransferInput`` (ADR-F018
code-validated writes) as the DB guard — including the headline invariant
``restricted ⇔ mechanism present``, parallel to PRIV-1's
``special_category ⇔ art9_condition``. ``restricted`` is *declared*, not derived
from a maintained adequacy list (plan § Decisions).

Revision ID: 0061
Revises: 0060
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

_TRANSFER_MECHANISMS = (
    "adequacy_regulations",
    "standard_contractual_clauses",
    "uk_idta",
    "binding_corporate_rules",
    "derogation",
)


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_len(column: str, max_len: int) -> str:
    return f"{column} IS NULL OR char_length({column}) <= {max_len}"


def upgrade() -> None:
    op.create_table(
        "transfers",
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
                name="fk_transfers_source_project_id",
            ),
            nullable=True,
        ),
        sa.Column(
            "processing_activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "processing_activities.id",
                ondelete="CASCADE",
                name="fk_transfers_processing_activity_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "vendors.id",
                ondelete="SET NULL",
                name="fk_transfers_vendor_id",
            ),
            nullable=True,
        ),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column(
            "restricted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("mechanism", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
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
            "char_length(destination) > 0 AND char_length(destination) <= 200",
            name="chk_transfers_destination_len",
        ),
        sa.CheckConstraint(
            f"mechanism IS NULL OR {_in_set('mechanism', _TRANSFER_MECHANISMS)}",
            name="chk_transfers_mechanism",
        ),
        sa.CheckConstraint(
            "(restricted AND mechanism IS NOT NULL) OR (NOT restricted AND mechanism IS NULL)",
            name="chk_transfers_restricted_requires_mechanism",
        ),
        sa.CheckConstraint(_opt_len("details", 2000), name="chk_transfers_details_len"),
    )
    # The hot query is "transfers of this activity" (the activity detail + export).
    op.create_index(
        "ix_transfers_processing_activity_id",
        "transfers",
        ["processing_activity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transfers_processing_activity_id", table_name="transfers")
    op.drop_table("transfers")
