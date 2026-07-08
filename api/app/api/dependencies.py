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

import logging
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import InternalError, PasswordChangeRequired, Unauthorized
from app.models.user import User
from app.security.jwt import decode_access_token

log = logging.getLogger(__name__)

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
    # SETUP-3a (ADR-F061 D5) — a disabled account's live access tokens die on
    # the next request: disable stamps ``disabled_at`` and revokes sessions, but
    # an already-issued (stateless) access token is only killed by this check.
    if user is None or user.deleted_at is not None or user.disabled_at is not None:
        raise _unauthorized()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
"""Type alias so handlers can write `user: CurrentUser` rather than
unpacking the Depends() each time."""


async def get_active_user(user: CurrentUser) -> User:
    """`CurrentUser` plus the must-change-password gate and the
    MFA-mandatory gate.

    Used by every authenticated endpoint EXCEPT the small set the user is
    allowed to call before completing a forced password change:

    - `GET  /api/v1/users/me`     — so the client can read the flag
    - `POST /api/v1/auth/change-password` — to actually clear the flag
    - `POST /api/v1/auth/logout`  — to walk away without changing it

    Anything else returns 403 with `error.code = "password_change_required"`,
    instructing the client to redirect to the change-password flow. This
    is the gate that enforces "can't use API beyond the change endpoint
    until password is changed" per Task B2's verification criteria.

    M-Sec.1 — when the deployment has ``LQ_AI_MFA_MANDATORY=true`` and
    the user has not yet enrolled MFA, this dependency raises
    :class:`MfaEnrollmentRequired` (403, ``code='mfa_enrollment_required'``).
    The whitelist endpoints (``/auth/mfa/setup``, ``/auth/mfa/enable``,
    ``/auth/logout``, ``/users/me``) keep using :data:`CurrentUser`
    directly so the user can complete enrollment.
    """
    if user.must_change_password:
        raise PasswordChangeRequired(
            message=(
                "You must change your password before using the API. "
                "POST /api/v1/auth/change-password to set a new password."
            ),
        )

    # M-Sec.1: mandatory-MFA deployment flag. The check fires AFTER
    # password-change so an admin onboarding a brand-new user with a
    # temporary password walks through password rotation first, MFA
    # second.
    from app.config import get_settings
    from app.errors import MfaEnrollmentRequired

    settings = get_settings()
    if settings.mfa_mandatory and not user.mfa_enabled:
        raise MfaEnrollmentRequired(
            message=(
                "This deployment requires MFA enrollment. "
                "POST /api/v1/auth/mfa/setup to begin enrollment."
            ),
        )
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]
"""Type alias for endpoints that require both a valid bearer token AND a
user who has cleared the must_change_password gate."""


async def get_admin_user(user: ActiveUser) -> User:
    """`ActiveUser` plus the ``is_admin == True`` gate.

    Used by every admin-only endpoint (D0.5 alias-CRUD; D3 audit-log;
    D1 tier-policy; future D-phase admin surfaces). Non-admin authenticated
    users get 403 ``forbidden``; admins pass through.

    The 403 carries ``code = "forbidden"`` (not ``unauthorized``) — the
    user *is* authenticated, they're just not authorized for this
    surface. The OpenAPI sketch documents this distinction.
    """

    if not user.is_admin:
        from app.errors import Forbidden

        raise Forbidden(
            message="Admin privileges required for this endpoint.",
        )
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]
"""Type alias for endpoints that require ``is_admin = true``. Stacks on
top of :data:`ActiveUser` (so it inherits the bearer-token + must-change-
password gate) and adds the admin check."""


