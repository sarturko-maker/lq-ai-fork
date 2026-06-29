# Slice A verification (ADR-F049) — matter document tool wired to one hybrid retriever

Dev stack, 2026-06-29. Slice A (the first F2 Phase-2 "cost play" slice) collapses three copies of the
matter FTS query into **one** retriever, `app/knowledge/retrieval.py:matter_hybrid_search`, and routes
**both** the agent's `search_documents` tool and the Track-B eval `fts_retrieve` through it. No embedder is
wired yet, so the tool passes `query_embedding=None` and the function takes its **FTS-only fast path** — which
must be byte-identical to the pre-Slice-A matter retriever and the frozen E0 baseline. A hybrid fusion branch
(FTS + pgvector, min-max fused) is present and unit-tested but **dormant** until Slice C. **No migration, no
new dependency, no gateway change.**

## 1. Deterministic gate (dev image, real test DB + InMemoryStore — no live model)

- `tests/agents/scenarios/test_matter_hybrid_search.py` — **3 passed.** The genuinely-new behaviour:
  - **document_id narrowing:** `document_id=None` searches the whole matter; a value narrows to one doc.
  - **scope isolation:** a keyword present in two different matters never crosses between them; passing
    matter B's `project_id` with matter A's `user_id` returns `[]` (owner re-assert is the boundary).
  - **fusion branch (synthetic 1536-dim vectors seeded directly):** `query_embedding=None` / `alpha>=1` stay
    FTS-only (the vector is ignored even when supplied); `alpha=0` ranks by cosine (the query's target chunk
    first); a middling `alpha` merges the FTS hit with the vector hit. Proves the branch Slice C lights up.
- `tests/agents/scenarios/test_cuad_retrieval_smoke.py` — **2 passed.** The drift guard
  (`test_matter_retriever_fts_only_matches_frozen_reference`) pins `matter_hybrid_search` (FTS-only) against
  a frozen `_REFERENCE_FTS` oracle (the exact pre-Slice-A matter query) — so any change to the matter scope,
  the FTS operator, or the tiebreak fails loudly. Plus the synthetic end-to-end baseline smoke.
- `tests/agents/test_agent_tools.py` — **20 passed.** The `search_documents` / `read_document` /
  `get_document_metadata` tool contract + the audit-body-free check, all **unchanged through the new path**
  (incl. the file seeded `ingestion_status='processing'` that still returns — guarding the deliberate
  absence of the KB-only `ingestion_status='ready'` filter on the matter path).
- Full api suite (touched-service gate): **see the PR body / HANDOFF for the quoted count.**
- `ruff check api scripts` + `ruff format --check api scripts` (CI commands, repo-root config) + `mypy app`
  (206 files): **clean.**

## 2. Track-B re-freeze — the no-regression gate (ADR-F015 finding)

The full **150-contract** CUAD baseline (2084 present + 4066 absent questions, 4911 chunks) re-run
retriever-only **through the new `matter_hybrid_search` path** (FTS-only mode), then compared field-by-field
to the frozen E0 baseline (`docs/fork/evidence/retrieval-eval/baseline/baseline.json`).

Run: dev image, throwaway pgvector test DB, `LQ_AI_CUAD_SUBSET=150`, no gateway / $0, 102 s. Working tree =
Slice A on top of `32cbdd34` (the merged N3 HEAD).

**Result — byte-identical, to full float precision:**

| metric | frozen E0 | Slice A (new path) | match |
|---|---|---|---|
| within-doc hit@8 | 0.39107485604606523 | 0.39107485604606523 | ✅ |
| within-doc MAP | 0.2964496737846744 | 0.2964496737846744 | ✅ |
| within-doc recall@5 | 0.3442663615357827 | 0.3442663615357827 | ✅ |
| cross-doc hit@8 | 0.044145873320537425 | 0.044145873320537425 | ✅ |
| cross-doc MAP | 0.018335489950179133 | 0.018335489950179133 | ✅ |
| present questions | 2084 | 2084 | ✅ |
| chunks | 4911 | 4911 | ✅ |

The **entire** `within_doc` + `cross_doc` + `absent_control` + `per_category_within_doc` blocks compare
equal. So the re-freeze writes nothing new: the run's `baseline.json`/`baseline.md` were byte-identical to the
frozen E0 artifacts and are **not** committed here (they would only duplicate them and confusingly re-label
the frozen baseline). This file records the comparison instead.

**Finding:** Slice A changes the matter retrieval *call path* — not the numbers. "Agent mode matches
retriever-only" is now structural (one function), not a hand-kept drift guard between two query copies. The
seam is ready for Slice C: `matter_hybrid_search` already takes `query_embedding` + `alpha`, so Slice C adds
the embedder and flips the call, and the same Track-B harness measures the delta with no rig change.

## Gate status

- New behaviour (fusion branch + scope isolation + document_id narrowing): ✅ deterministic
  (`test_matter_hybrid_search.py` 3/3).
- FTS-only byte-identity: ✅ drift guard vs frozen reference + ✅ full CUAD re-freeze == frozen E0 (above).
- Tool contract + audit-body-free: ✅ unchanged (`test_agent_tools.py` 20/20).
- No production change beyond the retriever + its two call sites; KB `hybrid_search` untouched; **no
  migration, no new dependency, no gateway change.**
- Fresh-context adversarial review (4-dim × adversarial verify): **see the PR body for the verdict.**
