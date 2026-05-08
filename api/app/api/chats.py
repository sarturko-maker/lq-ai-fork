"""Chats and messages endpoints.

Per ADR 0002 (backend owns auth) + the M1 build plan, the chat surface
lands progressively:

* **B5 (this commit).** ``POST /api/v1/chats/{chat_id}/messages`` is
  wired through to the gateway's ``/v1/chat/completions``. Persistence
  lands in C3 — until then this endpoint is a *stateless pass-through*:
  the request body's ``content`` becomes a single ``user`` message, the
  gateway's response becomes the response body, and **nothing is written
  to** ``chats`` **or** ``messages`` (those tables don't exist yet — C3
  adds them). The gateway-side ``inference_routing_log`` row IS written
  (B4), so the audit trail still captures the call.

* **C3.** Real ``chats`` and ``messages`` tables; the request persists a
  user message, the response persists the assistant message, the
  citation engine attaches verified citations.

The other endpoints in this module (list/create/get/patch/delete chats,
list messages, citations) stay 501 — those are all C3 territory.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.api._stub import not_implemented
from app.api.dependencies import ActiveUser
from app.clients.gateway import GatewayClient, get_gateway_client
from app.errors import LQAIError, ValidationError as DomainValidationError
from app.schemas.gateway import (
    ChatCompletionMessage,
    ChatCompletionRequest,
)

router = APIRouter(prefix="/chats", tags=["chats"])
log = logging.getLogger(__name__)

_C3 = "C3 — Chat service + message persistence"


# ---------------------------------------------------------------------------
# Request schema (matches the OpenAPI sketch's MessageCreate).
# ---------------------------------------------------------------------------


class MessageCreateRequest(BaseModel):
    """`MessageCreate` schema from backend-openapi.yaml.

    B5 supports ``content`` and ``model``. C2 adds ``skills`` (list of
    skill names to attach) and ``skill_inputs`` (per-skill input
    bindings) and forwards both to the gateway as the
    ``lq_ai_skills`` / ``lq_ai_skill_inputs`` request-extension fields.
    """

    content: str = Field(min_length=1)
    model: str = Field(default="smart")
    """Model alias (per the OpenAPI sketch). Defaults to ``smart`` —
    operators map ``smart`` to a real model in ``gateway.yaml``.
    See ``gateway.yaml.example`` for the alias list."""

    skills: list[str] = Field(default_factory=list)
    """C2: skill names to attach. The backend forwards them as
    ``lq_ai_skills`` to the gateway, which fetches each from the
    backend's internal-skills endpoint and assembles the prompt."""

    skill_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """C2: per-skill input bindings, keyed by skill name. Forwarded as
    ``lq_ai_skill_inputs`` to the gateway. Per-skill scoping so two
    attached skills with overlapping variable names don't collide."""

    stream: bool = False
    """Whether to stream the response as SSE chunks. ``False`` returns a
    single JSON body; ``True`` returns a ``text/event-stream`` response
    matching the OpenAPI sketch's ``MessageStreamEvent``."""


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _build_gateway_request(
    payload: MessageCreateRequest,
    *,
    chat_id: str,
) -> ChatCompletionRequest:
    """Translate the backend request into a gateway-shaped request.

    B5 maps the single ``content`` string to one ``user`` message. C3
    will pull prior messages from ``messages`` to build full conversation
    context; until then the gateway sees a single-turn request.

    The ``chat_id`` is forwarded so the gateway's ``inference_routing_log``
    row carries it (correlation across the stateless pass-through; once
    C3 persists, the same id resolves to the chat row).

    C2: ``skills`` and ``skill_inputs`` from the backend's
    MessageCreate body forward as ``lq_ai_skills`` and
    ``lq_ai_skill_inputs`` to the gateway, which assembles the prompt.
    """

    return ChatCompletionRequest(
        model=payload.model,
        messages=[ChatCompletionMessage(role="user", content=payload.content)],
        stream=payload.stream,
        chat_id=chat_id,
        lq_ai_skills=list(payload.skills),
        lq_ai_skill_inputs=dict(payload.skill_inputs),
    )


def _validate_chat_id(chat_id: str) -> str:
    """Reject non-UUID chat ids per the OpenAPI sketch's ``{chat_id}: uuid``."""

    try:
        uuid.UUID(chat_id)
    except ValueError as exc:
        raise DomainValidationError(
            "chat_id must be a UUID",
            details={"chat_id": chat_id},
        ) from exc
    return chat_id