async def get_operator_user(user: ActiveUser) -> User:
    """`ActiveUser` plus the ``role == 'operator'`` gate — SETUP-3a (ADR-F061 D4).

    The OPERATOR fence. The platform operator owns the gateway-proxy surfaces
    (model aliases, provider keys, gateway config, tier-policy writes,
    tier-floor override) — concerns that reach the gateway's key-holding
    egress, not a tenant's data. These are reclassified off :data:`AdminUser`
    onto this dependency so an org-admin (a customer) cannot touch them.

    Mirrors :func:`get_admin_user`: an authenticated NON-operator gets 403
    ``forbidden`` (they *are* authenticated, just not authorized here — a 403,
    not a 404; the fence is not an existence secret). The operator role is
    bootstrap-only and carries ``is_admin=true``, so an operator ALSO passes
    every :data:`AdminUser` surface (org-admin ⊂ operator).
    """

    if getattr(user, "role", "member") != "operator":
        from app.errors import Forbidden

        raise Forbidden(
            message="Operator (platform) privileges required for this endpoint.",
        )
    return user


OperatorUser = Annotated[User, Depends(get_operator_user)]
"""Type alias for the operator fence (ADR-F061 D4). Stacks on
:data:`ActiveUser` and requires ``role == 'operator'``. Applied to the
gateway-proxy admin surfaces so only the platform operator — never a tenant's
org-admin — can reach them."""


def tenant_admin_visibility(user: User) -> bool:
    """Whether ``user`` may see/act on OTHER users' tenant data — SETUP-5b
    (ADR-F064 D2). This governs the pre-F061 "admin-sees-all" business-logic
    bypass, NOT a dependency gate.

    Several pre-operator tenant-data endpoints widen an owner filter for
    ``is_admin`` so a single company's admin sees every user's matters / playbooks
    / tabular runs. ADR-F061 D3 made the platform ``operator`` an ``is_admin``
    superset, which silently handed it that cross-user visibility too. This
    helper narrows the bypass to a *tenant* admin: the org-admin keeps
    admin-sees-all; the ``operator`` is excluded and falls back to owner-scoped
    (member-like) access on tenant data.

    The rationale is separation of duties — platform operations vs. the company's
    legal matters. Mode-neutral (ADR-F058: three delivery modes): the operator
    is "whoever runs the platform" — a hosting company in Mode 2 (hosted SaaS)
    or the company's OWN IT in self-host Mode 1. Minting an operator is OPTIONAL
    (``FIRST_RUN_OPERATOR_EMAIL``); a self-hoster that skips it has no operator
    row and org-admins keep admin-sees-all unchanged, so the operator /
    no-operator choice IS the separation-of-duties dial. This touches only the
    cross-user *visibility* seams: the operator keeps every OperatorUser fence
    surface, every AdminUser admin surface, and normal member-like access to
    the rows it owns.
    """

    return user.is_admin and user.role != "operator"


# PRD §5.2 RBAC three-role system (Wave C); ``operator`` added SETUP-5b
# (ADR-F064 D1). ``viewer`` users can read resources they own but cannot
# mutate; ``admin``, ``member`` AND ``operator`` may all mutate. ``operator``
# is included because the platform operator owns its OWN rows (test matters,
# chats, runs) and mutates them member-like — ADR-F064 D2 removes only the
# operator's CROSS-USER tenant-data visibility (a business-logic seam), never
# its ability to act on rows it owns. Backed by ``users.role`` (migrations
# 0017/0085) with a server-default of ``member`` so existing rows + new
# signups inherit mutating access without explicit promotion.
_MUTATING_ROLES = frozenset({"admin", "member", "operator"})


async def get_mutating_user(user: ActiveUser) -> User:
    """``ActiveUser`` plus a role check that excludes ``viewer``.

    SETUP-5b (ADR-F064 D1). Applied to every tenant-data state-changing
    endpoint (POST/PATCH/PUT/DELETE on owned resources) so a ``viewer``
    login is an ENFORCED read-only account (auditors / observers), not just
    a label. Read-only endpoints (GET), self-service ``/auth`` + ``/users/me``
    routes, and service-to-service surfaces keep their own gate — the full
    map is the drift-guard allowlist in ``tests/test_mutation_rbac.py``.

    Returns 403 with ``code='forbidden'`` and a body naming the role
    requirement so a CLI / UI can render a useful message. The 403 fires on
    the CALLER'S OWN role BEFORE any resource lookup, so it never leaks a
    resource's existence — cross-user access stays 404 in the handler body.
    """

    if getattr(user, "role", "member") not in _MUTATING_ROLES:
        from app.errors import Forbidden

        raise Forbidden(
            message=(
                "This endpoint requires a member, admin, or operator role; "
                "viewer-role users have read-only access."
            ),
            details={"role": user.role, "required_roles": sorted(_MUTATING_ROLES)},
        )
    return user


