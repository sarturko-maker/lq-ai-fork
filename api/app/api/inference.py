"""User-facing inference inquiry endpoints — Wave B (PRD §3.13).

Backs the Tier Awareness UI's click-for-details panel:

* ``GET /api/v1/inference/current-tier?provider=&model=`` — looks up
  the derived tier + human-readable explanation for a (provider, model)
  pair. The UI calls this on hover/click of the tier badge so the user
  sees "Anthropic Enterprise (ZDR)" instead of just "3".
* ``GET /api/v1/inference/tier-config`` — returns the deployment's
  allowed_tiers + default minima. Available to any authenticated user
  (the policy is a deployment-level disclosure, not a secret); the
  admin-only ``/admin/tier-policy`` PATCH lives in :mod:`admin`.

Both endpoints proxy through to the gateway: the gateway is the
single source of truth for tier derivation (per ADR 0011) and for the
operator's tier policy (per ADR 0010). The backend's role is to
normalize the response shape against the OpenAPI sketch and to apply
the standard user-token auth gate (the gateway's admin API is
shared-secret, not user-bearing).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.api.dependencies import ActiveUser
from app.clients.gateway import GatewayClient, get_gateway_client
from app.errors import LQAIError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/inference", tags=["inference"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CurrentTierResponse(BaseModel):
    """``GET /inference/current-tier`` response.

    ``provider`` and ``model`` echo back so the caller can correlate
    the answer to the question (the gateway may normalize names — e.g.,
    resolve an alias before returning the tier).
    """

    provider: str
    model: str
    routed_inference_tier: int | None = None
    routed_provider_type: str | None = None
    """The provider's ``type`` (anthropic / openai / vertex / ollama / ...).
    The Provider Compliance Matrix table the UI renders is keyed on
    this rather than the operator-defined ``provider`` name."""

    explanation: str = ""
    """Human-readable one-line summary the UI can show next to the
    badge ("Anthropic Enterprise (ZDR) — Tier 3"). Synthesized
    here; the operator can override per-deployment via the Provider
    Compliance Matrix doc."""


class TierConfigResponse(BaseModel):
    """``GET /inference/tier-config`` response — the operator's tier policy."""

    allowed_tiers_global: list[int]
    default_minimum_tier: int
    privileged_minimum_tier: int
    warn_on_tiers: list[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TIER_LABELS: dict[int, str] = {
    1: "Tier 1 — Local / air-gapped",
    2: "Tier 2 — Self-hosted cloud",
    3: "Tier 3 — Enterprise managed inference (ZDR / no-training)",
    4: "Tier 4 — Standard cloud API",
    5: "Tier 5 — Consumer / free tier",
}


def _explain_tier(
    *,
    provider: str,
    model: str,
    provider_type: str | None,
    tier: int | None,
) -> str:
    """Render the one-line explanation the UI shows next to the badge.

    Operators who want richer prose link the tier badge to the Provider
    Compliance Matrix in ``docs/compliance/`` (M1 deliverable). This
    string is the at-a-glance summary that surfaces without a click.
    """

    if tier is None:
        return (
            f"No tier derived for {provider!r} / {model!r}. The deployment's "
            "gateway.yaml may not declare a tier for this provider/model "
            "pair; check inference_tiers in gateway.yaml."
        )
    label = _TIER_LABELS.get(tier, f"Tier {tier}")
    type_part = f" ({provider_type})" if provider_type else ""
    return f"{label} — {provider}{type_part} · {model}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/current-tier",
    response_model=CurrentTierResponse,
    summary="Derive the routed inference tier for a (provider, model) pair",
)
async def get_current_tier(
    user: ActiveUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
    request: Request,
    provider: str = Query(..., min_length=1, max_length=200),
    model: str = Query(..., min_length=1, max_length=200),
) -> CurrentTierResponse:
    """GET /api/v1/inference/current-tier — derive tier from gateway config.

    The lookup runs against the gateway's live model list (``/v1/models``)
    which already carries ``routed_inference_tier`` per entry (see
    ``GatewayConfig.iter_resolved_models``). Returns 404 when the
    (provider, model) pair isn't configured — the UI can fall back to
    rendering "Tier unknown" rather than guessing.
    """

    try:
        models_payload = await gateway.list_models(
            request_id=request.headers.get("x-request-id")
        )
    except LQAIError:
        raise

    # ``list_models`` returns the OpenAI ``ListModelsResponse`` shape
    # extended by the gateway:
    #
    # * Provider-native models are emitted as
    #   ``{"id": "<provider>/<model>", "owned_by": "<provider>",
    #     "provider_type": "<type>", "routed_inference_tier": <int>}``.
    # * Aliases (``smart``, ``fast``, ...) are emitted as
    #   ``{"id": "<alias>", "lq_ai_kind": "alias",
    #     "lq_ai_resolves_to": "<provider>/<model>", "routed_inference_tier": <int>}``.
    #
    # We accept the caller's (provider, model) in either form:
    #   1. Provider-native exact: ``id == f"{provider}/{model}"``.
    #   2. Alias form: ``id == model and lq_ai_kind == 'alias'`` (provider
    #      is then ignored / treated as documentation).
    data = models_payload.get("data", [])
    matched: dict[str, Any] | None = None
    composite_id = f"{provider}/{model}"
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == composite_id and entry.get("owned_by") == provider:
            matched = entry
            break
        if entry.get("id") == model and entry.get("lq_ai_kind") == "alias":
            matched = entry
            break

    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No (provider={provider!r}, model={model!r}) entry in the gateway's model list."
            ),
        )

    tier = matched.get("routed_inference_tier")
    # Provider-native entries carry ``provider_type``; aliases carry
    # neither (we surface null in that case — operators can still
    # render the badge using the routed_inference_tier alone).
    provider_type = matched.get("provider_type")

    return CurrentTierResponse(
        provider=provider,
        model=model,
        routed_inference_tier=int(tier) if isinstance(tier, int) else None,
        routed_provider_type=str(provider_type) if provider_type else None,
        explanation=_explain_tier(
            provider=provider,
            model=model,
            provider_type=str(provider_type) if provider_type else None,
            tier=int(tier) if isinstance(tier, int) else None,
        ),
    )


@router.get(
    "/tier-config",
    response_model=TierConfigResponse,
    summary="Read the deployment's tier policy (allowed tiers + minima)",
)
async def get_tier_config(
    user: ActiveUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
    request: Request,
) -> TierConfigResponse:
    """GET /api/v1/inference/tier-config — operator's tier policy.

    User-accessible (not admin-only) — the policy is a deployment-level
    disclosure the UI uses to render allowed/disallowed tier badges.
    The admin-write surface lives at ``PATCH /api/v1/admin/tier-policy``.
    """

    payload = await gateway.get_tier_config(
        request_id=request.headers.get("x-request-id")
    )
    policy = payload.get("tier_policy", {})
    return TierConfigResponse(
        allowed_tiers_global=list(policy.get("allowed_tiers_global") or [1, 2, 3, 4]),
        default_minimum_tier=int(policy.get("default_minimum_tier", 4)),
        privileged_minimum_tier=int(policy.get("privileged_minimum_tier", 3)),
        warn_on_tiers=list(policy.get("warn_on_tiers") or [4, 5]),
    )


__all__ = ["router"]
