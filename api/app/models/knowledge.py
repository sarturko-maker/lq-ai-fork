"""KnowledgeBase ORM models — per docs/db-schema.md §`knowledge_bases`.

A KnowledgeBase is a user-curated collection of files that can be
queried via hybrid (vector + full-text) retrieval. Users attach files
that have completed C5's document pipeline (``ingestion_status='ready'``)
and then run queries against the KB; the C6 retrieval surface returns
ranked chunks with combined vector + FTS scores.

Lifecycle (M1):

* Created on `POST /api/v1/knowledge-bases` (Task C6).
* Files attached/detached via
  `POST/DELETE /api/v1/knowledge-bases/{id}/files`.
* Queried via `POST /api/v1/knowledge-bases/{id}/query`.
* Soft-deleted via `DELETE /api/v1/knowledge-bases/{id}` — flips
  ``archived_at`` from NULL to ``now()``. Hard-delete is D6 territory.

The ``hybrid_alpha`` field is the per-KB default for the linear-combine
of vector and FTS scores. Per-query overrides are accepted at the
query handler boundary.

Per ADR 0008 the embedding column on ``document_chunks`` is
``vector(1536)``; this module owns the join shape, not the chunk
embedding column.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    PrimaryKeyConstraint,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeBase(Base):
    """A user-curated collection of files for hybrid retrieval.

    ``hybrid_alpha`` is the per-KB default for the score combine
    (0=vector-only, 1=FTS-only, 0.5=balanced). The DB CHECK constraint
    enforces ``[0, 1]``; the API also clamps at the request boundary.

    ``archived_at`` is the soft-delete column — set on `DELETE`, NULL
    means active.
    """

    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            "hybrid_alpha >= 0.0 AND hybrid_alpha <= 1.0",
            name="chk_knowledge_bases_alpha_range",
        ),
        CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_knowledge_bases_name_len",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_knowledge_bases_owner_id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id", ondelete="SET NULL", name="fk_knowledge_bases_project_id"
        ),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hybrid_alpha: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.5"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeBase id={self.id} owner_id={self.owner_id} "
            f"name={self.name!r} alpha={self.hybrid_alpha} "
            f"archived={self.archived_at is not None}>"
        )


class KnowledgeBaseFile(Base):
    """Many-to-many join: knowledge_base ↔ file.

    Both ends ``ON DELETE CASCADE`` — dropping a KB removes its
    attachments; hard-deleting a file removes the join rows referencing
    it (D6 path; soft-delete leaves attachments intact). The composite
    ``(kb_id, file_id)`` is the primary key.
    """

    __tablename__ = "knowledge_base_files"
    __table_args__ = (
        PrimaryKeyConstraint("kb_id", "file_id", name="pk_knowledge_base_files"),
    )

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE", name="fk_kb_files_kb_id"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE", name="fk_kb_files_file_id"),
        nullable=False,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeBaseFile kb_id={self.kb_id} file_id={self.file_id}>"
