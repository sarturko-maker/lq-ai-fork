"""Admin endpoints under ``/admin/v1/...`` (PRD §4.5).

A3 lands surface stubs:

* ``GET /admin/v1/providers/health`` — 501 (B3+ wires real provider probes).
* ``GET /admin/v1/usage`` — 501 (cost-tracker task wires this).
* ``GET /admin/v1/tier-config`` — returns the loaded ``tier_policy`` block.
* ``GET /admin/v1/anonymization-config`` — 501 (M2).

Every other admin endpoint sketched in PRD §4.5 (``PATCH``-style writes,
``POST /admin/v1/config/reload``) lands later.

Note re: OpenAPI vs. PRD: ``docs/api/gateway-openapi.yaml`` (an older sketch)
shows ``/admin/inference-tiers`` rather than ``/admin/v1/tier-config``.
Per ``CLAUDE.md`` decision routing the PRD wins; the implementation order's
A3 entry and PRD §4.5 both specify ``/admin/v1/tier-config``, so that's what
A3 ships. The OpenAPI sketch will get refreshed in a later docs pass.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.config import GatewayConfig

router = APIRouter(prefix="/admin/v1", tags=["admin"])


def _not_implemented(*, message: str, next_task: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": {
                "code": "not_implemented",
                "message": message,
                "details": {"next_task": next_task},
            }
        },
    )


def _config(request: Request) -> GatewayConfig:
    return request.app.state.config  # type: ignore[no-any-return]


@router.get("/providers/health")
async def providers_health(request: Request) -> JSONResponse:
    """Per-provider health probe — 501 until provider adapters land (B3+)."""

    return _not_implemented(
        message=(
            "Provider health probes are not yet implemented. Provider "
            "adapters land starting at B3 (Anthropic); this endpoint becomes "
            "real once an adapter has a health-probe contract to call."
        ),
        next_task="B3 — Anthropic provider adapter",
    )


@router.get("/usage")
async def usage(request: Request) -> JSONResponse:
    """Per-key/per-model usage and cost — 501 until cost tracking lands."""

    return _not_implemented(
        message=(
            "Usage and cost reporting are not yet implemented. The cost "
            "tracker is wired after the first provider adapter lands."
        ),
        next_task="post-B3 — cost tracker",
    )


@router.get("/tier-config")
async def get_tier_config(request: Request) -> dict[str, Any]:
    """Return the loaded ``tier_policy`` block from ``gateway.yaml``.

    A3 returns the loaded policy as-is. ``PATCH`` (admin-only updates) and
    audit logging of changes land in D1, where tier-floor refusal logic and
    its operational surface are wired together.
    """

    cfg = _config(request)
    return {"tier_policy": cfg.tier_policy.model_dump(mode="json")}


@router.get("/anonymization-config")
async def get_anonymization_config(request: Request) -> JSONResponse:
    """Anonymization config — M2 feature; A3 returns 501.

    The ``anonymization`` block does load into config (so operators can put
    M2-shaped settings in their ``gateway.yaml`` today), but the surface is
    stubbed until the M2 implementation lands. Returning 501 here matches
    the chat-completions stub posture: the config is parsed; the feature is
    not yet served.
    """

    return _not_implemented(
        message=(
            "Anonymization configuration is an M2 feature. The "
            "``anonymization`` block in gateway.yaml loads today but is not "
            "yet enforced; this admin surface lands with the M2 anonymization "
            "middleware (PRD §4.7)."
        ),
        next_task="M2 — anonymization middleware (PRD §4.7)",
    )
