"""OrgSkillVersion ORM model — org-authored skill propose/approve harness (ADR-F067 D2/D3, B-2a).

Backs the ``org_skill_versions`` table per migration 0091. See that migration's docstring for
the full design rationale, including the implementer's-call that proposal state lives HERE and
``user_skills`` is left completely untouched.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrgSkillVersion(Base):
    """One org-authored skill version — either an open proposal or an immutable approved
    snapshot (ADR-F067 D2/D3).

    Content columns (``slug``, ``version_no``, ``raw_yaml``, ``body``, ``frontmatter``,
    ``content_hash``, ``source_user_skill_id``, ``author_user_id``) are written once at INSERT
    and never updated — "approval pins bytes, not a row" (D2). Only the state/review/revoke
    columns transition: ``proposed -> approved | rejected``; ``approved -> revoked |
    superseded`` (``superseded`` is set only by a newer approval of the same slug, never via an
    endpoint).

    The runtime reads ONLY ``state == 'approved'`` rows (never the live, mutable
    ``user_skills`` row) at the two composition chokepoints
    (``build_area_inventory`` / ``build_area_skill_wiring``) — this is the TOCTOU-closing
    invariant the whole harness exists for.
    """

    __tablename__ = "org_skill_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_org_skill_versions"),
        CheckConstraint(
            "state IN ('proposed','approved','rejected','superseded','revoked')",
            name="chk_org_skill_versions_state",
        ),
        CheckConstraint(
            "char_length(slug) BETWEEN 1 AND 80",
            name="chk_org_skill_versions_slug_len",
        ),
        CheckConstraint(
            "version_no >= 1",
            name="chk_org_skill_versions_version_no",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    """Stable skill identifier. No-shadowing (D2): a propose 409s when this collides with a
    shipped catalog name — enforced at the API boundary, not here."""

    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    """1-based, per-slug, monotonically increasing. Computed at propose time as
    ``COALESCE(MAX(version_no), 0) + 1`` for the slug; the ``uq_org_skill_versions_slug_version``
    unique index is the race guard."""

    raw_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    """Verbatim canonical YAML frontmatter block, NO trailing newline — reassembled with
    :func:`app.agents.skill_backend.reconstruct_skill_md` for serving."""

    body: Mapped[str] = mapped_column(Text, nullable=False)
    """The markdown body — author bytes, unmodified by the provenance banner (the banner is
    prefixed at SERVE time only; stored bytes never mutate)."""

    frontmatter: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """Parsed-dict copy of ``raw_yaml``, kept alongside so admin listing reads never re-parse
    YAML on the hot path."""

    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    """sha256 hexdigest over the reconstructed ``SKILL.md`` text (author bytes only — the
    approver/date do not exist yet at propose time, so they cannot be part of the hash)."""

    source_user_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "user_skills.id",
            ondelete="SET NULL",
            name="fk_org_skill_versions_source",
        ),
        nullable=True,
    )
    """The author's ``user_skills`` row this version was synthesized from. SET NULL on delete —
    the approved snapshot survives the source row's deletion; it is already an independent,
    immutable copy."""

    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_org_skill_versions_author",
        ),
        nullable=True,
    )

    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'proposed'"))

    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_org_skill_versions_reviewer",
        ),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Reject reason. Never included in audit ``details`` (audit carries ``has_note`` only) —
    length capped at the API layer, not here."""

    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_org_skill_versions_revoker",
        ),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def title(self) -> str | None:
        return (self.frontmatter or {}).get("lq_ai", {}).get("title")

    @property
    def description(self) -> str | None:
        return (self.frontmatter or {}).get("description")

    @property
    def tags(self) -> list[str]:
        return (self.frontmatter or {}).get("lq_ai", {}).get("tags") or []

    def __repr__(self) -> str:
        return (
            f"<OrgSkillVersion slug={self.slug!r} version_no={self.version_no} "
            f"state={self.state!r}>"
        )
