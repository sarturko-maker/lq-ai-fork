"""processing_activities table — PRIV-1 (fork, ADR-F018)

The first typed-domain table of the Privacy module: one Article 30 GDPR ROPA
record per row, scoped to a Privacy matter (``projects.id``, ON DELETE CASCADE).
DDL only — no seed (this is per-matter operator/agent data, not standard rows).

The CHECK constraints mirror the Pydantic domain invariants in
``app.schemas.ropa.ProcessingActivityInput`` (ADR-F018 code-validated writes) at
the DB boundary as defense-in-depth: an off-list lawful basis / role / Article 9
condition, an empty retention, or a special-category record without an Article
9(2) condition cannot be persisted even if a caller bypasses the schema.

Revision ID: 0058
Revises: 0057
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

# GDPR-canonical allowed sets — the SQL CHECK mirrors of the Pydantic enums in
# app.schemas.ropa (authoritative there; duplicated here as the DB guard).
_LAWFUL_BASES = (
    "consent",
    "contract",
    "legal_obligation",
    "vital_interests",
    "public_task",
    "legitimate_interests",
)
_ART9_CONDITIONS = (
    "explicit_consent",
    "employment_social_security",
    "vital_interests",
    "not_for_profit_body",
    "made_public_by_data_subject",
    "legal_claims",
    "substantial_public_interest",
    "health_or_social_care",
    "public_health",
    "archiving_research_statistics",
)
_CONTROLLER_ROLES = ("controller", "joint_controller", "processor")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "processing_activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="CASCADE",
                name="fk_processing_activities_project_id",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("lawful_basis", sa.Text(), nullable=False),
        sa.Column("controller_role", sa.Text(), nullable=False),
        sa.Column("retention", sa.Text(), nullable=False),
        sa.Column(
            "special_category",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("art9_condition", sa.Text(), nullable=True),
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
            name="chk_processing_activities_name_len",
        ),
        sa.CheckConstraint(
            "char_length(purpose) > 0 AND char_length(purpose) <= 2000",
            name="chk_processing_activities_purpose_len",
        ),
        sa.CheckConstraint(
            "char_length(retention) > 0 AND char_length(retention) <= 1000",
            name="chk_processing_activities_retention_required",
        ),
        sa.CheckConstraint(
            _in_set("lawful_basis", _LAWFUL_BASES),
            name="chk_processing_activities_lawful_basis",
        ),
        sa.CheckConstraint(
            _in_set("controller_role", _CONTROLLER_ROLES),
            name="chk_processing_activities_controller_role",
        ),
        sa.CheckConstraint(
            "(special_category AND art9_condition IS NOT NULL) "
            "OR (NOT special_category AND art9_condition IS NULL)",
            name="chk_processing_activities_art9_requires_special",
        ),
        sa.CheckConstraint(
            f"art9_condition IS NULL OR {_in_set('art9_condition', _ART9_CONDITIONS)}",
            name="chk_processing_activities_art9_condition",
        ),
    )
    op.create_index(
        "ix_processing_activities_project_id",
        "processing_activities",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_activities_project_id", table_name="processing_activities")
    op.drop_table("processing_activities")
