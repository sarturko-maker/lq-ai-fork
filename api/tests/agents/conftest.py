"""Shared fixtures for the agents test suite (F2 Slice C1, ADR-F049).

Inject a hermetic **fake** ``EmbeddingProvider`` by default, so tests that exercise
the matter ``search_documents`` path — which now embeds the query via the configured
local door (`tools.py:_search` → `get_embedding_provider()`) — do NOT load or
download the real `fastembed` model. CI runs bare pytest with neither the bundled
model nor (necessarily) Hugging Face network, so the real model would download
mid-test: slow + flaky. The real embedder is exercised explicitly where it belongs —
``test_embedding_provider`` (gated on the bundled model) and the corpus-gated CUAD
hybrid eval, which both construct providers directly rather than via the global.

Per the DI rule (CLAUDE.md), substitute the fake through the same
``set_embedding_provider`` seam rather than monkeypatching.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.knowledge import embedding_provider as ep, rerank_provider as rp


class _FakeEmbeddingProvider:
    """Model-free, deterministic. Matter chunks carry no ``embedding_local`` in these
    tests, so the vector side is empty and retrieval falls back to FTS — the fake's
    vector value is irrelevant to the assertions, only that no model loads. For tests
    that need REAL cosine geometry (Slice C2 paraphrase ranking), use
    ``tests.agents.embedding_fakes.ConceptEmbeddingProvider`` instead (passed explicitly,
    not via this autouse seam)."""

    name = "fake:test"
    dim = 768

    async def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


@pytest.fixture(autouse=True)
def _hermetic_embedding_provider() -> object:
    """Default every agents test to the fake provider; reset after so the lazy
    process-global rebuilds from config outside this scope."""
    ep.set_embedding_provider(_FakeEmbeddingProvider())
    try:
        yield
    finally:
        ep.set_embedding_provider(None)


class _IdentityRerankProvider:
    """Model-free reranker that PRESERVES the input (hybrid) order — descending scores
    aligned with input. Insurance so a test that flips ``rerank_enabled`` without
    injecting its own fake never loads the real cross-encoder (rerank is OFF by
    default, so production tests don't reach the global). Tests that assert reordering
    pass an explicit ``KeywordRerankProvider`` (``tests.agents.embedding_fakes``)."""

    name = "fake:identity-rerank"

    async def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [float(len(passages) - i) for i in range(len(passages))]


@pytest.fixture(autouse=True)
def _hermetic_rerank_provider() -> object:
    """Default every agents test to the identity reranker; reset after (Slice D)."""
    rp.set_rerank_provider(_IdentityRerankProvider())
    try:
        yield
    finally:
        rp.set_rerank_provider(None)
