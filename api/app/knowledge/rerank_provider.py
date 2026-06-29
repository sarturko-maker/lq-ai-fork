"""Pluggable cross-encoder reranker — F2 Slice D (fork, ADR-F049).

After :func:`app.knowledge.retrieval.matter_hybrid_search` casts a wide, high-recall
candidate net (FTS + pgvector fusion, ADR-F049 Slice C1), a **cross-encoder reranker**
reorders those candidates by scoring each *(query, passage)* pair **jointly** — the
precision tool a bi-encoder embedder cannot be (it embeds query and passage
independently, then compares). :func:`app.knowledge.retrieval.matter_search_reranked`
fetches a wider candidate set and reranks it down to the top-k the agent reads.

* **Door A — :class:`LocalRerankProvider`** (the default): an in-process ``fastembed``
  (ONNX) ``TextCrossEncoder``. No gateway, no provider key, $0/token. This is the
  **same SECOND inference locus** ADR-F049 §Consequences already carves out for the
  C1 embedder — it holds no key and egresses nothing; it just extends that recorded
  trade (it is local in-process scoring, not external-provider generation, which
  ADR-F010 governs). The reranker reuses ``fastembed`` — **no new dependency**.
* **Door B — gateway reranker:** there is no gateway ``/rerank`` endpoint today, so
  Door B is **deferred**. :func:`build_rerank_provider` leaves the dispatch seam.

Selection is by config (:class:`app.config.Settings`): ``rerank_enabled`` (the
production default is set by the Track-B B3 gate — ON only if precision@5 lifts),
``rerank_model``, ``rerank_candidates``. The provider is a process-global
(:func:`get_rerank_provider`), mirroring :func:`get_embedding_provider`; callers may
override via :func:`set_rerank_provider` (composition root / tests).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

# Door A default — a small, fast MS-MARCO cross-encoder (~5 MB ONNX). Chosen for
# per-search CPU latency; ``BAAI/bge-reranker-base`` (the native bge-family match) is
# the configurable quality alternative the Track-B calibration weighs against it.
DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


@runtime_checkable
class RerankProvider(Protocol):
    """One cross-encoder reranker.

    ``score`` returns one relevance score per passage, **aligned with the input
    order**; higher = more relevant. The scores are an *ordering* only (raw
    cross-encoder logits — not calibrated across queries, same contract as the
    fused/FTS score on :class:`app.knowledge.retrieval.MatterSearchHit`).
    """

    name: str

    async def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class LocalRerankProvider:
    """Door A — in-process ``fastembed`` ``TextCrossEncoder``. No gateway, no key, $0.

    The model is loaded lazily on first use (``fastembed`` is imported inside
    :meth:`_ensure_model` so the module imports cleanly where the dep is absent — the
    embedder's pattern). Inference is synchronous, so it runs in a worker thread via
    :func:`asyncio.to_thread` to avoid blocking the event loop.
    """

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_RERANK_MODEL,
        cache_dir: str | None = None,
    ) -> None:
        self.name = f"local:{model_name}"
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model: object | None = None

    def _ensure_model(self) -> object:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self._model_name, cache_dir=self._cache_dir)
            log.info(
                "local reranker model loaded",
                extra={"event": "local_reranker_loaded", "model": self._model_name},
            )
        return self._model

    def _score_sync(self, query: str, passages: list[str]) -> list[float]:
        model = self._ensure_model()
        # rerank() yields one float per passage, aligned with the input order.
        return [float(s) for s in model.rerank(query, passages)]  # type: ignore[attr-defined]

    async def score(self, query: str, passages: Sequence[str]) -> list[float]:
        items = list(passages)
        if not items:
            return []
        return await asyncio.to_thread(self._score_sync, query, items)


def build_rerank_provider(settings: Settings) -> RerankProvider:
    """Construct the configured reranker. Only Door A (local) exists today; a future
    gateway ``/rerank`` door would dispatch here (no destructive change to add it)."""
    return LocalRerankProvider(
        model_name=settings.rerank_model,
        cache_dir=settings.rerank_cache_dir,
    )


_provider: RerankProvider | None = None


def get_rerank_provider() -> RerankProvider:
    """Process-global reranker (lazy), mirroring :func:`get_embedding_provider`."""
    global _provider
    if _provider is None:
        _provider = build_rerank_provider(get_settings())
    return _provider


def set_rerank_provider(provider: RerankProvider | None) -> None:
    """Override the process-global reranker (composition root / tests)."""
    global _provider
    _provider = provider
