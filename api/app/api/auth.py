"""Auth endpoints — Task B1.

Per ADR 0002 (Backend owns authentication) and `backend-openapi.yaml`,
the backend exposes:

- `POST /api/v1/auth/login`    — username/password → JWT access + refresh.
                                  423 + mfa_token when the user has MFA enabled.
- `POST /api/v1/auth/refresh`  — refresh-token → new access + rotated refresh.
- `POST /api/v1/auth/logout`   — bearer token → revoke ALL active sessions
                                  for the calling user. Returns 204.
- `POST /api/v1/auth/mfa/setup`  — TOTP enrollment. **501 until D5.**
- `POST /api/v1/auth/mfa/verify` — TOTP verification. **501 until D5.**

Refresh tokens are opaque random strings (not JWTs) — only their bcrypt
hashes are persisted to `user_sessions`. Refresh rotates the token: the
old session row is marked revoked and a new row is inserted with the
new hash. This shrinks the post-compromise window if a refresh token
leaks (compromised → first-use detection works because the second use
finds a revoked session and 401s).

Every wrong-credentials response is a generic 401 with no detail about
which leg failed (email vs password). Per OWASP authentication guidance,
we don't reveal whether an email exists in the system.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._stub import not_implemented
from app.api.dependencies import CurrentUser
from app.config import get_settings
from app.db.session import get_db
from app.models.user import User, UserSession
from app.security import (
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    hash_password,
    refresh_token_matches,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_D5 = "D5 — MFA enrollment + verification"


# ---------------------------------------------------------------------------
# Request / response models — shapes match docs/api/backend-openapi.yaml.
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """`LoginRequest` schema from backend-openapi.yaml."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    """`/auth/refresh` body per backend-openapi.yaml."""

    refresh_token: str = Field(min_length=1)


class UserPublic(BaseModel):
    """`User` schema from backend-openapi.yaml.

    Mirrors the OpenAPI `User`. We lift this into a Pydantic model rather
    than serializing the ORM row directly so the API surface is decoupled
    from the storage shape — adding a column to `users` won't accidentally
    leak it to the client.
    """

    id: str
    email: str
    display_name: str | None = None
    is_admin: bool
    mfa_enabled: bool
    must_change_password: bool = False
    created_at: datetime
    last_login_at: datetime | None = None

    @classmethod
    def from_user(cls, user: User) -> UserPublic:
        return cls(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
            mfa_enabled=user.mfa_enabled,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class LoginResponse(BaseModel):
    """`LoginResponse` schema from backend-openapi.yaml."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    user: UserPublic


class TokenResponse(BaseModel):
    """`TokenResponse` schema from backend-openapi.yaml.

    NOTE: the OpenAPI sketch's `TokenResponse` does not include `refresh_token`.
    PRD §5.1 mandates that refresh tokens are rotated on each refresh — and a
    rotated token must be returned to the client or the client cannot use the
    new session. We therefore extend `TokenResponse` with `refresh_token`,
    additive to the OpenAPI sketch (existing fields are unchanged). This drift
    is flagged in the B1 task report so the OpenAPI sketch can be corrected.
    """

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str


class MfaChallenge(BaseModel):
    """`MfaChallenge` schema from backend-openapi.yaml."""

    mfa_token: str
    methods: list[str]


class ChangePasswordRequest(BaseModel):
    """`ChangePasswordRequest` schema from backend-openapi.yaml.

    Both the current (last-known) password and the new password are
    required. The current password gates the change so a stolen access
    token alone cannot rotate credentials — see PRD §5.1.
    """

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    """Return `(user_agent, ip_address)` for the session row, both nullable.

    `user_agent` comes straight off the User-Agent header.
    `ip_address` honors `X-Forwarded-For` only if the request reached us
    through a trusted proxy — we conservatively use the immediate client
    IP from `request.client` for now and let an operator front the
    deployment with a reverse proxy that sets the column itself if they
    want X-Forwarded-For semantics. (Future: trusted-proxy config.)
    """
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


async def _create_session(
    db: AsyncSession,
    user: User,
    request: Request,
) -> tuple[str, UserSession]:
    """Mint and persist a new refresh-token session.

    Returns (plaintext_refresh_token, the inserted UserSession row).
    The plaintext is for the response body; the row carries the hash.
    """
    settings = get_settings()
    plaintext, hashed = create_refresh_token()
    user_agent, ip_address = _client_metadata(request)

    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hashed,
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=_utcnow() + timedelta(seconds=settings.jwt_refresh_token_ttl_seconds),
    )
    db.add(session)
    await db.flush()
    return plaintext, session


def _login_response(user: User, refresh_token: str) -> LoginResponse:
    """Build the LoginResponse for a successful login or refresh-with-user."""
    settings = get_settings()
    access_token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.jwt_access_token_ttl_seconds,
        refresh_token=refresh_token,
        user=UserPublic.from_user(user),
    )


