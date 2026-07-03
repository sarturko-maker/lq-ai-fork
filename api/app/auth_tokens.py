"""User-lifecycle token service — SETUP-3a (ADR-F061 D1/D2).

Issuance + single-use validation for the ``user_auth_tokens`` table (migration
0085). One table, two purposes: ``invite`` and ``password_reset``.

Token-at-rest discipline (ADR-F059 pattern):

* The opaque secret is ``secrets.token_urlsafe(32)`` (~256 bits) — not
  brute-forceable offline. It appears ONLY in the email link and (for invites)
  the invite-create response; it is NEVER logged or persisted in the clear.
* At rest we store ONLY the domain-separated HMAC-SHA256 hex digest
  (``token_hmac``). The index key is derived from ``jwt_secret`` with a
  distinct domain string PER PURPOSE, so an invite HMAC and a reset HMAC of the
  same plaintext differ and neither collides with the refresh-token index.
* Validation is one indexed equality plus ``SELECT ... FOR UPDATE``; single-use
  is an atomic ``consumed_at`` write under that row lock (the ``consumed_at IS
  NULL`` predicate is re-evaluated after a concurrent winner commits, so a
  parallel redeem of the same token yields exactly one winner — Postgres READ
  COMMITTED EvalPlanQual, same mechanism the refresh handler relies on).

The functions take the ``AsyncSession`` as an argument (injected by the caller,
matching :mod:`app.audit`); they flush but never commit — the caller's outer
transaction owns the boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user_auth_token import UserAuthToken

INVITE = "invite"
PASSWORD_RESET = "password_reset"

_TOKEN_BYTES = 32

# Domain-separation labels — distinct per purpose AND distinct from the
# refresh-token index (jwt.py's "lq-ai-refresh-token-index-v1"). Bump the
# version suffix to force a re-key of all outstanding tokens of that purpose.
_TOKEN_DOMAINS: dict[str, bytes] = {
    INVITE: b"lq-ai:invite-token:v1",
    PASSWORD_RESET: b"lq-ai:password-reset-token:v1",
}


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _index_key(purpose: str) -> bytes:
    """Derive the per-purpose HMAC index key from ``jwt_secret``.

    Domain-separated so the same secret's other HMAC/JWT uses stay distinct.
    Raises ``KeyError`` for an unknown purpose — a programming error, not user
    input (endpoints pass the module constants).
    """
    domain = _TOKEN_DOMAINS[purpose]
    settings = get_settings()
    return hmac.new(settings.jwt_secret.encode("utf-8"), domain, hashlib.sha256).digest()


def hash_auth_token(purpose: str, plaintext: str) -> str:
    """Deterministic HMAC-SHA256 hex verifier for a lifecycle-token plaintext.

    Same input + same ``jwt_secret`` + same purpose ⇒ same digest, so a redeem
    is one indexed equality lookup instead of a scan.
    """
    return hmac.new(_index_key(purpose), plaintext.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_token() -> str:
    """Mint a fresh opaque token secret (~256 bits, URL-safe)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


