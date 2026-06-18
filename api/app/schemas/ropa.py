"""ROPA domain schema — PRIV-1 (fork, ADR-F018).

The **validation contract** for the Privacy module's typed domain. This module
is the single source of truth for what a valid Records-of-Processing-Activities
entry is — the code invariants the ADR-F018 write path enforces:

1. ``lawful_basis`` is one of the six Article 6(1) GDPR bases (enum).
2. ``retention`` is required and non-empty (a ROPA entry must state how long
   the data is kept — Article 30(1)(f)).
3. ``special_category`` ⇒ ``art9_condition`` present (Article 9 processing
   needs an Article 9(2) condition); conversely a non-special record must not
   carry one (an Article 9 condition on non-special data is incoherent).

``ProcessingActivityInput`` is what PRIV-2's guarded write tool validates a
model proposal against **before** commit: a proposal that fails is rejected back
to the agent with the validation error (agent proposes → code disposes → commit
or reject-and-retry; never a silent write or a silent fix — ADR-F018). The ORM
model (``app.models.ropa.ProcessingActivity``) carries the same invariants as DB
CHECK constraints (defense-in-depth).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LawfulBasis(StrEnum):
    """Article 6(1) GDPR lawful bases for processing."""

    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTERESTS = "legitimate_interests"


class Art9Condition(StrEnum):
    """Article 9(2)(a)-(j) conditions for processing special-category data."""

    EXPLICIT_CONSENT = "explicit_consent"
    EMPLOYMENT_SOCIAL_SECURITY = "employment_social_security"
    VITAL_INTERESTS = "vital_interests"
    NOT_FOR_PROFIT_BODY = "not_for_profit_body"
    MADE_PUBLIC_BY_DATA_SUBJECT = "made_public_by_data_subject"
    LEGAL_CLAIMS = "legal_claims"
    SUBSTANTIAL_PUBLIC_INTEREST = "substantial_public_interest"
    HEALTH_OR_SOCIAL_CARE = "health_or_social_care"
    PUBLIC_HEALTH = "public_health"
    ARCHIVING_RESEARCH_STATISTICS = "archiving_research_statistics"


class ControllerRole(StrEnum):
    """The data-protection role the operator plays for this activity."""

    CONTROLLER = "controller"
    JOINT_CONTROLLER = "joint_controller"
    PROCESSOR = "processor"


class SystemType(StrEnum):
    """Inventory type of an IT system/asset where personal data lives.

    Oscar's DSAR systems-walk list plus OneTrust/TrustArc asset types (PRIV-3,
    ADR-F019). The SQL CHECK in ``app.models.ropa`` mirrors this set.
    """

    DATABASE = "database"
    ANALYTICS = "analytics"
    CRM = "crm"
    SUPPORT = "support"
    EMAIL_MARKETING = "email_marketing"
    LOGS = "logs"
    BACKUP = "backup"
    THIRD_PARTY_PROCESSOR = "third_party_processor"
    OTHER = "other"


class VendorRole(StrEnum):
    """The data-protection relationship a vendor/third party has with the operator.

    The Article 30(1)(e) "categories of recipients" axis (PRIV-5a, ADR-F019). The
    SQL CHECK in ``app.models.ropa`` mirrors this set.
    """

    PROCESSOR = "processor"
    SUB_PROCESSOR = "sub_processor"
    JOINT_CONTROLLER = "joint_controller"
    SEPARATE_CONTROLLER = "separate_controller"
    RECIPIENT = "recipient"


class DpaStatus(StrEnum):
    """Status of the Article 28 data-processing agreement with a vendor."""

    IN_PLACE = "in_place"
    PENDING = "pending"
    NOT_REQUIRED = "not_required"
    NONE = "none"


class TransferMechanism(StrEnum):
    """The Chapter V (Art 44-49) basis that legitimises a restricted transfer.

    The Article 30(1)(e) "transfers + safeguards" axis (PRIV-5b, ADR-F019). The
    SQL CHECK in ``app.models.ropa`` mirrors this set.
    """

    ADEQUACY_REGULATIONS = "adequacy_regulations"
    STANDARD_CONTRACTUAL_CLAUSES = "standard_contractual_clauses"
    UK_IDTA = "uk_idta"
    BINDING_CORPORATE_RULES = "binding_corporate_rules"
    DEROGATION = "derogation"


class ProcessingActivityInput(BaseModel):
    """A proposed ROPA entry — the validated write contract (ADR-F018).

    Reject, don't sanitize (CLAUDE.md): an out-of-enum basis, an empty
    retention, or a special-category entry without an Article 9(2) condition is
    a hard validation error, surfaced verbatim to whoever (PRIV-2: the agent)
    proposed it.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=2000)
    lawful_basis: LawfulBasis
    controller_role: ControllerRole
    # Article 30(1)(f): the envisaged time limits for erasure. Free text (e.g.
    # "7 years after contract end") but REQUIRED — invariant 2.
    retention: str = Field(min_length=1, max_length=1000)
    special_category: bool = False
    art9_condition: Art9Condition | None = None

    @field_validator("retention")
    @classmethod
    def _retention_not_blank(cls, v: str) -> str:
        # str_strip_whitespace already trimmed; an all-whitespace value would
        # have become "" and tripped min_length, but guard explicitly so the
        # invariant reads at the seam it governs.
        if not v.strip():
            raise ValueError("retention is required and must not be blank")
        return v

    @model_validator(mode="after")
    def _special_category_requires_art9(self) -> ProcessingActivityInput:
        """Invariant 3: special-category ⇔ Article 9(2) condition present.

        Both directions: special data needs a condition; non-special data must
        not assert one (an Article 9 condition on ordinary data is incoherent
        and would mislead the ROPA).
        """
        if self.special_category and self.art9_condition is None:
            raise ValueError(
                "special-category processing requires an Article 9(2) condition (art9_condition)"
            )
        if not self.special_category and self.art9_condition is not None:
            raise ValueError("art9_condition must be set only when special_category is true")
        return self


