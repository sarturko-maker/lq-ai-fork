"""messages.kind discriminator column

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-12

Adds a LQ.AI-specific message classification column ``messages.kind`` with
CHECK constraint over ``{user, ai, refusal, system}``. Distinct from the
OpenAI-style ``messages.role`` column. Backfill rule:

    role='assistant' -> kind='ai'
    role='user'      -> kind='user'
    role='system'    -> kind='system'
    role='tool'      -> kind='system'

Required for: tier-floor refusal block (D.1 §3.4), receipts filtering
(D.1 §3.5). Refusal turns will set ``kind='refusal'`` with
``role='assistant'`` (the assistant "spoke" the refusal).
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.create_check_constraint(
        "chk_messages_kind",
        "messages",
        "kind IN ('user', 'ai', 'refusal', 'system')",
    )
    op.execute(
        """
        UPDATE messages SET kind = CASE
            WHEN role = 'assistant' THEN 'ai'
            WHEN role = 'user'      THEN 'user'
            WHEN role = 'system'    THEN 'system'
            WHEN role = 'tool'      THEN 'system'
            ELSE 'user'
        END
        """
    )
    op.create_index("idx_messages_kind", "messages", ["kind"])


def downgrade() -> None:
    op.drop_index("idx_messages_kind", table_name="messages")
    op.drop_constraint("chk_messages_kind", "messages", type_="check")
    op.drop_column("messages", "kind")
