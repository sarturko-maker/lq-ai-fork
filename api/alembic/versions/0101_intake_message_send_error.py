"""INTAKE-4b — intake_messages.send_error (ADR-F087)

One additive, nullable column.

``draft_email_reply`` now SENDS after a human approves it (ADR-F087: the tool's
execution IS the send). A send that fails leaves the outbound row in place — the
lawyer's approved text is not thrown away — with this column recording WHY, and
moves the thread to ``error``.

The value is an error CLASS ONLY: ``http_502``, ``timeout``, ``transport``,
``duplicate``, ``not_configured``, ``no_inbound_message``, ``unexpected``. Never
a provider message, never a body, never an address — a provider error string
routinely quotes the recipient and the subject, and this column is read by
humans and (unlike the body) by log-adjacent tooling. The 100-char CHECK is the
structural reminder: nothing that long is a class.

NULL on every existing row, on every inbound row, and on an outbound row that
was delivered.

Revision ID: 0101
Revises: 0100
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("intake_messages", sa.Column("send_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_intake_messages_send_error_len",
        "intake_messages",
        "send_error IS NULL OR char_length(send_error) BETWEEN 1 AND 100",
    )


def downgrade() -> None:
    op.drop_constraint("chk_intake_messages_send_error_len", "intake_messages", type_="check")
    op.drop_column("intake_messages", "send_error")
