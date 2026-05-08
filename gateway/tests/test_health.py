"""Smoke tests for the gateway's /health and /ready endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.unit
async def test_health_returns_503_with_structured_body() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_implemented"
    assert body["service"] == "inhouse-ai-gateway"
    assert "next_task" in body


@pytest.mark.unit
async def test_ready_returns_503_with_structured_body() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_implemented"
    assert body["service"] == "inhouse-ai-gateway"
