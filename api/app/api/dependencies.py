"""FastAPI dependencies for authenticated endpoints.

`get_current_user` is the canonical dependency for any handler that needs
"the calling user." It:

1. Pulls the bearer token from the `Authorization` header.
2. Decodes and validates the JWT (signature + expiry + type).
3. Looks up the user in the DB.
4. Raises 401 with a `WWW-Authenticate: Bearer` header for any of the above
   failing — matching the OpenAPI sketch's documented 401 contract and
   RFC 6750's bearer-token error response shape.

A separate `require_admin` would build on this; that lives wherever it is
first needed (admin endpoints land later — see C7, D3, D4, D5, D6, D7).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.errors import PasswordChangeRequired
from app.models.user import User
from app.security.jwt import decode_access_token

# tokenUrl is the documented login endpoint (per the OpenAPI sketch).
# auto_error=True so a missing Authorization header raises 401 directly;
# we don't rely on the handler to recheck.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)


def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    """Build the canonical 401 with the WWW-Authenticate header per RFC 6750."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the calling user from the bearer token.

    Raises 401 on:
    - missing or malformed Authorization header (handled by oauth2_scheme)
    - bad signature, expired, or wrong-type JWT
    - user id in JWT does not exist in the DB
    - user has been soft-deleted (`deleted_at IS NOT NULL`)
    """
    claims = decode_access_token(token)
    if claims is None:
        raise _unauthorized()

    result = await db.execute(select(User).where(User.id == claims.user_id))
    user = result.scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise _unauthorized()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
"""Type alias so handlers can write `user: CurrentUser` rather than
unpacking the Depends() each time."""


async def get_active_user(user: CurrentUser) -> User:
    """`CurrentUser` plus the must-change-password gate.

    Used by every authenticated endpoint EXCEPT the small set the user is
    allowed to call before completing a forced password change:

    - `GET  /api/v1/users/me`     — so the client can read the flag
    - `POST /api/v1/auth/change-password` — to actually clear the flag
    - `POST /api/v1/auth/logout`  — to walk away without changing it

    Anything else returns 403 with `error.code = "password_change_required"`,
    instructing the client to redirect to the change-password flow. This
    is the gate that enforces "can't use API beyond the change endpoint
    until password is changed" per Task B2's verification criteria.
    """
    if user.must_change_password:
        raise PasswordChangeRequired(
            message=(
                "You must change your password before using the API. "
                "POST /api/v1/auth/change-password to set a new password."
            ),
        )
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]
"""Type alias for endpoints that require both a valid bearer token AND a
user who has cleared the must_change_password gate."""