async def issue_invite(
    db: AsyncSession,
    *,
    email: str,
    role: str,
    created_by: uuid.UUID,
    ttl_seconds: int,
    now: datetime | None = None,
) -> tuple[str, UserAuthToken]:
    """Mint an invite token for ``email`` at ``role``.

    Returns ``(plaintext, row)``. The row carries only the HMAC. The caller is
    responsible for having revoked any prior active invite (see
    :func:`revoke_active_invites_for_email`) and for the 409 pre-check.
    """
    now = now or _utcnow()
    plaintext = generate_token()
    token = UserAuthToken(
        purpose=INVITE,
        email=email,
        role=role,
        token_hmac=hash_auth_token(INVITE, plaintext),
        created_by=created_by,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(token)
    await db.flush()
    return plaintext, token


async def issue_password_reset(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ttl_seconds: int,
    now: datetime | None = None,
) -> tuple[str, UserAuthToken]:
    """Mint a password-reset token for ``user_id``. Returns ``(plaintext, row)``.

    Mirrors the invite side (security review fix 2): any prior active reset
    token for the user is revoked FIRST, so at most one reset link is ever
    live — repeated requests within the TTL cannot accumulate up to the
    rate-limit's worth of concurrently-valid tokens.
    """
    now = now or _utcnow()
    await revoke_active_password_resets_for_user(db, user_id=user_id, now=now)
    plaintext = generate_token()
    token = UserAuthToken(
        purpose=PASSWORD_RESET,
        user_id=user_id,
        token_hmac=hash_auth_token(PASSWORD_RESET, plaintext),
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(token)
    await db.flush()
    return plaintext, token


async def revoke_active_password_resets_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Revoke every active password-reset token for ``user_id``; return the count.

    Parallels :func:`revoke_active_invites_for_email`. Called before issuing a
    new reset token (single-live-link invariant) and after a successful reset
    (belt-and-braces: no sibling token survives a completed reset).
    """
    now = now or _utcnow()
    result = await db.execute(
        update(UserAuthToken)
        .where(
            UserAuthToken.purpose == PASSWORD_RESET,
            UserAuthToken.user_id == user_id,
            UserAuthToken.consumed_at.is_(None),
            UserAuthToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.flush()
    return int(getattr(result, "rowcount", 0) or 0)


async def consume_token(
    db: AsyncSession,
    *,
    purpose: str,
    plaintext: str,
    now: datetime | None = None,
) -> UserAuthToken | None:
    """Atomically redeem a single-use token; return the row or ``None``.

    Returns ``None`` for an unknown / expired / already-consumed / revoked
    token (the caller maps all of these to ONE uniform 400 — no distinguishing
    signal). On success ``consumed_at`` is stamped inside the row lock so a
    concurrent redeem of the same token finds it consumed and gets ``None``.
    """
    now = now or _utcnow()
    token_hmac = hash_auth_token(purpose, plaintext)
    matched = (
        await db.execute(
            select(UserAuthToken)
            .where(
                UserAuthToken.token_hmac == token_hmac,
                UserAuthToken.purpose == purpose,
                UserAuthToken.consumed_at.is_(None),
                UserAuthToken.revoked_at.is_(None),
                UserAuthToken.expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if matched is None:
        return None

    # Belt-and-braces constant-time re-check (the SQL equality already matched;
    # guards any future collation surprise on the indexed column).
    if not hmac.compare_digest(matched.token_hmac, token_hmac):
        return None

    matched.consumed_at = now
    await db.flush()
    return matched


async def find_active_invite_for_email(
    db: AsyncSession,
    *,
    email: str,
    now: datetime | None = None,
) -> UserAuthToken | None:
    """Return an unexpired, unconsumed, unrevoked invite for ``email``, if any.

    Used by the invite-create 409 pre-check.
    """
    now = now or _utcnow()
    return (
        await db.execute(
            select(UserAuthToken)
            .where(
                UserAuthToken.purpose == INVITE,
                UserAuthToken.email == email,
                UserAuthToken.consumed_at.is_(None),
                UserAuthToken.revoked_at.is_(None),
                UserAuthToken.expires_at > now,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def revoke_active_invites_for_email(
    db: AsyncSession,
    *,
    email: str,
    now: datetime | None = None,
) -> int:
    """Revoke every active invite for ``email``; return the count revoked.

    Called by resend (revoke-then-reissue) so at most one invite is ever live.
    """
    now = now or _utcnow()
    result = await db.execute(
        update(UserAuthToken)
        .where(
            UserAuthToken.purpose == INVITE,
            UserAuthToken.email == email,
            UserAuthToken.consumed_at.is_(None),
            UserAuthToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.flush()
    # UPDATE returns a CursorResult (has rowcount); the static type is the base
    # Result, so read it defensively for the type checker.
    return int(getattr(result, "rowcount", 0) or 0)
