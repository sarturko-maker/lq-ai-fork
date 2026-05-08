"""Skills endpoints — Task C1 (filesystem loading).

Implements the read side of the skills surface:

* ``GET /api/v1/skills`` — list summaries (no SKILL.md body in the
  response; that lives behind the per-skill detail endpoint).
* ``GET /api/v1/skills/{skill_name}`` — full skill detail including
  the body markdown, the verbatim YAML frontmatter, and any
  ``reference/`` and ``examples/`` files (loaded lazily here so a list
  call doesn't slurp the whole library off disk).

The fork endpoint (``POST /api/v1/skills/{skill_name}/fork``) remains a
501 stub; it lands in a future task once user/team-scope storage is
wired through the database.

Auth: per ``app/api/__init__.py`` the skills router is mounted under
``Depends(get_active_user)``, so every handler here inherits the
B1 bearer-token check plus the B2 must-change-password gate. No
per-handler auth code needed.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented
from app.errors import NotFound
from app.skills.registry import MutableSkillRegistry
from app.skills.schema import filter_summary_for_response

router = APIRouter(prefix="/skills", tags=["skills"])


def _registry(request: Request) -> MutableSkillRegistry:
    """Return the live :class:`MutableSkillRegistry` from app state.

    The lifespan handler installs ``app.state.skill_registry``. If the
    handler is somehow exercised before that (e.g., a test that bypasses
    lifespan), surface a clear error rather than ``AttributeError``.
    """

    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    if holder is None:
        # This is a configuration / wiring bug, not a user error. The
        # canonical 500 envelope from ``app.errors`` is the right shape.
        from app.errors import InternalError

        raise InternalError(
            message="Skill registry is not initialised; the API process is "
            "not yet ready to serve skill queries.",
            details={"hint": "lifespan startup did not run"},
        )
    return holder


@router.get("")
async def list_skills(
    request: Request,
    scope: str = Query(default="all", pattern="^(builtin|user|team|all)$"),
    tag: str | None = Query(default=None),
) -> JSONResponse:
    """Return summaries for every loaded skill.

    The ``scope`` query parameter is accepted for OpenAPI conformance
    but, in C1, only ``builtin`` skills exist — user/team-scope forks
    are deferred until DB-backed skill storage lands. Unknown ``scope``
    values are rejected by the regex above.
    """

    holder = _registry(request)
    registry = holder.current()

    # ``builtin``, ``all`` → return everything; ``user`` / ``team`` →
    # empty list until the user/team scopes exist. This is the
    # conservative-posture answer (don't pretend forks exist when they
    # don't); when forks land they extend this branch.
    if scope in ("user", "team"):
        return JSONResponse(content=[])

    summaries = registry.list_summaries(tag=tag)
    payload = [filter_summary_for_response(s) for s in summaries]
    return JSONResponse(content=payload)


@router.get("/{skill_name}")
async def get_skill(request: Request, skill_name: str) -> JSONResponse:
    """Return full skill detail for ``skill_name`` or 404 if no such skill."""

    holder = _registry(request)
    registry = holder.current()
    skill = registry.get_skill(skill_name)
    if skill is None:
        raise NotFound(
            message=f"Skill {skill_name!r} is not in the registry.",
            details={"skill_name": skill_name},
        )

    # ``model_dump`` here drops ``None`` values for OpenAPI-optional
    # fields the same way the list endpoint does — keeps the response
    # compact and matches the sketch's optional-may-be-absent reading.
    raw = skill.model_dump()
    payload = {
        k: v
        for k, v in raw.items()
        if v is not None and not (isinstance(v, list) and len(v) == 0 and k in {"tags"})
    }
    return JSONResponse(content=payload)


@router.post("/{skill_name}/fork")
async def fork_skill(request: Request, skill_name: str) -> JSONResponse:
    """Stub — landing in a future task once user/team scope is wired."""

    return not_implemented(
        request,
        next_task="C1+ — user/team scope storage (TBD)",
        endpoint="POST /api/v1/skills/{skill_name}/fork",
    )
