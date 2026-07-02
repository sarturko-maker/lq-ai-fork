"""JWT access tokens, refresh tokens, and MFA challenge tokens.

Token model (per ADR 0002 / PRD §5.1):

- **Access token** — short-lived JWT signed with HS256, ~15 min TTL. Carries
  `sub` (user id), `email`, `is_admin`, `iat`, `exp`. Stateless: never stored
  server-side; validated by signature and expiry on every request. Rotated
  by the refresh flow.

- **Refresh token** — long-lived (~7 days) opaque random string. The plaintext
  is returned to the client on login and refresh; a deterministic HMAC-SHA256
  verifier is stored in `user_sessions.refresh_token_hmac` (unique-indexed) so a
  database leak does not let an attacker re-authenticate, while the refresh
  lookup stays a single indexed query (ADR-F059). Rotated on each use.

- **MFA challenge token** — JWT with type=mfa, ~5 min TTL. Issued by
  `/auth/login` when the user has `mfa_enabled=true` and 423-ed back; D5
  consumes it at `/auth/mfa/verify` to mint the real access+refresh pair.

We use `pyjwt` (not python-jose). pyjwt is smaller, has fewer transitive
dependencies, and is the more actively maintained of the two. The crypto
backend ships via `pyjwt[crypto]`. We only use HS256 in v1 — a single
backend service signing tokens for itself does not need asymmetric keys.

The signing secret is `settings.jwt_secret`. Operators MUST override the
default in production; the dev default is intentionally obvious so it
trips review.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

# Algorithm pinned at the module level so a config drift can't accept
# unsigned (`alg: none`) tokens.
_JWT_ALGORITHM = "HS256"

# Type discriminator stamped into the `typ` claim of every JWT we mint
# so the decoder can refuse, e.g., an MFA token submitted as if it were
# an access token.
_TYPE_ACCESS = "access"
_TYPE_MFA = "mfa"
_TYPE_WOPI = "wopi"


@dataclass(frozen=True)
class AccessTokenClaims:
    """Claims extracted from a validated access token.

    Returned by `decode_access_token` on success. The handler turns
    `user_id` into a `User` row via the DB; the dataclass itself does
    not touch the database.
    """

    user_id: uuid.UUID
    email: str
    is_admin: bool
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class MfaTokenClaims:
    """Claims extracted from a validated MFA challenge token."""

    user_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class WopiTokenClaims:
    """Claims extracted from a validated WOPI editor-session token.

    The WOPI ``access_token`` (ADR-F047, libreoffice-editor Slice 2). It is a
    host-minted opaque string from Collabora's perspective; we make it a signed
    JWT scoped to a single ``(user, file)`` pair so the WOPI host can validate
    it without a server-side session table. ``file_id`` binds the token to one
    file so it cannot be replayed against another file (the handler asserts the
    claim equals the URL file id), and ``name`` carries the editing user's
    display name for the WOPI ``UserFriendlyName`` without a second DB query.
    """

    user_id: uuid.UUID
    file_id: uuid.UUID
    name: str
    issued_at: datetime
    expires_at: datetime


def _utcnow() -> datetime:
    """Current UTC time, with timezone — JWT's `iat`/`exp` are POSIX seconds."""
    return datetime.now(tz=UTC)


def create_access_token(user_id: uuid.UUID, email: str, *, is_admin: bool) -> str:
    """Mint a signed access-token JWT for `user_id`.

    Encodes `sub`, `email`, `is_admin`, `iat`, `exp`, and a `typ` claim so
    we can refuse, e.g., a refresh-context MFA token presented as an
    access token. Returns the encoded JWT as a UTF-8 string.
    """
    settings = get_settings()
    now = _utcnow()
    payload: dict[str, object] = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_access_token_ttl_seconds)).timestamp()),
        "typ": _TYPE_ACCESS,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims | None:
    """Decode and validate an access-token JWT.

    Returns the claims on success; returns `None` for any of:
    - bad signature
    - expired
    - malformed
    - missing required claim
    - wrong `typ` (e.g., an MFA token submitted as access)

    Returning None rather than raising gives the dependency a clean
    "401 Unauthorized" path without try/except plumbing in the handler.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    if payload.get("typ") != _TYPE_ACCESS:
        return None

    sub = payload.get("sub")
    email = payload.get("email")
    is_admin = payload.get("is_admin")
    iat = payload.get("iat")
    exp = payload.get("exp")
    if sub is None or email is None or is_admin is None or iat is None or exp is None:
        return None

    try:
        user_id = uuid.UUID(str(sub))
    except (TypeError, ValueError):
        return None

    return AccessTokenClaims(
        user_id=user_id,
        email=str(email),
        is_admin=bool(is_admin),
        issued_at=datetime.fromtimestamp(int(iat), tz=UTC),
        expires_at=datetime.fromtimestamp(int(exp), tz=UTC),
    )


def create_mfa_token(user_id: uuid.UUID) -> str:
    """Mint a signed MFA challenge token (issued by /auth/login on 423).

    The token's only payload is the user id and a short TTL. D5's
    /auth/mfa/verify consumes it; if it expires before the user submits
    a TOTP code, the user re-enters credentials at /auth/login.
    """
    settings = get_settings()
    now = _utcnow()
    payload: dict[str, object] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.mfa_token_ttl_seconds)).timestamp()),
        "typ": _TYPE_MFA,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_mfa_token(token: str) -> MfaTokenClaims | None:
    """Decode and validate an MFA challenge token. Counterpart to `create_mfa_token`."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    if payload.get("typ") != _TYPE_MFA:
        return None

    sub = payload.get("sub")
    iat = payload.get("iat")
    exp = payload.get("exp")
    if sub is None or iat is None or exp is None:
        return None

    try:
        user_id = uuid.UUID(str(sub))
    except (TypeError, ValueError):
        return None

    return MfaTokenClaims(
        user_id=user_id,
        issued_at=datetime.fromtimestamp(int(iat), tz=UTC),
        expires_at=datetime.fromtimestamp(int(exp), tz=UTC),
    )


