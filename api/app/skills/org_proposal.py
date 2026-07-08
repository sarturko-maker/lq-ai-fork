"""Org-skill propose synthesis + strict frontmatter validation (ADR-F067 D2/D3, B-2a).

This module is the pure, no-DB-access core of the org-skills harness:

* :func:`synthesize_org_skill` turns an author's own :class:`~app.models.user_skill.UserSkill`
  row into canonical ``SKILL.md`` content — the SAME frontmatter dict shape
  ``api.skills._skill_from_user_skill`` (``api/app/api/skills.py:115-152``) already produces for
  the gateway-facing synthesized payload, so a proposal's content is byte-identical to "what the
  author's own skill currently renders as" at propose time.
* :func:`validate_org_frontmatter` enforces the D3.3 CLOSED allowlist — reject, don't sanitize:
  it names every offending key path rather than stripping anything.
* :func:`render_provenance_banner` / :func:`served_skill_md` implement the D3.5 provenance
  posture: the banner is prefixed to the BODY at serve time only — stored bytes (and the content
  hash, which covers author bytes only) never change.

Callers (the propose endpoint, the admin approve/list endpoints, the runtime composition seam)
own all HTTP status codes and audit rows; nothing here raises HTTP-shaped errors. The sole DB
touchpoint in this module is :func:`load_approved_org_skill_versions` — the one shared reader
for "the org's currently-approved snapshots", so that query cannot drift across its many call
sites (the member Library read, the admin catalog/inventory, the runtime composition seam and
the matter-capabilities panel all route through it).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.skill_backend import reconstruct_skill_md
from app.models.org_skill import OrgSkillVersion

if TYPE_CHECKING:
    from app.models.user_skill import UserSkill

# F067 D3.6 — a hostile or accidental context-flooding skill is capped before it can tax every
# run's token budget (F051). Enforced by the CALLER (the propose endpoint 422s); this module
# only computes `size_bytes` for the caller to compare.
ORG_SKILL_MAX_BYTES = 32 * 1024

# F067 D3.3 — the CLOSED schema. Everything outside these two allowlists is a 422 naming the
# offending key, which automatically covers the explicitly-DENIED `allowed-tools` (deepagents
# renders it into the system prompt), `minimum_inference_tier` / `ensemble_verification`
# (cost/behaviour-bearing — those come from area/matter/deployment config, never org prompt
# content), `inputs`, `columns`, `use_organization_profile`, `is_organization_profile`,
# `self_improvement`, and anything credential-shaped.
ALLOWED_TOP_LEVEL = frozenset({"name", "description", "lq_ai"})
ALLOWED_LQ_AI = frozenset(
    {"title", "version", "author", "tags", "jurisdiction", "output_format", "trigger_examples"}
)


@dataclass(frozen=True)
class OrgSkillContent:
    """The synthesized content for one org-skill proposal — everything a caller needs to
    populate an :class:`~app.models.org_skill.OrgSkillVersion` row's content columns."""

    frontmatter: dict[str, Any]
    """The parsed frontmatter dict — identical shape to ``_skill_from_user_skill``'s
    ``content_yaml`` source (``{name, description, lq_ai: {...}}``)."""

    raw_yaml: str
    """Verbatim canonical YAML block, NO trailing newline (``yaml.safe_dump(...).rstrip("\\n")``)
    — the exact bytes stored in ``org_skill_versions.raw_yaml``."""

    body: str
    """The markdown body — the author's ``UserSkill.body`` bytes, unmodified."""

    content_hash: str
    """sha256 hexdigest over the reconstructed ``SKILL.md`` text
    (``reconstruct_skill_md(raw_yaml, body)``), UTF-8 encoded."""

    size_bytes: int
    """``len()`` of that same reconstructed text's UTF-8 encoding — what the caller compares
    against :data:`ORG_SKILL_MAX_BYTES`."""


def synthesize_org_skill(row: UserSkill) -> OrgSkillContent:
    """Synthesize canonical org-skill content from the author's own ``UserSkill`` row.

    Mirrors ``api.skills._skill_from_user_skill`` EXACTLY for the frontmatter shape: top-level
    ``{name: row.slug, description: row.description, lq_ai: {...}}``; ``lq_ai`` starts as
    ``{"title": row.display_name, "version": row.version}``, gains ``tags`` when the row has
    any, then gains every non-``None`` ``frontmatter_extra`` key not already set (``lq_ai:``
    wins on conflict — same precedence as the gateway synthesizer). This is a snapshot: later
    edits to ``row`` do not retroactively change an already-synthesized :class:`OrgSkillContent`.
    """

    lq_ai: dict[str, Any] = {"title": row.display_name, "version": row.version}
    if row.tags:
        lq_ai["tags"] = list(row.tags)
    for key, value in (row.frontmatter_extra or {}).items():
        if value is not None and key not in lq_ai:
            lq_ai[key] = value

    frontmatter: dict[str, Any] = {
        "name": row.slug,
        "description": row.description,
        "lq_ai": lq_ai,
    }
    raw_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
    body = row.body

    content_hash = hashlib.sha256(reconstruct_skill_md(raw_yaml, body).encode("utf-8")).hexdigest()

    return OrgSkillContent(
        frontmatter=frontmatter,
        raw_yaml=raw_yaml,
        body=body,
        content_hash=content_hash,
        size_bytes=content_size_bytes(raw_yaml, body),
    )