def _assistant_message_dict(
    *,
    chat_id: str,
    content: str,
    model: str | None,
    routed_provider: str | None,
    routed_inference_tier: int | None,
    tokens_in: int | None,
    tokens_out: int | None,
    cost_estimate: float | None,
) -> dict[str, object]:
    """Build the ``Message`` dict from the OpenAPI sketch.

    ``id`` is synthesized — until C3, no row exists. Operators reading
    the response should not rely on the id resolving to a database
    record yet. Documented in the response below.
    """

    from datetime import UTC, datetime

    return {
        "id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "role": "assistant",
        "content": content,
        "model": model,
        "provider": routed_provider,
        "routed_inference_tier": routed_inference_tier,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_estimate": cost_estimate,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints.
# ---------------------------------------------------------------------------


@router.get("")
async def list_chats(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="GET /api/v1/chats")


@router.post("")
async def create_chat(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="POST /api/v1/chats")


@router.get("/{chat_id}")
async def get_chat(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="GET /api/v1/chats/{chat_id}")


@router.patch("/{chat_id}")
async def update_chat(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="PATCH /api/v1/chats/{chat_id}")


@router.delete("/{chat_id}")
async def delete_chat(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="DELETE /api/v1/chats/{chat_id}")


@router.get("/{chat_id}/messages")
async def list_messages(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="GET /api/v1/chats/{chat_id}/messages")


@router.post(
    "/{chat_id}/messages",
    response_model=None,  # union return type; FastAPI handles via Response
    summary="Post a user message; pass through to the gateway and return the response",
    description=(
        "B5 stateless pass-through. Until C3 lands chat persistence, this endpoint "
        "translates the request into a single-turn gateway call and returns the "
        "response. The gateway-side `inference_routing_log` row is written; "
        "the chat / messages tables do not yet exist, so nothing is persisted "
        "on the backend side."
    ),
)
async def send_message(
    chat_id: str,
    request: Request,
    user: ActiveUser,
    gateway: Annotated[GatewayClient, Depends(get_gateway_client)],
) -> JSONResponse | StreamingResponse:
    """POST a user message; pass through to the gateway and return the response.

    Auth gate: bearer token + cleared must_change_password (B2).

    Behavior (B5):

    1. Parse the request body as ``MessageCreate``.
    2. Translate to a single-turn ``ChatCompletionRequest`` with the
       request's ``content`` as the only message.
    3. Call :meth:`GatewayClient.chat_completion` (or its streaming
       variant if ``stream=True``).
    4. Surface the gateway's ``routed_inference_tier`` to the response.
    5. **Do NOT persist anything** — chats and messages tables don't
       exist yet; C3 adds them.
    6. **Do NOT write** ``inference_routing_log`` from the backend —
       the gateway already writes it (B4). Backend writing would
       double-count.
    """

    _validate_chat_id(chat_id)

    try:
        raw_body = await request.json()
    except Exception as exc:
        raise DomainValidationError(
            "Request body is not valid JSON",
        ) from exc

    try:
        payload = MessageCreateRequest.model_validate(raw_body)
    except ValidationError as exc:
        raise DomainValidationError(
            "Request body failed schema validation",
            details={"errors": exc.errors()},
        ) from exc

    # Forward an X-Request-Id so the gateway's audit row correlates back
    # to this hop. Use an upstream-supplied id if the caller provided
    # one; otherwise synthesize a UUID per the same convention as the
    # gateway's synthesize_request_id.
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
        or f"req_{uuid.uuid4().hex}"
    )

    gw_request = _build_gateway_request(payload, chat_id=chat_id)

    log.info(
        "chat send_message: user=%s chat_id=%s model=%s stream=%s request_id=%s",
        user.id,
        chat_id,
        payload.model,
        payload.stream,
        request_id,
    )

    if payload.stream:
        return await _stream_response(
            gateway=gateway,
            request=gw_request,
            chat_id=chat_id,
            request_id=request_id,
        )
    return await _non_streaming_response(
        gateway=gateway,
        payload=payload,
        request=gw_request,
        chat_id=chat_id,
        request_id=request_id,
    )


@router.get("/{chat_id}/messages/{message_id}/citations")
async def get_citations(request: Request, chat_id: str, message_id: str) -> JSONResponse:
    return not_implemented(
        request,
        next_task=_C3,
        endpoint="GET /api/v1/chats/{chat_id}/messages/{message_id}/citations",
    )


