"""Smoke tests for the /health and /ready endpoints.

Locked-in test stack per CONTRIBUTING.md: pytest-asyncio with asyncio_mode=auto,
httpx.AsyncClient with ASGITransport for in-process FastAPI tests.

Liveness (/health) is unconditional — once the process is serving requests
it returns 200. Readiness (/ready) checks DB + Redis + MinIO + gateway and
reports per-dependency status; in unit-test mode none of those are
available so the endpoint reports 503 with a list of failed dependencies.
The integration test that asserts `/ready -> 200` lives in the cross-
service `tests/` folder (alongside docker-compose) — out of scope here.
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
async def test_ready_reports_per_dependency_status() -> None:
    """Readiness: returns structured per-dependency status.

    In unit-test mode none of DB / Redis / MinIO / gateway are reachable,
    so we expect 503 with `failed` listing the unreachable dependencies.
    The body shape (status, dependencies map, failed list) is part of the
    contract: clients can read it to surface which dependency is down.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["service"] == "lq-ai-api"
    assert body["status"] == "not_ready"
    deps = body["dependencies"]
    # All four dependencies are surfaced even when they fail.
    assert set(deps.keys()) == {"database", "redis", "storage", "gateway"}
    for name, dep in deps.items():
        assert "ok" in dep, f"dependency '{name}' missing 'ok' field"
    # Every failed dep appears in the failed list.
    assert sorted(body["failed"]) == sorted(name for name, dep in deps.items() if not dep["ok"])
