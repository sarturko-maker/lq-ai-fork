"""enhance_prompt_interactions table + reasoning_visibility on users — Wave A

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-11

Wave A of the M1 backend gap-fill (per the audit completed 2026-05-11).
Two additive changes that ride together because both back the Enhance
Prompt UX described in PRD §3.2:

1. ``enhance_prompt_interactions`` — telemetry table the PRD §3.2 data
   model commits to (``EnhancePromptInteraction``: id, user_id,
   raw_input, expansion_applied, expanded_output, reasoning,
   skip_reason, used, edited_before_use, created_at). The ``used`` and
   ``edited_before_use`` flags update post-hoc when the user accepts /
   edits / skips the expansion in the UI; the initial row is written
   when the model returns its expansion.

2. ``users.reasoning_visibility`` — account-level enum
   (``always_show`` | ``disclosure`` | ``on_request``) per PRD §3.2.
   Defaults to ``disclosure`` (the spec default — collapsed-behind-
   disclosure is the right balance between transparency and noise).
   The column is added with a CHECK constraint enforcing the enum at
   the DB layer so an invalid value can't sneak through application
   bugs.

Reversible: ``downgrade()`` drops the column + the table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- enhance_prompt_interactions ---------------------------------------
    op.create_table(
        "enhance_prompt_interactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_enhance_prompt_interactions_user",
            ),
            nullable=False,
        ),
        sa.Column(
            "chat_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "chats.id",
                ondelete="SET NULL",
                name="fk_enhance_prompt_interactions_chat",
            ),
            nullable=True,
        ),
        sa.Column("raw_input", sa.Text(), nullable=False),
        sa.Column("expansion_applied", sa.Boolean(), nullable=False),
        sa.Column("expanded_output", sa.Text(), nullable=True),
        sa.Column("reasoning", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edited_before_use", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "routed_inference_tier",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("routed_provider", sa.Text(), nullable=True),
        sa.Column("routed_model", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "routed_inference_tier IS NULL OR (routed_inference_tier BETWEEN 1 AND 5)",
            name="chk_enhance_prompt_tier_range",
        ),
        sa.CheckConstraint(
            "expansion_applied OR skip_reason IS NOT NULL",
            name="chk_enhance_prompt_skip_has_reason",
        ),
    )
    op.create_index(
        "idx_enhance_prompt_user_created",
        "enhance_prompt_interactions",
        ["user_id", sa.text("created_at DESC")],
    )

    # --- users.reasoning_visibility ----------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "reasoning_visibility",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'disclosure'"),
        ),
    )
    op.create_check_constraint(
        "chk_users_reasoning_visibility_enum",
        "users",
        "reasoning_visibility IN ('always_show', 'disclosure', 'on_request')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_users_reasoning_visibility_enum", "users", type_="check")
    op.drop_column("users", "reasoning_visibility")
    op.drop_index("idx_enhance_prompt_user_created", table_name="enhance_prompt_interactions")
    op.drop_table("enhance_prompt_interactions")
