"""Tests for the OpenAI-compatible inference surface.

Surface state after B3:

* ``POST /v1/chat/completions`` — routes to Anthropic when the model
  resolves there; returns a structured ``provider_unavailable`` 503 when
  the credential isn't configured (the case in this fixture); returns
  the A3-style 501 only for models that don't resolve to Anthropic.
* ``POST /v1/embeddings`` — still 501 (B6 lands the OpenAI adapter).
* ``GET /v1/models`` — returns the configured aliases.

End-to-end coverage of the chat-completion happy path lives in
``test_inference_anthropic.py`` (Anthropic upstream mocked with respx)
and ``test_anthropic_provider.py`` (real-key, marked ``provider``).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_chat_completions_returns_503_when_anthropic_key_missing(
    client: AsyncClient,
) -> None:
    """B3 wires the Anthropic adapter; with no key, the route returns a
    structured 503 ``provider_unavailable`` rather than the A3 501 stub.

    The conftest sets ``GATEWAY_CONFIG_PATH`` to ``gateway.yaml.example``
    but does not set ``ANTHROPIC_API_KEY``, so the lifespan logs a
    warning and skips adapter instantiation. Real-key end-to-end coverage
    is in :mod:`tests.test_anthropic_adapter_provider` (gated on
    ``provider`` mark).
    """

    response = await client.post(
        "/v1/chat/completions",
        json={"model": "smart", "messages": []},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "provider_unavailable"
    assert body["error"]["details"]["provider"] == "anthropic-prod"


@pytest.mark.unit
async def test_chat_completions_returns_501_for_non_anthropic_alias(
    client: AsyncClient,
) -> None:
    """Aliases that don't resolve to Anthropic still return 501 in B3.

    The ``embedding`` alias in ``gateway.yaml.example`` points at the
    OpenAI provider; B6 lands the OpenAI adapter, so B3 reports 501 with
    a ``next_task`` pointer.
    """

    response = await client.post(
        "/v1/chat/completions",
        json={"model": "embedding", "messages": []},
    )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "not_implemented"
    assert "B4" in body["error"]["details"]["next_task"]


@pytest.mark.unit
async def test_embeddings_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/embeddings",
        json={"model": "embedding", "input": "hello"},
    )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "not_implemented"
    assert "message" in body["error"]


@pytest.mark.unit
async def test_models_returns_configured_aliases(client: AsyncClient) -> None:
    response = await client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    ids = [entry["id"] for entry in body["data"]]
    # Aliases that exist in gateway.yaml.example
    for expected in ("smart", "fast", "budget", "local", "embedding"):
        assert expected in ids, f"alias {expected!r} missing from /v1/models"
    # Each entry must have the OpenAI-compatible shape
    for entry in body["data"]:
        assert set(entry.keys()) >= {"id", "object", "created", "owned_by"}
        assert entry["object"] == "model"


@pytest.mark.unit
async def test_chat_completions_rejects_get(client: AsyncClient) -> None:
    """Sanity: only POST is registered on /v1/chat/completions."""

    response = await client.get("/v1/chat/completions")
    assert response.status_code == 405