def content_size_bytes(raw_yaml: str, body: str) -> int:
    """UTF-8 byte size of the reconstructed ``SKILL.md`` served for these stored bytes.

    The single definition of "how big is this org skill" — shared by propose-time synthesis
    (:func:`synthesize_org_skill`) and every later recompute-from-stored-columns caller (the
    admin review read, the author's proposal read). Content columns are immutable, so this is
    stable for a given row."""
    return len(reconstruct_skill_md(raw_yaml, body).encode("utf-8"))


def validate_org_frontmatter(frontmatter: dict[str, Any]) -> list[str]:
    """Return the sorted list of offending dotted key paths; empty means valid.

    F067 D3.3 CLOSED-schema check: any top-level key not in :data:`ALLOWED_TOP_LEVEL`, and any
    ``lq_ai`` key not in :data:`ALLOWED_LQ_AI`, is offending (dotted as ``lq_ai.<key>``). Also
    flags a non-dict ``lq_ai`` (as ``"lq_ai"`` itself — its keys cannot be enumerated) and a
    non-string ``name``/``description`` when present. Reject, don't sanitize: nothing here
    strips or coerces — the caller 422s naming every offending path.

    This is well-formedness-BEFORE-schema: callers should additionally run
    ``SkillFrontmatter.model_validate(frontmatter)`` after this returns empty, to catch
    structural issues the permissive shipped-skill parser would otherwise let through (e.g. a
    missing ``description``).
    """

    offending: set[str] = set()

    for key in frontmatter:
        if key not in ALLOWED_TOP_LEVEL:
            offending.add(key)

    if "name" in frontmatter and not isinstance(frontmatter["name"], str):
        offending.add("name")
    if "description" in frontmatter and not isinstance(frontmatter["description"], str):
        offending.add("description")

    lq_ai = frontmatter.get("lq_ai")
    if lq_ai is not None:
        if not isinstance(lq_ai, dict):
            offending.add("lq_ai")
        else:
            for key in lq_ai:
                if key not in ALLOWED_LQ_AI:
                    offending.add(f"lq_ai.{key}")

    return sorted(offending)


def render_provenance_banner(author: str, approver: str, approved_on: str) -> str:
    """The F067 D3.5 provenance sentence, verbatim vocabulary.

    ``author``/``approver`` are caller-resolved labels (emails — never raw user IDs in
    model-facing text; the caller substitutes ``"unknown"`` when a FK was nulled).
    ``approved_on`` is a caller-formatted date string (``YYYY-MM-DD``).
    """

    return (
        f"Provenance: org-authored by {author}, approved by {approver} on {approved_on} "
        "— your company's own material, not LQ-shipped."
    )


def served_skill_md(version: OrgSkillVersion, *, author_label: str, approver_label: str) -> str:
    """The exact bytes the runtime serves for an approved org-skill version.

    The provenance banner is prefixed to the BODY as a Markdown blockquote at serve time only —
    frontmatter stays parseable, the stored ``body``/``raw_yaml`` bytes never mutate, and the
    ``content_hash`` (computed at propose time over author bytes only) stays valid. Uses
    ``version.reviewed_at`` for the approval date; falls back to ``"unknown"`` if unset (this
    function is meant to be called on ``state == 'approved'`` snapshots, where ``reviewed_at``
    is always set, but stays defensive rather than raising).
    """

    approved_on = version.reviewed_at.date().isoformat() if version.reviewed_at else "unknown"
    banner = render_provenance_banner(author_label, approver_label, approved_on)
    body_with_banner = f"> {banner}\n\n{version.body}"
    return reconstruct_skill_md(version.raw_yaml, body_with_banner)


async def load_approved_org_skill_versions(db: AsyncSession) -> dict[str, OrgSkillVersion]:
    """The org's currently-``approved`` org-skill snapshots (ADR-F067 D2/D3), keyed by slug.

    The module's single DB touchpoint and the ONE place the ``state == 'approved'`` snapshot
    query lives, so "what counts as a live org skill" cannot drift between the member Library
    read, the admin catalog/inventory, the runtime composition seam and the capability panel.
    Callers that only need the slug set derive it from ``.keys()``."""
    rows = (
        (await db.execute(select(OrgSkillVersion).where(OrgSkillVersion.state == "approved")))
        .scalars()
        .all()
    )
    return {v.slug: v for v in rows}


__all__ = [
    "ALLOWED_LQ_AI",
    "ALLOWED_TOP_LEVEL",
    "ORG_SKILL_MAX_BYTES",
    "OrgSkillContent",
    "content_size_bytes",
    "load_approved_org_skill_versions",
    "render_provenance_banner",
    "served_skill_md",
    "synthesize_org_skill",
    "validate_org_frontmatter",
]
