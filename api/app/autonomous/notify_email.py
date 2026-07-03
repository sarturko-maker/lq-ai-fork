"""Best-effort SMTP email for autonomous notifications — M4-C1.

The transport core was generalised into :mod:`app.email` (SETUP-3a, ADR-F061
D6) so autonomous notifications and user-lifecycle mail share one fault-tolerant
sender. This module keeps its public API — :func:`send_notification_email` —
frozen and simply delegates: the ``notify`` chokepoint handler writes a durable
in-app :class:`~app.models.autonomous.AutonomousNotification` row (the record of
truth) and then calls this as a **best-effort** email copy.

The never-raise / smtp_host-gated-no-op contract is preserved verbatim by
:func:`app.email.send_email`; email is a convenience copy of the in-app
notification, never the durable record. The ``subject`` / ``body`` carry only
what the ``notify`` ``params`` carried — counts / IDs / a receipt link — never
raw entity values.
"""

from __future__ import annotations

import logging

from app.email import send_email

log = logging.getLogger(__name__)


async def send_notification_email(
    *,
    to_addr: str | None,
    subject: str,
    body: str,
) -> bool:
    """Best-effort send of an autonomous notification by email.

    Delegates to :func:`app.email.send_email`. Returns ``True`` only on a
    successful send; returns ``False`` — never raises — when SMTP is
    unconfigured, the recipient is missing, or the send fails for any reason.

    Args:
        to_addr: The recipient address (the session user's email). A falsy
            value short-circuits to a ``False`` no-op.
        subject: Email subject — the notification ``title``.
        body: Email body — the notification ``body`` (counts / IDs / receipt
            link; never raw entity values).
    """
    return await send_email(to_addr=to_addr, subject=subject, body=body)
