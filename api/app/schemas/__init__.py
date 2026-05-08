"""Pydantic schemas owned by the api/ subsystem.

Per CLAUDE.md, ``api/`` and ``gateway/`` are self-contained services that
talk over HTTP using OpenAPI-defined contracts. This package mirrors the
shapes the api/ subsystem needs to send to (or receive from) the gateway;
the gateway has its own copy under ``gateway/app/providers/openai_schema.py``.
The two are kept in sync against ``docs/api/gateway-openapi.yaml`` — the
canonical contract.
"""

from app.schemas.gateway import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    GatewayErrorEnvelope,
    GatewayErrorPayload,
)

__all__ = [
    "ChatCompletionChoice",
    "ChatCompletionChunk",
    "ChatCompletionChunkChoice",
    "ChatCompletionDelta",
    "ChatCompletionMessage",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionUsage",
    "GatewayErrorEnvelope",
    "GatewayErrorPayload",
]
