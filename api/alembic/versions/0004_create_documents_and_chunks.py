"""create documents and document_chunks tables — Task C5

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-08

Adds the `documents` and `document_chunks` tables per
docs/db-schema.md §`documents` and §`document_chunks`. Also enables
the pgvector extension so embeddings (deferred to C6 per ADR 0006)
can land via ALTER TABLE without a migration that needs CREATE
EXTENSION privileges.

Notes:
- Per ADR 0006 the embeddings column is nullable for M1 — C6 will
  backfill once the embedding model selection lands.
- `documents.file_id` has ON DELETE CASCADE: if a file is hard-deleted
  (D6 export+delete or a future GC sweep) all its parsed artifacts go
  with it. C4's soft-delete does NOT trigger this — soft-delete leaves
  the bytes and chunks intact for the audit window.
- `document_chunks.document_id` ON DELETE CASCADE follows the same
  pattern: hard-deleting a document drops every chunk.
- `(document_id, chunk_index)` UNIQUE constraint backs the
  idempotency-on-replace strategy (the worker deletes prior chunks for
  a document before re-inserting).
- `content_tsv` is a generated TSVECTOR column — Postgres maintains it
  on every INSERT/UPDATE, no application code involved. C6 hybrid
  retrieval reads from it via the GIN index.
- `embedding` is `VECTOR(1536)` — sized for OpenAI's
  text-embedding-3-small / -large; if C6 picks a different model with
  a different dim, a migration ALTER TABLE swaps it. The dim is part
  of the column type, so changing it is a destructive ALTER (drop and
  re-add); for M1 we accept this.
- `idx_chunks_embedding` is `ivfflat` per docs/db-schema.md §349; for
  larger deployments the schema doc suggests `hnsw`. We follow the
  schema doc.

Reversible: downgrade drops the tables (CASCADE removes the indexes);
the pgvector extension stays installed because other apps in the
cluster may rely on it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions — pgvector for embeddings (C6 will backfill; C5 writes
    # NULL for the embedding column per ADR 0006).
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE", name="fk_documents_file_id"),
            nullable=False,
            unique=True,
        ),
        # Parser used: 'docling+pymupdf' (both succeeded), 'pymupdf' (Docling
        # fell through), 'docling' (PyMuPDF unavailable — not currently a
        # supported path; reserved for future). Free-text rather than enum
        # so future parser additions don't need a migration.
        sa.Column("parser", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("character_count", sa.Integer(), nullable=True),
        # Docling's structured representation. Stashed for M2 consumption;
        # M1's chunker drives off the PyMuPDF character stream and ignores
        # this column. JSONB so future readers can index into it.
        sa.Column("structured_content", postgresql.JSONB(), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.execute("CREATE INDEX idx_documents_file_id ON documents (file_id)")

    # ------------------------------------------------------------------
    # document_chunks
    # ------------------------------------------------------------------
    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "documents.id", ondelete="CASCADE", name="fk_document_chunks_document_id"
            ),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("char_offset_start", sa.Integer(), nullable=False),
        sa.Column("char_offset_end", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
        # `embedding` is added via raw DDL below — pgvector's `vector`
        # type isn't first-class in SQLAlchemy core. Per ADR 0006 the
        # column is nullable for M1; C6 backfills.
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_doc_idx"),
        sa.CheckConstraint(
            "char_offset_start >= 0",
            name="chk_document_chunks_offset_start_nonneg",
        ),
        sa.CheckConstraint(
            "char_offset_end >= char_offset_start",
            name="chk_document_chunks_offset_end_gte_start",
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="chk_document_chunks_index_nonneg",
        ),
    )

    # Add the pgvector `embedding` column via raw DDL — the type
    # isn't first-class in SQLAlchemy core without the optional
    # `pgvector` package. Per ADR 0006 the column stays NULL for M1;
    # C6 backfills.
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(1536)")

    # Generated TSVECTOR column — Postgres maintains it on every
    # INSERT/UPDATE. Used by C6's hybrid (vector + FTS) retrieval.
    # Generated columns can't be expressed cleanly via SQLAlchemy core
    # in 2.0 without per-dialect compiler hooks; raw DDL is clearer.
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN content_tsv TSVECTOR
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        """
    )

    # GIN index on the TSVECTOR for FTS queries (C6).
    op.execute("CREATE INDEX idx_chunks_tsv ON document_chunks USING gin (content_tsv)")

    # ANN index on the embedding column. ivfflat per docs/db-schema.md
    # §349 — sufficient for moderate scale; transition to hnsw for
    # larger deployments. The index can be created against an empty
    # table; the vector(1536) declaration is required for ivfflat to
    # attach (it doesn't work on plain float arrays).
    op.execute(
        """
        CREATE INDEX idx_chunks_embedding
            ON document_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """
    )

    # Ordered-retrieval index — the (document_id, chunk_index) pair is
    # already UNIQUE so this is mostly redundant, but the schema doc
    # specifies it explicitly and ordered scans benefit from the index
    # being declared as a regular B-tree.
    op.execute("CREATE INDEX idx_chunks_document ON document_chunks (document_id, chunk_index)")


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("documents")
    # The vector extension stays installed; other apps in the cluster
    # may rely on it. Dropping an extension in a downgrade is generally
    # undesirable.
