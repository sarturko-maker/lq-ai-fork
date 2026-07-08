"""deployment_branding singleton — white-labeling (BRAND-1a, fork, ADR-F068)

One deployment-level branding row (Option-A stack-per-tenant, ADR-F058, so
deployment == tenant — no org scoping): ``product_name`` (empty = default
brand), ``palette`` (the validated brandable-token subset as JSONB), and an
optional raster logo held as BYTEA with its SNIFFED content type. The logo
lives in the row rather than files/S3 because the branding surface is
unauthenticated by design (the login page renders it) — no S3 credentials or
signed URLs may exist on an unauth path.

Clones the ``organization_profile`` singleton pattern (migration 0010): the
partial unique index on ``((true))`` collapses every row to the same index
value so a second insert 23505s, and the existing ``set_updated_at()``
trigger function maintains ``updated_at`` on UPDATE (the GET's
``logo_version`` cache-buster derives from it).

Revision ID: 0090
Revises: 0089
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_branding",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("product_name", sa.String(80), nullable=False, server_default=sa.text("''")),
        sa.Column("palette", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("logo_bytes", BYTEA, nullable=True),
        sa.Column("logo_content_type", sa.String(32), nullable=True),
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
        sa.Column(
            "updated_by",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_deployment_branding_updated_by"
            ),
            nullable=True,
        ),
    )

    # Singleton enforcement — at most one row (mig 0010 pattern).
    op.execute(
        "CREATE UNIQUE INDEX idx_deployment_branding_singleton ON deployment_branding ((true))"
    )

    # Auto-maintain updated_at via the existing trigger function.
    op.execute(
        "CREATE TRIGGER trg_deployment_branding_updated_at "
        "BEFORE UPDATE ON deployment_branding "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_deployment_branding_updated_at ON deployment_branding")
    op.drop_index("idx_deployment_branding_singleton", table_name="deployment_branding")
    op.drop_table("deployment_branding")
