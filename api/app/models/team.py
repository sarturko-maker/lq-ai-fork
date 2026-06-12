"""Team + TeamMember ORM models — Task D8.1a.

Backs the ``teams`` and ``team_members`` tables per migration 0014.
Membership model is operator-admin-controlled (ADR 0012 §"Out of
scope" + the D8.1 design decisions): ``is_admin`` users create teams
and assign members; each membership row carries a ``role`` (``admin``
or ``member``) that determines mutate rights on team-scope skills
once D8.1b lands.

Deleting a team cascades to ``team_members`` (membership disappears
with the team) and to ``user_skills`` with ``scope='team'`` (the
team's skill library is removed with the team). User deletion
cascades into membership rows so a deleted user is removed from
every team they belonged to; teams they created persist (the
``created_by_user_id`` FK is RESTRICT — operators must explicitly
re-assign or delete a team before deleting its creator).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Team(Base):
    """A named group whose members can share team-scope skills (D8.1)."""

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    """Stable lowercase identifier; unique across the deployment."""

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_teams_created_by"),
        nullable=False,
    )
    """The operator-admin who created this team. RESTRICT — deleting the
    creating user requires re-assigning or deleting the team first."""

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

    def __repr__(self) -> str:
        return f"<Team id={self.id} slug={self.slug!r} name={self.name!r}>"


class TeamMember(Base):
    """Membership of one user in one team, with role.

    Composite primary key on ``(team_id, user_id)`` — a user can belong
    to a team at most once. Both columns CASCADE on user/team delete so
    membership rows never outlive their referents.
    """

    __tablename__ = "team_members"
    __table_args__ = (
        PrimaryKeyConstraint("team_id", "user_id", name="pk_team_members"),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE", name="fk_team_members_team"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_team_members_user"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    """One of ``'admin'`` (mutate rights on team-scope skills in D8.1b)
    or ``'member'`` (read-only access). CHECK constraint enforces the
    enum at the DB layer."""

    added_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_team_members_added_by"),
        nullable=False,
    )
    """The operator-admin who added this membership row. RESTRICT so
    audit-log forensics ('who let X into team Y?') survive user
    deletion until the membership row itself is gone."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return f"<TeamMember team_id={self.team_id} user_id={self.user_id} role={self.role!r}>"
