"""Unit tests for the api observability surface (M-Obs.1 / PRD §5.4).

Mirrors gateway/tests/test_observability.py. Covers:

* ``/metrics`` endpoint mounts and serves Prometheus text format.
* HTTP middleware records counter + histogram rows per request.
* ``/metrics`` itself is excluded from the latency histogram.
* OpenTelemetry stays dormant unless the operator opts in via env.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.observability import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    _otel_enabled,
    install_observability,
)


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/hello")
    async def hello() -> dict[str, str]:
        return {"hello": "world"}

    install_observability(
        app, service_name="lq-ai-api-test", service_version="0.0.0-test"
    )
    return app


@pytest.mark.unit
def test_metrics_endpoint_serves_text_format() -> None:
    """``GET /metrics`` returns Prometheus text exposition format."""

    app = _build_app()
    with TestClient(app) as client:
        client.get("/api/v1/hello")
        response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "lq_ai_api_http_requests_total" in body
    families = {f.name for f in text_string_to_metric_families(body)}
    # Parser strips ``_total`` suffix from counter family names.
    assert "lq_ai_api_http_requests" in families


@pytest.mark.unit
def test_http_request_increments_counter_and_histogram() -> None:
    """A successful 200 increments both the counter and the histogram."""

    app = _build_app()
    before_count = _counter_value(
        HTTP_REQUESTS_TOTAL,
        labels={"method": "GET", "route": "/api/v1/hello", "status": "200"},
    )
    before_hist = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/api/v1/hello", "status": "200"},
    )
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/api/v1/hello").status_code == 200
    after_count = _counter_value(
        HTTP_REQUESTS_TOTAL,
        labels={"method": "GET", "route": "/api/v1/hello", "status": "200"},
    )
    after_hist = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/api/v1/hello", "status": "200"},
    )
    assert after_count - before_count == 3
    assert after_hist - before_hist == 3


@pytest.mark.unit
def test_metrics_endpoint_excluded_from_histogram() -> None:
    """``/metrics`` counted but not added to the latency histogram."""

    app = _build_app()
    before = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/metrics", "status": "200"},
    )
    with TestClient(app) as client:
        client.get("/metrics")
        client.get("/metrics")
    after = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/metrics", "status": "200"},
    )
    assert after == before


@pytest.mark.unit
def test_unmatched_route_labels_with_sentinel() -> None:
    """A 404 on an unknown path is labelled ``__unmatched__`` (bounded cardinality)."""

    app = _build_app()
    with TestClient(app) as client:
        assert client.get("/nope/this/does/not/exist").status_code == 404
    value = _counter_value(
        HTTP_REQUESTS_TOTAL,
        labels={"method": "GET", "route": "__unmatched__", "status": "404"},
    )
    assert value >= 1


@pytest.mark.unit
def test_otel_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the OTel env var set, the SDK is not initialized (PRD §5.7)."""

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    assert _otel_enabled() is False


@pytest.mark.unit
def test_otel_enabled_when_endpoint_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting ``OTEL_EXPORTER_OTLP_ENDPOINT`` flips the opt-in to True."""

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    assert _otel_enabled() is True


# --- Helpers ----------------------------------------------------------------


def _counter_value(counter: object, *, labels: dict[str, str]) -> float:
    for family in counter.collect():  # type: ignore[attr-defined]
        for sample in family.samples:
            if sample.name.endswith("_total") and sample.labels == labels:
                return float(sample.value)
    return 0.0


def _histogram_sample_count(histogram: object, *, labels: dict[str, str]) -> float:
    for family in histogram.collect():  # type: ignore[attr-defined]
        for sample in family.samples:
            if sample.name.endswith("_count") and sample.labels == labels:
                return float(sample.value)
    return 0.0
