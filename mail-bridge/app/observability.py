"""OpenTelemetry init for the Mail Bridge.

Mirrors ``slack-bridge/app/observability.py`` (and ``api``/``gateway``) at the
M1 substrate level: opt-in via ``OTEL_EXPORTER_OTLP_ENDPOINT``,
auto-instrumentation for FastAPI + httpx, no domain metrics.
"""

from __future__ import annotations

import logging

import httpx

from .config import Settings

log = logging.getLogger(__name__)

_otel_enabled = False


def mute_url_logging() -> None:
    """Stop httpx from logging full request URLs.

    SECURITY, not tidiness: ``httpx`` logs ``HTTP Request: GET <full url>`` at
    INFO, and this bridge's attachment downloads use AgentMail's **presigned
    CDN links, which are themselves the credential** (unauthenticated, ~1 h
    TTL — ``docs/fork/evidence/intake-probe/findings.md`` verdict (b)). At INFO
    the signature would land in the log stream even though none of our own log
    lines carry it. Capping the third-party loggers at WARNING closes that.

    Called once at the composition root; the bridge emits no request-level
    tracing of its own, so nothing is lost.
    """

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def init_otel(settings: Settings) -> None:
    """Initialise OTel TracerProvider + auto-instrumentations.

    No-op when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset (PRD §5.7
    no-telemetry-by-default promise applies here too).
    """

    global _otel_enabled

    if not settings.otel_exporter_otlp_endpoint:
        _otel_enabled = False
        log.info(
            "otel.disabled — OTEL_EXPORTER_OTLP_ENDPOINT unset; bridge will "
            "emit no telemetry. Per PRD §5.7's no-telemetry-by-default."
        )
        return

    # Lazy import keeps the OTel surface out of the startup hot-path for
    # operators who don't opt in.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {"service.name": settings.otel_service_name, "service.namespace": "lq-ai"}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    trace.set_tracer_provider(provider)

    # NOTE: httpx is deliberately NOT instrumented process-globally here —
    # see instrument_http_client below.
    _otel_enabled = True

    log.info(
        "otel.initialised — exporter=%s, service.name=%s",
        settings.otel_exporter_otlp_endpoint,
        settings.otel_service_name,
    )


def instrument_http_client(client: httpx.AsyncClient) -> None:
    """Trace ONE httpx client, opt-in per client.

    SECURITY, and the reason this is not the usual process-global
    ``HTTPXClientInstrumentor().instrument()``: the instrumentation records the
    full request URL as a span attribute, and the bridge's attachment downloads
    use AgentMail's presigned CDN links, which ARE the credential. A global
    patch would put a live signature into every trace — the same leak class as
    the httpx INFO log that :func:`mute_url_logging` closes, just via a
    different sink.

    So the caller instruments the clients whose URLs are safe (the LQ.AI api and
    the AgentMail REST API) and leaves the CDN client untraced.

    No-op when OTel is disabled, and defensively no-op if the installed
    instrumentation does not expose per-client instrumentation — never a global
    fallback, which is the thing this exists to avoid.
    """

    if not _otel_enabled:
        return

    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    instrument_client = getattr(HTTPXClientInstrumentor, "instrument_client", None)
    if instrument_client is None:  # pragma: no cover - depends on installed version
        log.warning(
            "otel.httpx.per_client_unavailable — httpx spans disabled rather than "
            "risking a presigned attachment URL in a span attribute."
        )
        return
    instrument_client(client)
