"""Skills endpoints — Task C1 (filesystem loading) + Task D8 (user shadows).

Implements the read side of the skills surface and the fork operation:

* ``GET /api/v1/skills`` — list summaries. Merges filesystem-canonical
  built-ins with the caller's user-scope skills per ADR 0012; user
  shadows dedupe a built-in on slug collision.
* ``GET /api/v1/skills/{skill_name}`` — full skill detail. Tries the
  caller's user-scope row first (shadow path); falls through to the
  registry's built-in if no shadow exists.
* ``POST /api/v1/skills/{skill_name}/fork`` — copy a built-in's
  content into a fresh user-scope row owned by the caller (D8). The
  ``scope: team`` branch is rejected with a 400 pointing at D8.1.

The owner-scoped management surface for user skills (POST /user-skills,
PATCH, DELETE, list-mine) lives in
:mod:`app.api.user_skills` — that's where the "manage my skills" page
talks to. This module owns the merged picker view.

Auth: per ``app/api/__init__.py`` the skills router is mounted under
``Depends(get_active_user)``, so every handler here inherits the
B1 bearer-token check plus the B2 must-change-password gate.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser
from app.audit import audit_action
from app.db.session import get_db
from app.errors import NotFound
from app.models.user_skill import UserSkill
from app.skills.registry import MutableSkillRegistry
from app.skills.schema import filter_summary_for_response

router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Registry access
# ---------------------------------------------------------------------------


def _registry(request: Request) -> MutableSkillRegistry:
    """Return the live :class:`MutableSkillRegistry` from app state.

    The lifespan handler installs ``app.state.skill_registry``. If the
    handler is somehow exercised before that (e.g., a test that bypasses
    lifespan), surface a clear error rather than ``AttributeError``.
    """

    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    if holder is None:
        from app.errors import InternalError

        raise InternalError(
            message="Skill registry is not initialised; the API process is "
            "not yet ready to serve skill queries.",
            details={"hint": "lifespan startup did not run"},
        )
    return holder


# ---------------------------------------------------------------------------
# Synthesizing Skill-shape payloads from user_skills rows
# ---------------------------------------------------------------------------
#
# Filesystem built-ins parse a real ``SKILL.md`` and produce a
# :class:`Skill` (or :class:`SkillSummary`). User-scope rows are
# structured DB data — we synthesize an equivalent payload so the
# wire shape is identical whichever source the row came from. The
# gateway-side parser doesn't need to know which source it's reading.


def _summary_from_user_skill(row: UserSkill) -> dict[str, Any]:
    """Return the ``SkillSummary`` shape for a user-scope row, with
    ``None``/empty optionals dropped per the existing summary contract."""

    extra = dict(row.frontmatter_extra or {})
    summary: dict[str, Any] = {
        "name": row.slug,
        "version": row.version,
        "scope": "user",
        "title": row.display_name,
        "description": row.description,
        "tags": list(row.tags or []),
        "jurisdiction": extra.get("jurisdiction"),
        "minimum_inference_tier": extra.get("minimum_inference_tier"),
        "output_format": extra.get("output_format"),
    }
    return {k: v for k, v in summary.items() if v is not None and v != []}


def _skill_from_user_skill(row: UserSkill) -> dict[str, Any]:
    """Return the full ``Skill`` shape for a user-scope row.

    The ``content_yaml`` field is synthesized — we don't preserve a
    verbatim YAML block for user skills, so we re-emit one in the
    canonical shape (``name`` / ``description`` / ``lq_ai``) that the
    gateway's permissive parser already handles for filesystem skills.
    """

    import yaml  # local — only this synthesizer uses it

    lq_ai: dict[str, Any] = {"title": row.display_name, "version": row.version}
    if row.tags:
        lq_ai["tags"] = list(row.tags)
    for key, value in (row.frontmatter_extra or {}).items():
        if value is not None and key not in lq_ai:
            lq_ai[key] = value

    frontmatter = {
        "name": row.slug,
        "description": row.description,
        "lq_ai": lq_ai,
    }
    content_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)

    payload: dict[str, Any] = {
        **_summary_from_user_skill(row),
        "content_yaml": content_yaml,
        "content_md": row.body,
        "reference_files": [],
        "example_files": [],
    }
    return payload


async def _load_user_shadow(
    db: AsyncSession, *, user_id: uuid.UUID, slug: str
) -> UserSkill | None:
    """Return the caller's non-archived user-scope row for ``slug``, if any."""

    stmt = select(UserSkill).where(
        UserSkill.scope == "user",
        UserSkill.owner_user_id == user_id,
        UserSkill.slug == slug,
        UserSkill.archived_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _list_user_shadows(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[UserSkill]:
    """All non-archived user-scope rows owned by ``user_id``."""

    stmt = (
        select(UserSkill)
        .where(
            UserSkill.scope == "user",
            UserSkill.owner_user_id == user_id,
            UserSkill.archived_at.is_(None),
        )
        .order_by(UserSkill.updated_at.desc(), UserSkill.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_skills(
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    scope: str = Query(default="all", pattern="^(builtin|user|team|all)$"),
    tag: str | None = Query(default=None),
) -> JSONResponse:
    """Return summaries for skills visible to the caller.

    Merging semantics (per ADR 0012):

    * ``scope=all`` (default) — caller's user-scope rows first, then
      built-ins. Dedup on slug: a user shadow hides the built-in of
      the same slug from this listing.
    * ``scope=user`` — caller's user-scope rows only.
    * ``scope=builtin`` — filesystem built-ins only (no shadow merge).
    * ``scope=team`` — empty list until D8.1 (team scope deferred).

    The ``tag`` filter applies to both layers; a built-in matches if
    its ``lq_ai.tags`` contains the tag, a user shadow matches if its
    ``tags`` column contains it.
    """

    if scope == "team":
        # Deferred to D8.1 per ADR 0012; honor the contract by returning
        # the empty set rather than 501 — clients can render "no team
        # skills yet" without checking for a status code.
        return JSONResponse(content=[])

    holder = _registry(request)
    registry = holder.current()

    user_rows: list[UserSkill] = []
    if scope in ("user", "all"):
        user_rows = await _list_user_shadows(db, user_id=user.id)
        if tag is not None:
            user_rows = [r for r in user_rows if tag in (r.tags or [])]

    user_summaries = [_summary_from_user_skill(r) for r in user_rows]
    shadowed_slugs = {r.slug for r in user_rows}

    if scope == "user":
        return JSONResponse(content=user_summaries)

    builtin_summaries = [
        filter_summary_for_response(s)
        for s in registry.list_summaries(tag=tag)
        if s.name not in shadowed_slugs
    ]

    if scope == "builtin":
        return JSONResponse(content=builtin_summaries)

    return JSONResponse(content=user_summaries + builtin_summaries)


@router.get("/{skill_name}")
async def get_skill(
    request: Request,
    skill_name: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Return full skill detail, preferring the caller's user shadow if any.

    Resolution order: caller's non-archived user-scope row for this
    slug, then the filesystem-canonical built-in. 404 if neither
    matches.
    """

    shadow = await _load_user_shadow(db, user_id=user.id, slug=skill_name)
    if shadow is not None:
        return JSONResponse(content=_skill_from_user_skill(shadow))

    holder = _registry(request)
    registry = holder.current()
    skill = registry.get_skill(skill_name)
    if skill is None:
        raise NotFound(
            message=f"Skill {skill_name!r} is not in the registry.",
            details={"skill_name": skill_name},
        )

    raw = skill.model_dump()
    payload = {
        k: v
        for k, v in raw.items()
        if v is not None and not (isinstance(v, list) and len(v) == 0 and k in {"tags"})
    }
    return JSONResponse(content=payload)


@router.post("/{skill_name}/fork", status_code=status.HTTP_201_CREATED)
async def fork_skill(
    request: Request,
    skill_name: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: dict[str, Any] | None = None,
) -> JSONResponse:
    """Fork a filesystem-canonical built-in into a new user-scope row.

    Mirrors the OpenAPI sketch's contract (``new_name`` + ``scope`` in
    the body). D8 only implements ``scope='user'``; ``scope='team'`` is
    rejected with a 400 pointing at D8.1.

    If ``new_name`` matches an existing user-scope slug for this user,
    409. If ``new_name`` is omitted or equals the source slug, the new
    row becomes a same-slug shadow — which is the expected "I want my
    own version of nda-review" UX.
    """

    body = dict(payload or {})
    scope = body.get("scope", "user")
    if scope == "team":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "team-scope skills are deferred to D8.1 (ADR 0012 §Out of scope). "
                "Use scope='user' to fork into your personal scope."
            ),
        )
    if scope != "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope must be 'user' (team scope is deferred to D8.1)",
        )

    holder = _registry(request)
    registry = holder.current()
    source = registry.get_skill(skill_name)
    if source is None:
        raise NotFound(
            message=f"Skill {skill_name!r} is not in the registry.",
            details={"skill_name": skill_name},
        )

    # Local import to avoid circular: user_skills imports nothing from
    # skills, but we want to reuse its slug validator + tag normaliser
    # without duplicating the bounds constants.
    from app.api.user_skills import _validate_slug, _validate_tags

    new_slug = body.get("new_name") or source.name
    new_slug = _validate_slug(new_slug)
    forked_tags = _validate_tags(list(source.tags or []))

    # Mirror the source's lq_ai extension keys onto frontmatter_extra so
    # the synthesized payload after the fork looks shape-identical to
    # the original. Tier-floor, jurisdiction, output_format, etc. all
    # carry through.
    frontmatter_extra: dict[str, Any] = {}
    if source.jurisdiction is not None:
        frontmatter_extra["jurisdiction"] = source.jurisdiction
    if source.minimum_inference_tier is not None:
        frontmatter_extra["minimum_inference_tier"] = source.minimum_inference_tier
    if source.output_format is not None:
        frontmatter_extra["output_format"] = source.output_format

    row = UserSkill(
        scope="user",
        owner_user_id=user.id,
        slug=new_slug,
        display_name=source.title,
        description=source.description or "",
        version=source.version or "1.0.0",
        tags=forked_tags,
        frontmatter_extra=frontmatter_extra,
        body=source.content_md,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a user skill named {new_slug!r} already exists for this user",
        ) from None

    await audit_action(
        db,
        user_id=user.id,
        action="user_skill.created",
        resource_type="user_skill",
        resource_id=str(row.id),
        request=request,
        details={
            "slug": new_slug,
            "version": row.version,
            "tags": forked_tags,
            "forked_from": skill_name,
        },
    )
    await db.commit()
    await db.refresh(row)

    return JSONResponse(
        content=_skill_from_user_skill(row), status_code=status.HTTP_201_CREATED
    )
