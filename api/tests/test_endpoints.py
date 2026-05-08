"""Endpoint scaffold tests — every /api/v1 route returns the canonical 501 body.

A4 registers every endpoint from `docs/api/backend-openapi.yaml` as a
stub returning HTTP 501 with a structured body that names the implementing
M1 task. Until each implementing task lands, the contract is:

    {
      "error": {
        "code": "not_implemented",
        "message": "Endpoint scaffold; full implementation lands in Task ...",
        "endpoint": "<METHOD /path>",
        "next_task": "<task ID — task title>"
      }
    }

This test enumerates the registered routes via `app.routes` and exercises
every one. It pins both the surface (every route returns 501) and the body
shape (clients can rely on `error.code == 'not_implemented'`).
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.main import app

# Substitution table for path parameters when exercising stubs.
# Any UUID-shaped parameter gets a fixed UUID v4; named params get a
# safe identifier.
_DUMMY_UUID = "00000000-0000-4000-8000-000000000000"
_PARAM_VALUES: dict[str, str] = {
    "project_id": _DUMMY_UUID,
    "chat_id": _DUMMY_UUID,
    "message_id": _DUMMY_UUID,
    "file_id": _DUMMY_UUID,
    "kb_id": _DUMMY_UUID,
    "prompt_id": _DUMMY_UUID,
    "skill_name": "nda-review",
}


def _materialise(path: str) -> str:
    """Replace `{param}` placeholders with concrete values for the request."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in _PARAM_VALUES:
            raise AssertionError(
                f"Path parameter '{name}' has no test value — "
                f"add it to _PARAM_VALUES in test_endpoints.py"
            )
        return _PARAM_VALUES[name]

    return re.sub(r"\{([^}]+)\}", repl, path)


def _api_v1_routes() -> list[tuple[str, str, str]]:
    """Return (method, registered_path, materialised_path) for every /api/v1 route."""
    rows: list[tuple[str, str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            rows.append((method, route.path, _materialise(route.path)))
    return rows


# Materialised once at import time so pytest reports the route in the parametrize id.
ROUTES = _api_v1_routes()


@pytest.mark.unit
async def test_route_inventory_is_nonempty() -> None:
    """Sanity: at least 29 (method, path) pairs are registered under /api/v1."""
    # 29 distinct paths in the sketch; multiple methods per path gives more
    # registrations than that. Lower bound is a safety check against
    # accidentally dropping the include_router calls.
    assert len(ROUTES) >= 29


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "path_template", "path"),
    ROUTES,
    ids=[f"{m} {p}" for (m, p, _) in ROUTES],
)
async def test_endpoint_returns_canonical_501_body(
    method: str, path_template: str, path: str
) -> None:
    """Every /api/v1 endpoint returns HTTP 501 with the documented body shape."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path)

    assert response.status_code == 501, (
        f"{method} {path} returned {response.status_code}, expected 501"
    )
    body = response.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == "not_implemented"
    # Endpoint label is the (template) METHOD + path the stub was registered for.
    # We don't assert exact equality on the verb because the stub helper formats
    # it as a method+path label.
    assert path_template in err["endpoint"]
    assert err["next_task"]
    assert err["message"].startswith("Endpoint scaffold")
