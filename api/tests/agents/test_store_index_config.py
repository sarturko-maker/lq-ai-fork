"""F2 Slice C2 — the Store semantic IndexConfig (ADR-F049).

Unit-level proof of :func:`app.agents.store.build_store_index_config` — the single
helper that BOTH composition roots (production ``AsyncPostgresStore``) and these tests
(an ``InMemoryStore``) use to build the index, so the index the tests exercise is the
SAME shape production wires:

* the config's shape: ``dims`` == the provider's, ``fields`` == ``["content"]`` (we
  embed only the transcript text, not ``encoding``/timestamps), and ``embed`` is an
  async callable that returns one provider vector per input;
* end-to-end through ``InMemoryStore(index=cfg)``: a ``put`` is embedded and
  ``asearch(query=…)`` ranks by cosine (``SearchItem.score`` populated) — and a
  filter-only store (no index) leaves ``score=None`` (the back-compat / degraded path).

Hermetic: a tiny DETERMINISTIC concept embedder (no model download) — CI never loads
fastembed here. The real local embedder is exercised by the live A5 gate, not in CI.
"""

from __future__ import annotations

import pytest
from langgraph.store.memory import InMemoryStore

from app.agents.store import build_store_index_config
from tests.agents.embedding_fakes import ConceptEmbeddingProvider

pytestmark = pytest.mark.unit  # pure in-memory: InMemoryStore + a fake embedder, no I/O


def test_index_config_shape() -> None:
    cfg = build_store_index_config(ConceptEmbeddingProvider())
    assert cfg["dims"] == 3
    assert cfg["fields"] == ["content"]


async def test_index_config_embed_callable_returns_provider_vectors() -> None:
    provider = ConceptEmbeddingProvider()
    cfg = build_store_index_config(provider)
    vecs = await cfg["embed"](["the Manchester office", "the fee cap"])  # type: ignore[operator]
    assert vecs == await provider.embed(["the Manchester office", "the fee cap"])
    assert all(len(v) == provider.dim for v in vecs)


async def test_indexed_store_ranks_paraphrase_by_cosine() -> None:
    """A paraphrase query (no literal overlap) ranks the right item via the semantic index."""
    store = InMemoryStore(index=build_store_index_config(ConceptEmbeddingProvider()))
    await store.aput(("c", "t1"), "a.md", {"content": "working from the Manchester office today"})
    await store.aput(("c", "t2"), "b.md", {"content": "the fee cap is four percent"})

    # "northern premises" shares NO word with t1's text, but maps to the same concept.
    loc = await store.asearch(("c", "t1"), query="northern premises", limit=5)
    fee = await store.asearch(("c", "t2"), query="northern premises", limit=5)
    assert loc and loc[0].score is not None and loc[0].score >= 0.6
    assert fee and fee[0].score is not None and fee[0].score < 0.6


async def test_filter_only_store_leaves_score_none() -> None:
    """No index → ``query=`` is a silent no-op (score None): the degraded / back-compat path."""
    store = InMemoryStore()  # no index
    await store.aput(("c", "t1"), "a.md", {"content": "the Manchester office"})
    items = await store.asearch(("c", "t1"), query="northern premises", limit=5)
    assert items and items[0].score is None
