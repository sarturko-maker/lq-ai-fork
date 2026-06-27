# Research — Document retrieval at SCALE, with COST as a first-class dimension

**For:** the maintainer's follow-up to the first discovery pass
(`document-discovery-and-map.md`). That pass was **cost-blind** — it assumed the common case is one
small document you inline, and called lexical FTS "adequate." The maintainer rejected that for SCALE.
The driving scenario *here*: **one deal/matter with ~1000 documents** (mixed big and small),
**no embeddings yet** (the `pgvector` column is NULL), and the user asks **ONE question against the
ENTIRE document set**. This document centres cost, answers that scenario, and seriously evaluates
**PageIndex** plus **novel LOCAL chunking / embedding / enrichment** (local = run models on our own
infra, no per-token provider cost) as the cost-control play.

**Method:** codebase re-discovery (LQ.AI fork, branch `fork/c3-update-memory-ux`, head `1f8fc87`,
verified live against the running dev stack) + web research on unit costs + the first doc's
adversarially-verified PageIndex verdicts carried forward. Code claims were re-read at the cited
file:line; **live container introspection** is quoted where it changes the verdict. **Date:**
2026-06-27.

**Posture reminders baked into every recommendation:** all external-provider LLM calls route through
the in-house gateway (sole key-holder + only egress, ADR-F010); a per-action cost cap / halt / grant
brake exists on every agent tool call (R4/R5/R6, ADR-F002); unit-of-work memory is
**auto-write-then-correct** (ADR-F042); Apache-2.0 posture, AGPL is a hard server-side-only boundary;
new dependencies are SBOM/supply-chain surface and must be justified.

**What carries forward from the first doc (right):** the **documents MAP** — a maintained
`{document → one-line description · role · side · status}` layer — is the correct *cross-document
selection* primitive, it belongs in the typed fact ledger (ADR-F042/F043/F044), it is a sibling of
the authorship roster (ADR-F048), and PageIndex is the wrong *first* tool. **What this doc corrects:**
the cost blindness, and the claim that FTS is adequate at scale. The map is necessary but **not
sufficient** at 1000 documents — it routes *selection*, it does not *retrieve content*; at scale you
need a real within-corpus retriever underneath it, and the cheapest correct one is **local
embeddings**, not the cloud-embedding path the codebase currently wires.

---

## 1. Executive summary

- **Cost-at-scale verdict:** at N≈1000 mixed documents the dominant cost is **one-time indexing**, and
  the cheapest correct index is **local embeddings on our own CPU/GPU**, not a cloud-embedding round
  trip and emphatically not LLM-per-document tree-building. The recurring **per-query** cost of a
  local dense+FTS+rerank stack is **effectively zero dollars** (local compute, milliseconds), versus a
  real and recurring spend for any LLM-in-the-loop retriever (PageIndex tree-navigation) and a real
  one-time spend for any LLM-enrichment pass.

- **Recommended retrieval stack (the answer):** a **four-layer** pipeline —
  **(L1) documents MAP** (cheap router: which documents are even relevant) → **(L2) within-corpus
  hybrid retrieval** (local dense embeddings in `pgvector` + Postgres FTS, fused, then a **local
  cross-encoder rerank**) → **(L3) within-document navigation** (read the selected doc, or FTS inside
  it) → **selection/stickiness** glue (the map + active-document convention). L2 is the missing piece
  at scale.

- **The substrate is already 80% built and the first doc missed it.** The fork already ships a full
  hybrid retriever for KnowledgeBases — pgvector cosine + FTS + min-max score fusion
  (`api/app/knowledge/retrieval.py`), an embed worker that **auto-fires on ingest completion**
  (`api/app/workers/document_pipeline.py:85-89`), lazy embed-on-read, and a `vector(1536)` column on
  every chunk. The matter document tools simply **don't call it** — they run FTS-only
  (`api/app/agents/tools.py:70-83`). The gap at scale is **wiring + a vector backfill**, not new
  architecture.

- **The expensive blocker is the embedding *source*, not the machinery.** The wired embedding path
  routes the `embedding` alias to **OpenAI `text-embedding-3-small`** through the gateway
  (`gateway.yaml.example`), but the gateway's embeddings endpoint only works if an OpenAI key is
  configured, and every embedded token is **billed**. At 1000 documents that one-time bill is small in
  absolute terms (**~$1–6 per full matter**, see §4) — but it is a **recurring egress + per-token
  dependency** for something we can do **locally for free**.

- **Local embeddings are the cost play, and the SBOM cost is far smaller than the first doc implied.**
  **`torch 2.12.1` is ALREADY installed in the api/worker image** (transitive via Docling — verified
  live). `transformers`, `onnxruntime`, and `sentence-transformers` are **not** yet present. So a local
  embedder via **FastEmbed/ONNX** adds `onnxruntime` + the model file (tens of MB) and **no torch
  cost**; via `sentence-transformers` it adds `transformers` (torch already paid). Concrete throughput:
  **~50 embeddings/sec per CPU core** with FastEmbed ONNX on BGE-small — a 1000-doc corpus
  (~30k chunks) embeds in **~10 minutes on one core**, or far less across the worker pool / a GPU.

- **The gateway rule does NOT block local embeddings — it has two compliant doors.** (1) **In-process**
  encoding in the api/ingest worker is **local compute, not egress** — no key, no network, no provider;
  the gateway's mandate is about *external-provider* calls (ADR-F010), and a model file on our disk is
  not a provider. (2) If we prefer the gateway to remain the single inference choke point, the gateway
  **already defines Tier-1 local providers** (`ollama-local`, `vllm-local`, `local`/`local-fast`
  aliases — "Fully local; no data leaves the deployment", `gateway.yaml.example`); the Ollama
  embeddings adapter is a **documented ~30-line stub** away from serving local embeddings through the
  gateway (`gateway/app/providers/ollama.py:256-282`). Either door is clean; §5 recommends which.

