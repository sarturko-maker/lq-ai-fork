"""Shared best-effort SMTP transport — SETUP-3a (ADR-F061 D6).

Generalised out of ``app.autonomous.notify_email`` so both autonomous
notifications AND the user-lifecycle mail (invites, password resets) share one
transport with identical fault-tolerance semantics:

* **Clean no-op when unconfigured.** With ``smtp_host`` unset (or no recipient
  / no usable From address) :func:`send_email` returns ``False`` without
  raising and logs at debug. Operators who never set SMTP still get working
  in-app notifications and in-band invite links (the invite-create response
  carries the accept URL when mail is off — ADR-F061 D6).
* **Never raises.** Any transport / auth / parse failure is caught, logged at
  warning, and surfaced as ``False``. A failed send must never break the
  caller (an autonomous run, an admin creating an invite).

No new dependency (CLAUDE.md SBOM posture): stdlib ``smtplib`` +
:class:`email.message.EmailMessage`, run off the event loop via
:func:`asyncio.to_thread` so blocking socket I/O never stalls the caller's loop.

The ``subject`` / ``body`` carry only what the caller supplied — counts / IDs /
links — never raw entity values. This module transports; it does not compose.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger(__name__)


def _send_sync(
    *,
    host: str,
    port: int,
    use_tls: bool,
    username: str | None,
    password: str | None,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    timeout: int,
) -> None:
    """Blocking SMTP send — runs in a worker thread via ``asyncio.to_thread``.

    Builds a plain-text :class:`EmailMessage`, connects, optionally issues
    STARTTLS, optionally logs in, and sends. The ``timeout`` bounds connect
    AND subsequent socket ops (STARTTLS / send) so a hung mail server can't tie
    up the worker thread indefinitely. Raises on any failure (including a
    :class:`TimeoutError`); the async wrapper catches and logs.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(msg)


async def send_email(*, to_addr: str | None, subject: str, body: str) -> bool:
    """Best-effort plain-text email send. Returns ``True`` only on success.

    Returns ``False`` — never raises — when SMTP is unconfigured, the recipient
    is missing, no From address is usable, or the send fails for any reason.

    Args:
        to_addr: Recipient address. A falsy value short-circuits to ``False``.
        subject: Email subject.
        body: Email body (links / counts / IDs; never raw entity values).
    """
    settings = get_settings()

    # Clean no-op: email disabled (no host) or no recipient.
    if not settings.smtp_host or not to_addr:
        log.debug(
            "email_send_skipped",
            extra={
                "event": "email_send_skipped",
                "configured": bool(settings.smtp_host),
                "has_recipient": bool(to_addr),
            },
        )
        return False

    from_addr = settings.smtp_from or settings.smtp_username
    if not from_addr:
        # No usable From address — treat as unconfigured rather than guess.
        log.debug(
            "email_send_skipped",
            extra={"event": "email_send_skipped", "reason": "no_from_addr"},
        )
        return False

    try:
        await asyncio.to_thread(
            _send_sync,
            host=settings.smtp_host,
            port=settings.smtp_port,
            use_tls=settings.smtp_use_tls,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
            timeout=settings.smtp_timeout,
        )
    except Exception:
        # Best-effort: a transport/auth/parse failure must NEVER propagate.
        log.warning(
            "email_send_failed",
            extra={"event": "email_send_failed"},
            exc_info=True,
        )
        return False

    return True
