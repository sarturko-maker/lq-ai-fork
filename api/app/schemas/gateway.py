"""Pydantic schemas mirroring the gateway's OpenAI-compatible surface.

The gateway exposes :doc:`/v1/chat/completions <docs/api/gateway-openapi.yaml>`
as its inference entrypoint. This module declares the request and response
shapes the backend uses to talk to that surface. The shapes mirror
``gateway/app/providers/openai_schema.py`` (B3) — by ADR 0003 / CLAUDE.md
they cannot import from ``gateway/`` directly, so the parallel definitions
are kept in sync against the OpenAPI sketch.

LQ.AI extensions documented in ``docs/api/gateway-openapi.yaml``:

* Request side: ``minimum_inference_tier``, ``skill_name``, ``chat_id``,
  ``anonymize``.
* Response side: ``routed_inference_tier``, ``routed_provider``,
  ``cost_estimate``, ``anonymization_applied``.

Permissive policy
-----------------

``extra="allow"`` on the response models so a forward-looking gateway
revision (or a streaming chunk variant we don't know about yet) round-trips
without rejection. The backend reads only the fields it needs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChatRole = Literal["system", "user", "assistant", "tool"]


# --- Chat completion request --------------------------------------------------


class ChatCompletionMessage(BaseModel):
    """One message in a chat-completion request or response."""

    model_config = ConfigDict(extra="allow")

    role: ChatRole
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions request body, plus LQ.AI extensions.

    The backend constructs one of these and posts it to the gateway's
    ``/v1/chat/completions`` endpoint. ``model`` is the operator-defined
    alias (``smart``, ``fast``) or a provider-native model name; the
    gateway router resolves it.
    """

    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1)
    messages: list[ChatCompletionMessage]
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stream: bool = False
    stop: list[str] | str | None = None
    n: int | None = Field(default=None, ge=1, le=1)

    # --- LQ.AI extensions (per gateway-openapi.yaml) -------------------------
    minimum_inference_tier: int | None = Field(default=None, ge=1, le=5)
    skill_name: str | None = None
    chat_id: str | None = None
    anonymize: bool = True

    # --- C2 (skill prompt assembly per ADR 0007) -----------------------------
    lq_ai_skills: list[str] = Field(default_factory=list)
    """Skill names to attach. The gateway fetches each from
    ``/api/v1/internal/skills/{name}`` and assembles them into the
    system message before dispatching to the provider."""

    lq_ai_skill_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """Per-skill input bindings, keyed by skill name."""


# --- Chat completion response -------------------------------------------------


class ChatCompletionUsage(BaseModel):
    """Token-usage summary, OpenAI-shaped."""

    model_config = ConfigDict(extra="allow")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


FinishReason = Literal["stop", "length", "content_filter", "tool_calls"]


class ChatCompletionChoice(BaseModel):
    """One choice in a non-streaming chat-completion response."""

    model_config = ConfigDict(extra="allow")

    index: int = 0
    message: ChatCompletionMessage
    finish_reason: FinishReason | None = None


class ChatCompletionResponse(BaseModel):
    """Non-streaming chat-completion response body.

    Mirrors OpenAI's ``chat.completion`` plus the LQ.AI extension fields
    populated by the gateway (``routed_inference_tier``, etc.). The
    backend reads these to surface tier annotations to the API caller.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)

    # --- LQ.AI extensions ---------------------------------------------------
    routed_inference_tier: int | None = Field(default=None, ge=1, le=5)
    routed_provider: str | None = None
    cost_estimate: float | None = None
    anonymization_applied: bool | None = None
    lq_ai_applied_skills: list[str] | None = None
    """Skills successfully assembled into the prompt for this request
    (C2). Null when no skills were attached. Backend surfaces this in
    audit logs and the chat response."""


# --- Streaming chunk ----------------------------------------------------------


class ChatCompletionDelta(BaseModel):
    """Partial message delta inside a streaming chunk."""

    model_config = ConfigDict(extra="allow")

    role: ChatRole | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatCompletionChunkChoice(BaseModel):
    """One choice in a streaming chat-completion chunk."""

    model_config = ConfigDict(extra="allow")

    index: int = 0
    delta: ChatCompletionDelta = Field(default_factory=ChatCompletionDelta)
    finish_reason: FinishReason | None = None


class ChatCompletionChunk(BaseModel):
    """Streaming chat-completion chunk envelope.

    The gateway emits these as ``data: <json>`` SSE frames; the backend
    deserializes each frame back into a chunk via the streaming helper
    in :mod:`app.clients.gateway`.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatCompletionChunkChoice]
    usage: ChatCompletionUsage | None = None

    # --- LQ.AI extensions ---------------------------------------------------
    routed_inference_tier: int | None = Field(default=None, ge=1, le=5)
    routed_provider: str | None = None
    lq_ai_applied_skills: list[str] | None = None


# --- Gateway error envelope --------------------------------------------------


class GatewayErrorPayload(BaseModel):
    """Inner error object — matches ``GatewayError.error`` in the sketch."""

    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class GatewayErrorEnvelope(BaseModel):
    """Outer ``GatewayError`` shape — ``{"error": {...}}``.

    The backend deserializes any non-2xx response body into one of these
    so the gateway client can map ``error.code`` to the appropriate
    backend exception class via :func:`app.errors.map_gateway_error_code`.
    """

    error: GatewayErrorPayload
