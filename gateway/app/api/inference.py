"""OpenAI-compatible inference endpoints (B4 router landed).

Surface:

* ``POST /v1/chat/completions`` — accepts an OpenAI-format chat-completion
  request, runs it through :class:`app.router.Router`, returns the
  OpenAI-shaped response stamped with ``routed_inference_tier`` and
  ``routed_provider``. The HTTP response also carries the tier in a
  dedicated header (:data:`TIER_HEADER`) so header-only consumers
  (proxies, instrumentation) don't need to parse the body.
* ``POST /v1/embeddings`` — 501 stub. Embeddings adapter lands later;
  Anthropic has no embeddings endpoint.
* ``GET  /v1/models`` — returns the configured ``model_aliases`` from
  ``gateway.yaml``.

What B4 added on top of B3
--------------------------

* **Real router.** The B3-era ``_resolve_anthropic_target`` is gone;
  alias resolution + tier derivation + dispatch + fallback live in
  :mod:`app.router`. Anthropic remains the only adapter; the dispatch
  is registry-based, so B6 plugs in additional adapters by registering
  themselves rather than touching this handler.
* **Tier annotation.** Every routed request is annotated with
  ``routed_inference_tier`` (1-5). The annotation appears in:

  * The HTTP response header :data:`TIER_HEADER` (header-only consumers).
  * The response body's ``routed_inference_tier`` extension field
    (already documented in ``docs/api/gateway-openapi.yaml``).
  * The ``inference_routing_log`` audit row (DB-backed audit trail).

  Both surfaces are populated for parity. Documented in
  ``docs/api/gateway-openapi.yaml`` and ``docs/PRD.md`` §4.
* **Routing-log writes.** Every request — successful or failed — writes
  one row to ``inference_routing_log`` via the configured
  :class:`app.routing_log.RoutingLogWriter`. The writer never raises
  out of :meth:`write`, so audit-log unavailability cannot block an
  inference call.
* **Fallback chain.** When the primary provider returns a
  fallback-eligible error, the router walks the alias's configured
  ``fallback`` list. With only Anthropic shipped today this is dead
  code in production, but unit-tested with mocked adapters so it's
  ready when B6 lands additional providers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Final

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.clients.backend import BackendClient, Skill, get_backend_client
from app.config import GatewayConfig
from app.errors import LQAIError
from app.providers import (
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ProviderAdapter,
    ProviderAdapterError,
    ProviderAuthError,
    ProviderHTTPError,
    ProviderNetworkError,
    ProviderUnsupportedError,
)
from app.skills import assemble_skill_prompt
from app.router import (
    ChatCompletionRoutedResult,
    ModelResolutionError,
    NoAdapterAvailableError,
    ResolvedTarget,
    RoutedProviderError,
    Router,
    estimate_cost,
    synthesize_request_id,
)
from app.routing_log import (
    InferenceRoutingLogRow,
    NullRoutingLogWriter,
    RoutingLogWriter,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["inference"])


TIER_HEADER: Final[str] = "X-LQ-AI-Routed-Inference-Tier"
"""HTTP response header carrying the routed Inference Tier (1-5).

Documented in ``docs/api/gateway-openapi.yaml``. The body's
``routed_inference_tier`` extension field carries the same value;
the header exists so header-only consumers (HTTP-tracing proxies,
front-end instrumentation) don't have to parse the body."""

PROVIDER_HEADER: Final[str] = "X-LQ-AI-Routed-Provider"
"""HTTP response header carrying the provider name that handled the request."""


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


def _map_provider_error_to_response(exc: ProviderAdapterError) -> JSONResponse:
    """Map a :class:`ProviderAdapterError` to the right HTTP status + envelope.

    Centralizes the mapping so the streaming and non-streaming paths use
    the same rules. Per the gateway-openapi.yaml error enum:

    * Auth errors → ``unauthorized`` / 502 (the gateway is its own auth
      domain; an upstream credential failure is a misconfiguration, not
      the caller's fault).
    * Upstream 429 → ``rate_limit_exceeded`` / 429.
    * Upstream other 4xx → ``provider_unavailable`` / 502.
    * Upstream 5xx (after fallback exhausted) → ``provider_unavailable`` /
      502.
    * Network / DNS / TLS / timeout → ``provider_unavailable`` / 503.
    * ``ProviderUnsupportedError`` → ``not_implemented`` / 501.
    """

    if isinstance(exc, ProviderUnsupportedError):
        return _gateway_error(
            code=exc.code,
            message=exc.message,
            http_status=status.HTTP_501_NOT_IMPLEMENTED,
            details=exc.details,
        )
    if isinstance(exc, ProviderAuthError):
        logger.warning("provider auth rejected: %s", exc.message)
        return _gateway_error(
            code=exc.code,
            message=exc.message,
            http_status=status.HTTP_502_BAD_GATEWAY,
            details=exc.details,
        )
    if isinstance(exc, ProviderHTTPError):
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
    if isinstance(exc, ProviderNetworkError):
        return _gateway_error(
            code=exc.code,
            message=exc.message,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=exc.details,
        )
    return _gateway_error(
        code=exc.code,
        message=exc.message,
        http_status=status.HTTP_502_BAD_GATEWAY,
        details=exc.details,
    )


