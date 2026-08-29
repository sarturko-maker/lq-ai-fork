"""Outbound reply — INTAKE-2 (ADR-F086), consumed by INTAKE-4.

Wraps exactly one provider call: ``inboxes.messages.reply``. Recipients are
NOT passed — the probe verified AgentMail derives them from the message being
answered, and not passing them is the point: the bridge cannot be steered into
mailing a third party by anything the agent produces.
"""

from __future__ import annotations

import logging

from agentmail import AsyncAgentMail, SendAttachment

from .schemas import SendReplyRequest, SendReplyResponse

log = logging.getLogger(__name__)


class MailSender:
    """Sends approved replies through the provider."""

    def __init__(self, *, client: AsyncAgentMail, inbox_id: str) -> None:
        self._client = client
        self._inbox_id = inbox_id

    async def reply(self, request: SendReplyRequest) -> SendReplyResponse:
        response = await self._client.inboxes.messages.reply(
            self._inbox_id,
            request.reply_to_provider_message_id,
            text=request.text,
            attachments=[
                SendAttachment(
                    filename=a.filename,
                    content_type=a.content_type,
                    content_disposition="attachment",
                    content=a.content_b64,
                )
                for a in request.attachments
            ],
        )
        log.info(
            "mail-bridge: reply sent",
            extra={
                "event": "mail_reply_sent",
                "attachments": len(request.attachments),
                "thread_id": response.thread_id,
            },
        )
        return SendReplyResponse(
            provider_message_id=response.message_id,
            provider_thread_id=response.thread_id,
        )
