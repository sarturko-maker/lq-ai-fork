"""assessments + risks — PRIV-A1 (fork, ADR-F018, ADR-F019)

The Privacy module's assessment track — PIA / DPIA / LIA / TIA records and the
risk findings within them, the assessment-track sibling of the ROPA inventory.

* ``assessments`` — one privacy assessment. Deployment-global (ADR-F019): not
  matter-owned; nullable ``source_project_id`` (ON DELETE SET NULL) is
  provenance only. ``updated_at`` carries ``onupdate`` (server-side via the ORM)
  so a real "last modified" is maintained — the ROPA carried debt, fixed here.
* ``risks`` — child of one assessment (required FK, ON DELETE CASCADE — a risk
  has no meaning without its parent).
* ``assessment_processing_activities`` — M:N link between assessments and the
  processing activities they cover (composite PK, CASCADE both ends).

The CHECK constraints mirror ``app.schemas.assessment`` (ADR-F018 code-validated
writes) as the DB guard — including the within-row half of the headline
invariant ``completed ⇒ risk_rating present``. The cross-row half (a completed
DPIA/high-risk assessment needs ≥1 risk with a mitigation) is enforced in the
app layer, not a DB trigger (plan § headline invariant).

Revision ID: 0064
Revises: 0063
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

_ASSESSMENT_TYPES = ("pia", "dpia", "lia", "tia")
_ASSESSMENT_STATUSES = ("draft", "in_progress", "completed")
_RISK_LEVELS = ("low", "medium", "high")
_RISK_STATUSES = ("open", "mitigated", "accepted")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_len(column: str, max_len: int) -> str:
    return f"{column} IS NULL OR char_length({column}) <= {max_len}"


def upgrade() -> None:
    op.create_table(
        "assessments",
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
                name="fk_assessments_source_project_id",
            ),
            nullable=True,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("risk_rating", sa.Text(), nullable=True),
        sa.Column("conditions", sa.Text(), nullable=True),
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
            "char_length(title) > 0 AND char_length(title) <= 200",
            name="chk_assessments_title_len",
        ),
        sa.CheckConstraint(_in_set("type", _ASSESSMENT_TYPES), name="chk_assessments_type"),
        sa.CheckConstraint(_in_set("status", _ASSESSMENT_STATUSES), name="chk_assessments_status"),
        sa.CheckConstraint(
            f"risk_rating IS NULL OR {_in_set('risk_rating', _RISK_LEVELS)}",
            name="chk_assessments_risk_rating",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR risk_rating IS NOT NULL",
            name="chk_assessments_completed_requires_rating",
        ),
        sa.CheckConstraint(_opt_len("summary", 5000), name="chk_assessments_summary_len"),
        sa.CheckConstraint(_opt_len("conditions", 5000), name="chk_assessments_conditions_len"),
    )

    op.create_table(
        "risks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "assessments.id",
                ondelete="CASCADE",
                name="fk_risks_assessment_id",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("likelihood", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(description) > 0 AND char_length(description) <= 2000",
            name="chk_risks_description_len",
        ),
        sa.CheckConstraint(_in_set("likelihood", _RISK_LEVELS), name="chk_risks_likelihood"),
        sa.CheckConstraint(_in_set("impact", _RISK_LEVELS), name="chk_risks_impact"),
        sa.CheckConstraint(_in_set("status", _RISK_STATUSES), name="chk_risks_status"),
        sa.CheckConstraint(_opt_len("mitigation", 2000), name="chk_risks_mitigation_len"),
        sa.CheckConstraint(_opt_len("owner", 200), name="chk_risks_owner_len"),
    )
    # The hot query is "risks of this assessment" (the assessment detail view).
    op.create_index("ix_risks_assessment_id", "risks", ["assessment_id"])

    op.create_table(
        "assessment_processing_activities",
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "assessments.id",
                ondelete="CASCADE",
                name="fk_apa_assessment_id",
            ),
            primary_key=True,
        ),
        sa.Column(
            "processing_activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "processing_activities.id",
                ondelete="CASCADE",
                name="fk_apa_processing_activity_id",
            ),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("assessment_processing_activities")
    op.drop_index("ix_risks_assessment_id", table_name="risks")
    op.drop_table("risks")
    op.drop_table("assessments")