- **PageIndex, reconsidered at scale: still NOT the corpus-query answer; a NICHE later option for the
  rare oversized single document.** The cost-at-scale lens makes it *worse*, not better, for the
  1000-doc question: it is a *within-one-document* navigator whose index is built by **~150–260 LLM
  calls per document** (web-confirmed). ×1000 that is a five-to-six-figure call count and a real bill
  even at budget tiers (§4, §6). It can be pointed at a *local* model via LiteLLM (which collapses the
  *dollar* cost but not the *latency/complexity*), and it adds `litellm` — **absent from the api image
  today** (verified) — as a second egress-capable client. Verdict: **niche/later**, gated on a measured
  oversized-doc need, and even then build the free chunk-derived section map first.

- **Contextual enrichment (small local LLM writes a one-line "what this chunk is" before embedding) is
  the high-value *optional* upgrade — do it LOCALLY or not at all.** Anthropic's own number for
  cloud contextual retrieval is **$1.02 per million document tokens one-time** (with prompt caching);
  at our scale that's a modest one-time bill, but the *same* enrichment on a local Tier-1 model is
  **$0** and doubles as the **documents-map description generator** — one local pass populates both the
  router (L1) and better embeddings (L2). Defer it behind dense+FTS+rerank, but design for it.

- **Decomposition:** (a) **cheap win** — wire the matter tools to the *existing* hybrid retriever and
  add a vector-coverage signal (no new dep, immediate scale relief once vectors exist); (b)
  **scale-foundation** — a **local embedding** backfill so vectors exist without per-token cost
  (ADR-F049); (c) **advanced** — local contextual enrichment feeding both the map and embeddings, and
  (only if measured) chunk-derived section maps / PageIndex. Triggers and thresholds in §8.

---

## 2. What the first pass got wrong

The first doc is correct on *selection* (the documents map) and on the single-small-document common
case. It is wrong on two load-bearing points, both downstream of treating cost as free.

### 2a. The cost blind spot (named)

The first doc's balance rule is *"just read the whole document … tokens are cheap enough … inlining
beats any retrieval machinery"* (`document-discovery-and-map.md` §1, §6). That is true for **one**
≲40k-char document and **false** as a corpus strategy. It never models:

- **One-time index cost vs per-query cost** as separate axes (the entire shape of the scale problem).
- **The recurring per-token cost of the embedding source** it implicitly endorsed (the wired path
  bills every embedded token to OpenAI through the gateway).
- **The LLM-call multiplier** of any reasoning-based index (PageIndex) at ×1000.
- **Local compute as a cost lever** — the option that makes per-query cost genuinely zero.

The corrected stance: **cost has two axes — ONE-TIME (index/enrich/tree-build) and PER-QUERY — and
they trade off.** "Just read it" minimises both for N=1; at N=1000 it is not on the table at all (§3),
and the right move is to push cost into a **cheap, local, one-time** index so per-query stays near
zero. §4 is the parametric model the first doc lacked.

### 2b. "FTS is adequate at scale" — the verified error

The first doc states *"FTS retrieval is adequate at our scale"* and *"the gap is a description +
selection-stickiness gap, not a retrieval-power gap"* (§3). **Verdict on that claim: REFUTED for the
1000-document corpus-query scenario.** Two independent reasons, one from the code and one from the
problem:

- **It mis-scoped its own evidence.** The doc verified that the *matter tools* are FTS-only
  (`tools.py:70-83`) and concluded FTS is the ceiling. But the fork **already contains** a hybrid
  dense+FTS retriever with min-max fusion and candidate overshoot (`api/app/knowledge/retrieval.py`,
  ADR 0008), an embed worker wired to fire on ingest (`document_pipeline.py:85-89`), and a
  `vector(1536)` column on every chunk (`document.py:207-211`). FTS-only is a **wiring choice on the
  matter path**, not the platform's retrieval ceiling. Calling FTS "adequate" while a superior built
  retriever sits one function call away is the central miss.

- **Lexical FTS structurally fails the corpus query.** `websearch_to_tsquery('english', …)` matches
  **stemmed lexemes**. Ask *"which documents limit our liability?"* across 1000 docs and FTS returns
  only chunks containing "liabilit*"/"limit*" — it misses "cap on damages," "aggregate exposure shall
  not exceed," "indemnification ceiling," and every synonym/paraphrase a contract actually uses. At
  small N a human (or the agent) papers over recall gaps by reading everything; at N=1000 there is no
  papering over — **recall is the whole game**, and lexical recall over legal paraphrase is exactly
  where dense embeddings earn their keep. FTS stays valuable for **exact terms, defined-term names,
  party names, dollar figures, citations** — which is why the recommendation is **hybrid**, not
  "replace FTS," matching what ADR 0008 already built.

**Net:** the first doc's *selection* thesis (the map) survives intact and is carried forward (§7). Its
*retrieval* thesis (FTS is enough) does not survive the scale scenario and is corrected to **hybrid
local-dense + FTS + local rerank** (§5).

---

## 3. The scale scenario

**Setup (the maintainer's driving case):** one matter, ~1000 documents, mixed sizes (NDAs and emails
of a few KB alongside 200-page credit agreements and data-room PDFs), **`document_chunks.embedding`
is NULL for all of them** (the column exists; nothing populated it on the matter path), and the user
asks **one question over the entire set** — e.g. *"Across everything in this deal, where do we give
the counterparty audit rights, and on what notice?"*

### 3a. Why inline fails — concretely

The agent's read cap is **40,000 chars (~10k tokens)** per document (`tools.py:65`); the operating
budget is **200k input tokens**, compaction at ~170k (`factory.py:33`). Suppose the 1000 documents
average a conservative **8k tokens** each (many are far larger): the corpus is **~8 million tokens** —
**~47×** the entire context window. You cannot inline the corpus; you cannot inline even 3% of it.
Even at a hypothetical 1M-token window, (a) you'd pay to ingest 8M tokens **per question**, (b)
"lost-in-the-middle" degradation makes a needle in 8M tokens unreliable, and (c) the read cap truncates
any single big document anyway. **Inline is categorically off the table at N=1000** — the first doc's
default has no purchase here.

### 3b. Why bare FTS fails — concretely

Run the matter's current path: `search_documents("audit rights")` → `_FTS_SQL`
(`tools.py:70-83`), top-8 chunks by `ts_rank_cd`. Failure modes at scale:

- **Recall:** documents that grant audit rights as *"the Provider shall permit inspection of its
  records upon thirty (30) days' notice"* contain neither "audit" nor "rights" — **invisible to FTS**.
  The one question silently misses the clauses that matter.
- **Top-8 truncation:** with 1000 documents, the relevant clauses can easily exceed 8 hits across
  many files; `_SEARCH_LIMIT = 8` (`tools.py:61`) returns a tiny, lexically-biased slice with no
  recall guarantee and no cross-document aggregation.
- **No routing:** FTS returns *chunks*, not a *ranked set of documents*. The agent gets passages with
  no sense of "these 6 of 1000 documents are the ones to read in full," so it cannot do the
  select-then-read loop the architecture is built around.

### 3c. The layered problem (definition)

The scale scenario decomposes into four layers; conflating them is what made the first doc's analysis
slip. The recommended stack maps one component to each:

| Layer | Question | Failure at N=1000 if absent | Component (recommended) |
|---|---|---|---|
| **L1 — Corpus routing** | *Which of the 1000 documents are even relevant?* | Agent reads/searches blind across everything | **Documents MAP** (descriptions as router signal, §7) |
| **L2 — Within-corpus retrieval** | *Across the relevant set, which passages answer this?* | Lexical recall misses paraphrase; no ranking of docs | **Local dense + FTS hybrid + local rerank** (§5) — the missing piece |
| **L3 — Within-doc navigation** | *Inside the chosen big document, where is the clause?* | Read cap truncates; can't locate section | **read_document + in-doc FTS**, later chunk-section map / PageIndex (§6) |
| **Selection / stickiness** | *Which document are we working on across turns?* | Drift between similar files; re-derivation | **Map + active-doc convention** (§7) |

The first doc solved **L1** and **selection** well, and assumed L2 was solved by FTS. At N=1000 **L2
is the binding constraint**, and it is solved cheaply by the substrate that already exists — once
**vectors exist** and the matter tools **call the hybrid retriever**.

---

## 4. Cost model (the heart)

This is the analysis the first doc lacked. Two axes, kept strictly separate:

- **ONE-TIME** — paid once per document at ingest (index build / embed / enrich / tree-build).
  Re-paid only on re-ingest or model change.
- **PER-QUERY** — paid every time the user asks a question.

…and two currencies:

- **$ (API path)** — external-provider tokens billed through the gateway.
- **compute-time (local path)** — wall-clock on our own CPU/GPU; **$0 marginal**, bounded by hardware.

### 4a. Assumptions (stated, so they can be challenged)

- **Corpus sizing.** Average document = **8k tokens ≈ 32k chars** (conservative; legal corpora skew
  larger). Chunks are **~2,000 chars / ~500 tokens** with 200-char overlap (`chunker.py:51-52`) →
  **~18 chunks/doc** after overlap → **N=10 → ~180 chunks; N=100 → ~1,800; N=1000 → ~18,000 chunks**
  (call it **~30k** at the upper end for big-doc-heavy matters; ranges below bracket this).
