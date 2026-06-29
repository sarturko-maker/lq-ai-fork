"""document_chunks.embedding_local vector(768) — local-embedder column (ADR-F049 Slice C1)

The matter/agent retrieval path gets its own pgvector column for the in-process
local embedder (Door A, BAAI/bge-base-en-v1.5, 768-dim). This is **additive and
non-destructive**: the existing ``embedding vector(1536)`` column + its
``idx_chunks_embedding`` index are left untouched (the KB/chat path keeps the
gateway's native 1536). The maintainer ruled "keep both doors available, no
one-way destructive dim ALTER" — a second column, not a recreate, is how.

768 is coupled to bge-base-en-v1.5; if a future ADR repoints the matter embedder
to a different-dim model, that's another additive column or its own migration.
The column stays NULL until the local embed worker backfills it (graceful FTS
degrade meanwhile); the ivfflat index attaches to the empty column fine (the
``vector(768)`` declaration is what it needs).

Revision ID: 0078
Revises: 0077
Create Date: 2026-06-29
"""

from __future__ import annotations

from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive local-embedder column — raw DDL, like the 1536 column (0005): the
    # pgvector type isn't first-class in SQLAlchemy core. Nullable; the local
    # embed worker fills it (idempotent on `embedding_local IS NULL`).
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding_local vector(768)")

    # Cosine ANN index, mirroring idx_chunks_embedding (ivfflat, lists=100 —
    # sufficient at matter scale). Builds against the empty column.
    op.execute(
        """
        CREATE INDEX idx_chunks_embedding_local
            ON document_chunks
            USING ivfflat (embedding_local vector_cosine_ops)
            WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_local")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_local")
