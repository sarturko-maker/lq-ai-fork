"""INTAKE-1 substrate — projects.intake_state + intake_mailboxes/threads/messages (ADR-F086)

Additive-only schema for the "agent-monitored legal-intake inbox" milestone
(`docs/fork/plans/INTAKE-INBOX-plan.md`). No existing row is touched; every
new column is nullable-or-defaulted so every pre-existing ``projects`` row
keeps ``intake_state IS NULL`` (a normal matter, unaffected).

Four schema items:

* ``projects.intake_state`` — nullable TEXT, CHECK IN ('candidate',
  'promoted','dismissed'). NULL = normal matter (the overwhelming majority).
  Seam: the project row is created EAGERLY at ingest time (runs/files are
  project-scoped substrate, not policy); the agent's later
  ``record_intake_outcome`` (INTAKE-3) sets this to 'promoted' or
  'dismissed', or leaves it 'candidate' pending human review.
* ``intake_mailboxes`` — the admin-owned binding of one mailbox to one
  practice area + one owner user. Soft-deleted ``slack_workspaces``-style
  (this migration's closest precedent, ``0037_slack_workspaces.py``);
  uniqueness on (provider, inbox_id) is enforced on LIVE rows only via a
  partial index so a re-bind after disconnect doesn't collide with its own
  soft-deleted history.
* ``intake_threads`` — one row per provider email thread. UNIQUE
  (mailbox_id, provider_thread_id).
* ``intake_messages`` — the idempotency anchor: UNIQUE (thread_id,
  provider_message_id) makes duplicate webhook/websocket delivery a no-op
  on the unique key, per the plan's "Risks" section.

Downgrade is lossy only in the sense that any row using a value the
re-narrowed CHECK would reject can't exist by construction at this point in
history (no application code writes these columns before this migration
ships) — plain DROP TABLE / DROP COLUMN, no data-preservation UPDATE needed
(cf. 0093's downgrade, which DOES need one because 'awaiting_input' rows can
already exist by the time that migration is reverted).

Revision ID: 0098
Revises: 0097
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

# CHECK value sets — mirror app.models.intake's private tuples. Keep in sync.
_THREAD_STATUSES = ("received", "processing", "awaiting_human", "replied", "handled", "error")
_AUTH_STATES = ("pass", "fail", "unknown")
_MESSAGE_DIRECTIONS = ("in", "out")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # -------------------------------------------------------------------
    # projects.intake_state (ADR-F086 seam — see app.models.project.Project
    # .intake_state for the code-side comment at the column).
    # -------------------------------------------------------------------
    op.execute("ALTER TABLE projects ADD COLUMN intake_state TEXT")
    op.execute(
        "ALTER TABLE projects ADD CONSTRAINT chk_projects_intake_state "
        "CHECK (intake_state IS NULL OR intake_state IN ('candidate','promoted','dismissed'))"
    )

    # -------------------------------------------------------------------
    # intake_mailboxes
    # -------------------------------------------------------------------
    op.create_table(
        "intake_mailboxes",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("provider", sa.Text(), nullable=False, server_default=sa.text("'agentmail'")),
        sa.Column("inbox_id", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column(
            "practice_area_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "practice_areas.id",
                ondelete="RESTRICT",
                name="fk_intake_mailboxes_practice_area_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", ondelete="RESTRICT", name="fk_intake_mailboxes_owner_user_id"
            ),
            nullable=False,
        ),
        sa.Column("default_budget_profile", sa.Text(), nullable=True),
        sa.Column("max_steps", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(provider) BETWEEN 1 AND 50", name="chk_intake_mailboxes_provider_len"
        ),
        sa.CheckConstraint(
            "char_length(inbox_id) BETWEEN 1 AND 500", name="chk_intake_mailboxes_inbox_id_len"
        ),
        sa.CheckConstraint(
            "char_length(address) BETWEEN 1 AND 320", name="chk_intake_mailboxes_address_len"
        ),
        sa.CheckConstraint(
            "max_steps IS NULL OR (max_steps BETWEEN 1 AND 600)",
            name="chk_intake_mailboxes_max_steps_range",
        ),
    )
    # Uniqueness on LIVE rows only (partial index) — a soft-deleted mailbox's
    # (provider, inbox_id) can be re-bound by a fresh row without colliding
    # with its own history. Mirrors idx_projects_not_sandbox's shape (0022).
    op.create_index(
        "uq_intake_mailboxes_provider_inbox_live",
        "intake_mailboxes",
        ["provider", "inbox_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # -------------------------------------------------------------------
    # intake_threads
    # -------------------------------------------------------------------
    op.create_table(
        "intake_threads",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "mailbox_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "intake_mailboxes.id", ondelete="CASCADE", name="fk_intake_threads_mailbox_id"
            ),
            nullable=False,
        ),
        sa.Column("provider_thread_id", sa.Text(), nullable=False),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL", name="fk_intake_threads_project_id"),
            nullable=True,
        ),
        sa.Column(
            "agent_thread_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "agent_threads.id",
                ondelete="SET NULL",
                name="fk_intake_threads_agent_thread_id",
            ),
            nullable=True,
        ),
        sa.Column("subject", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'received'")),
        sa.Column("last_message_id", sa.Text(), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_state", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
        sa.UniqueConstraint(
            "mailbox_id",
            "provider_thread_id",
            name="uq_intake_threads_mailbox_provider_thread",
        ),
        sa.CheckConstraint(_in_set("status", _THREAD_STATUSES), name="chk_intake_threads_status"),
        sa.CheckConstraint(
            _in_set("auth_state", _AUTH_STATES), name="chk_intake_threads_auth_state"
        ),
        sa.CheckConstraint("char_length(subject) <= 998", name="chk_intake_threads_subject_len"),
        sa.CheckConstraint(
            "label IS NULL OR char_length(label) BETWEEN 1 AND 200",
            name="chk_intake_threads_label_len",
        ),
    )

    # -------------------------------------------------------------------
    # intake_messages
    # -------------------------------------------------------------------
    op.create_table(
        "intake_messages",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "thread_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "intake_threads.id", ondelete="CASCADE", name="fk_intake_messages_thread_id"
            ),
            nullable=False,
        ),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL", name="fk_intake_messages_run_id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "thread_id",
            "provider_message_id",
            name="uq_intake_messages_thread_provider_message",
        ),
        sa.CheckConstraint(
            _in_set("direction", _MESSAGE_DIRECTIONS), name="chk_intake_messages_direction"
        ),
    )


def downgrade() -> None:
    op.drop_table("intake_messages")
    op.drop_table("intake_threads")
    op.drop_index("uq_intake_mailboxes_provider_inbox_live", table_name="intake_mailboxes")
    op.drop_table("intake_mailboxes")
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS chk_projects_intake_state")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS intake_state")
