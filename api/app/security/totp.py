"""TOTP secrets, recovery codes, and verification helpers — D5.

Per PRD §5.3 and `docs/api/backend-openapi.yaml` (`/auth/mfa/setup`,
`/auth/mfa/verify`), MFA enrollment issues:

* a fresh TOTP secret (RFC 6238, base32-encoded) — persisted plaintext on
  ``users.totp_secret`` because the operator-of-self model gives the
  user no path to recover from a lost secret other than disabling MFA;
* a provisioning URI (``otpauth://``) the client renders as a QR code
  for the authenticator app;
* 10 single-use recovery codes — bcrypt-hashed before persistence on
  ``users.recovery_codes``. The plaintext is shown to the user once at
  enrollment and never again.

The keep-it-thin rule (per CLAUDE.md "code is part of the change"):
all TOTP-specific primitives live here so :mod:`app.api.auth` stays
focused on the HTTP shape. The handlers call into this module for
secret generation, code generation, and verification.

Recovery-code consumption (single-use): on a successful match in
:func:`consume_recovery_code`, the matched hash is removed from the
caller's list. The handler persists the new list in the same
transaction as the session creation, so a transient failure cannot
leak a re-usable code.
"""

from __future__ import annotations

import secrets

import pyotp

from app.security.passwords import hash_password, verify_password

# RFC 6238 §4 recommends 30-second time steps and 6-digit codes. pyotp's
# defaults match this; we declare them explicitly so a config drift
# can't silently widen the verification window.
_TOTP_DIGITS = 6
_TOTP_INTERVAL = 30

# Time-window slack when verifying a TOTP code. ``valid_window=1`` accepts
# the current step plus the immediately adjacent steps on either side
# (3 codes total, ~90s wall clock). This tolerates clock drift between
# the user's authenticator app and the server without meaningfully
# weakening the brute-force budget — ~3 of 10^6 codes per step instead
# of 1.
_TOTP_VERIFY_WINDOW = 1

# Recovery-code shape: 12 random hex chars, dash-separated into three
# groups of four for human readability (``xxxx-xxxx-xxxx``). 48 bits of
# entropy is well over the threshold needed against an online attacker;
# the bcrypt hash gates offline brute-force from a database leak.
_RECOVERY_CODE_GROUPS = 3
_RECOVERY_CODE_GROUP_LEN = 4
_RECOVERY_CODE_COUNT = 10

# Issuer name embedded in the otpauth:// URI. The authenticator app
# shows this above the per-account label; users with multiple LQ.AI
# deployments should still be able to tell them apart by account email
# (the label) so this is intentionally constant rather than per-tenant.
_PROVISIONING_ISSUER = "LQ.AI"


def generate_totp_secret() -> str:
    """Return a fresh base32-encoded TOTP secret.

    Wraps :func:`pyotp.random_base32` so callers do not import pyotp
    directly. The caller persists this on ``users.totp_secret``.
    """

    return pyotp.random_base32()


def provisioning_uri(secret: str, *, account_email: str) -> str:
    """Build the ``otpauth://`` provisioning URI for QR-code display.

    The URI encodes ``secret``, ``account_email`` (as the label), and a
    constant issuer (``LQ.AI``). The client renders this as a QR code
    that authenticator apps consume.
    """

    return pyotp.TOTP(secret, digits=_TOTP_DIGITS, interval=_TOTP_INTERVAL).provisioning_uri(
        name=account_email,
        issuer_name=_PROVISIONING_ISSUER,
    )


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP ``code`` against ``secret``.

    Returns ``True`` if the code matches the current 30s step or the
    immediately adjacent steps (drift tolerance). Returns ``False`` for
    a missing/empty secret or a malformed code rather than raising.
    """

    if not secret or not code:
        return False
    return bool(
        pyotp.TOTP(secret, digits=_TOTP_DIGITS, interval=_TOTP_INTERVAL).verify(
            code, valid_window=_TOTP_VERIFY_WINDOW
        )
    )


def generate_recovery_codes() -> tuple[list[str], list[str]]:
    """Return ``(plaintext_codes, hashed_codes)`` for fresh enrollment.

    The plaintext list is the one-time-display value the handler
    returns to the client. The hashed list is what gets persisted on
    ``users.recovery_codes``. Sizes match (10 each, paired by index
    only at generation time — order is not load-bearing on the stored
    side because :func:`consume_recovery_code` scans linearly).
    """

    plaintext: list[str] = []
    hashed: list[str] = []
    for _ in range(_RECOVERY_CODE_COUNT):
        code = "-".join(
            secrets.token_hex(_RECOVERY_CODE_GROUP_LEN // 2) for _ in range(_RECOVERY_CODE_GROUPS)
        )
        plaintext.append(code)
        hashed.append(hash_password(code))
    return plaintext, hashed


def consume_recovery_code(submitted: str, hashed_codes: list[str]) -> list[str] | None:
    """Look up ``submitted`` against ``hashed_codes`` and remove the match.

    Returns the *new* hashed-codes list (with the matched hash
    excluded) on success; returns ``None`` if no hash matched. The
    caller persists the returned list to enforce single-use.

    Linear bcrypt scan over up to 10 entries is acceptable: enrollment
    issues 10 codes; a worst-case verify is ~10x bcrypt-rounds (~250ms
    at the default 12 rounds). MFA verify is not on the hot path.
    """

    if not submitted or not hashed_codes:
        return None
    for index, stored in enumerate(hashed_codes):
        if verify_password(submitted, stored):
            return hashed_codes[:index] + hashed_codes[index + 1 :]
    return None
