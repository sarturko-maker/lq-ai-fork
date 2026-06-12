"""Organization Profile ORM model — Task D4.

Backs the singleton ``organization_profile`` table per migration 0010.
The Organization Profile is the org-wide voice / templates / "what
good looks like" reference automatically prepended to every skill's
prompt (per PRD §3.12) — ADR 0004 keeps built-in skills filesystem-
canonical, so a focused single-row table is a smaller surface than
introducing a full ``skills`` SQL table.

Singleton constraint enforced at the DB layer via the partial unique
index on ``((true))`` (see migration 0010); the GET/PUT endpoints
keep the row in place by upserting rather than inserting.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganizationProfile(Base):
    """The deployment's singleton Organization Profile content.

    ``content_md`` is a Markdown body — the "skill body" portion of a
    SKILL.md. The frontmatter equivalent (``is_organization_profile:
    true``, ``output_format: report``, etc.) is synthesized at fetch
    time so the gateway sees a normal :class:`Skill` shape.

    ``updated_by`` is the user who last performed a PUT. Nullable
    because PRD §3.12 doesn't require attribution on the read side
    (admin-edited; the column is informational and survives the
    user's own deletion via ``ON DELETE SET NULL``).
    """

    __tablename__ = "organization_profile"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    content_md: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
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
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_org_profile_updated_by"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<OrganizationProfile id={self.id} "
            f"len={len(self.content_md or '')} updated_at={self.updated_at}>"
        )
