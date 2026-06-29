"""Deterministic, model-free embedding fakes for the Slice-C2 Store-index tests.

A tiny CONCEPT embedder: distinct surface words map to the SAME dimension, so a
paraphrase (no literal overlap with the indexed text) still lands near its concept —
exactly the recall a lexical scan misses. Unit-normalised so cosine == dot product,
and unrelated concepts are ORTHOGONAL (cosine 0) — which lets a test assert honest
absence (an off-topic query must stay below the semantic threshold). No model loads;
CI never downloads fastembed through this path.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Distinct words per concept; unrelated concepts share no dimension → orthogonal vectors.
CONCEPTS: dict[str, set[str]] = {
    "location": {"manchester", "northern", "office", "city", "premises", "site", "working"},
    "fee": {"fee", "cap", "percent", "price", "rate", "cost"},
    "timeline": {"deadline", "march", "december", "schedule", "date", "timeline"},
}
_CONCEPT_KEYS = sorted(CONCEPTS)


class ConceptEmbeddingProvider:
    """A fake :class:`~app.knowledge.embedding_provider.EmbeddingProvider` (concept one-hot).

    Distinct from ``conftest.py``'s autouse ``_FakeEmbeddingProvider`` (768-dim zero vectors):
    that one is the hermetic *seam* that stops the real model loading and deliberately produces
    no usable geometry; THIS one produces meaningful cosine geometry to prove paraphrase ranking.
    Don't add a third — pick the right one of these two.
    """

    name = "fake:concept"
    dim = len(_CONCEPT_KEYS)

    async def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            words = set(re.findall(r"[a-z0-9]+", text.lower()))
            vec = [1.0 if (CONCEPTS[c] & words) else 0.0 for c in _CONCEPT_KEYS]
            norm = sum(x * x for x in vec) ** 0.5
            out.append([x / norm for x in vec] if norm else [0.0] * self.dim)
        return out
