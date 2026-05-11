"""Observability primitives for the LQ.AI Inference Gateway (PRD §5.4).

Two surfaces:

* **Prometheus** — ``/metrics`` endpoint, mounted on the FastAPI app.
  The metric set is small on purpose: HTTP-level counters/histograms
  (driven by middleware) plus a gateway-specific counter that fires
  once per routed inference request, labelled by provider and tier.
  Operators scrape the endpoint from their existing infra; LQ.AI does
  not push.
* **OpenTelemetry** — opt-in. Initialized only when the operator sets
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or the related OTEL env vars per
  the OTLP/HTTP exporter spec). When unset, this module is a no-op
  beyond exposing the constants — the SDK is imported but no
  TracerProvider is registered. That is the "no telemetry by default"
  guarantee in PRD §5.7.

The metrics names follow the Prometheus naming conventions
(``snake_case``, unit suffixes per the OpenMetrics rules: ``_total``
for counters, ``_seconds`` for time-valued histograms). Label
cardinality is bounded — the HTTP path label is the FastAPI route
template (``/v1/chat/completions``), not the raw URL, so cardinality
stays small even under heavy traffic.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# --- Prometheus registry + metrics -------------------------------------------

# Dedicated registry — keeps gateway metrics isolated from process-global
# state (no accidental cross-talk with libraries that also use the default
# registry). The /metrics handler renders this registry explicitly.
REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "lq_ai_gateway_http_requests_total",
    "Total HTTP requests handled by the gateway, labelled by method, route, and status.",
    labelnames=("method", "route", "status"),
    registry=REGISTRY,
)
"""HTTP request counter. ``route`` is the FastAPI route template
(e.g., ``/v1/chat/completions``); the raw path is never used as a
label to keep cardinality bounded."""

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "lq_ai_gateway_http_request_duration_seconds",
    "Latency of HTTP requests handled by the gateway.",
    labelnames=("method", "route", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)
"""HTTP latency histogram. Buckets are tuned for a mix of fast admin
calls (sub-100ms) and chat-completion long-poll requests (multi-second
to tens of seconds for non-streamed completions)."""

INFERENCE_REQUESTS_TOTAL = Counter(
    "lq_ai_gateway_inference_requests_total",
    "Inference requests dispatched by the router, labelled by provider, tier, and outcome.",
    labelnames=("provider", "tier", "outcome"),
    registry=REGISTRY,
)
"""Inference dispatch counter. ``outcome`` ∈ {``success``, ``refused``,
``provider_error``, ``network_error``}; ``tier`` is the resolved
Inference Tier (1-5) as a string; ``provider`` is the operator-chosen
provider name (e.g., ``anthropic-prod``). The router records one row
per request immediately after dispatch."""


# --- HTTP middleware ----------------------------------------------------------


async def _metrics_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """ASGI middleware that records per-request metrics.

    Resolves the FastAPI route template at the end of the request so
    we label by the matched path pattern rather than the raw URL. If
    no route matched (404 / 405 / etc.) we label with ``__unmatched__``
    so cardinality stays bounded.

    The ``/metrics`` endpoint itself is excluded from the histogram —
    counting our own scrape calls inflates the percentile baseline and
    breaks alerting on real traffic.
    """

    start = time.monotonic()
    method = request.method
    response: Response | None = None
    status_label: str
    try:
        response = await call_next(request)
        status_label = str(response.status_code)
    except Exception:
        # The error reaches the FastAPI exception handlers, which produce
        # the response. We record a synthetic 500 row so the failure is
        # at least counted; re-raise so the handler runs normally.
        status_label = "500"
        HTTP_REQUESTS_TOTAL.labels(method=method, route=_route_label(request), status=status_label).inc()
        raise

    route = _route_label(request)
    if route == "/metrics":
        # Don't record the scrape itself in the histogram (keeps p99s honest).
        HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=status_label).inc()
        return response

    elapsed = time.monotonic() - start
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=status_label).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method, route=route, status=status_label
    ).observe(elapsed)
    return response


def _route_label(request: Request) -> str:
    """Return the FastAPI route template for ``request``, or a sentinel.

    Reads ``request.scope['route']`` if Starlette resolved it; otherwise
    returns ``__unmatched__``. The sentinel prevents cardinality blowup
    on attack traffic that probes random paths.
    """

    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "__unmatched__"


# --- /metrics endpoint --------------------------------------------------------


def _metrics_endpoint() -> Response:
    """Render the registry in the Prometheus text exposition format."""

    body = generate_latest(REGISTRY)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)


# --- OpenTelemetry bootstrap --------------------------------------------------


_OTEL_INITIALIZED = False
"""Module-level guard: the SDK can only be initialized once per process.

