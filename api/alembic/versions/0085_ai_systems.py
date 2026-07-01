"""ai_systems register table — AIC-1 (fork, ADR-F057/F018/F019)

The first typed-domain table of the AI Compliance module: one row per AI system in
the company-wide EU AI Act (Regulation (EU) 2024/1689) register. DDL only — no seed
(this is agent/operator data, not standard rows).

Deployment-global (ADR-F019): ``source_project_id`` is nullable provenance
(``ON DELETE SET NULL``), never a scope filter. The register ALSO carries a durable
NON-NULL ``practice_area_id`` (ADR-F057/F021 — born flip-ready): the scoping key a
future ``visible_filter()`` will AND into reads when register enforcement flips from
shared-read to area-membership. FK ``RESTRICT`` so the scoping key can never become
NULL and silently un-scope the row (deliberately unlike the nullable
``projects.practice_area_id``).

The CHECK constraints mirror the Pydantic domain invariants in
``app.schemas.compliance.AiSystemInput`` (ADR-F018 code-validated writes) at the DB
boundary as defense-in-depth. There is deliberately NO risk-tier or role column:
the risk classification is a legal determination owned by the deterministic engine
(AIC-2, ADR-F057), never a free-write field — the register holds FACTS only.

Revision ID: 0085
Revises: 0084
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

# EU AI Act fact vocabularies — the SQL CHECK mirrors of the Pydantic enums in
# app.schemas.compliance (authoritative there; duplicated here as the DB guard).
_LIFECYCLE_STATUSES = ("in_development", "in_service", "decommissioned")
_DEVELOPMENT_ORIGINS = ("in_house", "third_party", "hybrid")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "ai_systems",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Durable NON-NULL authz scoping key (ADR-F057/F021); RESTRICT so it never
        # becomes NULL.
        sa.Column(
            "practice_area_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "practice_areas.id",
                ondelete="RESTRICT",
                name="fk_ai_systems_practice_area_id",
            ),
            nullable=False,
        ),
        # Provenance only (ADR-F019): nullable, SET NULL — the register outlives the
        # matter and is never scoped by it.
        sa.Column(
            "source_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="SET NULL",
                name="fk_ai_systems_source_project_id",
            ),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("intended_purpose", sa.Text(), nullable=False),
        sa.Column("lifecycle_status", sa.Text(), nullable=False),
        sa.Column("development_origin", sa.Text(), nullable=False),
        sa.Column("is_gpai", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("gpai_systemic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retirement_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_ai_systems_name_len",
        ),
        sa.CheckConstraint(
            "char_length(intended_purpose) > 0 AND char_length(intended_purpose) <= 2000",
            name="chk_ai_systems_intended_purpose_len",
        ),
        sa.CheckConstraint(
            _in_set("lifecycle_status", _LIFECYCLE_STATUSES),
            name="chk_ai_systems_lifecycle_status",
        ),
        sa.CheckConstraint(
            _in_set("development_origin", _DEVELOPMENT_ORIGINS),
            name="chk_ai_systems_development_origin",
        ),
        # A systemic-risk general-purpose model IS a general-purpose model.
        sa.CheckConstraint(
            "NOT gpai_systemic OR is_gpai",
            name="chk_ai_systems_gpai_coherence",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000",
            name="chk_ai_systems_notes_len",
        ),
        sa.CheckConstraint(
            "retirement_reason IS NULL OR char_length(retirement_reason) <= 1000",
            name="chk_ai_systems_retirement_reason_len",
        ),
    )
    op.create_index("ix_ai_systems_practice_area_id", "ai_systems", ["practice_area_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_systems_practice_area_id", table_name="ai_systems")
    op.drop_table("ai_systems")
