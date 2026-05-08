"""OpenAI-compatible inference endpoints.

Surface (B3 state):

* ``POST /v1/chat/completions`` — routes to the configured Anthropic
  adapter when the model alias resolves to an Anthropic provider.
  Returns a structured 501 when the resolved provider is not yet
  supported (B6 lands OpenAI / Vertex / Bedrock / Ollama).
* ``POST /v1/embeddings`` — 501 stub. Embeddings adapter lands later;
  Anthropic has no embeddings endpoint.
* ``GET  /v1/models`` — returns the configured ``model_aliases`` from
  ``gateway.yaml``.

Routing posture is intentionally minimal in B3
----------------------------------------------

B3 is the **adapter** task. The router (alias resolution + tier
derivation + fallback chains) is B4. Until B4 lands, this handler
implements just enough routing to verify the adapter end-to-end:

* If the request's ``model`` matches a configured alias whose primary
  provider is Anthropic → use that provider's adapter.
* If the request's ``model`` is one of the listed ``models`` for an
  Anthropic provider directly → use that provider's adapter.
* Otherwise → 501 with ``next_task = "B4 — Gateway router"``.

When B4 lands, this whole resolution block is replaced by a real
:class:`Router` that handles all aliases, fallback chains, and tier
derivation. The error envelope already conforms to ``GatewayError`` from
``docs/api/gateway-openapi.yaml`` so callers don't need to change.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.config import GatewayConfig, ProviderConfig
from app.providers import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ProviderAdapter,
    ProviderAdapterError,
    ProviderAuthError,
    ProviderHTTPError,
    ProviderNetworkError,
    ProviderUnsupportedError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["inference"])


# --- Helpers ------------------------------------------------------------------


def _not_implemented(
    *,
    message: str,
    next_task: str,
) -> JSONResponse:
    """Build the structured 501 envelope used for unimplemented surface."""

    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": {
                "code": "not_implemented",
                "message": message,
                "details": {"next_task": next_task},
            }
        },
    )


def _gateway_error(
    *,
    code: str,
    message: str,
    http_status: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a ``GatewayError``-shaped JSON response."""

    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def _config(request: Request) -> GatewayConfig:
    """Pull the loaded :class:`GatewayConfig` off ``app.state``."""

    return request.app.state.config  # type: ignore[no-any-return]


def _adapters(request: Request) -> dict[str, ProviderAdapter]:
    """Pull the adapter registry off ``app.state`` (set by lifespan)."""

    registry: dict[str, ProviderAdapter] = getattr(request.app.state, "adapters", {})
    return registry


# --- B3 routing (replaced by B4) ---------------------------------------------


def _resolve_anthropic_target(
    *,
    config: GatewayConfig,
    requested_model: str,
) -> tuple[ProviderConfig, str] | None:
    """Resolve ``requested_model`` to ``(provider_config, model_name)`` if Anthropic.

    Returns ``None`` when the model doesn't resolve to an Anthropic
    provider — the caller emits a 501 in that case so B4 has a single
    place to lift the routing.
    """

    # 1) Alias match: gateway.yaml ``model_aliases.<alias>`` whose primary
    #    points at an Anthropic provider.
    alias = config.model_aliases.get(requested_model)
    if alias is not None:
        provider = next(
            (p for p in config.providers if p.name == alias.primary.provider),
            None,
        )
        if provider is not None and provider.type == "anthropic":
            return provider, alias.primary.model

    # 2) Direct provider-native model: any Anthropic provider that lists
    #    ``requested_model`` in its ``models`` array.
    for provider in config.providers:
        if provider.type != "anthropic":
            continue
        if requested_model in provider.models:
            return provider, requested_model

    return None


# --- Route handlers -----------------------------------------------------------


