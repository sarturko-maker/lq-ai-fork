"""Observability primitives for the LQ.AI backend API (PRD §5.4).

Mirrors :mod:`gateway.app.observability` — same shape, different
metric-name prefix (``lq_ai_api_*`` vs ``lq_ai_gateway_*``) so a single
Prometheus scrape across both services has unambiguous labels.

See the gateway module for design rationale. The short version:

* Prometheus ``/metrics`` is always on (operator scrapes it).
* OpenTelemetry initializes only when ``OTEL_EXPORTER_OTLP_ENDPOINT``
  is set — that is the "no telemetry by default" guarantee in PRD §5.7.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)


# --- Prometheus registry + metrics -------------------------------------------

REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "lq_ai_api_http_requests_total",
    "Total HTTP requests handled by the api, labelled by method, route, and status.",
    labelnames=("method", "route", "status"),
    registry=REGISTRY,
)
"""HTTP request counter. ``route`` is the FastAPI route template
(e.g., ``/api/v1/chats/{chat_id}``); the raw path is never used as a
label so cardinality stays bounded under attack traffic."""

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "lq_ai_api_http_request_duration_seconds",
    "Latency of HTTP requests handled by the api.",
    labelnames=("method", "route", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)
"""HTTP latency histogram. Same buckets as the gateway so dashboards
that overlay both services compare like-for-like."""


# --- HTTP middleware ----------------------------------------------------------


async def _metrics_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """ASGI middleware that records per-request metrics.

    Resolves the FastAPI route template after dispatch so the path
    label is bounded. The ``/metrics`` endpoint is excluded from the
    latency histogram (counting our own scrape inflates p99s).
    """

    start = time.monotonic()
    method = request.method
    status_label: str
    try:
        response = await call_next(request)
        status_label = str(response.status_code)
    except Exception:
        status_label = "500"
        HTTP_REQUESTS_TOTAL.labels(
            method=method, route=_route_label(request), status=status_label
        ).inc()
        raise

    route = _route_label(request)
    if route == "/metrics":
        HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=status_label).inc()
        return response

    elapsed = time.monotonic() - start
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=status_label).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route, status=status_label).observe(
        elapsed
    )
    return response


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "__unmatched__"


# --- /metrics endpoint --------------------------------------------------------


def _metrics_endpoint() -> Response:
    body = generate_latest(REGISTRY)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)


# --- Access-log secret scrub (SAAS-2, ADR-F059 §6-item-4) --------------------

# The WOPI editor-session token rides as an `access_token` query param (WOPI
# protocol design), and uvicorn's default access log records the full request
# line INCLUDING the query string — so the token would land in container logs
# in EVERY environment. This filter redacts the value defensively; the Caddy
# edge (deploy/caddy) scrubs it a second time at the public boundary.
_ACCESS_TOKEN_RE = re.compile(r"(access_token=)[^&\s\"']+")


def _scrub_access_token(value: object) -> object:
    if isinstance(value, str) and "access_token=" in value:
        return _ACCESS_TOKEN_RE.sub(r"\1REDACTED", value)
    return value


class AccessTokenLogScrubFilter(logging.Filter):
    """Redact ``access_token=<value>`` from uvicorn access-log records.

    uvicorn access records carry the request line as ``record.args``
    (``(client_addr, method, full_path, http_version, status_code)``) with the
    query string in ``full_path``; we rewrite the args in place. If the record
    shape differs (already-formatted message, dict args), we fall back to
    scrubbing ``record.msg``. A malformed record never raises — logging must not
    be broken by the scrubber, so the filter always returns ``True``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            if isinstance(args, tuple) and args:
                scrubbed = tuple(_scrub_access_token(a) for a in args)
                if scrubbed != args:
                    record.args = scrubbed
            if isinstance(record.msg, str) and "access_token=" in record.msg:
                record.msg = _ACCESS_TOKEN_RE.sub(r"\1REDACTED", record.msg)
        except Exception:  # scrubbing must never break logging
            pass
        return True


def _install_access_log_scrub() -> None:
    """Attach the access-token scrubber to the ``uvicorn.access`` logger (idempotent)."""
    access_logger = logging.getLogger("uvicorn.access")
    if any(isinstance(f, AccessTokenLogScrubFilter) for f in access_logger.filters):
        return
    access_logger.addFilter(AccessTokenLogScrubFilter())


# --- OpenTelemetry bootstrap --------------------------------------------------


_OTEL_INITIALIZED = False


def _otel_enabled(env: dict[str, str] | None = None) -> bool:
    """Return True iff the operator has opted in to OTel export."""

    src = env if env is not None else os.environ
    for key in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    ):
        if src.get(key):
            return True
    return False


def _maybe_init_otel(service_name: str, service_version: str) -> None:
    """Initialize the OTel SDK if the operator opted in (PRD §5.7)."""

    global _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        return
    if not _otel_enabled():
        logger.debug(
            "OTel not initialized: OTEL_EXPORTER_OTLP_ENDPOINT unset "
            "(no-telemetry-by-default per PRD §5.7)"
        )
        return

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

    Idempotent — safe to call once per FastAPI app. Middleware must be
    added BEFORE routes so it wraps everything else; the ``/metrics``
    route is added here so the api's lifespan doesn't need to learn
    about it.
    """

    app.middleware("http")(_metrics_middleware)
    app.add_api_route(
        "/metrics",
        _metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )
    # ADR-F059 — scrub the WOPI access_token out of uvicorn's access log.
    _install_access_log_scrub()
    _maybe_init_otel(service_name=service_name, service_version=service_version)
    _instrument_fastapi(app)