def _config(request: Request) -> GatewayConfig:
    """Pull the loaded :class:`GatewayConfig` off ``app.state``."""

    return request.app.state.config  # type: ignore[no-any-return]


def _backend(request: Request) -> BackendClient:
    """Return the gateway's :class:`BackendClient`.

    The lifespan handler installs ``app.state.backend_client``; tests
    that bypass lifespan get the process-global default.
    """

    pre_built: BackendClient | None = getattr(request.app.state, "backend_client", None)
    if pre_built is not None:
        return pre_built
    return get_backend_client()


async def _apply_skill_prompt_assembly(
    chat_request: ChatCompletionRequest,
    *,
    backend: BackendClient,
    request_id: str,
) -> list[str]:
    """Mutate ``chat_request`` in place to include skill-assembled content.

    Returns the names of skills whose content was actually fetched and
    assembled (i.e., the value to surface as ``lq_ai_applied_skills`` on
    the response).

    No-ops when ``lq_ai_skills`` is empty.

    Raises :class:`LQAIError` subclasses on fetch failure / missing
    required input. The route handler's ``LQAIError`` handler in
    :mod:`app.main` translates them to the canonical envelope.
    """

    if not chat_request.lq_ai_skills:
        return []

    # Fetch each skill (cache-aware). Fail-fast on the first failure;
    # we don't try to dispatch a request with a partial skill block.
    skills: list[Skill] = []
    for name in chat_request.lq_ai_skills:
        skill = await backend.get_skill(name, request_id=request_id)
        skills.append(skill)

    # Pull out any existing system message(s). OpenAI permits multiple;
    # we concatenate them with a blank line so the assembler can
    # prepend skill content as one block.
    system_chunks: list[str] = []
    non_system: list[ChatCompletionMessage] = []
    for msg in chat_request.messages:
        if msg.role == "system" and msg.content:
            system_chunks.append(msg.content)
        else:
            non_system.append(msg)
    existing_system = "\n\n".join(s for s in system_chunks if s)

    assembled = assemble_skill_prompt(
        skills,
        skill_inputs=chat_request.lq_ai_skill_inputs or {},
        existing_system_message=existing_system or None,
    )

    new_system = ChatCompletionMessage(role="system", content=assembled)
    chat_request.messages = [new_system, *non_system]

    # Audit-log tagging: surface the first attached skill in the
    # B3-era ``skill_name`` field if the caller didn't set it.
    if not chat_request.skill_name and chat_request.lq_ai_skills:
        chat_request.skill_name = chat_request.lq_ai_skills[0]

    return [skill.name for skill in skills]


def _adapters(request: Request) -> dict[str, ProviderAdapter]:
    """Pull the adapter registry off ``app.state`` (set by lifespan)."""

    registry: dict[str, ProviderAdapter] = getattr(request.app.state, "adapters", {})
    return registry


def _router(request: Request) -> Router:
    """Pull the :class:`Router` instance off ``app.state``.

    The lifespan constructs the router after config + adapters are
    loaded; if it isn't there (lifespan didn't run, e.g., a test that
    bypassed startup) we fall back to constructing one on the fly.
    """

    pre_built: Router | None = getattr(request.app.state, "router", None)
    if pre_built is not None:
        return pre_built
    return Router(config=_config(request), adapters=_adapters(request))