# ---------------------------------------------------------------------------
# Endpoints.
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=None,  # union return type; FastAPI handles via `Response`
    status_code=status.HTTP_200_OK,
    summary="Authenticate with email and password",
    responses={
        200: {"model": LoginResponse},
        401: {"description": "Invalid credentials"},
        423: {"model": MfaChallenge, "description": "MFA required"},
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """POST /api/v1/auth/login — see backend-openapi.yaml."""
    # Look up the user. Email column is CITEXT so case is irrelevant.
    # `deleted_at IS NOT NULL` users are treated as non-existent.
    result = await db.execute(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # Generic 401 whether the user is missing or the password is wrong;
    # we do NOT reveal which leg failed. Still call verify_password on a
    # dummy hash to keep timing roughly equal between "no such user" and
    # "wrong password" branches — this is best-effort, not constant-time.
    if user is None:
        # Hash a constant-length string to consume comparable wall time.
        verify_password(payload.password, "$2b$12$" + "x" * 53)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # MFA branch: issue a short-lived challenge token; the client redeems
    # it at /auth/mfa/verify (D5). No session is created here — the user
    # has not yet completed authentication.
    if user.mfa_enabled:
        mfa_token = create_mfa_token(user.id)
        challenge = MfaChallenge(mfa_token=mfa_token, methods=["totp", "recovery_code"])
        return JSONResponse(
            status_code=status.HTTP_423_LOCKED,
            content=challenge.model_dump(),
        )

    # Happy path. Create a session, stamp last_login_at, return tokens.
    plaintext, _session = await _create_session(db, user, request)
    user.last_login_at = _utcnow()
    await db.commit()

    body = _login_response(user, plaintext)
    return JSONResponse(status_code=status.HTTP_200_OK, content=body.model_dump(mode="json"))


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token using refresh token",
    responses={
        200: {"model": TokenResponse},
        401: {"description": "Invalid, expired, or revoked refresh token"},
    },
)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """POST /api/v1/auth/refresh — rotate the refresh token, mint a new access token."""
    settings = get_settings()
    now = _utcnow()

    # Find the active session whose stored hash matches the presented token.
    # We can't index-lookup by hash (bcrypt salt is per-row), so we scan
    # active sessions and bcrypt-compare each. In v1 the active-session
    # count per user is tiny (a few devices); if this becomes hot, switch
    # to a deterministic HMAC index column. Tracked as DE candidate.
    result = await db.execute(
        select(UserSession).where(
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    candidates = result.scalars().all()

    matched: UserSession | None = None
    for session in candidates:
        if refresh_token_matches(payload.refresh_token, session.refresh_token_hash):
            matched = session
            break

    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Look up the owning user; if missing or soft-deleted, refuse.
    user_result = await db.execute(
        select(User).where(User.id == matched.user_id, User.deleted_at.is_(None))
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Rotate: revoke this session, mint a fresh one. Both happen in the
    # same transaction so a crash mid-way doesn't leave the user with an
    # active old session and no new one (or two active sessions).
    matched.revoked_at = now
    plaintext, _new_session = await _create_session(db, user, request)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, is_admin=user.is_admin),
        token_type="Bearer",
        expires_in=settings.jwt_access_token_ttl_seconds,
        refresh_token=plaintext,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke all active sessions for the calling user",
)
async def logout(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """POST /api/v1/auth/logout — bearer-authenticated.

    Revokes ALL active sessions for the calling user (conservative — see
    PRD §5.1; per-session logout can be added later if a use case
    materializes). The access token itself is stateless and remains valid
    until its TTL expires; clients are expected to discard it on logout.
    """
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# /auth/change-password — set a new password for the calling user.
# ---------------------------------------------------------------------------


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the calling user's password",
    responses={
        204: {"description": "Password changed successfully"},
        400: {"description": "New password fails policy check"},
        401: {"description": "Current password is wrong"},
    },
)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """POST /api/v1/auth/change-password.

    Bearer-authenticated; the bearer token's user is the one whose password
    is being changed. The current password is required (defense against
    a stolen access token; an attacker who only has the token cannot
    rotate the credentials underneath the legitimate user).

    Behavior:
    - Verifies `current_password` against the stored hash.
    - Validates `new_password` against the configured minimum length and
      "must differ from current" policy.
    - Hashes and stores the new password.
    - Clears `must_change_password` (the first-run forced-change flag).
    - Revokes ALL active sessions for the user — the caller must log in
      again with the new password. This is intentional: it invalidates
      any session that may have been spawned with the old credential.

    Returns 204 on success, 401 on wrong current password, 400 on policy
    violation. The response body for 400 names the violated rule so the
    UI can render a usable message.
    """
    settings = get_settings()

    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    new_password = payload.new_password
    if len(new_password) < settings.password_min_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"New password must be at least {settings.password_min_length} characters."),
        )

    if new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password.",
        )

    # Hash and persist. Clear the forced-change flag in the same transaction
    # so a crash mid-way doesn't leave the user in an inconsistent state.
    user.hashed_password = hash_password(new_password)
    user.must_change_password = False

    # Revoke all active sessions — the user must re-authenticate. This is
    # the same pattern as /auth/logout; we don't reuse the handler so the
    # behavior is explicit.
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# MFA stubs — D5 territory. The shapes are pinned by backend-openapi.yaml;
# we keep them returning the canonical 501 body so clients can detect that
# the surface exists but is not yet wired.
# ---------------------------------------------------------------------------


@router.post("/mfa/setup")
async def mfa_setup(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D5, endpoint="POST /api/v1/auth/mfa/setup")


@router.post("/mfa/verify")
async def mfa_verify(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D5, endpoint="POST /api/v1/auth/mfa/verify")
