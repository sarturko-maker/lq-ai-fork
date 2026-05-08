"""Knowledge-base service — Task C6.

Hybrid (vector + FTS) retrieval over chunks belonging to files attached
to a KB, plus the embedding-on-write / embedding-on-read backfill that
closes ADR 0006 §3.

Modules:

* :mod:`app.knowledge.embed` — embedding generation. Wraps the
  gateway's ``/v1/embeddings`` for the worker (eager backfill) and the
  query handler (lazy embed-on-read). Owns the tokenizer pick (ADR 0008
  picks ``tiktoken`` against OpenAI's ``cl100k_base``).
* :mod:`app.knowledge.retrieval` — the hybrid-score query. Builds the
  vector + FTS candidate sets, normalizes per ADR 0008's min-max +
  linear-combine, returns ranked :class:`SearchResult` objects.
"""

from app.knowledge.embed import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    count_tokens,
    embed_chunks_for_file,
    ensure_embeddings_for_chunk_ids,
    request_embedding_vector,
)
from app.knowledge.retrieval import (
    HybridSearchResult,
    hybrid_search,
)

__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
    "HybridSearchResult",
    "count_tokens",
    "embed_chunks_for_file",
    "ensure_embeddings_for_chunk_ids",
    "hybrid_search",
    "request_embedding_vector",
]
