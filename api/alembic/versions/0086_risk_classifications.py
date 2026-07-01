"""risk_classifications table — AIC-2 (fork, ADR-F057)

The sealed output of the deterministic EU AI Act verdict engine
(``app.aiact.classify``): one row per computed classification of an ``ai_systems``
row. The engine is the sole author of ``tier`` — there is no free-write tier column
anywhere (the presence gate). DDL only — no seed (agent/engine-produced data).

One CURRENT verdict per system (partial unique index on ``ai_system_id`` WHERE
``superseded_at IS NULL``); a fact/rule change supersedes the prior row and inserts a
fresh one (recompute-on-fact-change). Born flip-ready + deployment-global like the
register (ADR-F019/F021): NON-NULL ``practice_area_id`` FK RESTRICT, nullable
``source_project_id`` SET NULL provenance.

The tier/route CHECKs mirror the Pydantic enums in ``app.schemas.classification``
(authoritative there; duplicated here as the DB guard, defense-in-depth per ADR-F018).

Revision ID: 0086
Revises: 0085
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

# SQL CHECK mirrors of app.schemas.classification (authoritative there).
_RISK_TIERS = ("prohibited", "high", "limited", "minimal")
_CLASSIFICATION_ROUTES = (
    "art5_prohibited",
    "annex_i_safety_component",
    "annex_iii",
    "art50_transparency",
    "minimal",
)


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "risk_classifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ai_system_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "ai_systems.id",
                ondelete="RESTRICT",
                name="fk_risk_classifications_ai_system_id",
            ),
            nullable=False,
        ),
        # Durable NON-NULL scoping key (ADR-F057/F021 — born flip-ready).
        sa.Column(
            "practice_area_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "practice_areas.id",
                ondelete="RESTRICT",
                name="fk_risk_classifications_practice_area_id",
            ),
            nullable=False,
        ),
        # Provenance only (ADR-F019): nullable, SET NULL.
        sa.Column(
            "source_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="SET NULL",
                name="fk_risk_classifications_source_project_id",
            ),
            nullable=True,
        ),
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("facts_hash", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("article_refs", postgresql.JSONB(), nullable=False),
        sa.Column("predicate_trace", postgresql.JSONB(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("verdict_hash", sa.Text(), nullable=False),
        sa.Column("draft_basis", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in_set("tier", _RISK_TIERS), name="chk_risk_classifications_tier"),
        sa.CheckConstraint(
            _in_set("route", _CLASSIFICATION_ROUTES),
            name="chk_risk_classifications_route",
        ),
    )
    op.create_index(
        "ix_risk_classifications_ai_system_id", "risk_classifications", ["ai_system_id"]
    )
    op.create_index(
        "ix_risk_classifications_practice_area_id", "risk_classifications", ["practice_area_id"]
    )
    # At most one CURRENT verdict per system (the recompute-on-fact-change invariant).
    op.create_index(
        "uq_risk_classifications_current",
        "risk_classifications",
        ["ai_system_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_risk_classifications_current", table_name="risk_classifications")
    op.drop_index("ix_risk_classifications_practice_area_id", table_name="risk_classifications")
    op.drop_index("ix_risk_classifications_ai_system_id", table_name="risk_classifications")
    op.drop_table("risk_classifications")
