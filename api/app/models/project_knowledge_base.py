"""ProjectKnowledgeBase — matter <-> KB junction.

Composite PK on (project_id, knowledge_base_id). Both side FKs CASCADE
so deleting a project or KB removes the attachment row. attached_at
+ attached_by_user_id record who/when for audit ordering. Required
for Wave D.1 KB attach modal (spec §7.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectKnowledgeBase(Base):
    """Many-to-many junction between projects (matters) and knowledge_bases.

    Wire shape mirrors the ProjectFile and ProjectSkill junctions: composite
    PK, CASCADE on both side FKs, SET NULL on attached_by_user_id so audit
    rows survive user deletion. Created by Wave D.1 plan T2.
    """

    __tablename__ = "project_knowledge_bases"
    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id",
            "knowledge_base_id",
            name="pk_project_knowledge_bases",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="CASCADE",
            name="fk_project_knowledge_bases_project_id",
        ),
        nullable=False,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "knowledge_bases.id",
            ondelete="CASCADE",
            name="fk_project_knowledge_bases_kb_id",
        ),
        nullable=False,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    attached_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_project_knowledge_bases_attached_by",
        ),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<ProjectKnowledgeBase project_id={self.project_id} kb_id={self.knowledge_base_id}>"