MutatingUser = Annotated[User, Depends(get_mutating_user)]
"""Type alias for endpoints that must reject ``viewer`` users.

State-changing handlers (POST/PATCH/DELETE) on owned resources use
this in place of ``ActiveUser`` so the role gate fires before any
business logic runs. Admin-only endpoints continue to use
``AdminUser``; pure-read endpoints stay on ``ActiveUser``.
"""


async def get_autonomous_enabled_user(user: MutatingUser) -> User:
    """`MutatingUser` plus the per-user Autonomous Layer opt-in gate.

    The /autonomous/* mutate surface requires the user to have opted in
    (PRD §3.10, off by default). Read endpoints intentionally stay on plain
    `ActiveUser` so a user who opts out never loses access to the audit
    trail of what already ran (M4-C2 opt-out split; halt is a mutation and
    carries :data:`MutatingUser` directly).

    SETUP-5b §E (ADR-F064 D1): stacks on :data:`MutatingUser` (not
    :data:`ActiveUser`) so BOTH checks hold on every autonomous mutation —
    the viewer role gate fires first (403, role), then the opt-in flag
    (403, autonomous). This is an API-edge authz fix, not an extension of
    the frozen legacy executor.
    """
    if not user.autonomous_enabled:
        from app.errors import Forbidden

        raise Forbidden(
            message="Autonomous Layer is not enabled for this user.",
        )
    return user


AutonomousEnabledUser = Annotated[User, Depends(get_autonomous_enabled_user)]
"""Type alias for /autonomous mutate endpoints that require the per-user
opt-in flag (``autonomous_enabled = true``). Stacks on :data:`MutatingUser`
(bearer-token + must-change-password + viewer-excluding role gate,
ADR-F064 D1 §E) and adds the autonomous opt-in check. Read endpoints stay
on :data:`ActiveUser` per the M4-C2 opt-out split."""


# ---------------------------------------------------------------------------
# M3-D1 / M3-D3 — bridge bearer auth (service-to-service, no user)
# ---------------------------------------------------------------------------


def require_bridge_auth(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """Constant-time match the ``Authorization: Bearer …`` token against
    :envvar:`LQ_AI_BRIDGE_TOKEN`.

    Shared by every bridge → api persistence endpoint
    (`/api/v1/integrations/slack/workspaces`,
    `/api/v1/integrations/teams/tenants`, future bridges) because all
    bridges authenticate to the api with the same shared secret per
    M3-D1 decision #3.

    Raises:
      * :class:`InternalError` (500) when ``LQ_AI_BRIDGE_TOKEN`` is
        unset on the api — accepting bridge traffic with no enforced
        secret would silently break the trust contract.
      * :class:`Unauthorized` (401) on missing, malformed, or
        non-matching bearer.
    """

    expected = settings.lq_ai_bridge_token
    if not expected:
        log.error(
            "LQ_AI_BRIDGE_TOKEN is not set on the api/ service; refusing "
            "bridge traffic. Set the env var and restart."
        )
        raise InternalError(
            message=(
                "Bridge authentication is not configured on the backend. "
                "Operator must set LQ_AI_BRIDGE_TOKEN."
            ),
        )

    presented = ""
    if authorization and authorization.startswith("Bearer "):
        presented = authorization[len("Bearer ") :].strip()

    if not presented or not secrets.compare_digest(presented, expected):
        raise Unauthorized(
            message="Invalid or missing bridge bearer token.",
            details={"header": "Authorization"},
        )
