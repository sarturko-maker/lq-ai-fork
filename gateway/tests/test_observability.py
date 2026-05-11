"""Unit tests for the gateway observability surface (M-Obs.1 / PRD §5.4).

Covers:

* ``/metrics`` endpoint mounts and serves Prometheus text format.
* HTTP middleware records counter + histogram rows per request.
* ``/metrics`` itself is excluded from the latency histogram.
* OpenTelemetry stays dormant unless the operator opts in via env.
* Inference-dispatch counter increments with stable label values.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.observability import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    INFERENCE_REQUESTS_TOTAL,
    _otel_enabled,
    install_observability,
)


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/v1/hello")
    async def hello() -> dict[str, str]:
        return {"hello": "world"}

    @app.get("/v1/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("boom")

    install_observability(app, service_name="test-svc", service_version="0.0.0-test")
    return app


@pytest.mark.unit
def test_metrics_endpoint_serves_text_format() -> None:
    """``GET /metrics`` returns Prometheus text exposition format."""

    app = _build_app()
    with TestClient(app) as client:
        # Touch a route so the counter has at least one row to serialize.
        client.get("/v1/hello")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "lq_ai_gateway_http_requests_total" in body
    assert "lq_ai_gateway_http_request_duration_seconds" in body
    # Format parses cleanly. The parser strips the ``_total`` suffix
    # from counter family names per the OpenMetrics convention.
    families = list(text_string_to_metric_families(body))
    family_names = {f.name for f in families}
    assert "lq_ai_gateway_http_requests" in family_names


@pytest.mark.unit
def test_http_request_increments_counter_and_histogram() -> None:
    """A successful 200 increments both the counter and the histogram."""

    app = _build_app()
    before_count = _counter_value(
        HTTP_REQUESTS_TOTAL,
        labels={"method": "GET", "route": "/v1/hello", "status": "200"},
    )
    before_hist = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/v1/hello", "status": "200"},
    )
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/v1/hello").status_code == 200
    after_count = _counter_value(
        HTTP_REQUESTS_TOTAL,
        labels={"method": "GET", "route": "/v1/hello", "status": "200"},
    )
    after_hist = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/v1/hello", "status": "200"},
    )
    assert after_count - before_count == 3
    assert after_hist - before_hist == 3


@pytest.mark.unit
def test_metrics_endpoint_excluded_from_histogram() -> None:
    """``/metrics`` itself is counted but not added to the latency histogram.

    Counting our own scrape inflates p99s and breaks alerting on real
    traffic; the middleware short-circuits before the histogram observe.
    """

    app = _build_app()
    before = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/metrics", "status": "200"},
    )
    with TestClient(app) as client:
        client.get("/metrics")
        client.get("/metrics")
        client.get("/metrics")
    after = _histogram_sample_count(
        HTTP_REQUEST_DURATION_SECONDS,
        labels={"method": "GET", "route": "/metrics", "status": "200"},
    )
    assert after == before  # no histogram observations recorded


@pytest.mark.unit
def test_unmatched_route_does_not_blow_up_cardinality() -> None:
    """A 404 on an unknown path labels with ``__unmatched__``."""

    app = _build_app()
    with TestClient(app) as client:
        assert client.get("/nope/this/does/not/exist").status_code == 404
    # The label exists, with status=404. We just probe that the row was
    # written under the sentinel route label.
    value = _counter_value(
        HTTP_REQUESTS_TOTAL,
        labels={"method": "GET", "route": "__unmatched__", "status": "404"},
    )
    assert value >= 1


@pytest.mark.unit
def test_otel_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the OTel env var set, the SDK is not initialized.

    PRD §5.7: "no telemetry by default". The bootstrap function reads
    the env at call time; absent the configured endpoint, it returns
    False and the SDK never registers a TracerProvider.
    """

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    assert _otel_enabled() is False


@pytest.mark.unit
def test_otel_enabled_when_endpoint_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting ``OTEL_EXPORTER_OTLP_ENDPOINT`` flips the opt-in to True."""

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    assert _otel_enabled() is True


@pytest.mark.unit
def test_inference_counter_label_values_are_stable() -> None:
    """The ``outcome`` label is a small closed set so cardinality stays bounded."""

    INFERENCE_REQUESTS_TOTAL.labels(provider="p1", tier="3", outcome="success").inc()
    INFERENCE_REQUESTS_TOTAL.labels(provider="p1", tier="3", outcome="provider_error").inc()
    INFERENCE_REQUESTS_TOTAL.labels(provider="p2", tier="1", outcome="network_error").inc()
    # Round-trip through the registry to make sure the labels render.
    families = {
        family.name: family
        for family in HTTP_REQUESTS_TOTAL.collect()
        + HTTP_REQUEST_DURATION_SECONDS.collect()
        + INFERENCE_REQUESTS_TOTAL.collect()
    }
    inference = families["lq_ai_gateway_inference_requests"]
    seen_outcomes = {sample.labels["outcome"] for sample in inference.samples}
    assert seen_outcomes.issubset({"success", "provider_error", "network_error", "refused"})


# --- Helpers ----------------------------------------------------------------


def _counter_value(counter: object, *, labels: dict[str, str]) -> float:
    """Read the current scalar value of a labelled counter sample."""

    for family in counter.collect():  # type: ignore[attr-defined]
        for sample in family.samples:
            if sample.name.endswith("_total") and sample.labels == labels:
                return float(sample.value)
    return 0.0


def _histogram_sample_count(histogram: object, *, labels: dict[str, str]) -> float:
    """Read the ``_count`` sample of a labelled histogram."""

    for family in histogram.collect():  # type: ignore[attr-defined]
        for sample in family.samples:
            if sample.name.endswith("_count") and sample.labels == labels:
                return float(sample.value)
    return 0.0
