"""Unit tests for the pluggable embedding provider — F2 Slice C1 (ADR-F049).

Door A (``LocalEmbeddingProvider``, in-process fastembed) is exercised against the
real bundled model (no network — the model is vendored into the image at build).
Door B (``GatewayEmbeddingProvider``) is checked for the one behaviour that matters
here: it requests the configured ``dimensions`` so the gateway can emit vectors that
fit the same column as Door A. ``build_embedding_provider`` config selection is
checked without loading any model.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import pytest

from app.config import Settings
from app.knowledge import embedding_provider as ep

# The Door-A tests load the real fastembed model. It is bundled into the dev/prod
# image at build (LQ_AI_EMBEDDING_CACHE_DIR); CI runs bare pytest with neither the
# model nor (necessarily) Hugging Face network, so gate them on that env being set —
# the dev image runs them, CI skips them (the config + Door-B tests still run in CI).
_needs_local_model = pytest.mark.skipif(
    not os.environ.get("EMBEDDING_CACHE_DIR"),
    reason="local embedder model not bundled (set EMBEDDING_CACHE_DIR / run in the dev image)",
)

# ---------------------------------------------------------------------------
# config selection (no model load)
# ---------------------------------------------------------------------------


def test_build_provider_defaults_to_local() -> None:
    provider = ep.build_embedding_provider(Settings(embedding_provider="local"))
    assert isinstance(provider, ep.LocalEmbeddingProvider)
    assert provider.dim == 768
    assert provider.name.startswith("local:")


def test_build_provider_gateway_when_configured() -> None:
    provider = ep.build_embedding_provider(
        Settings(embedding_provider="gateway", embedding_dim=768)
    )
    assert isinstance(provider, ep.GatewayEmbeddingProvider)
    assert provider.dim == 768
    assert provider.name.startswith("gateway:")


# ---------------------------------------------------------------------------
# Door B — forwards `dimensions` so the gateway matches the local column dim
# ---------------------------------------------------------------------------


async def test_gateway_provider_requests_configured_dimensions(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    async def _fake_request(texts: Sequence[str], **kwargs: Any) -> list[list[float]]:
        seen["texts"] = list(texts)
        seen["dimensions"] = kwargs.get("dimensions")
        return [[0.0] * 768 for _ in texts]

    monkeypatch.setattr(ep, "request_embedding_vectors", _fake_request)
    provider = ep.GatewayEmbeddingProvider(model="embedding", dim=768)

    out = await provider.embed(["one", "two"])
    assert len(out) == 2 and all(len(v) == 768 for v in out)
    assert seen["dimensions"] == 768  # the column-matching reduction was requested
    assert seen["texts"] == ["one", "two"]


async def test_gateway_provider_empty_input_short_circuits(monkeypatch: Any) -> None:
    async def _boom(*_a: Any, **_k: Any) -> list[list[float]]:
        raise AssertionError("should not call the gateway for empty input")

    monkeypatch.setattr(ep, "request_embedding_vectors", _boom)
    assert await ep.GatewayEmbeddingProvider().embed([]) == []


# ---------------------------------------------------------------------------
# Door A — real in-process model (bundled in the image)
# ---------------------------------------------------------------------------


@_needs_local_model
async def test_local_provider_dim_and_determinism() -> None:
    provider = ep.LocalEmbeddingProvider()
    out1 = await provider.embed(["the limitation of liability clause"])
    out2 = await provider.embed(["the limitation of liability clause"])
    assert len(out1) == 1
    assert len(out1[0]) == 768  # bge-base-en-v1.5 native dim == the column dim
    assert all(isinstance(x, float) for x in out1[0])
    # Deterministic: same text → same vector (within float noise).
    assert max(abs(a - b) for a, b in zip(out1[0], out2[0], strict=True)) < 1e-5


@_needs_local_model
async def test_local_provider_query_and_passage_differ() -> None:
    """bge is asymmetric — the query path adds a retrieval instruction prefix, so
    the same text embeds differently as a query vs a passage."""
    provider = ep.LocalEmbeddingProvider()
    [passage] = await provider.embed(["indemnity cap"], is_query=False)
    [query] = await provider.embed(["indemnity cap"], is_query=True)
    assert len(passage) == len(query) == 768
    assert max(abs(a - b) for a, b in zip(passage, query, strict=True)) > 1e-3


async def test_local_provider_empty_input() -> None:
    assert await ep.LocalEmbeddingProvider().embed([]) == []