def create_wopi_token(user_id: uuid.UUID, file_id: uuid.UUID, *, name: str) -> str:
    """Mint a signed WOPI editor-session token for ``(user_id, file_id)``.

    Scoped to a single file: the WOPI host (``app.api.wopi``) asserts the ``fid``
    claim equals the URL file id, so a token minted for one file cannot open
    another even for the same user. ``name`` is the editing user's display name,
    surfaced as the WOPI ``UserFriendlyName``. TTL is ``wopi_token_ttl_seconds``.
    """
    settings = get_settings()
    now = _utcnow()
    payload: dict[str, object] = {
        "sub": str(user_id),
        "fid": str(file_id),
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.wopi_token_ttl_seconds)).timestamp()),
        "typ": _TYPE_WOPI,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_wopi_token(token: str) -> WopiTokenClaims | None:
    """Decode and validate a WOPI editor-session token.

    Returns the claims on success; ``None`` for a bad signature, expiry,
    malformed payload, missing claim, or wrong ``typ`` (so an access/MFA token
    can never be presented as a WOPI token). The caller maps ``None`` to 401.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    if payload.get("typ") != _TYPE_WOPI:
        return None

    sub = payload.get("sub")
    fid = payload.get("fid")
    name = payload.get("name")
    iat = payload.get("iat")
    exp = payload.get("exp")
    if sub is None or fid is None or name is None or iat is None or exp is None:
        return None

    try:
        user_id = uuid.UUID(str(sub))
        file_id = uuid.UUID(str(fid))
    except (TypeError, ValueError):
        return None

    return WopiTokenClaims(
        user_id=user_id,
        file_id=file_id,
        name=str(name),
        issued_at=datetime.fromtimestamp(int(iat), tz=UTC),
        expires_at=datetime.fromtimestamp(int(exp), tz=UTC),
    )


# ---------------------------------------------------------------------------
# Refresh tokens  (ADR-F059 — deterministic HMAC index, replaces the bcrypt scan)
#
# Per PRD §5.1 / ADR 0002, refresh tokens are opaque random strings — not JWTs.
# The plaintext goes to the client; we store only a verifier in user_sessions.
#
# We store a deterministic HMAC-SHA256, NOT a per-row bcrypt hash. Rationale
# (ADR-F059): the token is 32 bytes of CSPRNG output (~256 bits), so it is
# NOT brute-forceable offline — bcrypt's per-row salt bought nothing here except
# a CPU-DoS: /auth/refresh cannot attribute a presented token to a user before
# matching, so a bcrypt-per-row verifier forced a scan over EVERY active session
# (unindexable by a salted hash) with one bcrypt compare each — tens of seconds
# under accumulated sessions, and a bad-token flood amplifier. A deterministic
# HMAC over a high-entropy secret is a sufficient at-rest verifier and turns the
# lookup into ONE indexed equality query. bcrypt remains for PASSWORDS (low
# entropy — where its slowness is the point).
#
# The index key is DERIVED from jwt_secret (no new secret to provision) with a
# domain-separation constant so it is distinct from the JWT signing use of the
# same secret:
#   index_key = HMAC-SHA256(jwt_secret, "lq-ai-refresh-token-index-v1")
#   token_hmac = HMAC-SHA256(index_key, token)
# Rotating jwt_secret invalidates all stored verifiers (every session must
# re-login) — acceptable and the same blast radius as rotating the signing key.
# ---------------------------------------------------------------------------

_REFRESH_TOKEN_BYTES = 32

# Domain-separation label: keeps the derived refresh-index key distinct from any
# other HMAC use of jwt_secret. Bump the version suffix to force a re-key.
_REFRESH_INDEX_DOMAIN = b"lq-ai-refresh-token-index-v1"


def create_refresh_token() -> tuple[str, str]:
    """Mint a fresh refresh token.

    Returns ``(plaintext, token_hmac)``. The plaintext goes to the client
    (transported over TLS); the ``token_hmac`` hex digest goes into
    ``user_sessions.refresh_token_hmac`` (unique-indexed). The plaintext is
    never logged or persisted by the backend.
    """
    plaintext = secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)
    return plaintext, hmac_refresh_token(plaintext)


def _refresh_index_key() -> bytes:
    """Derive the refresh-token index key from ``jwt_secret`` (domain-separated)."""
    settings = get_settings()
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        _REFRESH_INDEX_DOMAIN,
        hashlib.sha256,
    ).digest()


def hmac_refresh_token(plaintext: str) -> str:
    """Deterministic HMAC-SHA256 verifier for a refresh-token plaintext.

    Same input + same ``jwt_secret`` always yields the same hex digest, so the
    refresh handler can look a session up by an indexed equality on this column
    instead of scanning + bcrypt-comparing every active session.
    """
    return hmac.new(_refresh_index_key(), plaintext.encode("utf-8"), hashlib.sha256).hexdigest()
