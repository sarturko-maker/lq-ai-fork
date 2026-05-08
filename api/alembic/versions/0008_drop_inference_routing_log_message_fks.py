"""drop inference_routing_log FKs to chats and messages — fix gateway write-order race

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-08

C3's migration 0006 added FK constraints on
``inference_routing_log.chat_id`` and ``.message_id`` (closing A2's
deferred items per the original plan). At smoke-test time we
discovered the constraints fight the gateway/backend write order:

* Backend generates the assistant ``message_id`` UUID before
  dispatch and passes it to the gateway in the request envelope.
* Gateway writes the ``inference_routing_log`` row at end-of-call
  (or on failure), with the message_id populated.
* Backend persists the assistant message row only after the gateway
  returns — so at the time the gateway writes, ``messages.id`` does
  not yet exist, and the FK constraint rejects the insert.

The B4 routing-log writer's "never raise" invariant swallows the
FK error and the audit row is lost — so the system silently dropped
every audit row across both unary and streaming inference paths.

We drop both FKs. The columns stay as nullable UUIDs and remain
useful for soft-correlation joins (``LEFT JOIN messages USING
(message_id)``); the ON DELETE SET NULL behavior was not
load-bearing because the ``messages`` row carries the same routing
metadata (routed_inference_tier, provider, model, tokens, cost) on
its own.

Reversible: ``downgrade()`` re-creates the constraints, but anyone
running the downgrade should expect to break new gateway writes
again.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_inference_routing_log_message_id",
        "inference_routing_log",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_inference_routing_log_chat_id",
        "inference_routing_log",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "fk_inference_routing_log_chat_id",
        "inference_routing_log",
        "chats",
        ["chat_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inference_routing_log_message_id",
        "inference_routing_log",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )
