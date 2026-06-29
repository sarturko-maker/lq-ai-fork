"""Unit tests for the pluggable cross-encoder reranker — F2 Slice D (ADR-F049).

Door A (``LocalRerankProvider``, in-process fastembed ``TextCrossEncoder``) is
exercised against the real bundled model (no network — vendored into the image at
build via ``RERANK_CACHE_DIR``). Config selection + the Protocol + the empty-input
short-circuit are checked without loading any model, so they run in CI too.
"""

from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.knowledge import rerank_provider as rp

# The Door-A tests load the real fastembed cross-encoder. It is bundled into the
# dev/prod image at build (RERANK_CACHE_DIR); CI runs bare pytest with neither the
# model nor (necessarily) Hugging Face network, so gate them on that env being set —
# the dev image runs them, CI skips them (the config tests still run in CI).
_needs_local_model = pytest.mark.skipif(
    not os.environ.get("RERANK_CACHE_DIR"),
    reason="local reranker model not bundled (set RERANK_CACHE_DIR / run in the dev image)",
)


# ---------------------------------------------------------------------------
# config selection + Protocol (no model load)
# ---------------------------------------------------------------------------


def test_build_provider_defaults_to_local() -> None:
    provider = rp.build_rerank_provider(Settings())
    assert isinstance(provider, rp.LocalRerankProvider)
    assert provider.name.startswith("local:")


def test_build_provider_honours_configured_model() -> None:
    provider = rp.build_rerank_provider(Settings(rerank_model="BAAI/bge-reranker-base"))
    assert isinstance(provider, rp.LocalRerankProvider)
    assert provider.name == "local:BAAI/bge-reranker-base"


def test_local_provider_satisfies_protocol() -> None:
    assert isinstance(rp.LocalRerankProvider(), rp.RerankProvider)


def test_get_rerank_provider_is_lazy_singleton_and_overridable() -> None:
    rp.set_rerank_provider(None)
    first = rp.get_rerank_provider()
    assert first is rp.get_rerank_provider()  # lazy singleton
    sentinel = rp.LocalRerankProvider(model_name="sentinel")
    rp.set_rerank_provider(sentinel)
    assert rp.get_rerank_provider() is sentinel
    rp.set_rerank_provider(None)  # the autouse fixture also resets


async def test_empty_input_short_circuits_before_model_load() -> None:
    # No passages => no model is touched (so this is safe off-image / in CI).
    assert await rp.LocalRerankProvider(model_name="never-loaded").score("q", []) == []


# ---------------------------------------------------------------------------
# Door A — real in-process cross-encoder (bundled in the image)
# ---------------------------------------------------------------------------


@_needs_local_model
async def test_local_reranker_orders_relevant_passage_first() -> None:
    provider = rp.LocalRerankProvider()
    query = "What is the governing law and jurisdiction of this agreement?"
    passages = [
        "Each party shall keep the other's confidential information secret.",
        "This agreement is governed by the laws of England and the English courts "
        "have exclusive jurisdiction over any dispute.",
        "All invoices are payable within thirty days of receipt.",
    ]
    scores = await provider.score(query, passages)
    assert len(scores) == 3
    assert all(isinstance(s, float) for s in scores)
    # The governing-law/jurisdiction passage (index 1) is the most relevant.
    assert scores.index(max(scores)) == 1


@_needs_local_model
async def test_local_reranker_is_deterministic() -> None:
    provider = rp.LocalRerankProvider()
    query = "indemnity cap"
    passages = ["the indemnity is capped at four percent", "unrelated boilerplate text"]
    first = await provider.score(query, passages)
    second = await provider.score(query, passages)
    assert max(abs(a - b) for a, b in zip(first, second, strict=True)) < 1e-4
