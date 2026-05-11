"""tsvector + GIN indexes on chats.title and messages.content — Wave B

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-11

Wave B of the M1 backend gap-fill. Backs the ``GET /api/v1/chats/search``
endpoint (PRD §1.7 success criterion: "search prior chats") with a
proper Postgres FTS index rather than ILIKE.

Two generated TSVECTOR columns (Postgres maintains both on
INSERT/UPDATE — same pattern as ``document_chunks.content_tsv`` from
migration 0005):

* ``chats.title_tsv`` — short, weighted to favor matches.
* ``messages.content_tsv`` — long; the actual conversation substance.

Each gets a GIN index for sub-linear FTS scans. The handler combines
both in a UNION-style query that returns chat rows + the snippet of
the matching message.

Reversible: ``downgrade()`` drops the indexes + columns.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- chats.title_tsv ---------------------------------------------------
    op.execute(
        """
        ALTER TABLE chats
        ADD COLUMN title_tsv TSVECTOR
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, ''))) STORED
        """
    )
    op.execute("CREATE INDEX idx_chats_title_tsv ON chats USING gin (title_tsv)")

    # --- messages.content_tsv ----------------------------------------------
    op.execute(
        """
        ALTER TABLE messages
        ADD COLUMN content_tsv TSVECTOR
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX idx_messages_content_tsv ON messages USING gin (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_messages_content_tsv")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS content_tsv")
    op.execute("DROP INDEX IF EXISTS idx_chats_title_tsv")
    op.execute("ALTER TABLE chats DROP COLUMN IF EXISTS title_tsv")
