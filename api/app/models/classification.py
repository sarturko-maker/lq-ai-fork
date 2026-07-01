"""Risk-classification ORM model — AIC-2 (fork, ADR-F057).

The sealed, re-derivable output of the deterministic verdict engine
(:func:`app.aiact.classify.classify`): one row per computed classification of an
:class:`~app.models.compliance.AiSystem`. The engine — not the model — is the sole
author of ``tier``; there is no free-write tier anywhere in the module (the presence
gate, ADR-F057).

**One current verdict per system, recompute-on-fact-change.** A classification is
never mutated in place: when the facts (or the rule set) change and the
``verdict_hash`` differs, the prior row is marked ``superseded_at`` and a fresh row
inserted. A partial unique index enforces at most one *current* (``superseded_at IS
NULL``) verdict per ``ai_system_id`` — the history is the audit trail.

**Sealed provenance.** ``verdict_hash`` is an unsigned SHA-256 digest over the
normalised facts + ``ruleset_version`` + tier + route + sorted article refs; a
fact/rule change visibly invalidates a prior verdict. ``draft_basis`` marks a verdict
that leans on an unsettled predicate (an Art 6(3) derogation).

**Born flip-ready + deployment-global (ADR-F019/F021)**, exactly like the register:
durable NON-NULL ``practice_area_id`` (FK RESTRICT — the future ``visible_filter()``
scoping key), nullable ``source_project_id`` provenance (SET NULL).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The verdict vocabularies — SQL CHECK mirrors of the Pydantic enums in
# ``app.schemas.classification`` (authoritative there; duplicated here as the DB
# guard, exactly as ``app.models.compliance`` mirrors the register enums).
_RISK_TIERS = ("prohibited", "high", "limited", "minimal")
_CLASSIFICATION_ROUTES = (
    "art5_prohibited",
    "annex_i_safety_component",
    "annex_iii",
    "art50_transparency",
    "minimal",
)


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class RiskClassification(Base):
    """One sealed EU AI Act risk verdict for an AI system (AIC-2)."""

    __tablename__ = "risk_classifications"
    __table_args__ = (
        CheckConstraint(_in_set("tier", _RISK_TIERS), name="chk_risk_classifications_tier"),
        CheckConstraint(
            _in_set("route", _CLASSIFICATION_ROUTES), name="chk_risk_classifications_route"
        ),
        Index("ix_risk_classifications_ai_system_id", "ai_system_id"),
        Index("ix_risk_classifications_practice_area_id", "practice_area_id"),
        # At most one CURRENT verdict per system — the recompute-on-fact-change
        # invariant. Superseded rows (superseded_at NOT NULL) are the history.
        Index(
            "uq_risk_classifications_current",
            "ai_system_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "ai_systems.id",
            ondelete="RESTRICT",
            name="fk_risk_classifications_ai_system_id",
        ),
        nullable=False,
    )
    # Durable NON-NULL scoping key (ADR-F057/F021 — born flip-ready), like the register.
    practice_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "practice_areas.id",
            ondelete="RESTRICT",
            name="fk_risk_classifications_practice_area_id",
        ),
        nullable=False,
    )
    # Provenance only (ADR-F019): which matter/run computed this verdict.
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_risk_classifications_source_project_id",
        ),
        nullable=True,
    )
    # The model's private input to the engine — the snapshot the verdict is a function
    # of. Never part of the read surface (VerdictRead omits it).
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    facts_hash: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str] = mapped_column(Text, nullable=False)
    article_refs: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    predicate_trace: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_hash: Mapped[str] = mapped_column(Text, nullable=False)
    draft_basis: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # NULL = the current verdict; set when a newer verdict supersedes this one.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RiskClassification id={self.id} ai_system_id={self.ai_system_id} "
            f"tier={self.tier!r} current={self.superseded_at is None}>"
        )
