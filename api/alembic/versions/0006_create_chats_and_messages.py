"""create chats + messages; close inference_routing_log FKs — Task C3

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-08

Adds the chat-persistence tables per ``docs/db-schema.md`` §`chats` /
§`messages` (with C3-specific deviations documented inline below) and
PRD §3.13. Two new tables, plus an ALTER on ``inference_routing_log``
to wire the deferred FK constraints that 0001 left dangling.

What lands:

* ``chats`` — owner-scoped chat container. ``title`` is NOT NULL with a
  ``"New chat"`` default; the API auto-renames the chat from the first
  user message's first 80 chars (see ``_auto_rename_chat`` in
  ``app/api/chats.py``). Soft-delete via ``archived_at`` (matches C7's
  posture; hard-delete is D6 territory).
* ``messages`` — one row per message exchange. ``role`` is
  CHECK-constrained to ``{user, assistant, system, tool}``. Routing
  metadata (``routed_inference_tier``, ``routed_provider``,
  ``routed_model``, token counts, cost) is persisted on assistant
  messages from the gateway's response. Cost is stored as
  ``cost_estimate_micros`` (BIGINT, USD micros) to avoid float drift
  in the audit trail; see C3's docstring on the chats handler and
  ``docs/db-schema.md`` for the unit. ``applied_skills`` is a
  ``text[]`` per ADR 0007 (skills are filesystem-canonical; no SQL
  table to FK to). ``citations`` is a ``jsonb`` column initialized to
  ``'[]'``; M2's citation engine populates the schema.
* ``inference_routing_log.chat_id`` and ``.message_id`` FK constraints
  added. Both ``ON DELETE SET NULL`` to preserve audit history when a
  chat or message row goes away (an audit log cannot be expunged just
  because the underlying conversation was deleted; D6 owns the
  user-deletion path that walks audit_log too).

Per A2's choice we use ``gen_random_uuid()`` (UUIDv4); the schema doc
shows ``uuid_generate_v7()`` aspirationally — not blocking C3.

Indexes:

* ``idx_chats_owner_active`` on ``(owner_id, created_at DESC)`` WHERE
  ``archived_at IS NULL`` — listing endpoint's primary read shape.
* ``idx_chats_project_active`` on ``(project_id)`` WHERE
  ``project_id IS NOT NULL AND archived_at IS NULL`` — project's-chats
  filter.
* ``idx_messages_chat_created`` on ``(chat_id, created_at)`` — ordered
  retrieval of a chat's history (the per-chat conversation read).

``updated_at`` on ``chats`` is maintained by the existing
``set_updated_at()`` trigger (created in 0001).

Reversible: downgrade drops the FKs on ``inference_routing_log`` then
the two tables in reverse dependency order (messages first, then chats
since ``messages.chat_id`` references ``chats.id``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # chats
    # ------------------------------------------------------------------
    op.create_table(
        "chats",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            # ON DELETE RESTRICT — audit-log integrity. D6 owns the
            # per-user export+delete path which deletes a user's chats
            # explicitly before deleting the user.
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_chats_owner_id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            # ON DELETE SET NULL — chats outlive their projects (per
            # C7's posture: archiving a project does not invalidate the
            # conversations that happened inside it).
            sa.ForeignKey("projects.id", ondelete="SET NULL", name="fk_chats_project_id"),
            nullable=True,
        ),
        sa.Column(
            "title",
            sa.Text(),
            nullable=False,
            # Default at the DB so the column is NOT NULL even when a
            # caller POSTs ``{}``. The API auto-renames the chat from
            # the first user message; if the user never sends one, the
            # default sticks.
            server_default=sa.text("'New chat'"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            name="chk_chats_title_len",
        ),
    )

    # Active-listing index — owner's non-archived chats, newest first.
    op.execute(
        """
        CREATE INDEX idx_chats_owner_active
            ON chats (owner_id, created_at DESC)
            WHERE archived_at IS NULL
        """
    )

    # Project-scoped filter — only fires when a chat is in a project.
    op.execute(
        """
        CREATE INDEX idx_chats_project_active
            ON chats (project_id)
            WHERE project_id IS NOT NULL AND archived_at IS NULL
        """
    )

    # updated_at trigger reuses the function created in 0001.
    op.execute(
        """
        CREATE TRIGGER trg_chats_set_updated_at
            BEFORE UPDATE ON chats
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at()
        """
    )

    # ------------------------------------------------------------------
    # messages
    # ------------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "chat_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chats.id", ondelete="CASCADE", name="fk_messages_chat_id"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Audit trail of which skills shaped this message exchange. Per
        # ADR 0007 we denormalize as a text array — skills are
        # filesystem-canonical (no skills SQL table) and audit reads
        # are write-light, so an extra join table costs more than it
        # saves.
        sa.Column(
            "applied_skills",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        # Routing metadata (set on assistant messages from the gateway's
        # response). User / system / tool messages leave these NULL.
        sa.Column("routed_inference_tier", sa.SmallInteger(), nullable=True),
        sa.Column("routed_provider", sa.Text(), nullable=True),
        sa.Column("routed_model", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        # Cost stored as integer USD micros to avoid float drift in the
        # audit trail. The gateway returns ``cost_estimate`` as a float
        # USD value; we round to 6 decimal places (1 micro) on persist.
        # Documented in ``docs/db-schema.md``.
        sa.Column("cost_estimate_micros", sa.BigInteger(), nullable=True),
        # Populated when the assistant message failed mid-stream or the
        # gateway raised an LQAIError; carries the canonical
        # ``app.errors`` code (e.g., ``provider_unavailable``,
        # ``gateway_timeout``). NULL on success.
        sa.Column("error_code", sa.Text(), nullable=True),
        # M2's citation engine populates the structured shape here. C3
        # initializes to ``[]`` so the column is queryable.
        sa.Column(
            "citations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="chk_messages_role",
        ),
        sa.CheckConstraint(
            "routed_inference_tier IS NULL OR (routed_inference_tier BETWEEN 1 AND 5)",
            name="chk_messages_tier_range",
        ),
        sa.CheckConstraint(
            "prompt_tokens IS NULL OR prompt_tokens >= 0",
            name="chk_messages_prompt_tokens_nonneg",
        ),
        sa.CheckConstraint(
            "completion_tokens IS NULL OR completion_tokens >= 0",
            name="chk_messages_completion_tokens_nonneg",
        ),
    )

    # Ordered retrieval of a chat's history.
    op.execute("CREATE INDEX idx_messages_chat_created ON messages (chat_id, created_at)")

    # ------------------------------------------------------------------
    # Close A2's deferred FK constraints on inference_routing_log.
    # ------------------------------------------------------------------
    # 0001 left ``chat_id`` and ``message_id`` as plain UUID columns
    # (no FK) because ``chats`` and ``messages`` didn't exist. They do
    # now. ON DELETE SET NULL because deleting a chat or message must
    # not silently expunge audit-log rows; the routing log is a
    # canonical record of what was routed and why, surviving
    # higher-level resource lifecycle.
    op.create_foreign_key(
        constraint_name="fk_inference_routing_log_chat_id",
        source_table="inference_routing_log",
        referent_table="chats",
        local_cols=["chat_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        constraint_name="fk_inference_routing_log_message_id",
        source_table="inference_routing_log",
        referent_table="messages",
        local_cols=["message_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop the routing-log FKs first; the columns themselves stay
    # (they belong to 0001 and 0001 keeps them nullable without an
    # FK, which is exactly the post-downgrade state).
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

    # Drop in reverse FK-dependency order. ``messages.chat_id`` ->
    # ``chats.id`` so messages must go first.
    op.drop_table("messages")

    op.execute("DROP TRIGGER IF EXISTS trg_chats_set_updated_at ON chats")
    op.drop_table("chats")
