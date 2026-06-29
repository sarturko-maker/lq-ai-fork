"""Pluggable embedding provider — F2 Slice C1 (fork, ADR-F049).

The matter/agent retrieval path needs embeddings to light up the vector side of
:func:`app.knowledge.retrieval.matter_hybrid_search`. The maintainer ruled we keep
**both doors** available behind one configurable, injected provider:

* **Door A — :class:`LocalEmbeddingProvider`** (the default): an in-process
  ``fastembed`` (ONNX) model — ``BAAI/bge-base-en-v1.5``, 768-dim, MIT. No gateway,
  no provider key, $0/token, and the dev stack works with no live gateway embedding
  model. This is a SECOND inference locus; ADR-F049 carves out *local in-process
  embedding* as permitted (it is not external-provider generation, which ADR-F010
  governs). Keeping Door B available preserves the single-egress option.
* **Door B — :class:`GatewayEmbeddingProvider`**: embeddings through the Inference
  Gateway's ``/v1/embeddings`` (the existing egress). OpenAI ``text-embedding-3-*``
  natively reduce to a requested ``dimensions`` (forwarded by the gateway's OpenAI
  adapter), so Door B can emit the same 768 dim as Door A → both fit the
  ``document_chunks.embedding_local vector(768)`` column.

Selection is by config (:class:`app.config.Settings`): ``embedding_provider`` =
``local`` | ``gateway`` (default ``local``). The provider is a process-global
(:func:`get_embedding_provider`), mirroring ``get_gateway_client``; callers may pass
an explicit ``provider=`` for test injection (the same seam ``request_embedding_*``
exposes for ``gateway=``).

bge models are **asymmetric**: a retrieval query is embedded with an instruction
prefix, a passage without — it materially lifts retrieval quality (the bge model
card). ``fastembed``'s ``query_embed`` does NOT apply this for the bundled
bge-base ONNX build (verified: it returns the same vector as ``embed``), so the
provider prepends the instruction itself on the ``is_query`` path. Callers never
hand-craft the prefix.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings
from app.knowledge.embed import DEFAULT_EMBEDDING_MODEL, request_embedding_vectors

log = logging.getLogger(__name__)

# Door A defaults — the local model + its native dim. 768 is coupled to bge-base;
# it must match the ``document_chunks.embedding_local vector(768)`` column (mig 0078)
# and, for Door B, the ``dimensions`` reduction requested from the gateway.
DEFAULT_LOCAL_MODEL = "BAAI/bge-base-en-v1.5"
DEFAULT_EMBEDDING_DIM = 768

# The bge-*-en-v1.5 retrieval query instruction (from the model card). Prepended to
# queries only; passages are embedded raw. A model without a query instruction sets
# this to "" (then the query/passage paths coincide).
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@runtime_checkable
class EmbeddingProvider(Protocol):
    """One embedding source. ``embed`` returns one vector per input text.

    ``is_query=True`` marks a retrieval query (asymmetric models add an
    instruction prefix); the default is the passage/document side. All vectors a
    provider returns have length :attr:`dim`.
    """

    name: str
    dim: int

    async def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]: ...


class LocalEmbeddingProvider:
    """Door A — in-process ``fastembed`` (ONNX). No gateway, no key, $0.

    The model is loaded lazily on first use (``fastembed`` is imported inside
    :meth:`_ensure_model` so the module imports cleanly where the dep is absent —
    the tiktoken-lazy pattern). Inference is synchronous, so it runs in a worker
    thread via :func:`asyncio.to_thread` to avoid blocking the event loop.
    """

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_LOCAL_MODEL,
        dim: int = DEFAULT_EMBEDDING_DIM,
        cache_dir: str | None = None,
        query_instruction: str = BGE_QUERY_INSTRUCTION,
    ) -> None:
        self.name = f"local:{model_name}"
        self.dim = dim
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._query_instruction = query_instruction
        self._model: object | None = None

    def _ensure_model(self) -> object:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name, cache_dir=self._cache_dir)
            log.info(
                "local embedding model loaded",
                extra={"event": "local_embedder_loaded", "model": self._model_name},
            )
        return self._model

    def _embed_sync(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        model = self._ensure_model()
        # bge asymmetry: prepend the retrieval instruction to queries (fastembed's
        # query_embed is a no-op prefix for the bundled ONNX build), raw for passages.
        inputs = [self._query_instruction + t for t in texts] if is_query else texts
        # embed() yields numpy float32 vectors — coerce to plain floats for pgvector.
        return [[float(value) for value in vector] for vector in model.embed(inputs)]  # type: ignore[attr-defined]

    async def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        return await asyncio.to_thread(self._embed_sync, items, is_query=is_query)


class GatewayEmbeddingProvider:
    """Door B — embeddings via the Inference Gateway (the existing egress).

    Wraps :func:`app.knowledge.request_embedding_vectors`, requesting ``dimensions``
    so an OpenAI ``text-embedding-3-*`` model emits :attr:`dim`-length vectors that
    fit the same column as Door A. ``is_query`` is irrelevant here (symmetric
    OpenAI embeddings) and ignored.
    """

    def __init__(
        self, *, model: str = DEFAULT_EMBEDDING_MODEL, dim: int = DEFAULT_EMBEDDING_DIM
    ) -> None:
        self.name = f"gateway:{model}"
        self.dim = dim
        self._model = model

    async def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        return await request_embedding_vectors(items, model=self._model, dimensions=self.dim)


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Construct the configured provider. Default (``local``) is Door A."""
    if settings.embedding_provider == "gateway":
        return GatewayEmbeddingProvider(model=DEFAULT_EMBEDDING_MODEL, dim=settings.embedding_dim)
    return LocalEmbeddingProvider(
        model_name=settings.embedding_model,
        dim=settings.embedding_dim,
        cache_dir=settings.embedding_cache_dir,
    )


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Process-global provider (lazy), mirroring ``get_gateway_client``."""
    global _provider
    if _provider is None:
        _provider = build_embedding_provider(get_settings())
    return _provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Override the process-global provider (composition root / tests)."""
    global _provider
    _provider = provider
