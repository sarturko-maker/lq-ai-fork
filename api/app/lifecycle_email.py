"""User-lifecycle email composition — SETUP-3a (ADR-F061 D6).

Builds the invite / password-reset messages (subject + body + link) and hands
them to the shared best-effort transport (:func:`app.email.send_email`). The
links are constructed from the ``public_base_url`` setting; when that is unset
the link falls back to a path-only string so the message body is still coherent
(and, for invites, the admin gets the accept URL back in the API response to
hand over out-of-band — ADR-F061 D6).

Content-only: no secrets beyond the single-use token in the link, and the token
is NEVER logged (the transport logs neither subject nor body).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.config import get_settings
from app.email import send_email


def _effective_base_url() -> str:
    """The configured public base URL, or ``""`` for the path-only fallback.

    Hardened against a scheme-only value (security review fix 3): the prod
    compose derives ``PUBLIC_BASE_URL: https://${LQ_AI_PUBLIC_ORIGIN}``, so an
    unset origin would yield the literal ``"https://"`` and the built links
    would read ``https:/accept-invite?...``. A base whose URL has a scheme but
    no host is treated as unset so the promised path-only fallback fires.
    """
    base = (get_settings().public_base_url or "").strip()
    if not base:
        return ""
    parts = urlsplit(base)
    if parts.scheme and not parts.netloc:
        # "https://", "https:" — a scheme with no host is not a usable base.
        return ""
    return base.rstrip("/")


def build_accept_url(token: str) -> str:
    """Absolute accept-invite URL, or a path-only fallback when no base URL.

    The web accept page lands in SETUP-3b; the path is a stable placeholder the
    operator can hand over today.
    """
    return f"{_effective_base_url()}/accept-invite?token={token}"


def build_reset_url(token: str) -> str:
    """Absolute password-reset URL, or a path-only fallback when no base URL."""
    return f"{_effective_base_url()}/reset-password?token={token}"


async def send_invite_email(*, to_addr: str, accept_url: str) -> bool:
    """Best-effort invite email. Returns ``True`` only on a successful send."""
    subject = "You've been invited to LQ.AI"
    body = (
        "An administrator has invited you to LQ.AI.\n\n"
        "Accept the invitation and set your password here:\n"
        f"{accept_url}\n\n"
        "This link is single-use and expires soon. If you did not expect this "
        "invitation you can ignore this email."
    )
    return await send_email(to_addr=to_addr, subject=subject, body=body)


async def send_password_reset_email(*, to_addr: str, reset_url: str) -> bool:
    """Best-effort password-reset email. Returns ``True`` only on success."""
    subject = "Reset your LQ.AI password"
    body = (
        "We received a request to reset your LQ.AI password.\n\n"
        "Set a new password here:\n"
        f"{reset_url}\n\n"
        "This link is single-use and expires within the hour. If you did not "
        "request a reset you can safely ignore this email — your password will "
        "not change."
    )
    return await send_email(to_addr=to_addr, subject=subject, body=body)
