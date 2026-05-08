"""Users endpoints.

`/users/me` lands in B1 (this task). Returns the calling user's public
profile per the `User` schema in backend-openapi.yaml.

`/users/me/export` (GDPR Article 20) and `/users/me/delete` (GDPR
Article 17) land in D6 — they remain 501 stubs.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented
from app.api.auth import UserPublic
from app.api.dependencies import CurrentUser

router = APIRouter(prefix="/users", tags=["users"])

_D6 = "D6 — Per-user export and delete (GDPR Articles 17 and 20)"


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get current user",
)
async def get_me(user: CurrentUser) -> UserPublic:
    """GET /api/v1/users/me — return the calling user's public profile."""
    return UserPublic.from_user(user)


@router.post("/me/export")
async def export_me(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D6, endpoint="POST /api/v1/users/me/export")


@router.post("/me/delete")
async def delete_me(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D6, endpoint="POST /api/v1/users/me/delete")