# ---------------------------------------------------------------------------
# Internal: streaming + non-streaming response builders.
# ---------------------------------------------------------------------------


async def _non_streaming_response(
    *,
    gateway: GatewayClient,
    payload: MessageCreateRequest,
    request: ChatCompletionRequest,
    chat_id: str,
    request_id: str,
) -> JSONResponse:
    """Run the non-streaming pass-through and serialize the response."""

    # The GatewayClient raises LQAIError subclasses for every failure
    # mode; the FastAPI exception handler (app.main) translates them
    # to the canonical error envelope. We let those propagate.
    response = await gateway.chat_completion(request, request_id=request_id)

    assistant_text = ""
    if response.choices:
        message = response.choices[0].message
        assistant_text = message.content or ""

    body: dict[str, object] = {
        "message": _assistant_message_dict(
            chat_id=chat_id,
            content=assistant_text,
            model=response.model,
            routed_provider=response.routed_provider,
            routed_inference_tier=response.routed_inference_tier,
            tokens_in=response.usage.prompt_tokens if response.usage else None,
            tokens_out=response.usage.completion_tokens if response.usage else None,
            cost_estimate=response.cost_estimate,
        ),
        "routed_inference_tier": response.routed_inference_tier,
        "routed_provider": response.routed_provider,
        "cost_estimate": response.cost_estimate,
        # C2: surface which skills were assembled into the prompt.
        "applied_skills": response.lq_ai_applied_skills or [],
        # B5 cannot return citations until C5 (document pipeline) lands.
        "citations": [],
        # Surface that B5 doesn't yet persist the message — clients can
        # show this if useful, and integration tests pin the marker.
        "stateless_passthrough": True,
    }

    headers: dict[str, str] = {}
    if response.routed_inference_tier is not None:
        headers["X-LQ-AI-Routed-Inference-Tier"] = str(response.routed_inference_tier)
    if response.routed_provider is not None:
        headers["X-LQ-AI-Routed-Provider"] = response.routed_provider

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=body,
        headers=headers,
    )


async def _stream_response(
    *,
    gateway: GatewayClient,
    request: ChatCompletionRequest,
    chat_id: str,
    request_id: str,
) -> StreamingResponse:
    """Run the streaming pass-through and serialize as SSE per the sketch."""

    # The OpenAPI sketch's ``MessageStreamEvent`` has two variants
    # (delta and complete). We emit a sequence of ``delta`` events
    # followed by a final ``complete`` event when the stream ends.
    # Mid-stream errors are surfaced as a final ``error`` SSE frame
    # whose body matches the canonical Error envelope.

    import json as _json

    async def _generate() -> AsyncIterator[bytes]:
        accumulated: list[str] = []
        last_tier: int | None = None
        last_provider: str | None = None
        last_model: str | None = None
        last_applied_skills: list[str] | None = None
        try:
            async for chunk in gateway.chat_completion_stream(request, request_id=request_id):
                last_tier = chunk.routed_inference_tier or last_tier
                last_provider = chunk.routed_provider or last_provider
                last_model = chunk.model
                if chunk.lq_ai_applied_skills is not None:
                    last_applied_skills = list(chunk.lq_ai_applied_skills)
                for choice in chunk.choices:
                    delta = choice.delta.content or ""
                    if not delta:
                        continue
                    accumulated.append(delta)
                    payload = {"type": "delta", "delta": delta}
                    yield f"data: {_json.dumps(payload, separators=(',', ':'))}\n\n".encode()
        except LQAIError as exc:
            # Surface the structured error envelope as a final SSE
            # frame so the client knows the stream ended in failure.
            envelope = exc.to_envelope()
            yield (f"data: {_json.dumps(envelope, separators=(',', ':'))}\n\n".encode())
            yield b"data: [DONE]\n\n"
            return

        # Stream ended cleanly. Emit a final ``complete`` event with the
        # synthesized assistant message and the routing metadata.
        complete: dict[str, Any] = {
            "type": "complete",
            "message": _assistant_message_dict(
                chat_id=chat_id,
                content="".join(accumulated),
                model=last_model,
                routed_provider=last_provider,
                routed_inference_tier=last_tier,
                tokens_in=None,
                tokens_out=None,
                cost_estimate=None,
            ),
            "applied_skills": last_applied_skills or [],
            "citations": [],
        }
        yield f"data: {_json.dumps(complete, separators=(',', ':'))}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
