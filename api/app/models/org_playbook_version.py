"""OrgPlaybookVersion ORM model — org-authored playbook propose/approve harness (ADR-F067 D2/D3, B-4).

Backs the ``org_playbook_versions`` table per migration 0095. See that migration's docstring for
the full design rationale, including why ``playbook_id`` is a PLAIN column (full-parity resolution
independent of the live ``playbooks`` row) and ``source_playbook_id`` is the separate provenance FK.
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


class OrgPlaybookVersion(Base):
    """One org-authored playbook version — either an open proposal or an immutable approved
    snapshot (ADR-F067 D2/D3, B-4).

    Content columns (``playbook_id``, ``version_no``, ``name``, ``contract_type``,
    ``description``, ``playbook_version``, ``positions``, ``content_hash``, ``source_playbook_id``,
    ``author_user_id``) are written once at INSERT and never updated — "approval pins bytes, not a
    row" (D2). Only the state/review/revoke columns transition: ``proposed -> approved | rejected``;
    ``approved -> revoked | superseded`` (``superseded`` is set only by a newer approval of the same
    playbook, never via an endpoint).

    The runtime reads ONLY ``state == 'approved'`` rows (never the live, mutable ``playbooks`` row
    or its ``playbook_positions``) at the composition chokepoint (``build_area_inventory`` + the
    render seam) — this is the TOCTOU-closing invariant the whole harness exists for. Because the
    org playbook is resolved by ``playbook_id`` from this snapshot INDEPENDENT of the live row
    (full skills parity), an author soft-deleting their source playbook cannot remove an approved
    capability; only an admin revoke can.
    """

    __tablename__ = "org_playbook_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_org_playbook_versions"),
        CheckConstraint(
            "state IN ('proposed','approved','rejected','superseded','revoked')",
            name="chk_org_playbook_versions_state",
        ),
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200",
            name="chk_org_playbook_versions_name_len",
        ),
        CheckConstraint(
            "version_no >= 1",
            name="chk_org_playbook_versions_version_no",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        server_default=text("gen_random_uuid()"),
    )
    playbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    """Stable adoption key (PLAIN column, not an FK). The Library adopts ``str(playbook_id)``; the
    runtime resolves the approved snapshot by this key independent of the live ``playbooks`` row —
    so the capability survives the author soft-deleting their source playbook (D2 parity with
    ``org_skill_versions.slug``)."""

    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    """1-based, per-playbook, monotonically increasing. Computed at propose time as
    ``COALESCE(MAX(version_no), 0) + 1`` for the playbook; the
    ``uq_org_playbook_versions_playbook_version`` unique index is the race guard."""

    name: Mapped[str] = mapped_column(Text, nullable=False)
    contract_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    playbook_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="1.0.0")
    """The playbook's own semver display string (``Playbook.version``) — named ``playbook_version``
    to avoid colliding with ``version_no`` (the harness proposal counter)."""

    positions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    """The CANONICAL frozen positions array (full fidelity). Serialized deterministically by
    :func:`app.agents.playbook_proposal.canonicalize_positions`; ``content_hash`` covers this plus
    the header. Immutable — a post-approval edit to the live playbook does not touch this row."""

    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    """sha256 hexdigest over the canonical positions+header JSON (author bytes only — the
    approver/date do not exist at propose time, so they cannot be part of the hash)."""

    source_playbook_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "playbooks.id",
            ondelete="SET NULL",
            name="fk_org_playbook_versions_source",
        ),
        nullable=True,
    )
    """The live ``playbooks`` row this version was frozen from — provenance ONLY. SET NULL on
    delete; the approved snapshot (resolved by ``playbook_id``) survives independently."""

    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_org_playbook_versions_author",
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
            name="fk_org_playbook_versions_reviewer",
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
            name="fk_org_playbook_versions_revoker",
        ),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def position_count(self) -> int:
        return len(self.positions or [])

    def __repr__(self) -> str:
        return (
            f"<OrgPlaybookVersion playbook_id={self.playbook_id} "
            f"version_no={self.version_no} state={self.state!r}>"
        )
