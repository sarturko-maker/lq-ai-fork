"""Bcrypt-backed password hashing and verification.

We call into `bcrypt` directly rather than wrapping it with `passlib`. The
passlib bcrypt backend has had recurring compatibility issues with bcrypt
4.x+ around the version-detection probe (`AttributeError: module 'bcrypt'
has no attribute '__about__'`). For one well-scoped operation — hash and
verify — the direct API is simpler, smaller, and avoids that maintenance
tax.

The cost factor (`rounds`) defaults to bcrypt's library default of 12,
which is the OWASP-recommended floor as of 2024. Operators can tune via
`BCRYPT_ROUNDS` if profiling shows the auth path is a bottleneck.

The functions are sync because bcrypt is CPU-bound; async wouldn't help.
The login endpoint is the one hot caller and is rate-limited at the edge.
"""

from __future__ import annotations

import bcrypt

from app.config import get_settings


def hash_password(plain: str) -> str:
    """Bcrypt-hash a plaintext password.

    Returns the hash as a UTF-8 string (the form stored in `users.hashed_password`).

    Raises ValueError if `plain` is empty — a footgun-prevention check; an
    empty password should never be accepted. The login endpoint should
    reject empty passwords before calling this; this is defense in depth.
    """
    if not plain:
        raise ValueError("password must not be empty")

    settings = get_settings()
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Returns True iff the password matches. Returns False on any mismatch
    or malformed-hash error — the caller treats both as authentication
    failure and surfaces a generic 401, not a "your hash is malformed"
    diagnostic.

    Constant-time inside bcrypt's `checkpw` so timing leaks the length
    of the hash but not whether the password matches.
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash (truncated, wrong prefix, etc.) — treat as no match.
        return False
