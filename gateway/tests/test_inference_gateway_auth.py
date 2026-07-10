"""UP-SEC-1 regression: the ``/v1`` inference surface enforces the gateway key.

Before UP-SEC-1 the ``/v1`` router carried NO ``dependencies=`` while the
``/admin/v1`` router already gated every call on the shared secret
(``app.api.admin``). With ``gateway_auth.enabled: true`` and the key env set,
anything that could reach the gateway port could POST ``/v1/chat/completions``
(spending provider credit) or read routing config — no ``X-LQ-AI-Gateway-Key``
required. This module pins the fix:

* every ``/v1`` verb (chat/completions, embeddings, models) 401s without the
  header when a key is configured;
* a wrong header 401s;
* the correct header passes the auth gate (the handler then rejects a
  malformed body with 400 — proving we got *past* auth, hermetically, with no
  upstream call).

The auth check is a router-level FastAPI dependency, so it runs BEFORE the
handler reads the request body — the negative cases don't need a valid payload
or any respx mock.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import GATEWAY_KEY_HEADER

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "gateway.yaml.example"

GATEWAY_KEY = "test-gateway-key-correct-horse"


@asynccontextmanager
async def _run_lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with app.router.lifespan_context(app):
        yield


@pytest_asyncio.fixture
async def gateway_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    """Bring the gateway up with ``gateway_auth.enabled: true`` + a key set.

    The example config ships ``gateway_auth.enabled: true``; setting the
    ``LQ_AI_GATEWAY_KEY`` env var makes ``_resolve_required_key`` return a
    non-empty secret, so auth is live.
    """

    monkeypatch.setenv("GATEWAY_CONFIG_PATH", str(EXAMPLE_CONFIG))
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AZURE_OPENAI_RESOURCE", "test-openai")
    monkeypatch.setenv("LQ_AI_VERSION", "0.1.0-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    monkeypatch.setenv("LQ_AI_GATEWAY_KEY", GATEWAY_KEY)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.main import app

    async with _run_lifespan(app):
        yield app


@pytest_asyncio.fixture
async def unauthed_client(gateway_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client that sends NO gateway-key header."""

    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client(gateway_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client that sends the correct gateway-key header on every call."""

    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={GATEWAY_KEY_HEADER: GATEWAY_KEY},
    ) as ac:
        yield ac


async def test_chat_completions_without_key_is_401(unauthed_client: AsyncClient) -> None:
    response = await unauthed_client.post(
        "/v1/chat/completions",
        json={"model": "smart", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 401
    # The gateway-key dependency raises a raw HTTPException whose detail is the
    # ``{"error": {...}}`` envelope, so FastAPI nests it under ``detail``.
    assert response.json()["detail"]["error"]["code"] == "unauthorized"


async def test_embeddings_without_key_is_401(unauthed_client: AsyncClient) -> None:
    response = await unauthed_client.post(
        "/v1/embeddings",
        json={"model": "embedding", "input": "hi"},
    )

    assert response.status_code == 401
    # The gateway-key dependency raises a raw HTTPException whose detail is the
    # ``{"error": {...}}`` envelope, so FastAPI nests it under ``detail``.
    assert response.json()["detail"]["error"]["code"] == "unauthorized"


async def test_models_without_key_is_401(unauthed_client: AsyncClient) -> None:
    response = await unauthed_client.get("/v1/models")

    assert response.status_code == 401
    # The gateway-key dependency raises a raw HTTPException whose detail is the
    # ``{"error": {...}}`` envelope, so FastAPI nests it under ``detail``.
    assert response.json()["detail"]["error"]["code"] == "unauthorized"


async def test_wrong_key_is_401(unauthed_client: AsyncClient) -> None:
    response = await unauthed_client.post(
        "/v1/chat/completions",
        json={"model": "smart", "messages": [{"role": "user", "content": "hi"}]},
        headers={GATEWAY_KEY_HEADER: "not-the-real-key"},
    )

    assert response.status_code == 401
    # The gateway-key dependency raises a raw HTTPException whose detail is the
    # ``{"error": {...}}`` envelope, so FastAPI nests it under ``detail``.
    assert response.json()["detail"]["error"]["code"] == "unauthorized"


async def test_correct_key_passes_auth_gate(authed_client: AsyncClient) -> None:
    """The correct header clears auth; the handler then 400s a non-JSON body.

    A 400 (not 401) proves the request got PAST the auth dependency and into
    the handler — no upstream/provider call is made, so this stays hermetic.
    """

    response = await authed_client.post(
        "/v1/chat/completions",
        content=b"this is not json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
