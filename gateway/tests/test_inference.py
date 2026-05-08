"""Tests for the OpenAI-compatible inference surface.

A3 acceptance:

* ``POST /v1/chat/completions`` returns 501 with the structured error envelope.
* ``POST /v1/embeddings`` returns 501.
* ``GET /v1/models`` returns the configured aliases.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_chat_completions_returns_501(client: AsyncClient) -> None:
    """Acceptance criterion from M1-IMPLEMENTATION-ORDER.md A3."""

    response = await client.post(
        "/v1/chat/completions",
        json={"model": "smart", "messages": []},
    )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "not_implemented"
    assert "next_task" in body["error"]["details"]
    assert "B3" in body["error"]["details"]["next_task"]


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
