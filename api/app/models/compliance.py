"""AI Compliance ORM models — AIC-1 (fork, ADR-F057/F018/F019).

The AI Compliance module's **typed, relational domain**. One first-class entity in
AIC-1: :class:`AiSystem`, one row per AI system in the company-wide EU AI Act
(Regulation (EU) 2024/1689) register — the AI-native twin of ROPA's
:class:`~app.models.ropa.ProcessingActivity`.

**Deployment-global scope (ADR-F019).** LQ.AI is single-tenant — the register is
the **company-wide** standing record, not a per-matter artifact. ``source_project_id``
is a **nullable** ``ON DELETE SET NULL`` FK carrying only provenance (which
matter/run first recorded the row), never ownership/scoping — exactly as
:class:`~app.models.ropa.ProcessingActivity`.

**Born flip-ready (ADR-F057/F021).** Unlike the ROPA exemplar (which predates
ADR-F021), every row also carries a **durable NON-NULL** ``practice_area_id`` — the
scoping key a future ``visible_filter()`` will AND into reads when register
enforcement flips from shared-read to area-membership. FK ``RESTRICT`` (not SET
NULL) so the scoping key can never become NULL and silently un-scope the row. This
is a deliberate, ADR-backed divergence from the ROPA columns, not a copy.

**Facts only — the presence gate (ADR-F057).** There is deliberately NO risk-tier
or legal-role column: under the EU AI Act a risk classification is a *legal
determination* owned by the deterministic engine (AIC-2), never a free-write field.
The register stores the FACTS that feed the engine (intended purpose, lifecycle,
build-vs-buy origin, GPAI flags); the verdict lands in a separate entity later.

**ADR-F018 — code-validated domain writes.** The integrity invariants live in the
Pydantic domain schema (``app.schemas.compliance``), validated by the agent write
path BEFORE commit; the CHECK constraints below DUPLICATE those invariants at the
DB boundary as defense-in-depth. The enum-ish columns are ``Text`` + a CHECK
against the allowed set (not a PG ``ENUM`` type), so the vocabulary evolves via an
ALTER CHECK rather than an ALTER TYPE dance.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# EU AI Act fact vocabularies — the SQL CHECK mirrors of the Pydantic enums in
# ``app.schemas.compliance`` (single source of the values). These are FACTS the
# classification engine consumes (AIC-2), never a verdict the model asserts.
_LIFECYCLE_STATUSES = ("in_development", "in_service", "decommissioned")
_DEVELOPMENT_ORIGINS = ("in_house", "third_party", "hybrid")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_len(column: str, max_len: int) -> str:
    """CHECK fragment for an optional Text column: NULL, or within length."""
    return f"{column} IS NULL OR char_length({column}) <= {max_len}"


class AiSystem(Base):
    """One AI system in the company-wide EU AI Act register (AIC-1).

    Deployment-global (ADR-F019): not owned by a matter. Born flip-ready
    (ADR-F057/F021): carries a durable NON-NULL ``practice_area_id``. Facts only
    (ADR-F057): no risk-tier/role column — the tier is the engine's determination.

    The DB invariants (mirroring ``app.schemas.compliance.AiSystemInput``):

    * ``lifecycle_status`` is one of in_development / in_service / decommissioned.
    * ``development_origin`` is one of in_house / third_party / hybrid.
    * ``gpai_systemic`` ⇒ ``is_gpai`` (a systemic-risk model is a GPAI model).
    * ``name`` non-empty ≤ 200; ``intended_purpose`` non-empty ≤ 2000; the
      optional ``notes`` / ``retirement_reason`` are length-bounded when present.
    """

    __tablename__ = "ai_systems"
    __table_args__ = (
        CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_ai_systems_name_len",
        ),
        CheckConstraint(
            "char_length(intended_purpose) > 0 AND char_length(intended_purpose) <= 2000",
            name="chk_ai_systems_intended_purpose_len",
        ),
        CheckConstraint(
            _in_set("lifecycle_status", _LIFECYCLE_STATUSES),
            name="chk_ai_systems_lifecycle_status",
        ),
        CheckConstraint(
            _in_set("development_origin", _DEVELOPMENT_ORIGINS),
            name="chk_ai_systems_development_origin",
        ),
        # A systemic-risk general-purpose model IS a general-purpose model — the
        # coherence invariant (mirrors ROPA's special_category ⇔ art9_condition).
        CheckConstraint(
            "NOT gpai_systemic OR is_gpai",
            name="chk_ai_systems_gpai_coherence",
        ),
        CheckConstraint(
            _opt_len("notes", 2000),
            name="chk_ai_systems_notes_len",
        ),
        CheckConstraint(
            _opt_len("retirement_reason", 1000),
            name="chk_ai_systems_retirement_reason_len",
        ),
        Index("ix_ai_systems_practice_area_id", "practice_area_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Durable authz scoping key (ADR-F057/F021 — born flip-ready). NON-NULL, FK
    # RESTRICT: a NULL scoping key would silently un-scope the row when register
    # read-enforcement later flips from shared-read to area-membership. Diverges
    # deliberately from the ROPA exemplar (which predates F021 and has none).
    practice_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "practice_areas.id",
            ondelete="RESTRICT",
            name="fk_ai_systems_practice_area_id",
        ),
        nullable=False,
    )
    # Provenance only (ADR-F019): which matter/run first recorded this system.
    # Nullable, ON DELETE SET NULL — the register row outlives any matter and is
    # never scoped/owned by it.
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_ai_systems_source_project_id",
        ),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    intended_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(Text, nullable=False)
    development_origin: Mapped[str] = mapped_column(Text, nullable=False)
    is_gpai: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    gpai_systemic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Soft-retire (mirrors PRIV-8a, ADR-F023): NULL = live. Set on retire so the
    # change is auditable; the row is never destroyed. Reads exclude retired rows
    # by default; the agent's list tool hides them.
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retirement_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AiSystem id={self.id} name={self.name!r} is_gpai={self.is_gpai}>"
