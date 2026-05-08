"""Smoke tests for the gateway's /health and /ready endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.unit
async def test_health_returns_200_alive() -> None:
    """Liveness: process is alive regardless of config / provider state."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert body["service"] == "lq-ai-gateway"


@pytest.mark.unit
async def test_ready_returns_503_until_config_loaded() -> None:
    """Readiness: scaffold-only state returns 503; A3 will flip this to 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["service"] == "lq-ai-gateway"
    assert body["reason"] == "scaffold_only"
