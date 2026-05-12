"""Pydantic schemas for the projects surface (Task C7).

Wire shapes for ``/api/v1/projects`` matching ``Project``,
``ProjectCreate``, and ``ProjectUpdate`` in
``docs/api/backend-openapi.yaml``. The ORM models live in
``app.models.project``; this module is the request/response surface.

The ``privileged`` ↔ ``minimum_inference_tier`` constraint is enforced
at *both* layers: a Pydantic ``model_validator`` rejects requests where
``privileged=true`` is set without a tier, and a DB ``CHECK`` constraint
catches anything that bypasses the API. Defense-in-depth.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

# Per the task brief: "max length; if not, document a sensible cap
# (suggested 100KB) and 400-on-exceed." We pin 100 KiB.
CONTEXT_MD_MAX_BYTES: int = 100 * 1024
"""Maximum byte length of ``context_md``. Enforced by the create/update
schemas; exceeding it returns a 422 (pydantic-driven). The DB column
itself is unrestricted ``TEXT`` so an admin migration can change the
cap without an ALTER."""

NAME_MAX_LEN: int = 200
"""Hard cap on project ``name``. Matches the DB CHECK constraint."""

SLUG_MAX_LEN: int = 80
"""Hard cap on project ``slug``. Matches the DB CHECK constraint."""

DESCRIPTION_MAX_LEN: int = 1000
"""Soft cap on the optional ``description`` field. Defensive — the DB
column is unrestricted ``TEXT``."""

# Slugs are lowercase ascii letters/digits separated by single dashes.
# We *generate* slugs on create when the caller doesn't supply one;
# this regex is also applied to caller-supplied slugs on PATCH. The
# leading/trailing-dash exclusion is captured by the regex shape.
SLUG_RE: re.Pattern[str] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# Type aliases for reusable annotated string fields.
# ---------------------------------------------------------------------------

ProjectName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=NAME_MAX_LEN, strip_whitespace=True),
]
"""1-200 chars, leading/trailing whitespace stripped."""

ProjectSlug = Annotated[
    str,
    StringConstraints(min_length=1, max_length=SLUG_MAX_LEN, strip_whitespace=True),
    Field(pattern=SLUG_RE.pattern),
]
"""1-80 chars, lowercase ascii letters/digits separated by dashes."""

ProjectDescription = Annotated[
    str,
    StringConstraints(max_length=DESCRIPTION_MAX_LEN),
]
"""Free-form description; capped at 1000 chars (defensive)."""

InferenceTier = Literal[1, 2, 3, 4, 5]
"""Per PRD §1.5.2 the tier spectrum is 1-5 inclusive."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify(value: str) -> str:
    """Render ``value`` as a slug per :data:`SLUG_RE`.

    Strategy: lowercase, replace any run of non-``[a-z0-9]`` chars with
    a single dash, strip leading/trailing dashes, truncate to
    :data:`SLUG_MAX_LEN`. Returns ``"project"`` for inputs that
    collapse to the empty string (a value that satisfies the regex
    minimally).
    """

    # Lowercase first; any uppercase is folded.
    lowered = value.lower()
    # Map any run of non-alphanumeric to a single dash.
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not cleaned:
        return "project"
    return cleaned[:SLUG_MAX_LEN].rstrip("-") or "project"


def _validate_context_md_bytes(value: str | None) -> str | None:
    """Reject ``context_md`` longer than :data:`CONTEXT_MD_MAX_BYTES` bytes.

    Counts UTF-8 bytes (not codepoints) so the cap is meaningful for
    non-ASCII content. Returns the value unchanged if accepted.
    """

    if value is None:
        return None
    nbytes = len(value.encode("utf-8"))
    if nbytes > CONTEXT_MD_MAX_BYTES:
        # Pydantic's ValueError → 422 wrapping at the FastAPI boundary.
        # This is the right shape (syntactic-validation failure on the
        # request body), distinct from our domain ValidationError used
        # for cross-field business rules.
        raise ValueError(
            f"context_md exceeds {CONTEXT_MD_MAX_BYTES} bytes ({nbytes} bytes received)"
        )
    return value


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    """``ProjectCreate`` from backend-openapi.yaml.

    ``slug`` is optional — when omitted, the handler derives one from
    ``name`` and resolves collisions per-owner with a numeric suffix
    (``-2``, ``-3``, …).
    """

    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    slug: ProjectSlug | None = None
    description: ProjectDescription | None = None
    context_md: str | None = None
    privileged: bool = False
    minimum_inference_tier: InferenceTier | None = None

    @model_validator(mode="after")
    def _validate_context_size(self) -> Self:
        _validate_context_md_bytes(self.context_md)
        return self

    @model_validator(mode="after")
    def _validate_privileged_implies_tier(self) -> Self:
        """Enforce the PRD §3.11 rule at the API boundary.

        ``privileged=true`` requires ``minimum_inference_tier`` to be
        set. The DB CHECK constraint catches anything that bypasses
        this (defense-in-depth) and the field-naming detail goes into
        the response so the client knows which field to fix.
        """

        if self.privileged and self.minimum_inference_tier is None:
            raise ValueError("minimum_inference_tier must be set when privileged=true")
        return self


class ProjectUpdateRequest(BaseModel):
    """``ProjectUpdate`` from backend-openapi.yaml.

    Every field is optional — PATCH applies only the fields the caller
    sets. The model uses an ``UNSET`` sentinel-like pattern via
    ``exclude_unset`` at the handler boundary.

    Two kinds of unset are conflated by ``Optional[...] = None`` in JSON:
    "field absent from body" and "field present with explicit null." For
    ``minimum_inference_tier`` the difference matters (a caller may want
    to *clear* the tier). FastAPI/Pydantic surfaces this through
    ``model_dump(exclude_unset=True)``: explicit-null is included, absent
    is dropped. The handler uses that pattern.
    """

    model_config = ConfigDict(extra="forbid")

    name: ProjectName | None = None
    slug: ProjectSlug | None = None
    description: ProjectDescription | None = None
    context_md: str | None = None
    privileged: bool | None = None
    # ``int | None`` so the caller can clear the tier explicitly.
    minimum_inference_tier: InferenceTier | None = None
    archived: bool | None = None
    """When set, archive (true) or unarchive (false) the project. The
    OpenAPI sketch has a separate DELETE for soft-delete; this field is
    the non-destructive form (PATCH ``{archived: true}``)."""

    @model_validator(mode="after")
    def _validate_context_size(self) -> Self:
        _validate_context_md_bytes(self.context_md)
        return self

    # We intentionally do NOT validate the privileged↔tier rule here —
    # PATCH applies a *partial* update, so the constraint must be
    # re-checked against the *merged* state in the handler. The DB
    # CHECK constraint is the safety net.


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ProjectResponse(BaseModel):
    """``Project`` schema from backend-openapi.yaml.

    Built from the ORM row via
    :meth:`from_row` with the attached file ids and skill names already
    materialised by the handler (a single round-trip with eager-loading
    is cleaner than a lazy load through the ORM relationship).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    context_md: str | None = None
    privileged: bool
    minimum_inference_tier: int | None = None
    attached_file_ids: list[uuid.UUID] = Field(default_factory=list)
    attached_skill_names: list[str] = Field(default_factory=list)
    attached_knowledge_base_ids: list[uuid.UUID] = Field(default_factory=list)
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
