"""Admin endpoints — A4 scaffold.

Audit-log query lands in Task D3 (Audit log: privilege fields). Tier-policy
GET / PUT lands in Task D1 (tier-floor enforcement) — the policy itself is
read by both the gateway (tier-derivation defaults) and the backend.

Note: the OpenAPI sketch declares `PUT /api/v1/admin/tier-policy`, while the
task description for A4 mentioned PATCH. The sketch is the source of truth
per CLAUDE.md decision routing, so we register PUT here.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/admin", tags=["admin"])

_D3 = "D3 — Audit log: privilege fields"
_D1 = "D1 — Tier-floor enforcement (refusals)"


@router.get("/audit-log")
async def get_audit_log(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D3, endpoint="GET /api/v1/admin/audit-log")


@router.get("/tier-policy")
async def get_tier_policy(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D1, endpoint="GET /api/v1/admin/tier-policy")


@router.put("/tier-policy")
async def update_tier_policy(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D1, endpoint="PUT /api/v1/admin/tier-policy")
