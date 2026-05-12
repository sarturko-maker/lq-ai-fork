"""ProjectKnowledgeBase — matter <-> KB junction.

Composite PK on (project_id, knowledge_base_id). Both FKs CASCADE so
deleting a project or KB removes the attachment row. attached_at
+ attached_by_user_id record who/when for audit ordering. Required
for Wave D.1 KB attach modal (spec §7.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectKnowledgeBase(Base):
    __tablename__ = "project_knowledge_bases"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_pkb_project_id"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE", name="fk_pkb_kb_id"),
        primary_key=True,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    attached_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_pkb_attached_by"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectKnowledgeBase project_id={self.project_id} "
            f"kb_id={self.knowledge_base_id}>"
        )
