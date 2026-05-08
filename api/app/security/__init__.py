"""Security primitives — password hashing and JWT token operations.

Per ADR 0002 (Backend owns authentication), the FastAPI backend is the sole
custodian of user credentials and session tokens. This package collects the
low-level primitives:

- `passwords` — bcrypt hash and verify, used by login and (in B2) first-run
  admin creation.
- `jwt` — JWT access tokens (short-lived, stateless) and refresh tokens
  (long-lived, hashed at rest in `user_sessions`).

The HTTP handlers live in `app.api.auth`; this package only deals with
crypto and serialization.
"""

from app.security.jwt import (
    AccessTokenClaims,
    MfaTokenClaims,
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    decode_access_token,
    decode_mfa_token,
    hash_refresh_token,
    refresh_token_matches,
)
from app.security.passwords import hash_password, verify_password

__all__ = [
    "AccessTokenClaims",
    "MfaTokenClaims",
    "create_access_token",
    "create_mfa_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_mfa_token",
    "hash_password",
    "hash_refresh_token",
    "refresh_token_matches",
    "verify_password",
]
