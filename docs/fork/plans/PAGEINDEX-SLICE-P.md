# Plan — F2 Slice P: PageIndex (reasoning-based, vectorless) retrieval — eval-first

Status: **DRAFT for maintainer edit** (CLAUDE.md flow: explore → written plan → human edits → implement).
Milestone: F2 — Memory / retrieval (ADR-F049 named PageIndex as the "eval candidate, Slice P").
Linked ADRs: **F049** (retrieval/memory architecture; PageIndex = eval candidate), **F010** (gateway is
the only egress — why we reimplement, not adopt, the library), **F015** (eval results are findings, not CI
bars), **F051 / F049-Slice-E** (the cost brakes this reuses). New ADR to draft: **F052**.

---

## 1. Why this slice, and what it is NOT

**The insight that triggered it.** PageIndex is *a table of contents the model navigates*. You build a
hierarchical tree of a document (sections → subsections, each with a title + short summary), and at query
time you hand the model the tree and let it *reason its way down* to the right section — no embeddings, no
vector DB, no fixed-size chunking ("vectorless / reasoning-based RAG"). The heavy compute is **LLM
reasoning, which runs on our gateway, not on this box**. Confirmed by investigation: the tree is ~10–100 KB
JSON, RAM-light; PageIndex is **gateway-bound, not RAM-bound — it runs fine on the 6.3 GB / zero-swap box.**

This is the **opposite** of the local-ONNX embed/rerank line (Slice C1/D), whose *batch evaluation* OOM-kills
this box (bge + cross-encoder + thousands of inferences → ~3.4 GB anon-rss → instant kill, no swap). The
PageIndex eval is gateway-bound, so **it is measurable here** — unlike the hybrid+rerank-at-scale batch we
had to defer to a bigger box.

**Reimplement, do not adopt.** `VectifyAI/PageIndex` is MIT, but it routes LLM calls through **LiteLLM** — a
new egress-capable client. That violates **gateway-only egress (ADR-F010)** and adds SBOM/supply-chain
surface against fork discipline. We rebuild the *technique* (tree-build + tree-navigate) as **gateway chat
calls**. No new dependency.

**Cost is the real risk, not RAM.** The reference impl spends ~150–260 LLM calls to build *one* document's
tree, plus 2–4 calls per query. So PageIndex **cannot be a corpus-wide default** — it is a **targeted,
per-document, deep-navigation** capability, and we have a **cheap-tree lever** (below) to cut most of the
build cost. This is exactly why the slice is paired with the cost-brake audit (§2): the safety story is what
makes a token-hungry retriever shippable.

**Correction banked from the investigation.** PageIndex is **not** a reranker-shaped `score(query, passages)`
provider (one investigator modeled it that way). Its interface is **`build_tree(document)` + `navigate(tree,
query)`** — it mirrors the provider *seam* (Protocol + factory + process-global get/set + gateway-routed) but
not the reranker's signature.

