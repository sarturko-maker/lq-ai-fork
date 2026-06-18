"""ROPA (Records of Processing Activities) ORM model — PRIV-1 (fork, ADR-F018).

The first **typed domain** of the LQ.AI Oscar Edition Privacy module. A
``processing_activity`` is one Article 30 GDPR record — a single processing
operation the controller/processor performs — hung off a Privacy **matter**
(``projects.practice_area_id`` → the Privacy area, ADR-F002). PRIV-1 is the
domain SPINE only: the table + the validation contract (``app.schemas.ropa``).
No agent writes to it yet — the validated, guarded write path is PRIV-2.

**ADR-F018 — code-validated domain writes.** The integrity invariants live in
the Pydantic domain schema (``app.schemas.ropa.ProcessingActivityInput``), which
the PRIV-2 write path validates BEFORE commit (agent proposes → code disposes;
a rejected proposal goes back to the model with the reason, never a silent
write/fix). The CHECK constraints below DUPLICATE those invariants at the DB
boundary as defense-in-depth — the ``projects.privileged ⇒ tier`` precedent — so
the table cannot hold an inconsistent row even if a future caller bypasses the
schema.

The free-text enum-ish columns (``lawful_basis``, ``controller_role``,
``art9_condition``) are stored as ``Text`` + a CHECK against the allowed set
rather than a PG ``ENUM`` type: the allowed values are GDPR-canonical and the
authoritative list is the Pydantic enum (``app.schemas.ropa``); a CHECK keeps
the migration cheap to evolve (ALTER a CHECK, no ``ALTER TYPE`` dance) while
still refusing an off-list value.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# GDPR-canonical allowed sets — the SQL CHECK mirrors of the Pydantic enums in
# ``app.schemas.ropa`` (single source of the values; kept here as literal SQL
# fragments so the migration and the model agree). Article 6(1) lawful bases,
# Article 9(2) special-category conditions, and the controller/processor roles.
_LAWFUL_BASES = (
    "consent",
    "contract",
    "legal_obligation",
    "vital_interests",
    "public_task",
    "legitimate_interests",
)
_ART9_CONDITIONS = (
    "explicit_consent",
    "employment_social_security",
    "vital_interests",
    "not_for_profit_body",
    "made_public_by_data_subject",
    "legal_claims",
    "substantial_public_interest",
    "health_or_social_care",
    "public_health",
    "archiving_research_statistics",
)
_CONTROLLER_ROLES = ("controller", "joint_controller", "processor")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class ProcessingActivity(Base):
    """One ROPA entry (Article 30 record) scoped to a Privacy matter.

    Child of a ``project`` (the matter / unit of work) — ``ON DELETE CASCADE``,
    so closing a matter removes its records. The DB invariants (mirroring
    ``app.schemas.ropa.ProcessingActivityInput``):

    * ``lawful_basis`` is one of the Article 6(1) bases.
    * ``controller_role`` is controller / joint_controller / processor.
    * ``retention`` is non-empty (a ROPA entry must state a retention period).
    * ``special_category`` ⇒ ``art9_condition`` present (Article 9 processing
      needs an Article 9(2) condition) — and when present it is one of the
      Article 9(2) conditions.
    """

    __tablename__ = "processing_activities"
    __table_args__ = (
        CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_processing_activities_name_len",
        ),
        CheckConstraint(
            "char_length(purpose) > 0 AND char_length(purpose) <= 2000",
            name="chk_processing_activities_purpose_len",
        ),
        CheckConstraint(
            "char_length(retention) > 0 AND char_length(retention) <= 1000",
            name="chk_processing_activities_retention_required",
        ),
        CheckConstraint(
            _in_set("lawful_basis", _LAWFUL_BASES),
            name="chk_processing_activities_lawful_basis",
        ),
        CheckConstraint(
            _in_set("controller_role", _CONTROLLER_ROLES),
            name="chk_processing_activities_controller_role",
        ),
        # The headline ADR-F018 invariant, at the DB boundary: special-category
        # processing requires an Article 9(2) condition; a non-special record
        # must not carry one (keeps the record honest, not just non-null).
        CheckConstraint(
            "(special_category AND art9_condition IS NOT NULL) "
            "OR (NOT special_category AND art9_condition IS NULL)",
            name="chk_processing_activities_art9_requires_special",
        ),
        CheckConstraint(
            f"art9_condition IS NULL OR {_in_set('art9_condition', _ART9_CONDITIONS)}",
            name="chk_processing_activities_art9_condition",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # The Privacy matter this record belongs to (ADR-F002 unit of work). CASCADE:
    # a ROPA entry has no life outside its matter.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="CASCADE",
            name="fk_processing_activities_project_id",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    lawful_basis: Mapped[str] = mapped_column(Text, nullable=False)
    controller_role: Mapped[str] = mapped_column(Text, nullable=False)
    retention: Mapped[str] = mapped_column(Text, nullable=False)
    special_category: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    art9_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessingActivity id={self.id} project_id={self.project_id} "
            f"name={self.name!r} special_category={self.special_category}>"
        )
