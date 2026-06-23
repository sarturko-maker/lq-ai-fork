"""matter_memory_entries — C3a (fork, ADR-F042): the unit-of-work memory spine

The durable store behind the auto-maintained "matter wiki" (the unit-of-work tier
of the 4-level memory model). The wiki itself stays the free-form
``projects.context_md`` (rewritten in place by the agent's ``update_matter_memory``
tool); THIS table holds the spine around it:

* ``wiki_snapshot`` rows — the prior ``context_md`` captured before each agent
  rewrite (undo substrate; ``trust='normal'``; ``run_id`` = the run that wrote it).
* ``correction`` rows — the supervising lawyer's corrections. ``trust='human-pinned'``,
  written ONLY through the authenticated human endpoint (no agent tool mints one —
  an agent-asserted "the lawyer said X" is forgeable by injection; ADR-F042 §Decision).
  The agent's auto-curation is structurally unable to touch these (it writes only
  ``context_md`` + ``wiki_snapshot`` rows).

**Additive-nullable on purpose (ADR-F042 Consequences):** C3b layers the typed
bi-temporal fact columns (``valid_at``/``invalid_at``/``superseded_by``/``value``/
``author``/``source_citation``/``type``) onto this same table as nullable columns
with NO backfill — correction/snapshot rows keep ``body_md``, typed-fact rows
populate the new columns. ``superseded_at`` is the C3a soft-supersede column.

The CHECK constraints mirror ``app.models.project.MatterMemoryEntry`` (and the
boundary caps in ``app.schemas.matter_memory`` / the pin endpoint) as the DB guard
— reject, don't truncate. The ``body_md`` cap is generous because a ``wiki_snapshot``
stores a prior ``context_md`` (PATCH-capped at 100 KiB), so it must exceed that.

Revision ID: 0068
Revises: 0067
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

_BODY_MAX_CHARS = 200_000


def upgrade() -> None:
    op.create_table(
        "matter_memory_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id",
                ondelete="CASCADE",
                name="fk_matter_memory_entries_project_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_matter_memory_entries_user_id",
            ),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("trust", sa.Text(), nullable=False, server_default=sa.text("'normal'")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "kind IN ('correction', 'wiki_snapshot')",
            name="chk_matter_memory_entries_kind",
        ),
        sa.CheckConstraint(
            "trust IN ('normal', 'human-pinned')",
            name="chk_matter_memory_entries_trust",
        ),
        sa.CheckConstraint(
            f"char_length(body_md) BETWEEN 1 AND {_BODY_MAX_CHARS}",
            name="chk_matter_memory_entries_body_len",
        ),
    )
    # The hot read: "the live pinned corrections of this matter" (injected every
    # run) — filters project_id + kind, orders by created_at.
    op.create_index(
        "ix_matter_memory_entries_project_kind_created",
        "matter_memory_entries",
        ["project_id", "kind", "created_at"],
    )
    # Cover the user_id FK (cascade hygiene; academic given projects.owner_id RESTRICT).
    op.create_index(
        "ix_matter_memory_entries_user_id",
        "matter_memory_entries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_matter_memory_entries_user_id", table_name="matter_memory_entries")
    op.drop_index(
        "ix_matter_memory_entries_project_kind_created",
        table_name="matter_memory_entries",
    )
    op.drop_table("matter_memory_entries")
