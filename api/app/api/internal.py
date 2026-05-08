"""Internal service-to-service routes (gateway → backend).

Per ADR 0006 (Skill prompt assembly), the gateway needs to read skill
content from the backend's registry during prompt assembly. The
user-facing ``GET /api/v1/skills/{name}`` endpoint is gated by
``get_active_user`` (B1 bearer + B2 password-change gate) and is
inappropriate for service-to-service traffic — the gateway has no
user.

This module exposes a parallel ``GET /api/v1/internal/skills/{name}``
endpoint authenticated by the existing ``X-LQ-AI-Gateway-Key`` shared
secret. Trust-domain separation: user-facing endpoints stay under
user-token auth; internal endpoints stay under shared-secret auth.
The two never mix on a single route. The response shape is identical
to the user-facing endpoint so the gateway-side client can reuse the
same response model.

Scope (M1):

* ``GET /api/v1/internal/skills/{name}`` — full Skill detail. Same body
  as the user-facing route.
* No ``GET /api/v1/internal/skills`` (list) — the gateway never enumerates,
  it only fetches the specific skill names a request has attached.

Auth posture
------------

The header check is constant-time (``secrets.compare_digest``). A missing
or wrong key returns 401. The gateway-key is shared with the backend via
``LQ_AI_GATEWAY_KEY`` (already set on both services for the
backend → gateway direction; reused here in the reverse direction).

If the operator has not configured ``LQ_AI_GATEWAY_KEY`` (i.e., it is
the empty string), the route returns 500 with
``code=internal_error`` and a clear log line — accepting the call
unauthenticated would be a security hole. This matches the
``LQ_AI_GATEWAY_KEY`` is required posture documented in
``docker-compose.yml``.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import InternalError, NotFound, Unauthorized
from app.skills.registry import MutableSkillRegistry

log = logging.getLogger(__name__)

# The same header name the backend → gateway direction uses (per
# docs/api/gateway-openapi.yaml securitySchemes); we reuse it for the
# reverse direction so operators only configure one secret.
GATEWAY_KEY_HEADER = "X-LQ-AI-Gateway-Key"

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_gateway_key(presented: str | None) -> None:
    """Constant-time check the presented gateway key against settings.

    Raises :class:`Unauthorized` (401) on missing or wrong key.
    Raises :class:`InternalError` (500) when the operator has not
    configured ``LQ_AI_GATEWAY_KEY`` — accepting traffic with no
    enforced secret would silently break the trust contract.
    """

    settings = get_settings()
    expected = settings.lq_ai_gateway_key
    if not expected:
        # Operator misconfiguration — refuse to accept service-to-service
        # traffic when the shared secret is unset rather than running
        # open. The log line is operator-actionable.
        log.error(
            "LQ_AI_GATEWAY_KEY is not set on the api/ service; refusing "
            "internal traffic. Set the env var and restart."
        )
        raise InternalError(
            message=(
                "Internal API authentication is not configured on the "
                "backend. Operator must set LQ_AI_GATEWAY_KEY."
            ),
        )
    if presented is None or not secrets.compare_digest(presented, expected):
        raise Unauthorized(
            message="Invalid or missing gateway key",
            details={"header": GATEWAY_KEY_HEADER},
        )


def _registry(request: Request) -> MutableSkillRegistry:
    """Return the live skill registry from app state.

    Mirrors the helper in ``app/api/skills.py``. Surfaces a clear
    InternalError (500) rather than ``AttributeError`` if lifespan
    didn't run.
    """

    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    if holder is None:
        raise InternalError(
            message=(
                "Skill registry is not initialised; the API process is "
                "not yet ready to serve skill queries."
            ),
            details={"hint": "lifespan startup did not run"},
        )
    return holder


@router.get("/skills/{skill_name}")
async def get_skill_internal(
    request: Request,
    skill_name: str,
    x_lq_ai_gateway_key: str | None = Header(default=None, alias=GATEWAY_KEY_HEADER),
) -> JSONResponse:
    """Return full skill detail for ``skill_name``.

    Same response shape as ``GET /api/v1/skills/{skill_name}`` — the
    full ``Skill`` from ``docs/api/backend-openapi.yaml``, with
    ``None``-valued optionals dropped for compactness. Auth is via
    ``X-LQ-AI-Gateway-Key`` (constant-time compare); 401 on bad key,
    404 on unknown skill name.
    """

    _verify_gateway_key(x_lq_ai_gateway_key)

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


__all__ = ["GATEWAY_KEY_HEADER", "router"]
