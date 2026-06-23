"""matter_memory_entries typed bi-temporal facts — C3b-1 (fork, ADR-F042)

Layers the typed-fact columns onto the C3a ``matter_memory_entries`` table, exactly
as the ``0068`` docstring promised: **additive-nullable, NO backfill**. Existing
``correction`` / ``wiki_snapshot`` rows keep ``body_md`` and leave the new columns
NULL; the new ``kind='fact'`` rows (the agent's dated fact ledger) populate them.

Ported from Graphiti's bi-temporal field set (`matter-memory-reuse.md`): a fact's
statement reuses ``body_md`` (so the body-length CHECK + the no-leak audit envelope
carry over unchanged), and the structure is added as nullable columns:

* ``author``         — who recorded a fact (``'agent'``). The CHECK also admits
  ``'lawyer'``, reserved for a future pin-endpoint change; C3b-1 does NOT populate it
  (existing correction rows keep ``author`` NULL — additive-nullable, no backfill).
  No agent path mints a human author (B2).
* ``source_citation`` — the agent-supplied PROSE source ("Cirrus MSA §9"); the
  structured Citation-Engine reference is deferred (the agent's doc tools expose
  only filename/page/snippet, never document ids/offsets).
* ``fact_type``      — a small area-neutral enum (party/term/date/decision/open_point/fact).
* ``valid_at`` / ``invalid_at`` — WORLD-time validity window (distinct from
  ``created_at`` = ingestion-time). Supersede = set ``invalid_at``, never delete —
  answering "what did we believe at signing" (``valid_at ≤ T < invalid_at``).
* ``superseded_by``  — the explicit forward link to the fact that replaced this one
  (a plain UUID, mirroring ``run_id`` — referential integrity is not load-bearing
  here, the temporal window is).

The CHECK constraints mirror ``app.models.project.MatterMemoryEntry`` (and the
boundary caps in ``app.schemas.matter_memory``) — reject, don't truncate; the
literals must stay identical across migration DDL / ORM / Pydantic enum.

Revision ID: 0070
Revises: 0069
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

_SOURCE_MAX_CHARS = 500


def upgrade() -> None:
    # Additive-nullable typed-fact columns (no server_default, no backfill).
    op.add_column("matter_memory_entries", sa.Column("author", sa.Text(), nullable=True))
    op.add_column("matter_memory_entries", sa.Column("source_citation", sa.Text(), nullable=True))
    op.add_column("matter_memory_entries", sa.Column("fact_type", sa.Text(), nullable=True))
    op.add_column(
        "matter_memory_entries",
        sa.Column("valid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matter_memory_entries",
        sa.Column("invalid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matter_memory_entries",
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Extend the kind domain to admit the typed-fact kind.
    op.drop_constraint("chk_matter_memory_entries_kind", "matter_memory_entries", type_="check")
    op.create_check_constraint(
        "chk_matter_memory_entries_kind",
        "matter_memory_entries",
        "kind IN ('correction', 'wiki_snapshot', 'fact')",
    )

    # Nullable-enum + temporal + length CHECKs (defense-in-depth; the Pydantic
    # schema is the user-facing boundary).
    op.create_check_constraint(
        "chk_matter_memory_entries_author",
        "matter_memory_entries",
        "author IS NULL OR author IN ('agent', 'lawyer')",
    )
    op.create_check_constraint(
        "chk_matter_memory_entries_fact_type",
        "matter_memory_entries",
        "fact_type IS NULL OR fact_type IN "
        "('party', 'term', 'date', 'decision', 'open_point', 'fact')",
    )
    op.create_check_constraint(
        "chk_matter_memory_entries_valid_window",
        "matter_memory_entries",
        "invalid_at IS NULL OR valid_at IS NULL OR invalid_at > valid_at",
    )
    op.create_check_constraint(
        "chk_matter_memory_entries_source_len",
        "matter_memory_entries",
        f"source_citation IS NULL OR char_length(source_citation) BETWEEN 1 AND {_SOURCE_MAX_CHARS}",
    )


def downgrade() -> None:
    # Typed-fact rows cannot survive the reverted (stricter) kind CHECK.
    op.execute("DELETE FROM matter_memory_entries WHERE kind = 'fact'")
    op.drop_constraint(
        "chk_matter_memory_entries_source_len", "matter_memory_entries", type_="check"
    )
    op.drop_constraint(
        "chk_matter_memory_entries_valid_window", "matter_memory_entries", type_="check"
    )
    op.drop_constraint(
        "chk_matter_memory_entries_fact_type", "matter_memory_entries", type_="check"
    )
    op.drop_constraint("chk_matter_memory_entries_author", "matter_memory_entries", type_="check")
    op.drop_constraint("chk_matter_memory_entries_kind", "matter_memory_entries", type_="check")
    op.create_check_constraint(
        "chk_matter_memory_entries_kind",
        "matter_memory_entries",
        "kind IN ('correction', 'wiki_snapshot')",
    )

    op.drop_column("matter_memory_entries", "superseded_by")
    op.drop_column("matter_memory_entries", "invalid_at")
    op.drop_column("matter_memory_entries", "valid_at")
    op.drop_column("matter_memory_entries", "fact_type")
    op.drop_column("matter_memory_entries", "source_citation")
    op.drop_column("matter_memory_entries", "author")
