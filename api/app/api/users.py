"""Users endpoints.

`/users/me` lands in B1. Returns the calling user's public profile per the
`User` schema in backend-openapi.yaml. Per Task B2, the `User` payload
includes `must_change_password` so a client can detect that the user is
in the forced-change state without first hitting a 403.

`/users/me/export` (GDPR Article 20) and `/users/me/delete` (GDPR
Article 17) land in D6 — they remain 501 stubs but are guarded by the
must_change_password gate (`ActiveUser` dependency) so they refuse 403
while the calling user has not cleared the gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented
from app.api.auth import UserPublic
from app.api.dependencies import CurrentUser, get_active_user

router = APIRouter(prefix="/users", tags=["users"])

_D6 = "D6 — Per-user export and delete (GDPR Articles 17 and 20)"


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get current user",
)
async def get_me(user: CurrentUser) -> UserPublic:
    """GET /api/v1/users/me — return the calling user's public profile.

    Reachable while `must_change_password=true` so the client can read the
    flag and route to the change-password flow. Other authenticated
    endpoints are gated until the user clears it.
    """
    return UserPublic.from_user(user)


@router.post("/me/export", dependencies=[Depends(get_active_user)])
async def export_me(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D6, endpoint="POST /api/v1/users/me/export")


@router.post("/me/delete", dependencies=[Depends(get_active_user)])
async def delete_me(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D6, endpoint="POST /api/v1/users/me/delete")