@router.post("/chat/completions", response_model=None)
async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    """OpenAI-compatible chat completions.

    Body validation is local to this handler (rather than via FastAPI's
    body parser) so we can return a structured ``GatewayError`` envelope
    on validation failure instead of FastAPI's default 422 shape.
    """

    try:
        raw = await request.json()
    except json.JSONDecodeError:
        return _gateway_error(
            code="invalid_request",
            message="Request body is not valid JSON",
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(raw, dict):
        return _gateway_error(
            code="invalid_request",
            message="Request body must be a JSON object",
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        chat_request = ChatCompletionRequest.model_validate(raw)
    except ValidationError as exc:
        return _gateway_error(
            code="invalid_request",
            message="Chat completion request failed schema validation",
            http_status=status.HTTP_400_BAD_REQUEST,
            details={"errors": exc.errors()},
        )

    config = _config(request)
    target = _resolve_anthropic_target(config=config, requested_model=chat_request.model)
    if target is None:
        return _not_implemented(
            message=(
                f"Model {chat_request.model!r} does not resolve to an Anthropic "
                "provider. B3 ships only the Anthropic adapter; alias resolution "
                "for non-Anthropic providers and full router/fallback logic land "
                "in B4 (router + tier derivation) and B6 (additional adapters)."
            ),
            next_task="B4 — Gateway router + alias resolution + tier derivation",
        )

    provider_config, native_model = target
    adapter_registry = _adapters(request)
    adapter = adapter_registry.get(provider_config.name)
    if adapter is None:
        # Most common cause: env var declared in api_key_env is not set.
        return _gateway_error(
            code="provider_unavailable",
            message=(
                f"Anthropic provider {provider_config.name!r} is configured but no "
                "adapter was instantiated; check that the credential environment "
                "variable referenced by 'api_key_env' is set"
            ),
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"provider": provider_config.name},
        )

    try:
        result = await adapter.chat_completion(
            chat_request,
            model=native_model,
            stream=chat_request.stream,
        )
    except ProviderUnsupportedError as exc:
        return _gateway_error(
            code=exc.code,
            message=exc.message,
            http_status=status.HTTP_501_NOT_IMPLEMENTED,
            details=exc.details,
        )
    except ProviderAuthError as exc:
        # Don't leak which header / how the auth failed; the message
        # carries only the safe wording from the adapter.
        logger.warning("provider auth rejected: %s", exc.message)
        return _gateway_error(
            code=exc.code,
            message=exc.message,
            http_status=status.HTTP_502_BAD_GATEWAY,
            details=exc.details,
        )
    except ProviderHTTPError as exc:
        # Map upstream 429 to gateway 429 so backoff signals propagate;
        # everything else upstream becomes a 502 (bad gateway).
        upstream = exc.upstream_status
        gw_status = (
            status.HTTP_429_TOO_MANY_REQUESTS if upstream == 429 else status.HTTP_502_BAD_GATEWAY
        )
        gw_code = "rate_limit_exceeded" if upstream == 429 else exc.code
        return _gateway_error(
            code=gw_code,
            message=exc.message,
            http_status=gw_status,
            details=exc.details,
        )
    except ProviderNetworkError as exc:
        return _gateway_error(
            code=exc.code,
            message=exc.message,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=exc.details,
        )
    except ProviderAdapterError as exc:
        # Catch-all for adapter errors we didn't enumerate above.
        return _gateway_error(
            code=exc.code,
            message=exc.message,
            http_status=status.HTTP_502_BAD_GATEWAY,
            details=exc.details,
        )

    if isinstance(result, ChatCompletionResponse):
        # Stamp the routed-provider field. ``routed_inference_tier`` is
        # B4's responsibility and stays ``None`` here.
        result.routed_provider = provider_config.name
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result.model_dump(mode="json", exclude_none=True),
        )

    # Streaming.
    return StreamingResponse(
        _stream_openai_sse(result, provider_name=provider_config.name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_openai_sse(
    chunks: AsyncIterator[ChatCompletionChunk],
    *,
    provider_name: str,
) -> AsyncIterator[bytes]:
    """Serialize chunks as OpenAI-format SSE frames.

    Each chunk becomes one ``data: <json>\\n\\n`` frame; the stream ends
    with the OpenAI ``data: [DONE]\\n\\n`` sentinel.
    """

    try:
        async for chunk in chunks:
            chunk.routed_provider = provider_name
            payload = chunk.model_dump(mode="json", exclude_none=True)
            yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()
    except ProviderAdapterError as exc:
        # Mid-stream failures: emit a final SSE frame carrying the error
        # envelope so the client sees the failure rather than a silent
        # truncation. We then stop iterating.
        envelope = {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}
        yield f"data: {json.dumps(envelope, separators=(',', ':'))}\n\n".encode()
    yield b"data: [DONE]\n\n"


@router.post("/embeddings")
async def embeddings(request: Request) -> JSONResponse:
    """OpenAI-compatible embeddings — B3 stub returns 501.

    Anthropic has no embeddings endpoint; the embedding alias in
    ``gateway.yaml.example`` points at OpenAI. The full embeddings path
    lands when the OpenAI adapter ships (B6) and the router routes
    embeddings independently.
    """

    return _not_implemented(
        message=(
            "Embeddings are not yet implemented. Anthropic (B3) has no "
            "first-party embeddings endpoint; the OpenAI adapter (B6) lands "
            "the embeddings path."
        ),
        next_task="B6 — OpenAI provider adapter (embeddings)",
    )


@router.get("/models")
async def list_models(request: Request) -> dict[str, Any]:
    """Return the configured aliases as an OpenAI-shaped models list."""

    return _config(request).to_models_payload()
