"""ROPA (Records of Processing Activities) ORM models — PRIV-1/PRIV-3 (fork).

The Privacy module's **typed, relational domain** (ADR-F018, ADR-F019). Two
first-class entities form a two-tier inventory graph — the OneTrust/TrustArc
"Business Process composes Systems" shape:

* :class:`ProcessingActivity` — one Article 30 GDPR record (a single processing
  operation: purpose, lawful basis, retention, special-category…). PRIV-1.
* :class:`System` — an IT system/asset where personal data lives (database, CRM,
  analytics, backups, a third-party processor…). PRIV-3.

linked many-to-many through :data:`processing_activity_systems` (a processing
activity uses several systems; a system serves several activities).

**Deployment-global scope (ADR-F019).** LQ.AI is single-tenant — an in-house
team's one client is its own organization, so the deployment IS the org. The
register is therefore the **company-wide** standing record, NOT matter- or
user-scoped. Both tables carry only a **nullable** ``source_project_id``
(``ON DELETE SET NULL``) — provenance (which matter/run first recorded the row),
never ownership/scoping. This SUPERSEDES PRIV-1's matter-scoping
(``processing_activities.project_id`` is dropped in migration 0059).

**ADR-F018 — code-validated domain writes.** The integrity invariants live in
the Pydantic domain schemas (``app.schemas.ropa``), which the agent write path
validates BEFORE commit (agent proposes → code disposes; a rejected proposal
goes back to the model with the reason, never a silent write/fix). The CHECK
constraints below DUPLICATE those invariants at the DB boundary as
defense-in-depth — the table cannot hold an inconsistent row even if a future
caller bypasses the schema.

The free-text enum-ish columns (``lawful_basis``, ``controller_role``,
``art9_condition``, ``system_type``) are stored as ``Text`` + a CHECK against the
allowed set rather than a PG ``ENUM`` type: the allowed values are GDPR/inventory
canonical and the authoritative list is the Pydantic enum (``app.schemas.ropa``);
a CHECK keeps the migration cheap to evolve (ALTER a CHECK, no ``ALTER TYPE``
dance) while still refusing an off-list value.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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

# System/asset types — Oscar's DSAR systems-walk list plus OneTrust/TrustArc
# asset types (PRIV-3 / ADR-F019). Authoritative list: app.schemas.ropa.SystemType.
_SYSTEM_TYPES = (
    "database",
    "analytics",
    "crm",
    "support",
    "email_marketing",
    "logs",
    "backup",
    "third_party_processor",
    "other",
)


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _opt_len(column: str, max_len: int) -> str:
    """CHECK fragment for an optional Text column: NULL, or within length."""
    return f"{column} IS NULL OR char_length({column}) <= {max_len}"


# Many-to-many link between processing activities and the systems they use
# (ADR-F019). Both sides CASCADE: deleting either end drops the link rows, not
# the surviving record. Composite PK = the pair (no duplicate links).
processing_activity_systems = Table(
    "processing_activity_systems",
    Base.metadata,
    Column(
        "processing_activity_id",
        UUID(as_uuid=True),
        ForeignKey(
            "processing_activities.id",
            ondelete="CASCADE",
            name="fk_pa_systems_processing_activity_id",
        ),
        primary_key=True,
    ),
    Column(
        "system_id",
        UUID(as_uuid=True),
        ForeignKey("systems.id", ondelete="CASCADE", name="fk_pa_systems_system_id"),
        primary_key=True,
    ),
)


class ProcessingActivity(Base):
    """One ROPA entry (Article 30 record) in the company-wide register.

    Deployment-global (ADR-F019): not owned by a matter. The DB invariants
    (mirroring ``app.schemas.ropa.ProcessingActivityInput``):

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
    # Provenance only (ADR-F019): which matter/run first recorded this entry.
    # Nullable, ON DELETE SET NULL — the register row outlives any matter and is
    # never scoped/owned by it.
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_processing_activities_source_project_id",
        ),
        nullable=True,
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

    systems: Mapped[list[System]] = relationship(
        secondary=processing_activity_systems,
        back_populates="processing_activities",
        order_by="System.name",
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessingActivity id={self.id} "
            f"name={self.name!r} special_category={self.special_category}>"
        )


class System(Base):
    """One IT system / asset where personal data lives — company-wide (ADR-F019).

    The "where" half of the two-tier inventory graph (the processing activity is
    the "what/why"). Invariants mirror ``app.schemas.ropa.SystemInput``:

    * ``name`` is non-empty (≤200).
    * ``system_type`` is one of the canonical inventory types.
    * the optional descriptive fields stay within length bounds.
    """

    __tablename__ = "systems"
    __table_args__ = (
        CheckConstraint(
            "char_length(name) > 0 AND char_length(name) <= 200",
            name="chk_systems_name_len",
        ),
        CheckConstraint(
            _in_set("system_type", _SYSTEM_TYPES),
            name="chk_systems_system_type",
        ),
        CheckConstraint(_opt_len("description", 2000), name="chk_systems_description_len"),
        CheckConstraint(_opt_len("owner", 200), name="chk_systems_owner_len"),
        CheckConstraint(_opt_len("hosting_location", 200), name="chk_systems_hosting_location_len"),
        CheckConstraint(_opt_len("retention", 1000), name="chk_systems_retention_len"),
        CheckConstraint(
            _opt_len("security_measures", 2000), name="chk_systems_security_measures_len"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL", name="fk_systems_source_project_id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    system_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    hosting_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention: Mapped[str | None] = mapped_column(Text, nullable=True)
    security_measures: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_usage: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    processing_activities: Mapped[list[ProcessingActivity]] = relationship(
        secondary=processing_activity_systems,
        back_populates="systems",
        order_by="ProcessingActivity.name",
    )

    def __repr__(self) -> str:
        return f"<System id={self.id} name={self.name!r} type={self.system_type!r}>"
