"""User-lifecycle email composition — SETUP-3a (ADR-F061 D6).

Builds the invite / password-reset messages (subject + body + link) and hands
them to the shared best-effort transport (:func:`app.email.send_email`). The
links are constructed from the ``public_base_url`` setting; when that is unset
the link falls back to a path-only string so the message body is still coherent
(and, for invites, the admin gets the accept URL back in the API response to
hand over out-of-band — ADR-F061 D6).

Content-only: no secrets beyond the single-use token in the link, and the token
is NEVER logged (the transport logs neither subject nor body).

BRAND-1a (ADR-F068): the product name in the subject/body is parameterized —
callers resolve it via :func:`get_branding_name` (the deployment-branding
singleton, default "LQ.AI"). The name lands in the SMTP SUBJECT header, so the
composer strips CR/LF/control characters belt-and-braces on top of the PUT
boundary's rejection.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.email import send_email
from app.models.deployment_branding import DeploymentBranding, strip_control_chars

DEFAULT_PRODUCT_NAME = "LQ.AI"


def _header_safe(name: str) -> str:
    """Strip control/format/line-separator characters (incl. CR/LF) from a
    subject-bound string.

    Belt-and-braces: the PUT boundary already REJECTS these characters
    (app/api/branding.py), but the subject header is an injection sink, so
    the composer never trusts its input either. Uses the SAME shared
    character classes as the boundary (app/models/deployment_branding).
    """
    return strip_control_chars(name).strip()


async def get_branding_name(db: AsyncSession) -> str:
    """The deployment's configured product name, or ``"LQ.AI"`` (BRAND-1a).

    Reads the ``deployment_branding`` singleton; an empty/absent name means
    the default brand.
    """
    result = await db.execute(select(DeploymentBranding.product_name).limit(1))
    name = result.scalar_one_or_none()
    return _header_safe(name or "") or DEFAULT_PRODUCT_NAME


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

    SETUP-3b (ADR-F061 addendum D1) — the ``/lq-ai`` prefix is the real SPA
    route (``web/src/routes/lq-ai/accept-invite``), not a placeholder.
    """
    return f"{_effective_base_url()}/lq-ai/accept-invite?token={token}"


def build_reset_url(token: str) -> str:
    """Absolute password-reset URL, or a path-only fallback when no base URL."""
    return f"{_effective_base_url()}/lq-ai/reset-password?token={token}"


async def send_invite_email(
    *, to_addr: str, accept_url: str, product_name: str = DEFAULT_PRODUCT_NAME
) -> bool:
    """Best-effort invite email. Returns ``True`` only on a successful send."""
    name = _header_safe(product_name) or DEFAULT_PRODUCT_NAME
    subject = f"You've been invited to {name}"
    body = (
        f"An administrator has invited you to {name}.\n\n"
        "Accept the invitation and set your password here:\n"
        f"{accept_url}\n\n"
        "This link is single-use and expires soon. If you did not expect this "
        "invitation you can ignore this email."
    )
    return await send_email(to_addr=to_addr, subject=subject, body=body)


async def send_password_reset_email(
    *, to_addr: str, reset_url: str, product_name: str = DEFAULT_PRODUCT_NAME
) -> bool:
    """Best-effort password-reset email. Returns ``True`` only on success."""
    name = _header_safe(product_name) or DEFAULT_PRODUCT_NAME
    subject = f"Reset your {name} password"
    body = (
        f"We received a request to reset your {name} password.\n\n"
        "Set a new password here:\n"
        f"{reset_url}\n\n"
        "This link is single-use and expires within the hour. If you did not "
        "request a reset you can safely ignore this email — your password will "
        "not change."
    )
    return await send_email(to_addr=to_addr, subject=subject, body=body)