- **Embedding $:** OpenAI `text-embedding-3-small` = **$0.02 / 1M tokens** standard, **$0.01 / 1M**
  Batch API ([OpenAI pricing](https://www.helicone.ai/llm-cost/provider/openai/model/text-embedding-3-small),
  [costgoat](https://costgoat.com/pricing/openai-embeddings)). Input-only; embed the **full corpus
  once** = ~8M tokens at N=1000.
- **Local embedding compute:** **~50 embeddings/sec per CPU core** (FastEmbed ONNX, BGE-small-en-v1.5,
  [Markaicode FastEmbed analysis](https://markaicode.com/pricing/fastembed-pricing-api-cost-production/)).
  One embedding ≈ one chunk. GPU is ~10–50× faster; we already have CUDA torch in-image (verified).
- **Contextual enrichment $:** Anthropic's published figure = **$1.02 / 1M document tokens one-time**
  with prompt caching ([Anthropic, Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)).
  Local enrichment on a Tier-1 model = **$0**, bounded by a small-LLM generation per chunk.
- **PageIndex tree-build:** **~150–260 LLM calls per ~86–100-page document**; **~$0.10–0.50/doc with
  GPT-4o** ([VectifyAI issue #232](https://github.com/VectifyAI/PageIndex/issues/232),
  [buildfastwithai guide](https://www.buildfastwithai.com/blogs/vectorless-rag-pageindex-guide)).
  Default node cap 20k tokens / 10 pages. Smaller docs cost proportionally fewer calls.
- **Per-query retrieval:** local dense+FTS+rerank = **one pgvector scan + one FTS scan + one rerank of
  ~40 candidates**. Rerank: **ms-marco-MiniLM ≈ 1.1s / 1000 candidates** on CPU (we rerank ~40, so
  **tens of ms**); bge-reranker-v2-m3 ≈ 12s/1000
  ([Benchmarking Rerankers, arXiv 2409.07691](https://arxiv.org/pdf/2409.07691)). Query-embedding =
  one local encode (~20ms) or one gateway embedding call ($0.02/M × ~30 tokens ≈ **$0.0000006**,
  negligible either way).

### 4b. ONE-TIME cost (paid once at ingest)

| Strategy | N=10 (~180 chunks / 80k tok) | N=100 (~1.8k chunks / 800k tok) | N=1000 (~18k chunks / 8M tok) | Currency |
|---|---|---|---|---|
| **Inline only** | $0 | $0 | $0 | — (no index; cost moves entirely to per-query, where it explodes — §4c) |
| **FTS-only** (today) | $0 (tsvector auto-generated on write) | $0 | $0 | local, already paid at ingest |
| **Cloud embeddings + pgvector** (wired path, OpenAI) | ~**$0.0016** (Batch ~$0.0008) | ~**$0.016** (Batch ~$0.008) | ~**$0.16** (Batch **~$0.08**) | **$**, recurring egress |
| **Local embeddings + pgvector** (recommended) | ~**4 sec** / 1 core | ~**36 sec** / 1 core | ~**6–10 min** / 1 core (seconds on GPU / worker pool) | **compute**, $0 |
| **+ Contextual enrichment (cloud)** | +~**$0.08** | +~**$0.82** | +**~$8** (≈ $1.02/M × 8M) | **$**, one-time |
| **+ Contextual enrichment (local small LLM)** | +minutes | +tens of min | +**hours on 1 core / ~tens of min on GPU** | **compute**, $0 |
| **+ PageIndex trees (cloud GPT-4o)** | ~**$1–5** (≈ $0.10–0.50 × 10) | ~**$10–50** | ~**$100–500** | **$**, one-time, **LLM-bound** |
| **+ PageIndex trees (local via LiteLLM)** | ~**150–260 calls × 10 docs** | ~×100 | **~150k–260k local LLM calls** | **compute**, $0 but **huge call count / latency** |

**Reading the table:** the cloud-embedding bill is *trivially small in absolute dollars*
(~$0.08–0.16 to vectorise the whole 1000-doc matter) — so the case for local embeddings is **not** "the
cloud bill is unaffordable." It is: **(1) it is a recurring per-token dependency and external egress
for data that never needs to leave**, re-billed on every re-ingest / model change / new matter;
**(2) it requires an OpenAI key the deployment may not have** (the gateway endpoint is otherwise inert);
**(3) the local alternative is $0 and a few minutes of compute we already have hardware for.** The
*expensive* one-time strategies are **enrichment** (~$8 cloud at N=1000) and especially **PageIndex
trees** (~$100–500 cloud; ~150k–260k LLM calls local) — which is the quantified reason PageIndex is not
the corpus-query answer.

### 4c. PER-QUERY cost (paid every question)

| Strategy | $ per query (N=1000) | latency per query | Notes |
|---|---|---|---|
| **Inline only** | **N/A** — 8M tokens ≫ context | — | impossible at scale (§3a) |
| **FTS-only** | **$0** | ~ms (one indexed scan) | cheap but **recall-poor** (§3b) — wrong answers, not expensive ones |
| **Local dense + FTS + local rerank** (recommended) | **~$0** (optional ~$0.0000006 if query-embed via gateway) | **~tens of ms** (2 scans + rerank ~40 cands) | the recommended steady state |
| **Cloud-embedding query side** | ~**$0.0000006** (one ~30-token embed) | +network RTT | only the *query* is embedded per call; corpus already vectorised |
| **PageIndex navigation** | **$0.002–0.02+** (multiple sequential LLM calls to walk the tree, **per document**) | **seconds–tens of seconds** | recurring LLM cost **every query**, multiplied if many docs have trees |

**The decisive contrast:** a local dense+FTS+rerank stack has **near-zero per-query dollars and
tens-of-ms latency forever**; PageIndex pays an **LLM bill on every single query** because navigation
*is* inference. At 1000 documents asked many questions a day, that recurring per-query LLM cost dwarfs
the one-time embedding bill of the recommended stack. **Cost-at-scale = push spend into a cheap,
local, one-time index; keep per-query near zero.** Embeddings do exactly that; tree-navigation does the
opposite.

### 4d. Honest uncertainty

- Chunk counts scale with the real size mix; a big-document-heavy matter is **~30k chunks**, lifting
  local embed time to **~10 min/core** and cloud embed to **~$0.16–0.30** — still small. Ranges above
  bracket this.
- PageIndex per-doc cost varies widely with structure and model; the $0.10–0.50/doc figure is GPT-4o
  on ~100-page docs — a budget/local model is cheaper per call but needs **more** calls if weaker, and
  the **call count** (150–260/doc) is the load-bearing scale problem regardless of model.
- The **~50 emb/sec/core** number is FastEmbed ONNX on a cloud vCPU; our Crostini/btrfs dev box may
  differ, and GPU changes the picture by 1–2 orders of magnitude. Treat compute-time figures as
  order-of-magnitude, not SLA.

---

## 5. The local stack

The concrete recommendation for **L2 (within-corpus retrieval)** — wired to the substrate that already
exists.

### 5a. Embedding model (CPU-friendly, permissive, dimension-aware)

**The 1536-dim question is the first decision.** Our column is `vector(1536)`
(`document.py:207-211`, `embed.py:56-59`), sized for OpenAI `text-embedding-3-small`. Strong open CPU
models output **768** (nomic-embed-text v1.5, Apache-2.0, 274MB, MTEB ~62.3) or **1024**
(mxbai-embed-large, Apache-2.0, 670MB, MTEB ~64.7; Qwen3-Embedding-0.6B, ~1024, MTEB ~64.3) — **none
natively 1536** ([morphllm Ollama embeddings](https://www.morphllm.com/ollama-embedding-models),
[modal MTEB](https://modal.com/blog/mteb-leaderboard-article)). Three ways to reconcile:

1. **ALTER the column to the local model's native dim** (e.g. 768). Cleanest; one migration; the
   `vector(N)` type is declared in raw DDL already, and the embed module's docstring **explicitly
   anticipates this** ("If a future ADR repoints the alias to a different-dim model, a migration alters
   the column," `embed.py:57-59`). Cost: the existing KB vectors (if any) must be re-embedded with the
   new model — fine, since the matter path has **no vectors yet** anyway.
2. **Matryoshka model truncated/padded to 1536** — nomic supports Matryoshka *down* from 768, not up;
   you cannot honestly pad 768→1536 (zeros distort cosine). So this only works with a model whose
   native dim **≥1536** (rare in the CPU class). Not recommended.
3. **Keep 1536 by choosing a 1536-native open model** (e.g. some E5-large / GTE-large variants reach
   1024; true 1536 open CPU models are scarce). Constrains model choice for no real benefit.

**Recommendation: option 1 — pick the best CPU model and ALTER the column to its dimension.** Concrete
first pick: **BGE-small-en-v1.5** (MIT, 45M params, 384-dim, the **fastest** — ~50 emb/sec/core via
FastEmbed ONNX) for the initial backfill **if** latency dominates; or **nomic-embed-text v1.5**
(Apache-2.0, 768-dim, MTEB ~62.3) / **bge-base-en-v1.5** (MIT, 768-dim) for a quality/size balance.
768-dim is the sweet spot: meaningfully better than 384 on legal paraphrase, half the storage of 1536,
CPU-tractable. (English-first matches the chunker's `'english'` tsquery and the corpus assumption;
revisit for multilingual matters.)

### 5b. Chunking strategy

**Keep the existing character-precise sliding-window chunker** (`chunker.py`) — it upholds the
load-bearing citation invariant `canonical_text[start:end] == chunk.content` (`document.py:135-141`),
which dense retrieval must not break. Two scale-aware refinements, both additive:

- **Tune chunk size to the embedder.** 2,000 chars / ~500 tokens (`chunker.py:51`) sits comfortably
  under every candidate model's context (BGE 512 tokens, nomic 8k). Leave as-is for v1; consider
  ~256-token chunks if rerank precision needs it later.
- **Do NOT switch to a semantic/LLM chunker.** That reintroduces per-document LLM cost (the thing we're
  avoiding) and threatens the offset invariant. The simple chunker is correct and free.

### 5c. Optional contextual enrichment (small LOCAL LLM) — design for it, defer it

Before embedding a chunk, prepend a one-line, LLM-generated context sentence ("This chunk is from the
indemnification section of the Cirrus MSA; it caps the Provider's aggregate liability") — Anthropic's
**Contextual Retrieval**, which cuts retrieval-failure rates materially
([Anthropic](https://www.anthropic.com/news/contextual-retrieval)). **Two reasons it's compelling
here and one reason to defer:**

- It **doubles as the documents-map (L1) description generator** — one local pass over a document
  yields both the per-chunk context (better L2 embeddings) and the per-document summary (L1 routing).
  One cost, two layers.
- Done on a **Tier-1 local model** it is **$0** (vs ~$8 cloud at N=1000, §4) — fully consistent with
  the cost thesis.
- **Defer** because dense+FTS+rerank alone already closes most of the FTS recall gap, and enrichment
  multiplies one-time compute (hours on one CPU core at N=1000 — §4b). Land it after measuring residual
  recall failures, and run it on the worker pool / GPU.

### 5d. Hybrid + local rerank

- **Reuse the shipped fusion.** `hybrid_search()` already runs pgvector cosine + FTS, min-max
  normalises each side, and combines `score = (1-α)·vector + α·fts` with 4× candidate overshoot
  (`retrieval.py:71-180`, defaults `top_k=10`, `α=0.5` — `schemas/knowledge.py:30,70`). This is exactly
  the L2 retriever the scale scenario needs; it just isn't called on the matter path.
- **Add a local cross-encoder rerank** over the fused top-~40 → final top-k. ms-marco-MiniLM-L-12-v2
  (Apache-2.0) reranks ~40 candidates in **tens of ms** on CPU; bge-reranker-base/-v2-m3 (heavier,
  multilingual) if quality demands ([arXiv 2409.07691](https://arxiv.org/pdf/2409.07691)). Rerank is
  where dense+FTS recall is converted into precision — high value, low cost, local.

### 5e. Wiring to the existing substrate (what actually changes)

The substrate is built; the matter path bypasses it. Concretely:

- **Vectors must exist on matter docs.** Today the embed worker fires on ingest
  (`document_pipeline.py:85-89`) calling `embed_chunks_for_file` (`embed.py:266`), which hits the
  gateway `embedding` alias → **OpenAI**. **Swap the source to local** (§5f) and the **same worker
  path backfills locally**. The lazy embed-on-read path (`ensure_embeddings_for_chunk_ids`,
  `embed.py:444`) carries over unchanged.
- **The matter search tool must call the hybrid retriever.** `_search` (`tools.py:161`) currently runs
  only `_FTS_SQL` (`tools.py:70-83`). Point it at a matter-scoped variant of `hybrid_search` (the
  KB-scoped `kbf.kb_id` join → the matter membership join already in `_FTS_SQL`,
  `tools.py:76-79`). The guard chokepoint (`guard.py`), the 404-conflation scope, and the citation
  invariant all carry over.
- **R4 stays honest.** The guard's R4 is a no-op for "local Postgres reads, zero marginal inference
  cost" (`guard.py:19-22,128-129`). A **local** dense search keeps that true. A cloud query-embedding
  would add a (negligible) per-call inference cost — another reason the local query encode is tidy.

### 5f. The gateway rule — verified verdict

**Question:** does running embedding models on our own infra violate "every LLM call routes through the
gateway; the gateway is the sole key-holder and only egress" (ADR-F010)?

**Verdict: NO — and there are two compliant doors; pick deliberately.**

- **Door A — in-process local encoding (recommended for embeddings).** Load the embedding model in the
  api/ingest worker and encode chunks in-process. This is **local compute, not egress**: no provider,
  no API key, no network call leaves the box. ADR-F010's mandate governs **external-provider**
  inference (the key-holding, the egress, the cost cap on third-party spend); a model file on our disk
  is not a provider and holds no key. The cost cap (R4) is *about* third-party spend — local encode has
  none. This door is the simplest and keeps embeddings off the gateway's request path entirely.
  **Caveat to flag for the maintainer:** it does mean **two inference loci** in the system (the gateway
  for chat/agents, in-process encode for embeddings). That is a real "transparency / single-choke-point"
  judgement call (CLAUDE.md values one readable egress), even though it breaks no security rule —
  embeddings are not generative and carry no provider key.

- **Door B — local model *behind the gateway* (recommended if single-choke-point matters more).** The
  gateway **already defines Tier-1 local providers** — `ollama-local` (type `ollama`, "Fully local;
  no data leaves the deployment", tier 1) and `vllm-local`, with `local`/`local-fast`/`local-thinking`
  aliases (`gateway.yaml.example`). The **only** gap for embeddings is that the Ollama adapter's
  `embeddings()` raises `ProviderUnsupportedError` (`gateway/app/providers/ollama.py:256-282`) — but it
  **documents the exact ~30-line fix** ("Ollama has an `/api/embed` endpoint; implement it here, add a
  Tier-1 `embedding-local` alias, ALTER the column"). Then `embed.py`'s `DEFAULT_EMBEDDING_MODEL =
  "embedding"` alias repoints to the local provider and the **entire existing embed/worker/retrieval
  path works unchanged**, every call still flowing through the gateway choke point and routing-log.
  Slightly more plumbing; preserves the "one egress, one audit" invariant exactly.

**Recommendation:** **Door A for the bulk backfill** (fastest, simplest, in the worker where the data
already is) **with Door B as the principled alternative** if the maintainer wants the gateway to remain
the single inference choke point on record. Either is clean; neither leaks a key or egresses data.

### 5g. SBOM / dependency cost — verified, and smaller than feared

Live container introspection (`docker compose exec api`):

- **`torch 2.12.1+cu130` is ALREADY installed** (transitive via `docling`). The single heaviest ML
  dependency is **already in the image and already justified** (ADR 0006). The first doc's implicit
  "torch/onnx is new heavy surface" worry is **substantially overstated** for torch.
- **`numpy 1.26.4`, `scipy 1.17.1` present** (also via docling) — embedding math has its numerics already.
- **`transformers`, `onnxruntime`, `sentence-transformers` are NOT present.** So the genuinely new
  SBOM line items are:
  - **FastEmbed/ONNX path:** add `onnxruntime` (+ `fastembed`, a thin wrapper) + a model file (BGE-small
    ~130MB ONNX). **No new torch cost.** Smallest footprint; recommended.
  - **sentence-transformers path:** add `sentence-transformers` + `transformers` (torch already paid).
    Heavier, more flexible (rerankers, more models).
- **`litellm` is ABSENT** (verified) — confirming the first doc: PageIndex's `litellm` is a *genuinely
  new egress-capable client*, and that surface is **not** introduced by the local-embedding plan.
- **`lxml 6.1.1` present** (OOXML round-trips) — not relevant here but confirms the introspection.

**Honest cost:** one new dependency family (`onnxruntime` + `fastembed`, both permissive — Apache-2.0)
plus a model artifact to vendor/cache. That is a real SBOM entry to justify — but it is **one
permissive runtime, not a torch-scale addition**, because torch is already here. Weigh it against the
recurring OpenAI-egress dependency it removes.

---

## 6. PageIndex, reconsidered at scale

**Does the cost-at-scale + local lens overturn the first doc's "skip now"? No — it *hardens* the skip
for the corpus query, and isolates a genuine *niche/later* use for the rare oversized single document.**

### 6a. The first doc's verified facts carry forward

- **MIT-licensed** — vendorable under Apache-2.0 (CONFIRMED, [LICENSE](https://github.com/VectifyAI/PageIndex/blob/main/LICENSE)).
- **Routes through LiteLLM, no direct provider SDK** — so it *could* be pointed at our gateway or a
  local model (REFUTED that it needs adapter work). But `litellm` is **absent from the api image today**
  (verified) — a new egress-capable client to add and trust.
- It is a **within-one-document** tree-of-contents navigator, not a cross-document retriever.

### 6b. What the cost lens adds

PageIndex's index is **LLM-built**: ~**150–260 calls per ~86–100-page document**
([issue #232](https://github.com/VectifyAI/PageIndex/issues/232)), ~**$0.10–0.50/doc with GPT-4o**.
For the 1000-document corpus query this is uniquely bad on **both** axes:

- **One-time:** ×1000 = **~$100–500 cloud** or **~150k–260k LLM calls locally** (§4b) — orders of
  magnitude above the **~$0.08–0.16 / ~6–10 min** of local embeddings, for an index that **still only
  navigates *within* each document** and does nothing for *cross-document* routing (the actual question).
- **Per-query:** navigation **is** inference — **multiple sequential LLM calls per query, per
  document** (§4c), **seconds–tens of seconds** and recurring dollars **forever**, versus the
  near-zero, tens-of-ms local hybrid. Cost-at-scale wants the opposite trade.

**Running it on a local model via LiteLLM** collapses the *dollar* cost to $0 but **not** the
**~150k–260k local LLM-call latency** to build trees, nor the per-query navigation latency, nor the new
`litellm` dependency. Local compute makes embeddings free; it does **not** make a 150k-call indexing job
or per-query LLM navigation cheap *in time*.

### 6c. Where per-doc reasoning-trees genuinely beat embeddings+rerank

Be fair to PageIndex — there is a real niche, just not this scenario:

- **A single, very large, highly-structured document** (a 300-page credit agreement, a master
  regulatory filing) where the question is *"walk me to the exact sub-section,"* explainability/audit
  of the **navigation path** is itself valuable, and chunk-embedding retrieval fragments
  cross-reference structure. There, one tree over **one** document (~150–260 calls, **once**) can beat
  dense chunks — this is L3, and only for the rare oversized doc that exceeds the read cap *and* where
  FTS-inside-the-doc fails.

### 6d. Verdict: **niche / later** (sharper than "skip now")

- **Now / corpus query:** **no.** Local dense+FTS+rerank dominates on cost and latency and actually
  solves L2; PageIndex solves neither L1 nor L2.
- **Later / oversized single doc (L3):** **maybe, gated.** Trigger: a *measured* matter where a single
  document exceeds the 40k-char read cap **and** in-document FTS demonstrably fails to locate the right
  section. Even then, build the **free chunk-derived section map first** (our chunks already carry
  `page_start`/`page_end` and headings-capable structure — a "section map from chunk headings/pages"
  gives PageIndex-style navigation with **zero** new dependency and **zero** LLM calls). Reach for
  PageIndex-via-gateway/local only if the free section map proves insufficient, and pay the `litellm`
  SBOM cost deliberately at that point.
- **Never:** as a *corpus-wide* index (×1000 trees) — the cost model rules it out unconditionally.

---

## 7. Layered architecture & the documents map

The unified design composes the first doc's selection layer **on top of** the scale retriever **on top
of** within-doc navigation — each layer cheap relative to the one below, each degrading gracefully.

```
USER QUESTION over ~1000 documents
        │
   ┌────▼─────────────────────────────────────────────────────────┐
   │ L1  DOCUMENTS MAP  (router — first doc's contribution)         │
   │     {doc → one-line description · role · side · status}        │
   │     • few hundred tokens for the whole matter                  │
   │     • descriptions double as router signal (§7a)               │
   │     • home: typed fact ledger, fact_type="document"            │
   │       (ADR-F042/F043/F044 spine: supersede, correct, undo)     │
   └────┬─────────────────────────────────────────────────────────┘
        │ narrows 1000 → the relevant handful (or "search all")
   ┌────▼─────────────────────────────────────────────────────────┐
   │ L2  WITHIN-CORPUS HYBRID RETRIEVAL  (this doc's contribution)  │
   │     local dense (pgvector) + FTS, min-max fused, + local       │
   │     cross-encoder rerank  → ranked passages + ranked DOCS      │
   │     • reuses api/app/knowledge/retrieval.py (ADR 0008)         │
   │     • vectors from LOCAL embeddings ($0, §5)                   │
   │     • near-zero $ / tens-of-ms per query                       │
   └────┬─────────────────────────────────────────────────────────┘
        │ "these 6 of 1000 are the ones" → select & read
   ┌────▼─────────────────────────────────────────────────────────┐
   │ L3  WITHIN-DOC NAVIGATION                                      │
   │     read_document (≤40k cap) / in-doc FTS;  later, only if     │
   │     measured: chunk-derived section map → PageIndex (§6)       │
   └────┬─────────────────────────────────────────────────────────┘
        │
   SELECTION / STICKINESS  (active-doc convention + map; §7c)
```

### 7a. How the map's descriptions double as cheap router signals

The first doc framed the map as *selection metadata* (a human/agent reads descriptions to pick a
document). At scale the **same descriptions are a retrieval signal**: embed the map's one-line
descriptions (or fold them into each chunk's contextual prefix, §5c) and an L1 pass becomes a cheap
dense match over **1000 short descriptions** instead of 18k chunks — a fast first cut that narrows the
corpus before the heavier L2 pass. The map is thus **both** the human-facing selection layer **and**
the machine-facing router — one artifact, two consumers. This is the synthesis the two docs together
produce: the first doc's *what-is-this-document* layer is exactly the routing index scale needs.

### 7b. How enrichment populates both layers

A single **local** contextual-enrichment pass (§5c) over a document yields, in one shot: (1) per-chunk
context sentences → better **L2** embeddings, and (2) a per-document summary → the **L1** map
description. So enrichment is not a third cost — it is the **shared generator** of the map and the
embeddings. This is why §5/§8 keep enrichment as the *same* deferred slice that upgrades both layers,
run locally for $0.

### 7c. Keeping auto-write-then-correct and roster separation

Unchanged from the first doc, and load-bearing:

- **The map stays auto-write-then-correct (ADR-F042).** The agent maintains document descriptions/roles
  as it learns; the lawyer corrects via the authenticated path; human-pinned corrections win.
  Embeddings and the map description are **agent/derived content** that needs supersede/correct/undo —
  which is exactly why descriptions live in the **fact ledger**, not on the model-free `File`/`Document`
  ingest rows (first doc §4, Option A vs C). Local embeddings are a derived index column, recomputable,
  not authored — they sit on `document_chunks.embedding` as today, no governance needed.
- **Map ≠ roster (ADR-F048).** The roster answers *who* (people → side); the map answers *what*
  (documents → role/status). A document's `side` is **derived from / consistent with** its author's
  roster side, but they stay distinct rows with distinct lifecycles. The L2 retriever is orthogonal to
  both — it ranks passages; the map/roster label and route them.

---

## 8. Recommended decomposition

Vertical slices, dependency-ordered, ≤2–3 days each, one PR each. Separated into **cheap-wins**,
**scale-foundation**, **advanced**. **Next fork ADR number is F049** (highest accepted is F048); next
migration is **0078**.

### Cheap wins (no new dependency)

- **Slice A — Wire the matter tools to the EXISTING hybrid retriever (no new dep, no ADR).**
  Point `_search` (`tools.py:161`) at a matter-scoped variant of `hybrid_search`
  (`retrieval.py:71`) — swap the KB membership join for the matter membership join already in
  `_FTS_SQL` (`tools.py:76-79`), keep the guard/scope/citation invariants. **Effect:** the moment any
  vectors exist, the matter path gets dense+FTS fusion instead of FTS-only — the single highest-leverage
  scale fix, reusing shipped code. *Until vectors exist it degrades to FTS-only automatically
  (`hybrid_search` skips the vector side when `embedding IS NULL` / no query vector — `retrieval.py:106`),
  so it is safe to ship before the backfill.* Trigger: ship now; it's pure upside.
  **Diff small; folds the standard security + simplification pass.**

- **Slice B — Vector-coverage signal in the inventory (tiny, no ADR).** Surface per-matter embedding
  coverage ("N of M documents vector-indexed") so the agent and cockpit know whether dense retrieval is
  live — reuses `_file_has_null_embedding_chunks` (`api/app/api/knowledge_bases.py:215`). Makes the
  scale story observable. Trigger: alongside A.

### Scale-foundation — local embeddings (the cost play)

- **Slice C — LOCAL embedding source + column dimension (ADR-F049, migration 0078).** Implement local
  embeddings via **Door A** (in-process FastEmbed/ONNX in the embed path — add `fastembed` +
  `onnxruntime`, vendor the BGE-small/nomic model) **or Door B** (implement the Ollama `embeddings()`
  stub, add a Tier-1 `embedding-local` alias). Repoint `DEFAULT_EMBEDDING_MODEL` / the `embedding`
  alias to local. **ALTER `document_chunks.embedding` to the chosen native dim** (768 recommended;
  migration 0078 — the path `embed.py:57-59` anticipates). The existing embed worker
  (`document_pipeline.py:85-89`) then backfills locally on ingest at **$0**.
  **Needs ADR-F049** ("local embeddings for matter retrieval"): it makes the architectural calls — local
  compute as a sanctioned non-egress inference locus (Door A) *or* the gateway-local-embeddings path
  (Door B); the 1536→768 dimension change; the new permissive SBOM line. Draft in this PR.
  **Trigger:** as soon as Slice A is in and any matter approaches the scale where FTS recall bites
  (the maintainer's 1000-doc scenario is already past it). This is the slice that makes the scale
  scenario actually work.

- **Slice D — Local cross-encoder rerank (depends on C; ADR addendum if a model family is added).**
  Add ms-marco-MiniLM (or bge-reranker) rerank over the fused top-~40 → final top-k, in-process. Turns
  dense+FTS recall into precision at tens-of-ms CPU cost. **Trigger:** after C, once dense+FTS is live
  and precision (not recall) is the residual complaint.

### Advanced — enrichment, then (only if measured) trees

- **Slice E — Local contextual enrichment feeding BOTH map and embeddings (depends on C; ADR addendum).**
  A local small-LLM pass writes per-chunk context (better L2) **and** the per-document map description
  (L1) in one shot (§5c, §7b), run on the worker pool / GPU, $0. **Trigger:** after measuring residual
  retrieval failures that survive dense+FTS+rerank — not before (it multiplies one-time compute).

- **Slice F — Documents MAP as typed fact (`fact_type="document"`) (the first doc's Slice 4; ADR-F049
  covers it or a sibling).** Promote the map to the fact ledger with the auto-write-then-correct spine
  (first doc §4 Option A). Independent of the retrieval slices but **synergistic** — its descriptions
  become the L1 router signal (§7a) and the enrichment target (Slice E). Can land in parallel with
  C/D. **Trigger:** when matters routinely exceed ~5 documents (the first doc's threshold) — already
  true at scale.

- **Backlog (no slice until triggered) — oversized-document navigation / PageIndex (L3).** Only if a
  *measured* single document exceeds the 40k-char read cap **and** in-document FTS fails: build the
  **free chunk-derived section map** first; evaluate PageIndex-via-gateway/local only if that's
  insufficient, paying the `litellm` SBOM cost deliberately. **Would need its own ADR** if a dependency
  is added (§6).

**Dependency order:** A → (B parallel) → **C** [ADR-F049] → D → E; **F** parallel to C/D; PageIndex
backlog gated on measurement. A and B are safe before C because hybrid degrades to FTS without vectors.

---

## 9. Open questions for the maintainer

1. **Local-embeddings door — in-process (Door A) or gateway-local (Door B)?** A is fastest and simplest
   (encode where the data is, no gateway round-trip) but creates **two inference loci** (gateway for
   chat, in-process for embeddings) — a transparency/single-choke-point judgement, though it leaks no
   key and egresses nothing. B preserves "one egress, one audit log" exactly at the cost of implementing
   the Ollama embeddings stub + running a local model server. **Which invariant matters more to you —
   minimal moving parts, or a single inference choke point?**

2. **Accept the new SBOM line (`onnxruntime` + `fastembed`, Apache-2.0, + a vendored model file)?**
   Torch is already in the image (verified), so this is **one permissive runtime, not a torch-scale
   add** — and it removes the recurring OpenAI-embedding egress dependency. Acceptable, or do you want
   to stay on cloud embeddings (small recurring $, needs an OpenAI key) for now?

3. **1536 → 768 column change.** The clean local path ALTERs `document_chunks.embedding` to the local
   model's native dim (768 recommended). The matter path has **no vectors yet**, so there's nothing to
   lose there; any existing **KB** vectors would need re-embedding. **OK to ALTER to 768 (better legal
   recall than 384, half the storage of 1536), or hold 1536 to avoid re-embedding KB data / keep a
   future OpenAI option open?**

4. **Local embedding model choice.** BGE-small (MIT, 384-dim, fastest — ~50/sec/core) vs
   nomic-embed-text v1.5 / bge-base (Apache-2.0/MIT, 768-dim, better recall, ~half the speed). Speed vs
   recall at the dimension you pick in Q3. **Default recommendation: 768-dim bge-base/nomic** — confirm?

5. **Enrichment — now or later?** It's the high-value upgrade and doubles as the map-description
   generator, but it multiplies one-time compute (hours/core at N=1000) and is only worth it once
   dense+FTS+rerank's residual recall failures are *measured*. **Defer behind Slice C/D (recommended),
   or fund the local enrichment pass up front because the 1000-doc matter is the explicit target?**

6. **Wire-then-backfill ordering.** Slice A (wire the hybrid retriever) is safe before vectors exist
   (degrades to FTS). **Ship A immediately as pure upside, or hold it until Slice C's local backfill so
   the first behaviour change is the full dense+FTS experience?**

7. **PageIndex trigger.** Do you accept "niche/later, gated on a *measured* oversized single document
   where in-doc FTS fails, free chunk-section-map first" — or do you want a spike on one real large
   legal document (e.g. a 300-page credit agreement) now to de-risk the eventual L3 decision? (The
   corpus-query verdict — never index ×1000 trees — is firm regardless.)

---

### Honest limits of this dossier

- **Compute-time figures are order-of-magnitude.** ~50 emb/sec/core is FastEmbed ONNX on a cloud vCPU;
  our Crostini/btrfs box and a GPU change it by 1–2 orders. Treat embed/enrich timings as planning
  estimates, not SLAs; benchmark on our hardware in Slice C.
- **No measured recall on our own corpus.** The FTS-fails-at-scale argument is from the lexical-vs-dense
  structure of legal paraphrase + the absent vector branch, not from a labelled retrieval eval on this
  fork's documents. Slice C should ship with a small recall eval (a handful of corpus questions with
  known-relevant docs) to convert the argument into a number.
- **PageIndex's legal-document accuracy is still unverified for our workload** (98.7% is FinanceBench /
  SEC filings) — carried forward unclosed from the first doc; the cost verdict does not depend on it.
- **The chunk-count math (~18 chunks/doc, ~18–30k at N=1000) is an estimate** from the chunker config
  and an 8k-token average; a big-doc-heavy matter shifts every one-time figure upward (ranges bracket
  it). The dollar conclusions are robust to this; the compute-time conclusions scale linearly.
- **Two inference loci (Door A) is a genuine design tension with CLAUDE.md's "one readable egress"
  value**, surfaced honestly in §5f / Q1 rather than waved away — it breaks no security rule but is a
  real call for the maintainer.