def _routing_log(request: Request) -> RoutingLogWriter:
    """Pull the :class:`RoutingLogWriter` off ``app.state`` (lifespan-bound)."""

    writer: RoutingLogWriter | None = getattr(request.app.state, "routing_log", None)
    return writer if writer is not None else NullRoutingLogWriter()


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
    gw_router = _router(request)
    log_writer = _routing_log(request)
    request_id = synthesize_request_id(_request_id_header(request))

    # --- Skill prompt assembly (C2) ----------------------------------------
    # Mutates chat_request in place: replaces system message(s) with
    # the assembled skill content (skills first, operator system
    # message after a separator). Errors here are typed LQAIError
    # subclasses (SkillNotFound / SkillFetchFailed / SkillInputMissing);
    # let them propagate to the FastAPI handler so the canonical
    # envelope wraps them.
    applied_skills: list[str] = []
    if chat_request.lq_ai_skills:
        backend = _backend(request)
        try:
            applied_skills = await _apply_skill_prompt_assembly(
                chat_request,
                backend=backend,
                request_id=request_id,
            )
        except LQAIError:
            # Re-raise — the global LQAIError handler in app.main
            # serializes the canonical envelope. We don't write a
            # routing-log row here because the request never reached
            # an adapter.
            raise

    # --- Resolution (no upstream call yet) ----------------------------------
    try:
        candidates = gw_router.resolve(chat_request.model)
    except ModelResolutionError as exc:
        await _write_unresolved(
            log_writer,
            chat_request=chat_request,
            request_id=request_id,
            message=str(exc),
        )
        return _gateway_error(
            code="invalid_model",
            message=str(exc),
            http_status=status.HTTP_400_BAD_REQUEST,
            details={"requested_model": chat_request.model},
        )

    # --- Streaming path -----------------------------------------------------
    if chat_request.stream:
        return await _stream_with_fallback(
            request=request,
            chat_request=chat_request,
            candidates=candidates,
            log_writer=log_writer,
            request_id=request_id,
            applied_skills=applied_skills,
        )

    # --- Non-streaming path -------------------------------------------------
    try:
        result = await gw_router.chat_completion(chat_request)
    except RoutedProviderError as wrapped:
        # The router attributes the failure to the actual target that
        # produced the error (rather than the last candidate). Unwrap
        # here, write the routing-log row with that target, and map the
        # underlying error to the right HTTP status.
        await _write_failure(
            log_writer,
            chat_request=chat_request,
            target=wrapped.target,
            request_id=request_id,
            error=wrapped.error,
            latency_ms=wrapped.latency_ms,
        )
        return _map_provider_error_to_response(wrapped.error)
    except NoAdapterAvailableError as exc:
        await _write_unavailable(
            log_writer,
            chat_request=chat_request,
            target=candidates[0],
            request_id=request_id,
            message=exc.message,
        )
        return _gateway_error(
            code="provider_unavailable",
            message=exc.message,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"provider": candidates[0].provider.name},
        )

    # --- Success: stamp tier on body, write log, return --------------------
    annotated = _annotate_response(result.response, target=result.target, config=config)
    if applied_skills:
        annotated.lq_ai_applied_skills = list(applied_skills)
    await _write_success(
        log_writer,
        chat_request=chat_request,
        result=result,
        request_id=request_id,
        cost_estimate=annotated.cost_estimate,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=annotated.model_dump(mode="json", exclude_none=True),
        headers={
            TIER_HEADER: str(result.target.routed_inference_tier),
            PROVIDER_HEADER: result.target.provider.name,
        },
    )


@router.post("/embeddings")
async def embeddings(request: Request) -> JSONResponse:
    """OpenAI-compatible embeddings — B4 still 501 (lands with B6)."""

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


# --- Streaming helpers --------------------------------------------------------


