"""OpenAI-compatible inference endpoints.

A3 lands the surface only:

* ``POST /v1/chat/completions`` — 501 stub (real routing in B3 + B4).
* ``POST /v1/embeddings`` — 501 stub.
* ``GET  /v1/models`` — returns the configured ``model_aliases`` from
  ``gateway.yaml``. This is the only inference endpoint that returns real
  data in A3, because it requires no provider call.

Error envelope follows ``GatewayError`` from ``docs/api/gateway-openapi.yaml``:

    {"error": {"code": "...", "message": "...", "details": {...}}}

A3-stub responses extend ``details`` with a ``next_task`` hint so anyone
hitting the gateway during M1 sees which task lands the real implementation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.config import GatewayConfig

router = APIRouter(prefix="/v1", tags=["inference"])


def _not_implemented(
    *,
    message: str,
    next_task: str,
) -> JSONResponse:
    """Build the standard 501 envelope used by A3 stubs."""

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
    """Pull the loaded :class:`GatewayConfig` off ``app.state``.

    The lifespan in :mod:`app.main` refuses to start if the config didn't
    load, so this attribute is always present at request time.
    """

    return request.app.state.config  # type: ignore[no-any-return]


@router.post("/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    """OpenAI-compatible chat completions — A3 stub returns 501.

    Real routing (alias resolution, tier derivation, provider dispatch) lands
    in B3 (Anthropic adapter) and B4 (router + alias resolution + tier
    derivation). The body is intentionally not read here so the stub can't
    accidentally accept malformed payloads as a side-effect.
    """

    return _not_implemented(
        message=(
            "Chat completions are not yet implemented. The Inference Gateway "
            "scaffold (M1 task A3) loads its config and exposes this surface; "
            "real routing lands in B3 (Anthropic adapter) and B4 (router + "
            "tier derivation)."
        ),
        next_task="B3 — Anthropic provider adapter",
    )


@router.post("/embeddings")
async def embeddings(request: Request) -> JSONResponse:
    """OpenAI-compatible embeddings — A3 stub returns 501."""

    return _not_implemented(
        message=(
            "Embeddings are not yet implemented. The Inference Gateway "
            "scaffold (M1 task A3) exposes this surface; an embeddings "
            "provider adapter lands in a later phase."
        ),
        next_task="B3 — Anthropic provider adapter (embeddings adapter follows)",
    )


@router.get("/models")
async def list_models(request: Request) -> dict[str, Any]:
    """Return the configured aliases as an OpenAI-shaped models list.

    The gateway exposes *aliases* (``smart``, ``fast``, ``budget``, ``local``,
    ``embedding``) rather than provider-native model names — per PRD §4.4,
    aliases decouple skill authoring from provider configuration.
    """

    return _config(request).to_models_payload()
