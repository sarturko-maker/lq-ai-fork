"""Admin endpoints — backend proxy + ``is_admin`` gate (D0.5).

Surface (current):

* ``GET    /api/v1/admin/aliases``           — list aliases (D0.5)
* ``GET    /api/v1/admin/aliases/{name}``    — single alias (D0.5)
* ``POST   /api/v1/admin/aliases``           — create alias (D0.5)
* ``PATCH  /api/v1/admin/aliases/{name}``    — update alias (D0.5)
* ``DELETE /api/v1/admin/aliases/{name}``    — remove alias (D0.5)
* ``GET    /api/v1/admin/config``            — sanitized gateway config (D0.5)
* ``GET    /api/v1/admin/audit-log``         — 501 (D3 wires real impl)
* ``GET    /api/v1/admin/tier-policy``       — 501 (D1)
* ``PATCH  /api/v1/admin/tier-policy``       — 501 (D1)

Auth posture: every admin endpoint stacks on top of the existing
``ActiveUser`` (bearer + must-change-password gate) AND the new
``AdminUser`` dependency that requires ``user.is_admin == True``.
Non-admin authenticated users see 403 with ``code = "forbidden"``.

The alias-CRUD endpoints proxy the gateway's ``/admin/v1/aliases``
surface. The backend is the only entity that holds the gateway-key,
so users can only mutate aliases through this router. The
:class:`GatewayClient` adds the gateway-key header on every call and
translates structured errors from the gateway via ADR 0003 — the
backend's typed exceptions surface as the canonical ``{"detail": ...}``
envelope through the global exception handler in :mod:`app.main`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api._stub import not_implemented
from app.api.dependencies import AdminUser
from app.clients.gateway import GatewayClient, get_gateway_client

router = APIRouter(prefix="/admin", tags=["admin"])

_D3 = "D3 — Audit log: privilege fields"
_D1 = "D1 — Tier-floor enforcement (refusals)"


# ---------------------------------------------------------------------------
# Existing surface (A4 stubs)
# ---------------------------------------------------------------------------


@router.get("/audit-log")
async def get_audit_log(request: Request, _admin: AdminUser) -> JSONResponse:
    return not_implemented(request, next_task=_D3, endpoint="GET /api/v1/admin/audit-log")


@router.get("/tier-policy")
async def get_tier_policy(request: Request, _admin: AdminUser) -> JSONResponse:
    return not_implemented(request, next_task=_D1, endpoint="GET /api/v1/admin/tier-policy")


@router.patch("/tier-policy")
async def update_tier_policy(request: Request, _admin: AdminUser) -> JSONResponse:
    return not_implemented(request, next_task=_D1, endpoint="PATCH /api/v1/admin/tier-policy")


# ---------------------------------------------------------------------------
# D0.5: alias CRUD proxy
# ---------------------------------------------------------------------------


class _FallbackEntry(BaseModel):
    """One ``fallback`` list entry on an alias write."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class AliasCreateRequest(BaseModel):
    """Request body for ``POST /api/v1/admin/aliases``."""

    name: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    fallback: list[_FallbackEntry] | None = None


class AliasUpdateRequest(BaseModel):
    """Request body for ``PATCH /api/v1/admin/aliases/{name}``."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    fallback: list[_FallbackEntry] | None = None


@router.get("/aliases")
async def list_aliases(
    _admin: AdminUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> dict[str, Any]:
    """List configured aliases via the gateway's admin surface."""

    return await gateway.list_aliases()


@router.get("/aliases/{name}")
async def get_alias(
    name: str,
    _admin: AdminUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> dict[str, Any]:
    """Return a single alias. 404 propagates from the gateway."""

    return await gateway.get_alias(name)


@router.post("/aliases", status_code=status.HTTP_201_CREATED)
async def create_alias(
    body: AliasCreateRequest,
    _admin: AdminUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> dict[str, Any]:
    """Create a new alias. 409 propagates from the gateway."""

    payload = body.model_dump(mode="json", exclude_none=True)
    return await gateway.create_alias(payload)


@router.patch("/aliases/{name}")
async def update_alias(
    name: str,
    body: AliasUpdateRequest,
    _admin: AdminUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> dict[str, Any]:
    """Update an existing alias. 404 propagates from the gateway."""

    payload = body.model_dump(mode="json", exclude_none=True)
    return await gateway.update_alias(name, payload)


@router.delete("/aliases/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_alias(
    name: str,
    _admin: AdminUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> JSONResponse:
    """Remove an alias. 404 propagates from the gateway."""

    await gateway.delete_alias(name)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


@router.get("/config")
async def get_admin_config(
    _admin: AdminUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> dict[str, Any]:
    """Return the gateway's sanitized current config (D0.5)."""

    return await gateway.get_admin_config()