class SystemInput(BaseModel):
    """A proposed System/asset inventory record — the validated write contract.

    The "where personal data lives" half of the two-tier inventory (ADR-F019);
    code-validated before commit exactly like :class:`ProcessingActivityInput`
    (reject, don't sanitize). Only ``name`` and ``system_type`` are required — an
    inventory entry is useful the moment it is named and typed; the descriptive
    fields fill in as the agent (or user) learns more. Blank optional fields are
    normalised to ``None`` so the register stores absence as NULL, not "".
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    system_type: SystemType
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=200)
    hosting_location: str | None = Field(default=None, max_length=200)
    retention: str | None = Field(default=None, max_length=1000)
    security_measures: str | None = Field(default=None, max_length=2000)
    ai_usage: bool = False

    @field_validator("description", "owner", "hosting_location", "retention", "security_measures")
    @classmethod
    def _blank_optional_to_none(cls, v: str | None) -> str | None:
        # str_strip_whitespace already trimmed; a whitespace-only optional should
        # mean "not provided", not an empty string in the register.
        if v is not None and not v.strip():
            return None
        return v


class VendorInput(BaseModel):
    """A proposed vendor/third-party (recipient) record — the validated write contract.

    The "categories of recipients" half of Article 30(1)(e) (PRIV-5a, ADR-F019):
    a third party to whom a processing activity discloses personal data. Only
    ``name``, ``vendor_role`` and ``dpa_status`` are required — the descriptive
    fields fill in as the agent (or user) learns more. Code-validated before
    commit exactly like the other domain inputs (reject, don't sanitize). Blank
    optional fields normalise to ``None`` so the register stores absence as NULL.

    Risk rating is deliberately NOT modelled here — risk is an assessment-track
    concept (PRIV-A1), not an inventory field (plan § Decisions).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    vendor_role: VendorRole
    description: str | None = Field(default=None, max_length=2000)
    country: str | None = Field(default=None, max_length=200)
    dpa_status: DpaStatus

    @field_validator("description", "country")
    @classmethod
    def _blank_optional_to_none(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v


class TransferInput(BaseModel):
    """A proposed third-country transfer — the validated write contract (ADR-F018).

    The "transfers + safeguards" half of Article 30(1)(e) (PRIV-5b, ADR-F019): a
    transfer of an activity's personal data to a third country / international
    organisation. The relational ids (the parent processing activity, the
    optional recipient vendor) are resolved against the register by the agent
    write tool, like the M:N links — this contract carries only the transfer's
    own content + the headline invariant:

    **A restricted transfer (recipient outside the UK/EEA) requires a Chapter V
    transfer mechanism; a non-restricted transfer must not assert one** — exactly
    parallel to ``special_category ⇔ art9_condition``. ``restricted`` is
    *declared* (set by the agent/code), not derived from a maintained adequacy
    list (plan § Decisions). Reject, don't sanitize.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    destination: str = Field(min_length=1, max_length=200)
    restricted: bool = False
    mechanism: TransferMechanism | None = None
    details: str | None = Field(default=None, max_length=2000)

    @field_validator("details")
    @classmethod
    def _blank_optional_to_none(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _restricted_requires_mechanism(self) -> TransferInput:
        """Invariant: restricted ⇔ a transfer mechanism present.

        Both directions: a restricted transfer needs a Chapter V safeguard; a
        non-restricted (intra-UK/EEA) transfer must not carry one (a mechanism on
        an unrestricted transfer is incoherent and would mislead the ROPA).
        """
        if self.restricted and self.mechanism is None:
            raise ValueError(
                "a restricted transfer (recipient outside the UK/EEA) requires a transfer "
                "mechanism (a Chapter V safeguard — e.g. standard_contractual_clauses, uk_idta)"
            )
        if not self.restricted and self.mechanism is not None:
            raise ValueError(
                "mechanism must be set only when the transfer is restricted (outside the UK/EEA)"
            )
        return self


# --- Read DTOs (PRIV-3 read API; from ORM via from_attributes) ----------------
#
# The register read surface. Summaries carry just enough to render a cross-link
# without recursing into the other entity's own links (id + label fields).


class SystemSummary(BaseModel):
    """A system as it appears linked under a processing activity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    system_type: str


class ProcessingActivitySummary(BaseModel):
    """A processing activity as it appears linked under a system or vendor."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    lawful_basis: str
    special_category: bool


class VendorSummary(BaseModel):
    """A vendor/recipient as it appears linked under a processing activity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    vendor_role: str


class TransferSummary(BaseModel):
    """A third-country transfer as it appears under its parent processing activity.

    A transfer is a child of one activity (Art 30 lists transfers within each
    record, PRIV-5b), so it surfaces here rather than as its own register entity.
    ``vendor`` is the recipient when it is a known vendor (intra-group transfers
    may have none).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    destination: str
    restricted: bool
    mechanism: str | None
    details: str | None
    vendor: VendorSummary | None = None


class ProcessingActivityRead(BaseModel):
    """One Article 30 record + the systems, recipients and transfers it carries."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    purpose: str
    lawful_basis: str
    controller_role: str
    retention: str
    special_category: bool
    art9_condition: str | None
    created_at: datetime
    updated_at: datetime
    systems: list[SystemSummary] = Field(default_factory=list)
    vendors: list[VendorSummary] = Field(default_factory=list)
    transfers: list[TransferSummary] = Field(default_factory=list)


class SystemRead(BaseModel):
    """One system/asset + the processing activities that use it (detail view)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    system_type: str
    description: str | None
    owner: str | None
    hosting_location: str | None
    retention: str | None
    security_measures: str | None
    ai_usage: bool
    created_at: datetime
    updated_at: datetime
    processing_activities: list[ProcessingActivitySummary] = Field(default_factory=list)


class VendorRead(BaseModel):
    """One vendor/recipient + the processing activities that disclose to it (detail view)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    vendor_role: str
    description: str | None
    country: str | None
    dpa_status: str
    created_at: datetime
    updated_at: datetime
    processing_activities: list[ProcessingActivitySummary] = Field(default_factory=list)


# --- Article 30 export (PRIV-4a) ---------------------------------------------
#
# The extractable RoPA deliverable over the deployment-global register. A
# read-and-render envelope (no new entity): the processing activities joined to
# their systems, recipients and transfers, plus the system and vendor
# inventories, plus an HONEST coverage note naming the Article 30(1) fields the
# domain does not yet capture (the data-subject / personal-data taxonomy —
# PRIV-6). The export renders what exists and never invents the rest.


class Article30Coverage(BaseModel):
    """Honest scope of the export — what Article 30(1) content is/ isn't captured yet."""

    fields_not_yet_recorded: list[str] = Field(default_factory=list)


class Article30Export(BaseModel):
    """The Article 30 RoPA export payload (JSON form; the CSV/XLSX render the same data)."""

    generated_at: datetime
    # NB: not ``register`` — that shadows a pydantic BaseModel attribute (UserWarning).
    register_name: str = "Article 30 Records of Processing Activities"
    coverage: Article30Coverage
    processing_activities: list[ProcessingActivityRead] = Field(default_factory=list)
    systems: list[SystemRead] = Field(default_factory=list)
    vendors: list[VendorRead] = Field(default_factory=list)