A second initialization call from a test fixture or a SIGHUP-style
reload would either no-op (best case) or duplicate the exporter (worst
case). We track explicitly so the second call is a clean no-op."""


def _otel_enabled(env: dict[str, str] | None = None) -> bool:
    """Return True iff the operator has opted in to OTel export.

    The trigger is any of ``OTEL_EXPORTER_OTLP_ENDPOINT``,
    ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT``, or
    ``OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`` being set. Matches the
    standard OTel autoconfiguration trigger so operators who already
    use the OTel ecosystem don't need to learn LQ.AI-specific env vars.
    """

    src = env if env is not None else os.environ
    for key in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    ):
        value = src.get(key)
        if value:
            return True
    return False


def _maybe_init_otel(service_name: str, service_version: str) -> None:
    """Initialize the OTel SDK if the operator has opted in.

    No-op when ``_otel_enabled()`` is False — that's the "no telemetry
    by default" guarantee. When enabled, registers a TracerProvider
    with an OTLP/HTTP exporter and attaches FastAPI + httpx
    instrumentation. The exporter respects the standard OTel env vars
    (``OTEL_EXPORTER_OTLP_ENDPOINT`` for the base URL, the per-signal
    overrides if set, ``OTEL_SERVICE_NAME`` to override service name,
    etc.) so operators configure once for the whole stack.

    Imported lazily so the OTel deps don't fire at module import time
    in deployments that don't use them (keeps cold-start fast and
    failure modes contained).
    """

    global _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        return
    if not _otel_enabled():
        logger.debug(
            "OTel not initialized: OTEL_EXPORTER_OTLP_ENDPOINT unset "
            "(no-telemetry-by-default per PRD §5.7)"
        )
        return

    # Lazy import — these are the heavyweight deps. We bury them inside
    # the conditional so deployments that disable OTel don't pay the
    # import-time cost.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME") or service_name,
            "service.version": service_version,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _OTEL_INITIALIZED = True
    logger.info(
        "OTel initialized: service.name=%s, otlp endpoint=%s",
        service_name,
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )


def _instrument_fastapi(app: FastAPI) -> None:
    """Attach FastAPI + httpx auto-instrumentation, if OTel is enabled.

    Runs after the FastAPI app is constructed (so the instrumentor can
    walk the routing tree). No-op when OTel is not enabled. Separating
    this from :func:`_maybe_init_otel` lets tests construct apps
    without spending time on instrumentation walks.
    """

    if not _OTEL_INITIALIZED:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


# --- Public surface ----------------------------------------------------------


def install_observability(
    app: FastAPI,
    *,
    service_name: str,
    service_version: str,
) -> None:
    """Wire metrics middleware, ``/metrics`` endpoint, and optional OTel.

    Idempotent: safe to call once per FastAPI app. Tests can call this
    on a fresh app without polluting global state — the registry and
    the OTel init guard are the only module-level state.

    Order matters: the middleware is added BEFORE any route registers
    so it's the outermost middleware in the stack and records every
    response (including FastAPI's own exception-handler output).
    """

    # Middleware first so it wraps everything else.
    app.middleware("http")(_metrics_middleware)

    # GET /metrics — Prometheus scrape target. Tagged out of the OpenAPI
    # schema since it's an infra surface, not a product surface.
    app.add_api_route(
        "/metrics",
        _metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )

    # OTel — only fires if the operator opted in via env.
    _maybe_init_otel(service_name=service_name, service_version=service_version)
    _instrument_fastapi(app)
