# Slice C2 live gate — real bge embedder through the production Store index path

**What.** F2 Slice C2 wires the Slice-C1 `EmbeddingProvider` as the langgraph Store's
`IndexConfig.embed`, so `store.asearch(query=…)` ranks conversation/memory items by cosine
(a silent no-op filter-only before). This is the cross-thread *paraphrase* recall N3's
`search_matter_conversations` consumes (lexical alone misses a reworded mention).

**How (ADR-F015 finding, not a CI bar).** The REAL `fastembed`/`BAAI/bge-base-en-v1.5`
model (Door A, bundled in the image at `/opt/fastembed-cache`), the production index config
(`build_store_index_config`), and a real `AsyncPostgresStore` on a **throwaway pgvector**
container (the live dev DB is never touched). Two realistic offloaded conversation
summaries are indexed; genuine paraphrase queries — sharing **no salient keyword** with
their target — must (a) clear the tool's `_SEM_THRESHOLD = 0.6`, (b) outrank the off-topic
thread, while (c) an unrelated query stays below threshold (honest absence preserved).

The synthetic concept embedder in CI proves the *mechanism* deterministically; this gate
proves the *real model* separates genuine paraphrases with margin.

## Result — VERDICT: PASS

| query (paraphrase, no keyword overlap) | T1 "Manchester head-office relocation" | T2 "capped 4% fee, monthly invoicing" |
|---|---|---|
| "which northern city are they moving their headquarters to" | **0.6827** ✅ ≥0.6 | 0.4593 |
| "what are the billing and payment terms" | 0.4298 | **0.6192** ✅ ≥0.6 |
| "what is the governing law and jurisdiction clause" (off-topic) | 0.4400 | 0.4419 |

Checks (all PASS):
- location paraphrase surfaces T1 (≥ threshold) and ranks T1 > T2
- fee paraphrase surfaces T2 (≥ threshold) and ranks T2 > T1
- off-topic stays below threshold on BOTH threads (no invented match)

**Threshold calibration.** Real data separates cleanly: paraphrase hits land **0.62–0.68**,
off-topic/related-but-wrong land **0.43–0.46**. `_SEM_THRESHOLD = 0.6` sits in the gap with
a safety margin toward precision (no false positives) — a lower 0.5–0.55 would also admit
the true hits but narrows the honest-absence margin. Tunable; 0.6 chosen for precision.

**Model:** `local:BAAI/bge-base-en-v1.5`, dim 768. Symmetric embedding (the pg store embeds
the query via `aembed_documents`; bge's query-instruction asymmetry is not applied through
the Store path — see `app/agents/store.py`). Script: `scratchpad/live_a5_gate.py` (session).
