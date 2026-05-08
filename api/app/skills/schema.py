"""Pydantic schemas for skill frontmatter and the wire shapes.

Two layers:

* :class:`SkillFrontmatter` / :class:`LQAIFrontmatter` — what we parse
  out of each ``SKILL.md``'s YAML front-matter block. Matches the
  conventions in ``docs/skill-authoring-guide.md`` but is **permissive**:
  unknown fields are kept (``model_config.extra = "allow"``), and most
  fields are optional because the M1 starter skills predate the formal
  guide and use a wider range of values (e.g., ``output_format:
  markdown`` rather than ``report``; some skills carry no ``lq_ai:``
  block at all). The loader emits a WARNING per skill when a strictly-
  required field is missing; it does not fail the whole startup.

* :class:`SkillSummary` / :class:`Skill` — the JSON shapes the backend
  API returns. Match the ``SkillSummary`` and ``Skill`` schemas in
  ``docs/api/backend-openapi.yaml``. ``SkillSummary`` is what
  ``GET /api/v1/skills`` returns per item; ``Skill`` is what
  ``GET /api/v1/skills/{skill_name}`` returns and includes the full
  body, the raw YAML frontmatter, the optional reference files, and
  the optional example files.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# All built-in M1 skills are filesystem-canonical; user/team-scope forks
# land later and gain ``user`` / ``team`` values for ``scope``. C1 only
# delivers the ``builtin`` scope.
SkillScope = Literal["builtin", "user", "team"]


class LQAIFrontmatter(BaseModel):
    """The ``lq_ai:`` namespace inside a SKILL.md's frontmatter.

    All fields are optional. The skill-authoring guide documents
    recommended values, but the M1 starter skill corpus uses a broader
    range — strict validation would reject most of it. The summary
    endpoint surfaces what is present; missing fields are simply not
    in the response.
    """

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    """Human-readable display name for the UI. Defaults to ``name``
    rendered title-cased when missing."""

    version: str | None = Field(
        default=None,
        description="Semver string, e.g. '1.0.0'. Free-form so we can surface "
        "non-conforming values without rejecting them.",
    )

    author: str | None = None

    tags: list[str] = Field(default_factory=list)
    """Discovery tags. Empty if not declared."""

    jurisdiction: str | None = None
    """Free-form per the corpus reality (``us``, ``regime-aware``,
    ``agnostic``, ``regime-dependent``, ``US-default``, etc.)."""

    output_format: str | None = None
    """Free-form per corpus (``report``, ``markdown``,
    ``structured_checklist``, ``redline``, etc.)."""

    minimum_inference_tier: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Tier-floor declaration; the gateway's tier-floor "
        "enforcement (D1) consults this. C1 only surfaces the value.",
    )

    use_organization_profile: bool | None = None
    is_organization_profile: bool | None = None
    self_improvement: bool | None = None

    trigger_examples: list[str] = Field(default_factory=list)


class SkillFrontmatter(BaseModel):
    """Top-level frontmatter shape.

    Two required fields — ``name`` and ``description``. ``name`` is the
    skill's stable identifier (matches the folder name); ``description``
    is the one-sentence trigger statement. Everything else nests under
    ``lq_ai:`` per the authoring guide.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    description: str
    lq_ai: LQAIFrontmatter = Field(default_factory=LQAIFrontmatter)


# --- Wire shapes -------------------------------------------------------------


class SkillSummary(BaseModel):
    """The shape ``GET /api/v1/skills`` returns per item.

    Mirrors ``SkillSummary`` in ``docs/api/backend-openapi.yaml``. The
    ``required`` set there is ``[name, version, scope, title]``; for
    skills whose frontmatter is sparse we default ``version`` to
    ``"unversioned"`` and ``title`` to a humanised form of ``name`` so
    the contract is honoured even when the source is incomplete.
    """

    name: str
    version: str
    scope: SkillScope
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    jurisdiction: str | None = None
    minimum_inference_tier: int | None = None
    output_format: str | None = None


class SkillFile(BaseModel):
    """A reference or example file relative to the skill folder."""

    path: str
    """Path relative to the skill folder, e.g. ``reference/severity_rubric.md``."""

    content: str


class Skill(SkillSummary):
    """The shape ``GET /api/v1/skills/{name}`` returns.

    Mirrors ``Skill`` in ``docs/api/backend-openapi.yaml`` (which is an
    ``allOf`` of ``SkillSummary`` plus body fields). ``content_yaml`` is
    the raw frontmatter block (re-emitted, not the source bytes), and
    ``content_md`` is the body markdown. Reference and example files
    are loaded lazily — only when this shape is materialised.
    """

    content_yaml: str
    content_md: str
    reference_files: list[SkillFile] = Field(default_factory=list)
    example_files: list[SkillFile] = Field(default_factory=list)


# --- Internal helpers --------------------------------------------------------


def derive_summary(name: str, frontmatter: SkillFrontmatter) -> SkillSummary:
    """Build a :class:`SkillSummary` from parsed frontmatter.

    Applies the contract-completion defaults documented above so the
    OpenAPI ``required`` set is always satisfied even when the source
    frontmatter is sparse.
    """

    lq = frontmatter.lq_ai
    title = lq.title or _humanise(name)
    version = lq.version or "unversioned"
    return SkillSummary(
        name=name,
        version=version,
        scope="builtin",
        title=title,
        description=frontmatter.description,
        tags=list(lq.tags),
        jurisdiction=lq.jurisdiction,
        minimum_inference_tier=lq.minimum_inference_tier,
        output_format=lq.output_format,
    )


def _humanise(name: str) -> str:
    """Turn ``msa-review-saas`` into ``Msa Review Saas``.

    Used as a fallback display name when the frontmatter omits ``title``.
    Not pretty for every name, but visible when present and explicit
    when absent — fixing it is a one-line frontmatter edit per skill.
    """

    return " ".join(part.capitalize() for part in name.split("-")) if name else name


def filter_summary_for_response(summary: SkillSummary) -> dict[str, Any]:
    """Return the summary as a dict with ``None``-valued optionals dropped.

    The OpenAPI sketch lists ``description``, ``tags``, ``jurisdiction``,
    ``minimum_inference_tier``, and ``output_format`` as optional. We
    omit them rather than emit ``null`` so the response stays compact
    and matches the sketch's "optional == may be absent" reading.
    """

    raw = summary.model_dump()
    return {k: v for k, v in raw.items() if v is not None and v != []}


__all__ = [
    "LQAIFrontmatter",
    "Skill",
    "SkillFile",
    "SkillFrontmatter",
    "SkillScope",
    "SkillSummary",
    "derive_summary",
    "filter_summary_for_response",
]
