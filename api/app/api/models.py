"""Models proxy — Task D0.

Exposes ``GET /api/v1/models`` to authenticated users. The handler is a
thin proxy over the gateway's merged-discovery ``GET /v1/models`` endpoint
(see ``docs/api/gateway-openapi.yaml``): aliases plus live-discovered
Ollama tags plus live-discovered Anthropic catalog rows. The response is
forwarded verbatim so the LQ.AI shell's model picker (D0) consumes one
stable contract.

Auth: per ``app/api/__init__.py`` the router is mounted under
``Depends(get_active_user)``. Anonymous reads are intentionally not
allowed — the picker's contents reveal which providers the operator has
configured, which is information that belongs only to authenticated
users.

The handler does NOT call provider APIs directly. The gateway is the
security boundary; only the gateway holds the operator's provider keys.
This proxy uses the existing :class:`GatewayClient` (B5 pool) so the
backend doesn't need any new outbound credentials.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.clients.gateway import GatewayClient, get_gateway_client

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models(
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> JSONResponse:
    """Return the gateway's merged ``GET /v1/models`` payload verbatim.

    Errors from the gateway client propagate as :class:`LQAIError`
    subclasses; the global exception handler in :mod:`app.main`
    translates them to the canonical ``{"detail": {"code", ...}}``
    envelope. Specifically:

    * Gateway 401 (bad shared-secret) → ``GatewayUnreachable`` /
      HTTP 503 with ``code = "gateway_unreachable"``. The user must not
      see "the operator misconfigured the gateway key".
    * Network failure → ``GatewayUnreachable`` / HTTP 503.
    * Timeout → ``GatewayTimeout`` / HTTP 504.
    * Structured gateway errors → mapped per
      :func:`app.errors.map_gateway_error_code`.

    The success body is forwarded as-is — the client side already
    understands the gateway's shape (per the OpenAPI sketch).
    """

    payload: dict[str, Any] = await gateway.list_models()
    return JSONResponse(content=payload)
