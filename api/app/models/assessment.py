"""Assessment ORM models — PRIV-A1 (fork, ADR-F018, ADR-F019, ADR-F027).

The Privacy module's **assessment track** — PIA / DPIA / LIA / TIA records and
the risk findings within them, the assessment-track sibling of the ROPA
inventory (``app.models.ropa``). Two first-class entities:

* :class:`Assessment` — one privacy assessment (a PIA/DPIA/LIA/TIA: type, title,
  status, overall risk rating, conditions). Links many-to-many to the
  :class:`~app.models.ropa.ProcessingActivity` records it covers, through
  :data:`assessment_processing_activities`.
* :class:`Risk` — a risk finding within exactly one assessment (CASCADE child —
  a risk has no meaning without its parent, the Transfer→Activity precedent).

**Deployment-global scope (ADR-F019).** Like the ROPA register, assessments are
the company-wide accountability record, NOT matter- or user-scoped: a nullable
``source_project_id`` (``ON DELETE SET NULL``) carries provenance (which
matter/run first recorded the assessment), never ownership/scoping.

**ADR-F018 — code-validated domain writes.** The integrity invariants live in
``app.schemas.assessment``, which the PRIV-A2 write path validates BEFORE commit.
The CHECK constraints below DUPLICATE the *within-row* invariants at the DB
boundary as defense-in-depth — including the within-row half of the headline
rule (*a ``completed`` assessment must carry a ``risk_rating``*). The headline
rule's cross-row half (*a completed DPIA/high-risk assessment needs ≥1 risk with
a mitigation*) is a relation across rows, enforced in the app layer
(``validate_assessment_completable``) rather than a DB trigger — the same way
ROPA keeps its cross-row rules in code.

As in ``app.models.ropa``, the enum-ish columns are stored as ``Text`` + a CHECK
against the allowed set (authoritative list = the Pydantic StrEnums in
``app.schemas.assessment``) — cheap to evolve, still refuses an off-list value.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Allowed sets — the SQL CHECK mirrors of the Pydantic StrEnums in
# ``app.schemas.assessment`` (single source of the values; kept here as literal
# SQL fragments so the migration and the model agree).
_ASSESSMENT_TYPES = ("pia", "dpia", "lia", "tia")
_ASSESSMENT_STATUSES = ("draft", "in_progress", "completed")
_RISK_LEVELS = ("low", "medium", "high")
_RISK_STATUSES = ("open", "mitigated", "accepted")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_len(column: str, max_len: int) -> str:
    """CHECK fragment for an optional Text column: NULL, or within length."""
    return f"{column} IS NULL OR char_length({column}) <= {max_len}"


# Many-to-many link between assessments and the processing activities they cover
# (an assessment assesses ≥1 activity; an activity may be covered by several
# assessments). Same shape as the ROPA link tables: composite PK, CASCADE both
# ends (deleting either end drops the link rows, not the surviving record).
assessment_processing_activities = Table(
    "assessment_processing_activities",
    Base.metadata,
    Column(
        "assessment_id",
        UUID(as_uuid=True),
        ForeignKey(
            "assessments.id",
            ondelete="CASCADE",
            name="fk_apa_assessment_id",
        ),
        primary_key=True,
    ),
    Column(
        "processing_activity_id",
        UUID(as_uuid=True),
        ForeignKey(
            "processing_activities.id",
            ondelete="CASCADE",
            name="fk_apa_processing_activity_id",
        ),
        primary_key=True,
    ),
)


class Assessment(Base):
    """One privacy assessment (PIA/DPIA/LIA/TIA) in the company-wide record.

    Deployment-global (ADR-F019): not owned by a matter. DB invariants mirror
    ``app.schemas.assessment.AssessmentInput``:

    * ``type`` is one of pia/dpia/lia/tia; ``status`` one of
      draft/in_progress/completed; ``risk_rating`` (when set) low/medium/high.
    * ``title`` is non-empty (≤200); the optional text fields stay within bounds.
    * **completed ⇒ risk_rating present** — the within-row half of the headline
      invariant (you can't close an unrated assessment). The cross-row half
      (completed high-risk/DPIA ⇒ a documented mitigation) is enforced in the app
      layer (``validate_assessment_completable``).
    """

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(
            "char_length(title) > 0 AND char_length(title) <= 200",
            name="chk_assessments_title_len",
        ),
        CheckConstraint(_in_set("type", _ASSESSMENT_TYPES), name="chk_assessments_type"),
        CheckConstraint(_in_set("status", _ASSESSMENT_STATUSES), name="chk_assessments_status"),
        CheckConstraint(
            f"risk_rating IS NULL OR {_in_set('risk_rating', _RISK_LEVELS)}",
            name="chk_assessments_risk_rating",
        ),
        # Within-row half of the headline ADR-F018 invariant, at the DB boundary:
        # a completed assessment must carry a risk rating.
        CheckConstraint(
            "status <> 'completed' OR risk_rating IS NOT NULL",
            name="chk_assessments_completed_requires_rating",
        ),
        CheckConstraint(_opt_len("summary", 5000), name="chk_assessments_summary_len"),
        CheckConstraint(_opt_len("conditions", 5000), name="chk_assessments_conditions_len"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Provenance only (ADR-F019): which matter/run first recorded this assessment.
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_assessments_source_project_id",
        ),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    risk_rating: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # PRIV-A1 fixes the ROPA carried debt: ``onupdate`` so a real "last modified"
    # is maintained (assessment status/rating rows genuinely mutate, unlike the
    # mostly-append ROPA inventory).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Risk findings are CHILDREN of this assessment (CASCADE — a risk has no
    # meaning without its parent; DB FK CASCADE + ORM delete-orphan).
    risks: Mapped[list[Risk]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="Risk.created_at",
    )
    processing_activities: Mapped[list[ProcessingActivity]] = relationship(
        secondary=assessment_processing_activities,
        order_by="ProcessingActivity.name",
    )

    def __repr__(self) -> str:
        return (
            f"<Assessment id={self.id} type={self.type!r} "
            f"status={self.status!r} risk_rating={self.risk_rating!r}>"
        )


class Risk(Base):
    """One risk finding within an assessment — PRIV-A1.

    A child of exactly one :class:`Assessment` (required FK, CASCADE). Invariants
    mirror ``app.schemas.assessment.RiskInput``:

    * ``description`` is non-empty (≤2000).
    * ``likelihood`` / ``impact`` are one of low/medium/high; ``status`` one of
      open/mitigated/accepted.
    * the optional ``mitigation`` / ``owner`` stay within length bounds.
    """

    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint(
            "char_length(description) > 0 AND char_length(description) <= 2000",
            name="chk_risks_description_len",
        ),
        CheckConstraint(_in_set("likelihood", _RISK_LEVELS), name="chk_risks_likelihood"),
        CheckConstraint(_in_set("impact", _RISK_LEVELS), name="chk_risks_impact"),
        CheckConstraint(_in_set("status", _RISK_STATUSES), name="chk_risks_status"),
        CheckConstraint(_opt_len("mitigation", 2000), name="chk_risks_mitigation_len"),
        CheckConstraint(_opt_len("owner", 200), name="chk_risks_owner_len"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE", name="fk_risks_assessment_id"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    likelihood: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    assessment: Mapped[Assessment] = relationship(back_populates="risks")

    def __repr__(self) -> str:
        return f"<Risk id={self.id} assessment_id={self.assessment_id} status={self.status!r}>"


# Imported for the relationship type only; placed at the foot to avoid a circular
# import at module load (ropa imports nothing from here).
from app.models.ropa import ProcessingActivity  # noqa: E402
