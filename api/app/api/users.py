"""Users endpoints — A4 scaffold.

`/users/me` lands in B1 (current-user lookup uses the access token).
`/users/me/export` and `/users/me/delete` are GDPR Articles 20 and 17;
they land in D6.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/users", tags=["users"])

_B1 = "B1 — User model + auth endpoints (backend)"
_D6 = "D6 — Per-user export and delete (GDPR Articles 17 and 20)"


@router.get("/me")
async def get_me(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_B1, endpoint="GET /api/v1/users/me")


@router.post("/me/export")
async def export_me(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D6, endpoint="POST /api/v1/users/me/export")


@router.post("/me/delete")
async def delete_me(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D6, endpoint="POST /api/v1/users/me/delete")
