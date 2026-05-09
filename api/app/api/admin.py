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

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._stub import not_implemented
from app.api.dependencies import AdminUser
from app.clients.gateway import GatewayClient, get_gateway_client
from app.db.session import get_db
from app.models.audit import AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])

_D1 = "D1 — Tier-floor enforcement (refusals)"


# ---------------------------------------------------------------------------
# D3 — /admin/audit-log read endpoint with privilege/tier/date filtering.
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    """Wire shape for one audit_log row in the read endpoint response."""

    id: str
    timestamp: datetime
    user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    privilege_marked: bool
    privilege_basis: str | None
    routed_inference_tier: int | None
    routed_provider: str | None
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    details: dict[str, Any] | None


class AuditLogPage(BaseModel):
    """Paginated response for ``GET /api/v1/admin/audit-log``."""

    items: list[AuditLogEntry]
    next_cursor: str | None = None


# Default page size; matches the C3 chats listing pattern. Operators
# with heavy audit-log volumes can adjust via the ``limit`` query param
# up to AUDIT_LOG_PAGE_MAX.
AUDIT_LOG_PAGE_DEFAULT = 50
AUDIT_LOG_PAGE_MAX = 500


@router.get(
    "/audit-log",
    response_model=AuditLogPage,
    summary="List audit-log entries with privilege / tier filters (D3)",
)
async def get_audit_log(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    privilege_marked: Annotated[
        bool | None,
        Query(
            description=(
                "Filter to entries with the given privilege flag. Omit to "
                "return both privileged and non-privileged rows."
            ),
        ),
    ] = None,
    routed_inference_tier: Annotated[
        int | None,
        Query(
            ge=1,
            le=5,
            description=(
                "Filter to entries with the given routed inference tier "
                "(1-5). Omit to return all tiers (and non-inference entries)."
            ),
        ),
    ] = None,
    action: Annotated[
        str | None,
        Query(description="Exact-match filter on ``action`` (e.g., ``chat.message_sent``)."),
    ] = None,
    user_id: Annotated[
        str | None,
        Query(description="Filter to entries authored by the given user (UUID string)."),
    ] = None,
    since: Annotated[
        datetime | None,
        Query(description="ISO-8601 timestamp; only entries at or after this time."),
    ] = None,
    until: Annotated[
        datetime | None,
        Query(description="ISO-8601 timestamp; only entries at or before this time."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=AUDIT_LOG_PAGE_MAX,
            description=f"Page size (1-{AUDIT_LOG_PAGE_MAX}).",
        ),
    ] = AUDIT_LOG_PAGE_DEFAULT,
    cursor: Annotated[
        str | None,
        Query(
            description=(
                "Opaque pagination cursor (the previous page's "
                "``next_cursor``). Omit on the first page."
            ),
        ),
    ] = None,
) -> AuditLogPage:
    """GET /api/v1/admin/audit-log — admin-only read of the audit log.

    Filters compose with AND. The result is ordered by
    ``timestamp DESC`` (most recent first). Pagination is cursor-based
    against the timestamp+id pair, so concurrent inserts during a
    paginated walk don't shift the page boundaries.

    Privilege filter semantics: ``privilege_marked=true`` returns only
    privileged-project rows (per PRD §3.11 / D3 verification step);
    ``privilege_marked=false`` returns only non-privileged rows; omitting
    the parameter returns both.
    """

    stmt = select(AuditLog)

    if privilege_marked is not None:
        stmt = stmt.where(AuditLog.privilege_marked.is_(privilege_marked))
    if routed_inference_tier is not None:
        stmt = stmt.where(AuditLog.routed_inference_tier == routed_inference_tier)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if since is not None:
        stmt = stmt.where(AuditLog.timestamp >= since)
    if until is not None:
        stmt = stmt.where(AuditLog.timestamp <= until)

    if cursor is not None:
        # Cursor encodes (iso-timestamp)|(uuid). We split on the last
        # ``|`` to remain robust against ISO timestamps that contain
        # ``+``. Bad cursors fall through to the "no filter" branch
        # rather than 4xx-ing — the next page just starts from the top.
        try:
            cursor_ts_str, cursor_id = cursor.rsplit("|", 1)
            cursor_ts = datetime.fromisoformat(cursor_ts_str)
            stmt = stmt.where(
                (AuditLog.timestamp < cursor_ts)
                | ((AuditLog.timestamp == cursor_ts) & (AuditLog.id > cursor_id))
            )
        except (ValueError, TypeError):
            pass

    stmt = stmt.order_by(AuditLog.timestamp.desc(), AuditLog.id.asc()).limit(limit + 1)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = f"{last.timestamp.isoformat()}|{last.id}"

    items = [
        AuditLogEntry(
            id=str(r.id),
            timestamp=r.timestamp,
            user_id=str(r.user_id) if r.user_id else None,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            privilege_marked=r.privilege_marked,
            privilege_basis=r.privilege_basis,
            routed_inference_tier=r.routed_inference_tier,
            routed_provider=r.routed_provider,
            ip_address=str(r.ip_address) if r.ip_address else None,
            user_agent=r.user_agent,
            request_id=r.request_id,
            details=r.details,
        )
        for r in page_rows
    ]

    return AuditLogPage(items=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# Existing surface (A4 stubs not yet implemented)
# ---------------------------------------------------------------------------


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
