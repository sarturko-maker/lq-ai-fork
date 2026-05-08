"""Organization Profile endpoints — A4 scaffold.

The Organization Profile is a singleton skill at the deployment level.
GET / PUT land in Task D4 (Organization Profile singleton); they read
and write a single row in the skills table whose `scope` is `org`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/organization-profile", tags=["organization-profile"])

_D4 = "D4 — Organization Profile singleton"


@router.get("")
async def get_organization_profile(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D4, endpoint="GET /api/v1/organization-profile")


@router.put("")
async def update_organization_profile(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D4, endpoint="PUT /api/v1/organization-profile")
