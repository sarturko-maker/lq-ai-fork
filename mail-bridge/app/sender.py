"""Outbound reply — INTAKE-2 (ADR-F086), wired by INTAKE-4b (ADR-F087).

Wraps exactly one provider call: ``inboxes.messages.reply``. Recipients are
NOT passed — the probe verified AgentMail derives them from the message being
answered, and not passing them is the point: the bridge cannot be steered into
mailing a third party by anything the agent produces.

Two INTAKE-4b additions, both of them "the bridge decides, not the caller":

* **Reply-To is composed HERE.** The api sends a validated matter reference as
  ``reply_to_tag``; this module turns it into ``<local>+<tag>@<domain>`` using its
  OWN configured inbox address. An api that could pass a whole address could be
  talked into pointing replies somewhere else. Plus-address delivery to the base
  inbox is proven live (``docs/fork/evidence/intake-probe/findings.md``).
* **Idempotency.** ``idempotency_key`` is required, handed to the provider's own
  ``idempotency_key`` parameter, AND remembered in a bounded in-process set so a
  repeat is refused (409) rather than delivered twice. Documented limit: that set
  is per PROCESS and holds :data:`_SEEN_KEYS_MAX` keys — a bridge restart or a
  flood of newer keys forgets it, and the provider-side key is what still stands.
  One bridge process per inbox is the deployment shape (``docker-compose.yml``).

There is deliberately **no subject**: the SDK's ``reply()`` takes none (only the
cold-send ``send()`` does, and we expose no cold send), so the delivered subject
is the provider's ``Re: <original>``. The tagged subject the api records on its
own row is for the matter file; the stamps that survive the wire are the
provider-assigned message id (layer 2) and this Reply-To tag (ADR-F088).
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

from agentmail import AsyncAgentMail

from .schemas import SendReplyRequest, SendReplyResponse

log = logging.getLogger(__name__)

#: How many recently-used idempotency keys one process remembers. Sized for
#: "every reply this deployment sends in a long working day", bounded so a
#: hostile or buggy caller cannot grow the process's memory without limit.
_SEEN_KEYS_MAX = 4096


class DuplicateSendError(Exception):
    """A send whose ``idempotency_key`` this process has already used."""


def compose_reply_to(inbox_address: str, tag: str) -> str | None:
    """``<local>+<tag>@<domain>`` — or ``None`` if the inbox address is unusable.

    The tag is already pattern-validated at the schema boundary (uppercase,
    no ``@``, no ``+``), so this is pure string surgery on OUR address.
    """
    local, sep, domain = inbox_address.partition("@")
    if not sep or not local or not domain:
        return None
    return f"{local}+{tag}@{domain}"


class MailSender:
    """Sends approved replies through the provider."""

    def __init__(self, *, client: AsyncAgentMail, inbox_id: str) -> None:
        self._client = client
        self._inbox_id = inbox_id
        self._seen_keys: OrderedDict[str, None] = OrderedDict()

    def _claim(self, key: str) -> None:
        """Reserve one idempotency key, or raise :class:`DuplicateSendError`.

        Claimed BEFORE the provider call, not after: a repeat that arrives while
        the first send is still in flight is the exact case a post-hoc record
        would miss. A provider failure therefore burns the key — deliberate, since
        the caller does not retry (ADR-F087: no retries) and a burnt key is a
        refused duplicate, never a duplicate letter.
        """
        if key in self._seen_keys:
            raise DuplicateSendError(key)
        self._seen_keys[key] = None
        while len(self._seen_keys) > _SEEN_KEYS_MAX:
            self._seen_keys.popitem(last=False)

    async def reply(self, request: SendReplyRequest) -> SendReplyResponse:
        self._claim(request.idempotency_key)
        reply_to = (
            compose_reply_to(self._inbox_id, request.reply_to_tag)
            if request.reply_to_tag is not None
            else None
        )
        # The SDK's OMIT sentinel is each optional field's default; passing an
        # explicit ``None`` would serialize ``"reply_to": null`` instead of
        # leaving the field out, so an untagged send omits the kwarg entirely.
        # F6a: a reply carries text only — the attachments field was dead surface
        # (draft_email_reply never delivers them) and is gone.
        kwargs: dict[str, Any] = {
            "text": request.text,
            "idempotency_key": request.idempotency_key,
        }
        if reply_to is not None:
            kwargs["reply_to"] = reply_to
        response = await self._client.inboxes.messages.reply(
            self._inbox_id, request.reply_to_provider_message_id, **kwargs
        )
        log.info(
            "mail-bridge: reply sent",
            extra={
                "event": "mail_reply_sent",
                "thread_id": response.thread_id,
                "tagged": request.reply_to_tag is not None,
            },
        )
        return SendReplyResponse(
            provider_message_id=response.message_id,
            provider_thread_id=response.thread_id,
        )
