"""Smoke tests for the /health and /ready endpoints.

Locked-in test stack per CONTRIBUTING.md: pytest-asyncio with asyncio_mode=auto,
httpx.AsyncClient with ASGITransport for in-process FastAPI tests.
"""

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
    assert body["service"] == "inhouse-ai-api"
    assert "next_task" in body


@pytest.mark.unit
async def test_ready_returns_503_with_structured_body() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_implemented"
    assert body["service"] == "inhouse-ai-api"
