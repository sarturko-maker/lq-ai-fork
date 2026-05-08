"""Smoke tests for the /health and /ready endpoints.

Locked-in test stack per CONTRIBUTING.md: pytest-asyncio with asyncio_mode=auto,
httpx.AsyncClient with ASGITransport for in-process FastAPI tests.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.unit
async def test_health_returns_200_alive() -> None:
    """Liveness: process is alive regardless of dependency state."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert body["service"] == "lq-ai-api"


@pytest.mark.unit
async def test_ready_returns_503_until_dependencies_wired() -> None:
    """Readiness: scaffold-only state returns 503; A4 will flip this to 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["service"] == "lq-ai-api"
    assert body["reason"] == "scaffold_only"