async def _stream_with_fallback(
    *,
    request: Request,
    chat_request: ChatCompletionRequest,
    candidates: list[ResolvedTarget],
    log_writer: RoutingLogWriter,
    request_id: str,
    applied_skills: list[str] | None = None,
) -> StreamingResponse:
    """Run the streaming path with primary + fallback chain.

    The router's :meth:`Router.chat_completion` only handles the
    non-streaming case; for streaming we walk candidates here so we can
    inject the tier annotation into each chunk before it goes out the
    wire and write the routing-log row when the stream finishes.

    Streaming surfaces the tier two ways: in the response headers (the
    same :data:`TIER_HEADER` as non-streaming) and inside each
    :class:`ChatCompletionChunk` envelope's
    ``routed_inference_tier`` field. We can't write the routing-log
    row until the stream completes (we need final token usage), so the
    write happens at the end of the iterator.
    """

    adapter_registry = _adapters(request)

    # Pick the first candidate with an adapter as the streaming target.
    # Streaming fallback (start one stream, abort, start another) is
    # operator-hostile — partial output to the client makes the
    # handover ambiguous. For now, streaming uses only the first
    # available candidate; if that fails before producing any output
    # the client sees an SSE error frame. Fallback for streaming is
    # tracked as a follow-up (see deferred items in M1-PROGRESS).
    target: ResolvedTarget | None = None
    adapter: ProviderAdapter | None = None
    for candidate in candidates:
        candidate_adapter = adapter_registry.get(candidate.provider.name)
        if candidate_adapter is not None:
            target = candidate
            adapter = candidate_adapter
            break

    if target is None or adapter is None:
        await _write_unavailable(
            log_writer,
            chat_request=chat_request,
            target=candidates[0],
            request_id=request_id,
            message="no adapter available for streaming",
        )
        return StreamingResponse(
            _single_error_sse(
                code="provider_unavailable",
                message=(
                    "No adapter available to handle the request; check that the "
                    "provider's credential env var is set"
                ),
            ),
            media_type="text/event-stream",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={
                TIER_HEADER: str(candidates[0].routed_inference_tier),
                PROVIDER_HEADER: candidates[0].provider.name,
            },
        )

    config = _config(request)

    async def upstream() -> AsyncIterator[ChatCompletionChunk]:
        # Adapter contract: stream=True returns an AsyncIterator[ChatCompletionChunk].
        produced = await adapter.chat_completion(
            chat_request,
            model=target.native_model,
            stream=True,
        )
        if isinstance(produced, ChatCompletionResponse):
            # Defensive — adapters shouldn't do this with stream=True.
            raise RuntimeError("adapter returned a response object for stream=True")
        async for chunk in produced:
            yield chunk

    return StreamingResponse(
        _stream_openai_sse(
            upstream(),
            target=target,
            config=config,
            chat_request=chat_request,
            log_writer=log_writer,
            request_id=request_id,
            applied_skills=applied_skills or [],
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            TIER_HEADER: str(target.routed_inference_tier),
            PROVIDER_HEADER: target.provider.name,
        },
    )


async def _stream_openai_sse(
    chunks: AsyncIterator[ChatCompletionChunk],
    *,
    target: ResolvedTarget,
    config: GatewayConfig,
    chat_request: ChatCompletionRequest,
    log_writer: RoutingLogWriter,
    request_id: str,
    applied_skills: list[str] | None = None,
) -> AsyncIterator[bytes]:
    """Serialize chunks as OpenAI-format SSE frames; write log on completion."""

    final_usage: ChatCompletionRoutedResult | None = None  # noqa: F841
    last_chunk: ChatCompletionChunk | None = None

    try:
        async for chunk in chunks:
            chunk.routed_provider = target.provider.name
            chunk.routed_inference_tier = target.routed_inference_tier
            if applied_skills:
                chunk.lq_ai_applied_skills = list(applied_skills)
            last_chunk = chunk
            payload = chunk.model_dump(mode="json", exclude_none=True)
            yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()
    except ProviderAdapterError as exc:
        envelope = {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}
        yield f"data: {json.dumps(envelope, separators=(',', ':'))}\n\n".encode()
        await _write_failure(
            log_writer,
            chat_request=chat_request,
            target=target,
            request_id=request_id,
            error=exc,
            latency_ms=None,
        )
        yield b"data: [DONE]\n\n"
        return

    yield b"data: [DONE]\n\n"

    # Persist the routing-log row using the final chunk's usage block.
    usage = (last_chunk.usage if last_chunk is not None else None) or None
    cost = (
        estimate_cost(
            provider_name=target.provider.name,
            native_model=target.native_model,
            usage=usage,
            rates=config.cost_tracking.rates,
        )
        if usage is not None
        else None
    )
    await log_writer.write(
        InferenceRoutingLogRow(
            requested_model=chat_request.model,
            routed_provider=target.provider.name,
            routed_model=target.native_model,
            routed_inference_tier=target.routed_inference_tier,
            tokens_in=(usage.prompt_tokens if usage is not None else None),
            tokens_out=(usage.completion_tokens if usage is not None else None),
            cost_estimate=cost,
            latency_ms=None,  # streaming latency is wall-time; left null for now
            request_id=request_id,
        )
    )


async def _single_error_sse(*, code: str, message: str) -> AsyncIterator[bytes]:
    """Emit a single SSE error frame plus ``[DONE]``."""

    envelope = {"error": {"code": code, "message": message, "details": {}}}
    yield f"data: {json.dumps(envelope, separators=(',', ':'))}\n\n".encode()
    yield b"data: [DONE]\n\n"


# --- Routing-log writers ------------------------------------------------------