### Non-goals (this slice)
- **No corpus-wide / ingest-time tree build.** Build is targeted (one document) and, in P1, in-memory for the
  eval only. Persistence + on-demand build = **P2** (gated on P1's result).
- **No agent tool wiring / no UX.** P1 ships the mechanism **dormant** (default off) and measures it, exactly
  as Slice A shipped the fusion branch dormant until C1 proved it. Agent tool = **P2**.
- **No migration in P1** (the tree is built in memory for the eval; persistence is a P2 migration).
- **No LiteLLM, no direct provider call** — every PageIndex LLM call goes through the gateway.
- **No replacement of hybrid+rerank.** The target architecture is *compositional*: hybrid+rerank routes the
  corpus → the right document (fast, cheap); PageIndex deep-navigates *within* a chosen document (slow,
  accurate). P1 measures the within-document deep-navigation quality only.

---

## 2. Cost brakes that already exist (audit result) — what P-work reuses, what's missing

Full inventory verified in-code across the fork agent path, the gateway, and the legacy executors.

### Enforced today (fork agent path — `api/app/agents/`)
| Brake | Where | Reuse for PageIndex |
|---|---|---|
| **`run_token_budget`** (R4 realised, 2M default, ≤0 disables) | `runner.py:465-467`, `config.py:221-249` | **Primary backstop.** Sums *all* model turns (lead + subagents) on `on_chat_model_end`. PageIndex's gateway calls in an agent run accumulate here. Coarse + uncalibrated. |
| **`fan_out_quota`** (8) | `fan_out_middleware.py`, `config.py:221-228` | Caps `task` subagents — only relevant if P2 fans out per-document builds. |
| **`max_steps`** (≤100, hard ceiling) | `runner.py:462-464`, `schemas/agent_runs.py:75` | Each gateway call ≈ steps; a big build could exhaust 100. |
| **Wall-clock** (900s constant) | `runner.py:64,373` | A long build could hit it; it's a constant, not a Setting. |
| **R6 grant / R5 halt+fence** | `guard.py:100-128` | A P2 `navigate_document` tool must be granted; halt/fence apply. |
| **Gateway per-call cost + routing log** | `router.py:443-470`, `routing_log.py:57-87` | Every call writes `cost_estimate` + `purpose`. Tag PageIndex calls (`pageindex_build`/`pageindex_navigate`) for visibility. |
| **estimate_read_cost tool** (Slice E pattern) | `tools.py`, `schemas/matter_memory.py` | Template for a P2 "estimate tree-nav cost" pre-flight so doctrine picks PageIndex only when justified. |
| **Legacy autonomous R4 USD cap** (real) | `autonomous/guard.py:213-233` | Pattern reference only — it's the legacy path, not the fork agent path. |

### Dormant / missing (the gaps a token-hungry retriever exposes)
- **No `run_id` in `inference_routing_log`** (`routing_log.py:57-87`) → cannot attribute a gateway call's
  cost to a run; `agent_runs.cost_usd` stays NULL (ADR-F051). *PageIndex per-run cost is not queryable in
  dollars* until the routing-log attribution slice lands.
- **No per-document build cost cap** — only the whole-run 2M-token ceiling exists.
- **No per-query LLM-call count cap** — `fan_out_quota` caps `task` subagents, not a sequential chain of
  gateway tool calls.
- **Gateway `request_validation.max_max_tokens` (16384) is DORMANT** (`gateway/config.py:326`, not enforced).
  A cheap free win: activating it would cap runaway per-call output. *Noted as a P2/independent gateway
  follow-up — not P1 scope.*
- **`run_token_budget` default (2M) is uncalibrated** — now that `agent_runs.total_tokens` persists (Slice
  G, mig 0079), a PageIndex run gives the first real calibration datapoint.

**P1 cost containment (in the provider + eval itself, no infra change):** the provider bounds calls —
`pageindex_max_build_calls` and `pageindex_max_nav_calls` (single nav call) — builds the tree **once per
document, cached in-memory across that document's questions**, and prefers the **structural (near-zero-LLM)
build** where structure exists. The eval runs ALONE on a small subset; gateway-bound, no OOM.

---

## 3. What we have to build a tree from (doc-structure finding)

Per-chunk we already store: `page_start/page_end` (1-based), **char offsets** (`char_offset_start/_end`,
byte-precise, invariant `content == normalized_content[start:end]`), `chunk_index` (ordered), `tokens`.
Per-document: `normalized_content` (full canonical text), `character_count`, `page_count`, and **Docling
`structured_content` JSONB** (heading hierarchy levels 1-6+, when `parser='docling+pymupdf'`).

**Verdict: `hybrid` feasibility.**
- **Cheap structural tree** is possible from Docling headings + page ranges (≈0 LLM calls) — *but* Docling
  offsets are **not char-precise** vs PyMuPDF, and the CUAD eval corpus is seeded from text and **may not
  carry `structured_content`**. So structural is a **production cost-optimization (P2)**, validated once
  ingestion provides structure — **not the P1 eval path**.
- **LLM-built tree over the chunks** is corpus-agnostic and testable now → **the P1 path.**

**Key design choice — build the tree over CHUNKS, not raw text.** Feed the model the document's *ordered
chunks* (index + text), and have it group them into a titled hierarchy where **each leaf node lists the
`chunk_index`es it covers**. Node → chunks is then **exact** (chunk_index → stored char offsets), avoiding
the "LLM emits wrong offsets" problem entirely. This makes navigation→spans exact for scoring.

```
TreeNode {
  id: str                  # stable path id, e.g. "2.3"
  title: str               # section heading the model assigns
  summary: str | None      # optional 1-line; navigation can run on titles alone (cheapest)
  chunk_indices: list[int] # leaf coverage; interior nodes aggregate children
  children: list[TreeNode]
}
```

---

## 4. Design — Slice P1 (mechanism + eval, dormant, NO migration)

### A. Provider seam — NEW `api/app/knowledge/page_tree_provider.py`
Mirror `embedding_provider.py` / `rerank_provider.py` structurally (Protocol + factory + process-global
`get_/set_` + carve-out comment), but with the **PageIndex interface**:
- `@runtime_checkable class PageTreeProvider(Protocol)`: `name: str`;
  `async def build_tree(self, chunks: Sequence[TreeChunk], *, build_calls_cap: int) -> TreeNode`;
  `async def navigate(self, tree: TreeNode, query: str, *, top_nodes: int) -> list[str]` (ranked node ids).
- `GatewayPageTreeProvider` (the only real door): routes through the gateway via an **injected async chat
  callable** (so production wires the gateway chat model and tests inject a fake — no global reach in
  business logic). Tags calls `purpose='pageindex_build' | 'pageindex_navigate'` for routing-log cost
  visibility. Bounds calls to the caps. Builds hierarchically in batches (group N chunks → titled nodes →
  group nodes) so build_calls scale with `ceil(doc_chunks / batch)`, not per-chunk.
- `build_page_tree_provider(settings, chat)` factory; process-global `get_page_tree_provider()` /
  `set_page_tree_provider()`. **No Door-B/local variant** — there is no local model; the gateway *is* the
  compute. (Future: a structural builder is a *build mode*, not a second door — see §6.)
- Carve-out comment: unlike the embedder/reranker (a local "second inference locus"), PageIndex's locus **is
  the gateway** — it holds no key, adds no egress, and is the gateway-only-egress-compliant way to do
  reasoning retrieval (ADR-F010, ADR-F052).

### B. Config — `api/app/config.py` (group with the rerank fields)
- `pageindex_enabled: bool = False` (**dormant** until the gate; flips on the measured result).
- `pageindex_model: str` — a **gateway alias** (NOT a provider model id), default the available reasoning
  alias on the local gateway (deepseek reasoning; Claude isn't on the local gateway). Routing/tier-floor
  apply per call.
- `pageindex_build_mode: str = "llm"` — `llm` (P1) | `structural` | `auto` (P2 modes; `structural` slots in
  when ingestion provides `structured_content`).
- `pageindex_max_build_calls: int = 12` — hard cap on tree-build gateway calls per document.
- `pageindex_batch_chunks: int = 25` — chunks grouped per build call.
- `pageindex_top_nodes: int = 3` — nodes navigation may select (matches the technique's "2-3 nodes").

### C. Within-document tree retrieval — `api/app/knowledge/retrieval.py`
NEW `async def matter_search_tree(db, *, project_id, user_id, query, document_id, top_k, provider,
build_calls_cap, top_nodes, reranker=None) -> list[MatterSearchHit]`:
1. Load the document's chunks (matter+owner scoped — same isolation as `matter_hybrid_search`;
   `document_id` **required** — PageIndex is within-document).
2. `tree = await provider.build_tree(chunks, build_calls_cap=...)` (caller caches per document across that
   doc's queries — the eval and any P2 caller own the cache; the function itself is stateless).
3. `node_ids = await provider.navigate(tree, query, top_nodes=...)`.
4. Gather the union of `chunk_indices` under the selected nodes → those chunks.
5. **Rank within the selected set** to `top_k`: if `reranker` is provided, reuse the Slice-D cross-encoder to
   order the selected chunks (compositional: PageIndex routes to the section, the reranker orders within it);
   else document order. Truncate to `top_k`. Return `MatterSearchHit`s (reuse the existing shape + char
   offsets for span scoring).
6. Provider error → **degrade to `matter_search_reranked`/`matter_hybrid_search`** for that document (never
   hard-fail; mirrors the embedder/reranker fallback discipline). `matter_hybrid_search` stays **byte-
   identical** → the frozen E0/Slice-A FTS baselines + `_REFERENCE_FTS` drift guard are untouched.

### D. Track-B PageIndex arm + calibration — `api/tests/agents/scenarios/`
- Extend `cuad_eval.py`: a **`pageindex` arm**, **within-document only** (cross-doc routing stays hybrid's
  job — state this explicitly; no silent cap). Build each contract's tree **once**, cache, answer all its
  present-clause questions, score selected chunks' char spans vs CUAD gold.
- **Primary metric = within-doc `recall@8` / `hit@8`** (did tree-navigation surface the chunk containing the
  clause? — that's what navigation controls). Secondary: `precision@k`, `MAP` (document-order truncation).
  All metrics already exist in `retrieval_metrics.py` — **no metric code.**
- NEW `test_cuad_pageindex_baseline.py` (mirror `test_cuad_rerank_baseline.py`): corpus-gated, real gateway
  (deepseek reasoning alias), **small subset of the LARGER CUAD contracts** (PageIndex's strength is long,
  structured docs — pick ~8 by length), run **ALONE** (gateway-bound → no OOM, unlike the C1/D batches).
  Estimate + record the gateway token cost from the routing log (`purpose='pageindex_*'`). Freeze evidence
  under `docs/fork/evidence/retrieval-eval-pageindex/`.
- **Gate (ADR-F015 finding, pre-registered post-baseline, never tighter than noise):** ship `pageindex_
  enabled=True` **only if** within-doc `recall@8` (and `hit@8`) **beats the hybrid+rerank within-doc floor**
  (Slice D: within-doc recall@8 ≈ 0.33, hit@8 ≈ 0.356) by ≥ the registered margin, at acceptable per-query
  call cost/latency. Else ship **dormant** with the honest finding (the Slice A/C1/D precedent).

### E. Deterministic, hermetic tests ($0, no gateway — CI-safe)
- `FakePageTreeProvider` in `api/tests/agents/embedding_fakes.py` (alongside the fake embedder/reranker):
  deterministic tree from chunk order; navigation = keyword-overlap node pick. No network.
- NEW `test_page_tree_provider.py`: Protocol shape; build-call cap respected; navigation returns ≤ top_nodes
  ids; injected-chat fake drives a deterministic tree; gateway provider tagged with the right `purpose`.
- NEW `test_matter_search_tree.py`: node→chunk mapping exactness (selected node ids → correct char spans);
  matter/owner scope isolation (reuse `test_matter_hybrid_search.py` seeding; cross-user/matter → empty, the
  404-conflate discipline); provider-error fallback == `matter_search_reranked`; reranker-within-section
  ordering path.
- Extend `test_cuad_retrieval_smoke.py`: a pageindex arm over the 3-contract synthetic corpus with the fake
  provider (deterministic, Postgres-only, CI).

---

## 5. Critical files
- NEW `api/app/knowledge/page_tree_provider.py` (provider seam; mirrors `rerank_provider.py`).
- `api/app/knowledge/retrieval.py` (`matter_search_tree`; `matter_hybrid_search` UNTOUCHED → frozen baselines
  hold); `api/app/config.py` (pageindex_* Settings).
- `api/tests/agents/scenarios/cuad_eval.py` (pageindex arm) + NEW `test_cuad_pageindex_baseline.py`; reuse
  `retrieval_metrics.py`; fakes in `api/tests/agents/embedding_fakes.py`; NEW `test_page_tree_provider.py`,
  `test_matter_search_tree.py`; extend `test_cuad_retrieval_smoke.py`.
- Gateway routing reuse: the agent's gateway chat path (`api/app/agents/factory.py` `build_gateway_chat_
  model`) — inject it as the provider's chat callable at the composition root; **no gateway code change in
  P1.**
- Docs: **ADR-F052** (PageIndex reasoning retrieval); update `plans/RETRIEVAL-MEMORY-eval-first.md`,
  `MILESTONES.md`, `HANDOFF.md`; evidence `docs/fork/evidence/retrieval-eval-pageindex/`; memory.

---

## 6. Slice P2 (follow-up — gated on P1's measured win; NOT this PR)
- **Persist the tree**: migration `documents.tree_index JSONB NULL` + `tree_status` (pending/ready/failed) —
  build once, reuse; idempotent background job (only for a *chosen* document, never corpus-wide).
- **Cheap structural build mode**: tree from Docling `structured_content` headings + page ranges (≈0 LLM
  calls); `auto` mode = structural where structure exists, LLM fallback. Validate the structural path's
  quality once ingestion provides `structured_content`.
- **Agent tool** `navigate_document(document_id, query)`: matter+owner scoped (404-conflate), gated on
  `tree_status='ready'`, R6-granted, reuses `run_token_budget`; doctrine selects it only for within-document
  deep-dives on large docs (compose with hybrid for routing).
- **Cost hardening**: a `estimate_tree_cost` pre-flight (Slice-E pattern); a per-document build token sub-cap;
  activate the dormant gateway `request_validation.max_max_tokens`; and (cross-service) the routing-log
  `run_id` attribution so PageIndex per-run **dollar** cost is queryable (closes the ADR-F051 gap).

---

## 7. Verification / DoD (ADR-F005 gate)
- **Deterministic** (dev image; repo root + `skills:/skills:ro`; `--network lq-ai_default`;
  `DATABASE_URL`→postgres): the new hermetic tests (fake provider) + full `tests/agents/` counts quoted; CI
  commands `ruff check api scripts` + `ruff format --check api scripts` + `mypy app` clean; the frozen
  E0/Slice-A FTS drift guard still byte-identical. CI (no gateway key) is authoritative — gateway-marked
  tests skip there.
- **Live (Track-B finding):** the N≈8 PageIndex calibration, within-doc, real gateway (deepseek reasoning),
  **run ALONE**; recall@8/hit@8 vs the hybrid+rerank within-doc floor; per-query call cost + latency
  recorded; gate margin pre-registered; baseline frozen under `docs/fork/evidence/retrieval-eval-pageindex/`
  (counts/scores + public CUAD ids only — no clause text). Chown evidence (written as root in-container).
- **No migration in P1** (persistence is P2). **No new dependency.** **No gateway code change.**
- **Fresh-context adversarial review** incl. the mandatory **security + simplification pass**: provider holds
  no key + all egress via gateway (ADR-F010); provider injected, not global-reached in business logic; tree
  built from *retrieved documents = untrusted model input* → the build/navigate prompts must treat chunk
  text as data, not instructions (prompt-injection: a contract clause saying "ignore prior instructions"
  must not steer tree-build/navigation); matter/owner scope on every read (cross-tenant → empty/404); no
  user text in SQL; KB/chat path provably untouched; no stray files / leaked secrets; dead-code/dup sweep.
- **ADR-F052** drafted in the PR (PageIndex = reasoning retrieval; reimplement-not-adopt per ADR-F010;
  gateway-is-the-locus; within-doc-only + compose-with-hybrid; the gate finding + default decision; the cost
  brakes reused + the gaps deferred to P2). HANDOFF updated; memory written; merge under the full ADR-F005
  gate (`gh ... --repo sarturko-maker/lq-ai-fork`; branch+PR — direct main pushes blocked; commits end
  `Co-Authored-By: Claude Opus 4.8`).

---

## 8. Risks / gotchas
- **Prompt injection via document text** (load-bearing): chunks are untrusted model input. Build/navigate
  prompts must fence chunk text as data. This is in the security pass, not optional.
- **CUAD eval corpus may lack `structured_content`** → P1 measures the **LLM** build path (correct + corpus-
  agnostic); the structural cost-optimization is a P2 validation. Don't claim the cheap path's numbers from
  P1.
- **Gateway quota / model availability**: the live eval needs the gateway up with reasoning-model quota
  (deepseek-pro; not Claude locally). If quota is thin, shrink N; CI uses the fake (no gateway).
- **Cost honesty**: PageIndex per-query LLM cost is **recurring** (2–4 calls) and tree-build is heavy — P1
  must report measured per-query + per-build token cost, not just quality, so the P2 ship/strategy decision
  is cost-aware. Don't bury the cost.
- **Metric framing**: CUAD gold is often a single clause → precision@5 caps low (the Slice D lesson);
  PageIndex's honest metric is **recall@8/hit@8** ("did navigation find the section?"). Pre-register on that.
- **Byte-identical guard**: `matter_search_tree` is a *new* path; `matter_hybrid_search` stays untouched so
  E0/Slice-A baselines + `_REFERENCE_FTS` hold.
- **Latency**: tree-navigation is seconds, not the reranker's tens of ms. Acceptable for a targeted deep-dive
  tool (P2), not for every search — the doctrine must reflect that.

## 9. Recommended order
provider seam + config (dormant) → `matter_search_tree` (+ fallback, reranker-within-section) → hermetic
fake-provider tests → Track-B pageindex arm + N≈8 live calibration (run ALONE; set the margin; freeze) → set
the production default on the result → ADR-F052 + plan/MILESTONES/HANDOFF/memory → adversarial review → PR +
merge under the ADR-F005 gate.

---

## 10. Upstream reuse verdict (awareness-only investigation of `github.com/LegalQuants/lq-ai` HEAD `efec90e`)

The maintainer asked: *if we're building, is there a reason not to reuse what upstream already has?* Upstream
is well ahead of our baseline `f91149a` (HEAD is PR #242+; new post-fork subsystems: a chat tool-loop
`api/app/chat/`, `tool_call_log` mig 0053, gateway `tool_egress_log.py`, `mcp_oauth_tokens` mig 0051, and
PR5b Anthropic tools-forwarding). Verdict per item:

| Fork item | Decision | Why |
|---|---|---|
| `run_token_budget` token brake (Slice F) | **REBUILD justified** | Upstream's only cost cap is the **autonomous** R4 — USD, coupled to the `AutonomousSession` ORM + a fixed `ToolIntent` enum + the phase-machine. The deepagents runner has none of those; it streams `on_chat_model_end` usage. Token accumulation is exact + provider-agnostic + needs no price table. |
| `FanOutQuotaMiddleware` (Slice E) | **REBUILD justified** | No upstream analogue — upstream has no model-chosen subagent (`task`) spawning to bound. |
| `guarded_dispatch` R4/R5/R6 | **REBUILD justified** | Upstream `autonomous/guard.py` requires an `AutonomousSession` + `ToolIntent` + `PHASE_GRANTS` — non-portable to `agent_runs`. R5/R6 are structurally isomorphic; only R4 differs (tokens vs USD). |
| `matter_hybrid_search` + cross-encoder rerank + **PageIndex** | **REBUILD justified** | Upstream retrieval is **flat vector+FTS only** — no cross-encoder, no structure/TOC awareness. Nothing to reuse. |
| **`agent_runs.cost_usd` (NULL today)** | **REUSE — the one wheel we're not using** | `api/app/citation/cost.py:106 estimate_judge_call_cost_usd` is a standalone async fn that rolls an average USD rate from `inference_routing_log` (the table our gateway already writes). Call it once at `settle_run` to estimate a per-run **USD** from the persisted `total_tokens` — **no migration, no gateway change.** It's an *estimate* (rolling average); *exact* per-call attribution still needs the deferred routing-log `run_id`. This refines Deliverable-1: a dollar figure is cheaply achievable **now** by reuse; only exactness is deferred. |
| Gateway USD cost tracking / rates / `FixedWindowRateLimiter` | **REUSE (already in our fork)** | Inherited at baseline; the per-tool-provider RPM limiter is already wired and extensible if we ever need request rate-limiting. |

**Flag for a maintainer decision (frozen-upstream / ADR-F001):** CLAUDE.md **blocker #2** ("gateway Anthropic
adapter is text-only — never forwards `tools`") is **resolved upstream** by PR5b
(`gateway/app/providers/anthropic.py`). Our fork still has the pre-PR5b adapter. *Low urgency for us* — we
route tool-calling through OpenAI-compatible providers and Claude isn't on the local gateway — but (a) the
blocker list is now partially stale, and (b) backporting PR5b would need explicit per-case approval. Not
acted on; surfaced only.

**Net:** the deepagents-path rebuilds are genuinely justified by the execution-model gap — we are **not**
reinventing reusable wheels, with the single exception of `cost_usd` (now folded into Slice O).

---

## 11. Companion Slice O — cost envelope: raise defaults ≥4× + tunable UI (a real prerequisite for liberal use)

> **STATUS: IMPLEMENTED** on `fork/f2-slice-o-cost-envelope` (ADR-F053, migration 0080) — budget profiles
> (economy/balanced/generous), balanced default = 4× economy, composer Budget dropdown. The `cost_usd`
> estimate (the actioned upstream-reuse finding) is split to **Slice O-2** (see §10).

PageIndex + liberal fan-out are only safe-to-use-freely if the *ceiling* is generous and the *knob* is easy.
Upstream has **no** budget-profile / per-user-quota / cost-dashboard system to reuse — this is new work.

**Raise the backstops (ceiling = runaway guard, not expected spend):**

| Brake | Today | ≥4× | Change |
|---|---|---|---|
| `run_token_budget` | 2,000,000 | **8,000,000** | `config.py` default (1 line) |
| `fan_out_quota` | 8 | **32** | `config.py` default |
| `max_steps` | 100 (ceiling `le=100`) | **400** | default **and** raise the `AgentRunCreate` schema ceiling |
| wall-clock | 900s (constant) | **3600s** | promote `DEFAULT_WALL_CLOCK_SECONDS` to a Setting first; bump arq `AGENT_RUN_JOB_TIMEOUT_SECONDS` (1020s) above it (→ ~3720s) |

**Tunable UI = budget *profiles*, not raw integers:** one dropdown — **Economy / Balanced / Generous** — at
the per-matter (default) and/or per-run (composer "advanced") level, mapping to a `(token_budget, fan_out,
max_steps, wall_clock)` tuple. "Easy to reduce" beats four number fields. `AgentRunCreate` already carries
`max_steps`; extend it with the profile (validated, high default) and thread into `execute_agent_run`.

**Fold in the reuse win:** populate `agent_runs.cost_usd` at `settle_run` via the upstream
`estimate_judge_call_cost_usd` rolling-average pattern (§10) — so the budget UI can show *estimated spend*,
not just a token count. Cost-honesty: 8M tokens is a large backstop on a premium model, but the local gateway
runs cheaper models and the knob is the mitigation; surface the estimate so the user sees it.

**Cost-honesty caveat to record in the ADR:** raising ceilings widens blast radius; the mitigation is (a) the
estimate is visible, (b) the knob dials down, (c) the brakes still fire at the (higher) ceiling.

Sequencing: **Slice O before/with Slice P** (P needs the headroom + the knob). O is small and independently
valuable. Draft as an addendum to ADR-F051 (it tunes the same brakes) or a short ADR-F053.

---

## 12. Strategy doctrine — the cost / speed / context balance (when capabilities kick in)

The capabilities (PageIndex, hybrid, rerank, fan-out) are only worth it **at sensible times**. With the
ceiling raised (Slice O), **cost is no longer the day-to-day throttle** — the agent *can* fan out and
deep-navigate freely. The real arbiters become **speed** and **context**:

- **Cost** — bounded by the (high, tunable) caps; a backstop, not a per-decision tax. ⇒ *fan out / deep-dive
  liberally* within the envelope.
- **Speed** — fan-out has spawn overhead; PageIndex navigation is **seconds/query** vs the reranker's tens of
  ms. ⇒ *fan out when parallel breadth genuinely beats the spawn cost; don't reflexively.*
- **Context** — some reads simply won't fit the window. ⇒ *this is why PageIndex earns its place — it
  navigates to sections instead of dumping a whole document.*

**Explicit selection rule (extends the Slice-E `RETRIEVAL_STRATEGY_DOCTRINE`):**
- **hybrid+rerank** — the default; fast, cheap, corpus-wide *routing* (which document?).
- **PageIndex** — only when a document is **too large to read wholesale** *and* **within-doc precision
  matters** *and* **latency is tolerable** (a deliberate deep-dive, not an interactive quick lookup).
- **fan-out (`task`)** — when breadth across documents/subquestions beats the spawn-latency cost; bounded by
  `fan_out_quota` (now 32).

This balance — not the cost cap — is what the doctrine prose must teach the model. The cap keeps it safe; the
doctrine keeps it *fast and within-context*. (P2's `estimate_tree_cost` pre-flight gives the agent the
numbers to make this trade explicitly.)
