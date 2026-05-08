"""Smoke tests for the gateway's /health and /ready endpoints.

A3 changes:
    /health      — still 200 (liveness; config-independent)
    /ready       — 503 when config is unset; 200 when config is loaded.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.unit
async def test_health_returns_200_alive() -> None:
    """Liveness: process is alive regardless of config / provider state.

    This test deliberately uses the raw ``app`` *without* running the
    lifespan, to demonstrate that ``/health`` is independent of config load.
    """

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert body["service"] == "lq-ai-gateway"


@pytest.mark.unit
async def test_ready_returns_503_until_config_loaded() -> None:
    """``/ready`` is 503 before lifespan finishes loading the config.

    Mount the endpoint on a fresh :class:`FastAPI` instance whose
    ``app.state`` has no ``config`` attached, simulating the pre-startup
    window (or a startup-failed window).
    """

    from app.main import ready

    fresh_app = FastAPI()
    fresh_app.add_api_route("/ready", ready)

    transport = ASGITransport(app=fresh_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["service"] == "lq-ai-gateway"
    assert body["reason"] == "config_not_loaded"


@pytest.mark.unit
async def test_ready_returns_200_when_config_loaded(client: AsyncClient) -> None:
    """Once the config is loaded, ``/ready`` flips to 200."""

    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "lq-ai-gateway"
    # Both counters are populated from gateway.yaml.example
    assert body["providers"] >= 1
    assert body["aliases"] >= 1