def _annotate_response(
    response: ChatCompletionResponse,
    *,
    target: ResolvedTarget,
    config: GatewayConfig,
) -> ChatCompletionResponse:
    """Stamp the routed-tier and routed-provider fields plus cost estimate."""

    response.routed_provider = target.provider.name
    response.routed_inference_tier = target.routed_inference_tier
    cost = estimate_cost(
        provider_name=target.provider.name,
        native_model=target.native_model,
        usage=response.usage,
        rates=config.cost_tracking.rates,
    )
    if cost is not None:
        response.cost_estimate = float(cost)
    return response


async def _write_success(
    writer: RoutingLogWriter,
    *,
    chat_request: ChatCompletionRequest,
    result: ChatCompletionRoutedResult,
    request_id: str,
    cost_estimate: float | None,
) -> None:
    from decimal import Decimal as _Decimal

    cost: _Decimal | None = None
    if cost_estimate is not None:
        cost = _Decimal(str(cost_estimate))

    await writer.write(
        InferenceRoutingLogRow(
            requested_model=chat_request.model,
            routed_provider=result.target.provider.name,
            routed_model=result.target.native_model,
            routed_inference_tier=result.target.routed_inference_tier,
            tokens_in=result.response.usage.prompt_tokens,
            tokens_out=result.response.usage.completion_tokens,
            cost_estimate=cost,
            latency_ms=result.latency_ms,
            request_id=request_id,
        )
    )


async def _write_failure(
    writer: RoutingLogWriter,
    *,
    chat_request: ChatCompletionRequest,
    target: ResolvedTarget,
    request_id: str,
    error: ProviderAdapterError,
    latency_ms: int | None,
) -> None:
    """Write a routing-log row for a request that reached an adapter and failed.

    The tier is still derived (the choke-point invariant) and the row
    captures the error code in ``refusal_reason`` so operators can grep
    for upstream-induced failures even though ``refused`` is technically
    a tier-floor concept (per D1). We use ``refused = false`` here
    because the tier policy did not refuse the request — the upstream
    failed. ``refusal_reason`` is overloaded as a free-text "why this
    row didn't carry usage data" — the schema's nullability accommodates
    that. D1 will tighten the semantics; we add a follow-up note in
    docs/M1-PROGRESS.md.
    """

    await writer.write(
        InferenceRoutingLogRow(
            requested_model=chat_request.model,
            routed_provider=target.provider.name,
            routed_model=target.native_model,
            routed_inference_tier=target.routed_inference_tier,
            latency_ms=latency_ms,
            refused=False,
            refusal_reason=f"upstream_error:{error.code}",
            request_id=request_id,
        )
    )


async def _write_unavailable(
    writer: RoutingLogWriter,
    *,
    chat_request: ChatCompletionRequest,
    target: ResolvedTarget,
    request_id: str,
    message: str,
) -> None:
    """Write a routing-log row when no adapter could handle the request."""

    await writer.write(
        InferenceRoutingLogRow(
            requested_model=chat_request.model,
            routed_provider=target.provider.name,
            routed_model=target.native_model,
            routed_inference_tier=target.routed_inference_tier,
            refused=False,
            refusal_reason=f"adapter_unavailable:{message}",
            request_id=request_id,
        )
    )


async def _write_unresolved(
    writer: RoutingLogWriter,
    *,
    chat_request: ChatCompletionRequest,
    request_id: str,
    message: str,
) -> None:
    """Write a routing-log row when the request couldn't even resolve.

    The schema requires ``routed_provider``, ``routed_model``, and
    ``routed_inference_tier`` to be NOT NULL; we use the literal
    sentinels ``"<unresolved>"`` and tier ``1`` so the row schema is
    valid and operators can still see the request was received. The
    ``refusal_reason`` carries the diagnostic.

    Tier ``1`` is the safest sentinel — it means "fully local, no data
    leaves the deployment", which is the conservative posture for "we
    don't know where this would have gone".
    """

    await writer.write(
        InferenceRoutingLogRow(
            requested_model=chat_request.model,
            routed_provider="<unresolved>",
            routed_model="<unresolved>",
            routed_inference_tier=1,
            refused=True,
            refusal_reason=f"invalid_model:{message}",
            request_id=request_id,
        )
    )


# --- Misc helpers -------------------------------------------------------------


def _request_id_header(request: Request) -> str | None:
    """Pull the upstream request id if the caller supplied one.

    Backend services typically forward their own request id (X-Request-Id)
    so downstream rows correlate with upstream traces. We accept either
    spelling for tolerance.
    """

    for name in ("x-request-id", "x-correlation-id"):
        header = request.headers.get(name)
        if header:
            return header
    return None
