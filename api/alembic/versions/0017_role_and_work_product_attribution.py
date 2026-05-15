"""users.role + work_product_attribution table — Wave C

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-11

Wave C of the M1 backend gap-fill. Two additive changes:

1. ``users.role`` — RBAC three-role enum per PRD §5.2. CHECK
   constraint enforces the values ``admin`` | ``member`` | ``viewer``
   at the DB layer. Default ``member``; the column is backfilled
   from the existing ``is_admin`` boolean so existing rows transition
   without a manual step (is_admin=True → 'admin', False → 'member').
   ``is_admin`` stays in place as a convenience flag the app keeps
   in sync with ``role`` — removing it would break backward
   compatibility with code that reads ``user.is_admin`` directly.

2. ``work_product_attribution`` — chain-of-custody table per PRD §3.3
   data model. One row per model-generated artifact (assistant
   message). Carries the routed inference annotation, the skill
   set applied, and a SHA-256 of the content for tamper-evidence.
   Included in the GDPR Article 20 export bundle per PRD §5.3.

Reversible: ``downgrade()`` drops the table + the column. The
backfill is not reverted (data preservation > strict reversibility).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users.role --------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'member'"),
        ),
    )
    # Backfill from is_admin so existing rows map cleanly.
    op.execute("UPDATE users SET role = CASE WHEN is_admin THEN 'admin' ELSE 'member' END")
    op.create_check_constraint(
        "chk_users_role_enum",
        "users",
        "role IN ('admin', 'member', 'viewer')",
    )

    # --- work_product_attribution -----------------------------------------
    op.create_table(
        "work_product_attribution",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "messages.id",
                ondelete="CASCADE",
                name="fk_work_product_attribution_message",
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_work_product_attribution_user",
            ),
            nullable=False,
        ),
        sa.Column(
            "chat_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "chats.id",
                ondelete="CASCADE",
                name="fk_work_product_attribution_chat",
            ),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="SET NULL",
                name="fk_work_product_attribution_project",
            ),
            nullable=True,
        ),
        sa.Column("routed_inference_tier", sa.Integer(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column(
            "skill_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "playbook_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "routed_inference_tier IS NULL OR (routed_inference_tier BETWEEN 1 AND 5)",
            name="chk_work_product_tier_range",
        ),
    )
    op.create_index(
        "idx_work_product_user_timestamp",
        "work_product_attribution",
        ["user_id", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_work_product_chat",
        "work_product_attribution",
        ["chat_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_work_product_chat", table_name="work_product_attribution")
    op.drop_index("idx_work_product_user_timestamp", table_name="work_product_attribution")
    op.drop_table("work_product_attribution")
    op.drop_constraint("chk_users_role_enum", "users", type_="check")
    op.drop_column("users", "role")
