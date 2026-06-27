# Research — OSS deepagents reference + a runnable evaluation design for the retrieval/memory architecture

**For:** the maintainer's two-part ask on top of `native-fit-reconciliation-store-vs-custom.md` (the
verified native-vs-custom verdict) and the prior retrieval/memory docs (`document-discovery-and-map.md`,
`document-retrieval-at-scale-and-cost.md`, `conversations-as-retrievable-knowledge-and-upstream-awareness.md`,
`retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md`, `deepagents-ecosystem.md`, `f0-s9-eval-reuse.md`).

**The two deliverables:**
- **(A)** An OSS-deepagents reference read + a refined, precise **native-vs-custom boundary** that corrects
  the over-claim "native solves retrieval."
- **(B) — the centerpiece —** a **concrete, runnable evaluation design** for the retrieval/memory
  architecture, with two tracks: **Track A** (Claude-judged DeepSeek on the agentic vision + long
  negotiation scenarios) and **Track B** (CUAD-gold, objective recall/precision at corpus scale).

**Method:** OSS findings from web research (repos/URLs cited inline, June 2026); native-API claims carried
from `native-fit-reconciliation-store-vs-custom.md` (introspected at our pins inside `lq-ai-api-1`,
2026-06-27); our harness/retriever claims verified at `file:line` in this repo this session; CUAD facts from
the Atticus/HuggingFace primary sources. **Date:** 2026-06-27.

**Posture reminders (unchanged):** every external LLM call routes through the in-house gateway (sole
key-holder + only egress, ADR-F010) — **local in-process compute is permitted**; the qualified provider is
**DeepSeek** (`deepseek` alias has quota; MiniMax out of quota); `guarded_tool_call` R4/R5/R6 brakes every
agent tool call; matter memory is auto-write-then-correct (ADR-F042); audit carries counts/types/IDs, never
raw values; upstream is FROZEN (ADR-F001).

---

## 1. Executive summary

- **OSS deepagents read: there is NO reference project that does cite-grade legal retrieval at scale — and
  that is itself the finding.** Every deepagents example (`langchain-ai/deepagents/examples/*`) is
  coding/research/content-gen; **none** demonstrates RAG, chunking, embeddings, rerank, or citation offsets
  ([examples README](https://github.com/langchain-ai/deepagents/blob/main/examples/README.md)). The richest
  retrieval reference is the third-party **Milvus + deepagents** tutorial — and it confirms our boundary:
  it wires the **native `StoreBackend`** to a vector store and **delegates chunking/embedding to the store
  abstraction**, showing **no hybrid fusion, no rerank, no byte-offsets**
  ([milvus.io](https://milvus.io/blog/how-to-build-productionready-ai-agents-with-deep-agents-and-milvus.md)).

- **Refined boundary (the maintainer's correction, made precise): deepagents/langgraph give the SUBSTRATE,
  not retrieval-at-scale.** Native = the `BaseStore` (namespaces + `asearch`), the `IndexConfig.embed`
  **hook**, `CompositeBackend`/`StoreBackend` routing, `MemoryMiddleware`, `SummarizationMiddleware`
  compaction/offload, and `task` fan-out. **NOT native** = chunking, embedding-at-scale, **hybrid FTS+dense
  fusion**, **reranking**, and **citation byte-offsets** — these remain OUR custom layer feeding the native
  store / our pgvector. §2 has the crisp table and the corrected prior-doc language.

- **Therefore the eval must test the WHOLE system — native substrate AND our custom layer — not assume
  native solves retrieval at scale.** A green "the Store returned something semantically near" is not the
  bar; the bar is *recall of the right span at corpus scale with a verifiable cite*, which only the custom
  layer can deliver and only an objective gold set can score.

- **Eval headline — two tracks, each proving a different thing.** **Track A** (Claude-judged DeepSeek):
  proves the **agentic vision** — does the agent *choose* the right retrieval move (read vs retrieve vs
  fan-out), ground its answer, survive long multi-doc negotiation, recall across threads, and respect the
  gates. Claude designs tasks + long scenarios and **judges** the outputs (small enough to read).
  **Track B** (CUAD-gold, objective): proves **retrieval at scale** — load *N* human-annotated CUAD
  contracts, fire clause-finding questions, and score retrieved/extracted spans against the gold annotations
  with **recall@k / precision / AUPR** — the 1000-doc case the orchestrator *cannot* eyeball.

- **Both tracks reuse what we already have.** The scenario rig (`api/tests/agents/scenarios/harness.py`)
  drives the **production** composition point against the live gateway and reads back settled
  `agent_run_steps` (`harness.py:253-365`). The **Claude-as-judge** pattern already ships
  (`commercial_redline_lib.py:223-277` — a gateway-routed LLM critic returning machine-readable verdict
  lines). The **objective-scoring** pattern already ships (`ropa_eval`/`assessment_eval` score structured
  agent output against expected sets). Track A ≈ generalise the redline judge; Track B ≈ a new objective
  scorer over CUAD gold spans. **No new framework** (f0-s9 already adjudicated: build on pytest, the loop
  must run in *our* stack to exercise the gateway/brakes/audit — `f0-s9-eval-reuse.md` §2).

- **CUAD is the right gold standard and it is usable.** 510 commercial contracts from SEC EDGAR, **41
  clause categories**, **>13,000 expert labels**, SQuAD-2.0 JSON (`context` + `question` + `answers{text,
  answer_start}`), **CC-BY-4.0** (attribution only — clean for our SBOM/notices), loadable via
  `datasets.load_dataset("theatticusproject/cuad-qa")` or the raw `CUADv1.json`
  ([Zenodo](https://zenodo.org/records/4595826),
  [HF cuad-qa](https://huggingface.co/datasets/theatticusproject/cuad-qa)). `answer_start` gives us
  **gold byte-offsets** — a direct objective check on *both* retrieval recall *and* the Citation Engine's
  offset contract. (Lavern already bundles CUAD as an eval corpus — `docs/LQVern/HANDOFFlavernevaluation.md:66`
  — corroborating the choice; we use the dataset, never Lavern's AGPL-adjacent runtime.)

- **The eval gates the build — measure before building.** Run Track B against **today's FTS-only matter path
  FIRST** to get a baseline, then gate each substrate-first slice on a measured delta: ship the Store wire
  (N0) only if conversation recall lights up; ship **local embeddings (Slice C)** only if **CUAD recall@k
  beats FTS-only by a pre-registered margin**; ship **rerank (Slice D)** only if it lifts **precision@k**.
  The prior docs' "build only if measured" triggers (recency weighting, within-chat recall) become
  *measured*, not assumed (§7).

- **Honest limits.** Claude can judge agentic quality and *small*-corpus correctness by reading; Claude
  **cannot** eyeball 1000-doc recall — that is exactly the gap CUAD-gold fills. Every Track-A/Track-B cycle
  spends **real DeepSeek tokens** (provider-quota + cost bound the cell sizes), and the embed step at CUAD
  scale is the dominant cost — both quantified and capped in §8/§9.

---

## 2. Refined native-vs-custom boundary (the maintainer's correction)

The prior reconciliation doc (`native-fit-reconciliation-store-vs-custom.md`) landed the right *verdict*
(adopt the native Store; keep two custom layers) but some of its summary language — and more of the earlier
retrieval docs — can be **read** as "the native Store covers retrieval." **It does not.** This section makes
the boundary exact so the eval tests the whole system.

### 2a. What deepagents/langgraph genuinely DO solve (verified at our pins)

- **Storage + namespaces + a search *API*.** `BaseStore.asearch(namespace_prefix, *, query, filter, limit)`
  over `AsyncPostgresStore` (pgvector) — hierarchical namespaces + metadata-filter + a *semantic-search
  entry point* (`native-fit…md` §2a).
- **An embedding *hook*, not an embedder.** `IndexConfig{dims, embed, fields}` where `embed` is a plain
  (async) callable — the place *our* embedder plugs in (`native-fit…md` §2a). The Store ships the socket;
  it does **not** ship the model, the chunking, or the indexing-at-scale.
- **Routing + memory tiers.** `CompositeBackend`/`StoreBackend` map `/memories/{level}/` onto namespaces;
  `MemoryMiddleware` always-injects digests; `SummarizationMiddleware` compacts and **offloads verbatim
  history** to the backend (`native-fit…md` §2c, §2e).
- **Fan-out.** `task` + `subagents=[...]`, model-driven, already adopted with zero scaffolding
  (`native-fit…md` §2d).

### 2b. What they do NOT solve — the gap, explicit

The native `store.search(query=)` is, at bottom, **single-vector ANN over stored items** (`native-fit…md`
§4g). It does not provide, and was never meant to provide:

1. **Chunking.** Splitting a 60-page contract into retrievable, offset-bearing units is ours
   (the ingest pipeline; `DocumentChunk` with `char_offset_start/end`, seeded in `harness.py:145-156`).
2. **Embedding-at-scale.** The Store calls *one* `embed` callable; deciding *what* to embed, *batching*
   thousands of chunks, and the **cost play** (local in-process model vs gateway) is ours (Slice C).
3. **Hybrid FTS+dense fusion.** Our retriever runs pgvector cosine **and** Postgres FTS, min-max-normalises
   each side, and blends `score = (1-α)·vector + α·fts` with a 4× candidate overshoot
   (`api/app/knowledge/retrieval.py:71-180`). The Store has **no FTS leg and no fusion**.
4. **Reranking.** A cross-encoder pass over the fused candidate set (planned Slice D) — the Store has none.
5. **Citation byte-offsets.** The legal must-have: a quote verifiable to an exact `[start,end)` span in the
   normalized source (the Citation Engine contract; the fidelity invariant asserted in
   `scenarios.py:117-119`). The Store returns an item + namespace + metadata — **no offset-grade citation**.

**Corrected prior-doc language.** Any phrasing in the earlier docs that the native Store "covers documents
retrieval" or "subsumes the retriever" applies **only to conversations** (provenance-cited, no offsets
needed) — **never to documents**, where hybrid/rerank/offset exceed the Store. `native-fit…md` §4b/§6.1-6.2
already draws this line for conversations; this doc generalises it: **right substrate per source type, and
the documents substrate is our custom layer behind (or beside) the native store.** The eval (§5-§6) tests
*that whole stack*, not the Store in isolation.

### 2c. Capability → native or custom (crisp table)

| Capability | Native (deepagents/langgraph) | Custom (ours) | Eval that tests it |
|---|---|---|---|
| Cross-thread memory **storage + namespaces** | ✅ `AsyncPostgresStore` + `CompositeBackend`/`StoreBackend` | — | Track A cross-thread recall (§5) |
| Memory **search API** (the call shape) | ✅ `store.asearch(ns, query=, filter=)` | — | Track A conversation recall |
| Embedding **hook** | ✅ `IndexConfig.embed` (a socket) | — | (enables both) |
| The **embedder** + embedding-at-scale + batching | ❌ | ✅ Slice C (local/gateway callable) | Track B recall delta vs FTS-only (§6) |
| **Chunking** (offset-bearing units) | ❌ | ✅ ingest pipeline / `DocumentChunk` | Track B span-overlap scoring (§6) |
| **Hybrid FTS+dense fusion** | ❌ (single-vector ANN only) | ✅ `knowledge/retrieval.py:71-180` | Track B FTS-only vs hybrid (§6) |
| **Reranking** | ❌ | ✅ planned Slice D (cross-encoder) | Track B +rerank precision lift (§6) |
| **Citation byte-offsets** | ❌ | ✅ Citation Engine / fidelity invariant | Track B `answer_start` overlap + Track A cite-check |
| **Bi-temporal facts + human-pinned corrections** | ❌ (no valid_at/invalid_at/as-of/pin-gate) | ✅ `MatterMemoryEntry` (ADR-F042/43/44) | Track A which-version / as-of scenarios (§5) |
| Compaction + **verbatim offload** of a chat | ✅ `SummarizationMiddleware` | — | Track A within-chat recall (§5) |
| Always-inject tier digests | ✅ `MemoryMiddleware` | — | Track A (regression: prompt-equivalence) |
| Subagent **fan-out** | ✅ `task` + `subagents` | — (declarative dicts only) | Track A fan-out strategy scenario (§5) |
| **Routing intent** (which move to make) | ❌ (model-driven, prose-guided) | ✅ our doctrine/skills/tool descriptions | Track A strategy-choice scenarios (§5) |

**Read:** native owns the *substrate columns*; **custom owns every retrieval-at-scale and cite-grade
column.** The eval must exercise the custom columns under load — which is precisely Track B's job, because
those are the columns the orchestrator can't eyeball.

---

## 3. OSS deepagents ecosystem — what exists, what to reuse, maturity

### 3a. Official examples — coding/research/content, no retrieval-at-scale

The canonical `langchain-ai/deepagents` ships ~15 examples
([examples README](https://github.com/langchain-ai/deepagents/blob/main/examples/README.md)): Deep Agents
Code (terminal coding agent), Open SWE, Deep Research (parallel sub-agents over web search), MCP Docs Agent,
several coding/sandbox agents, Content Builder (memory + subagents), Text-to-SQL, GTM Strategist,
Async-Subagent-Server, the Ralph Loop, "agents-as-folders," and a harness example. **None demonstrates RAG,
chunking, embeddings, a vector store, rerank, or citation offsets** (verified against the README). The
memory examples (Content Builder, Content Writer per-user memory) use the **native `StoreBackend`** for
durable files — they are the canonical *substrate* demonstration, not a retrieval-at-scale demonstration.

**Worth deep-reading anyway — for SUBSTRATE patterns, not retrieval:**
- **`examples/deep_research`** — the reference **fan-out + planning + write-up** loop. Mine its subagent
  decomposition and the planner-tool prose (relevant to our Track-A *strategy-choice* and *fan-out*
  scenarios; reinforces "fan-out is prose-guided, model-driven").
- **`libs/code` (Deep Agents Code)** — the most mature deepagents app; reference for human-in-the-loop
  approval + skills + memory-first protocol (our gate/skills posture analogue).

### 3b. The one real retrieval reference — Milvus + deepagents (third-party)

The **most relevant** OSS retrieval reference is Milvus's production tutorial
([milvus.io](https://milvus.io/blog/how-to-build-productionready-ai-agents-with-deep-agents-and-milvus.md)).
**What it does and why it matters to us:** it wires deepagents to a vector store via the **native
`StoreBackend`** —
`CompositeBackend(default=StateBackend(), routes={"/memories/": StoreBackend(store=MilvusStore(...))})` —
and **delegates chunking + embedding to the store abstraction** ("conversation content and tool results are
converted into embeddings and stored in Milvus"). Crucially it shows **no hybrid fusion, no rerank, no
byte-offset citation** — exactly the gap §2 names. **This is the OSS confirmation of the maintainer's
correction**: even a "production-ready" deepagents-RAG tutorial stops at native-store semantic memory and
does **not** reach cite-grade legal retrieval. The pattern to *reuse* from it: the **clean `StoreBackend`
mount for durable agent memory** (our N0). The pattern *not* to copy: treating the store as the whole
retrieval story.

### 3c. langgraph-native RAG references (substrate, not legal-grade)

LangChain's own **agentic-RAG tutorial** ([docs](https://docs.langchain.com/oss/python/langgraph/agentic-rag))
and the **memory-types walkthroughs**
([dev.to part 2](https://dev.to/sreeni5018/five-agent-memory-types-in-langgraph-a-deep-code-walkthrough-part-2-17kb))
show `store.search(namespace, query=, limit=k)` once an embedder is configured, and the
semantic-search-on-task-start "memory-first" protocol. Reuse: the **embed-callable wiring** and the
**memory-first prompt shape** (feeds our `IndexConfig.embed` = shared local embedder). These are
single-vector; they do **not** cover our hybrid/rerank/offset needs.

### 3d. Patterns to reuse for OUR custom chunking/embedding layer behind the native store

The OSS world does **not** hand us a legal hybrid retriever — we already built the better one
(`knowledge/retrieval.py`). What the ecosystem *does* give, to reuse:
- **The `IndexConfig.embed` socket** as the single seam where our **shared local embedder** (Slice C)
  plugs into the native conversation index — one embedder serves Store-conversations *and* documents-pgvector
  (`native-fit…md` §6.6). The Milvus example is the template for *mounting* it.
- **`StoreBackend`-as-durable-memory** (Content Builder / Content Writer / Milvus) — the N0 substrate shape,
  copy-paste-adjacent.
- **The deep-research fan-out decomposition** — prose-guided subagent dicts, for the Track-A fan-out scenario
  design and the C7b roster we already shipped.

### 3e. Maturity read (honest)

- **deepagents core + Store/StoreBackend/CompositeBackend:** mature enough to build on (it's our pinned 0.6.8;
  `native-fit…md` verified the signatures), but **ships breaking changes on minors** (the 0.7 namespace-factory
  removal — `deepagents-ecosystem.md` §1.1). Re-verify at each slice boundary.
- **OSS deepagents *retrieval* examples:** **thin** — single-vector native-store memory only. There is **no
  open project to copy for hybrid+rerank+offset legal retrieval.** Stated plainly: on the retrieval-at-scale
  axis we are ahead of the public examples, and we must validate with our **own** eval — which is the whole
  point of (B).
- **langmem:** already **rejected as a dependency** (stale, pre-1.0, SBOM bloat, no approval seam —
  `deepagents-ecosystem.md` §4 / `native-fit…md` §2f). Mine prompts only.

---

## 4. CUAD as gold standard

### 4a. What CUAD is

The **Contract Understanding Atticus Dataset (CUAD v1)** — **510 commercial legal contracts** drawn from the
public **SEC EDGAR** system, manually labelled under experienced-lawyer supervision to mark **41 categories
of clauses** lawyers look for in M&A/finance review, **>13,000 annotations** total, built over a year by law
students + lawyers + ML researchers ([Zenodo record](https://zenodo.org/records/4595826),
[CUAD paper](https://arxiv.org/abs/2103.06268)). The 41 categories include Governing Law, Effective Date,
Expiration Date, Renewal Term, Notice Period To Terminate Renewal, Cap On Liability, Uncapped Liability,
Indemnification, Non-Compete, Exclusivity, Most Favored Nation, Change Of Control, Assignment, IP Ownership
Assignment, License Grant, Audit Rights, Insurance, and more — i.e. **exactly the clauses our Commercial
agent already redlines** (cap, indemnity, IP, termination — `test_commercial_redline_eval.py:84-86`).

### 4b. Annotation format + license + how to load

- **Format = SQuAD 2.0 JSON.** Each instance: `id` (filename + category), `title`, `context` (full contract
  text), `question` (e.g. *"Highlight the parts … related to 'Governing Law'…"*), and `answers` = `{"text":
  [...gold clause strings...], "answer_start": [...char offsets into `context`...]}`. **Unanswerable**
  categories (the clause is absent) carry **empty** `answers` — the negative-control case, native to the
  dataset ([HF cuad-qa README](https://huggingface.co/datasets/theatticusproject/cuad-qa)).
- **Split.** The HF `cuad-qa` QA build exposes **22,450 train / 4,182 test** (category×contract) examples;
  the raw `CUADv1.json` (in the [Zenodo](https://zenodo.org/records/4595826) bundle, alongside PDFs + plain
  text + per-category XLSX) groups by contract → `paragraphs` → `qas`. **We use the raw per-contract grouping**
  so a "contract" = one matter document and its 41 questions.
- **License = CC-BY-4.0** — attribution only, no copyleft. **Clean for the fork**: cite Atticus in
  `NOTICES.md`; the dataset is *test data*, never shipped in the product image (downloaded into the eval
  fixture dir, gitignored). This is materially cleaner than the AGPL traps we navigate elsewhere.
- **The `answer_start` offsets are the gift.** They are **human gold byte-offsets** — so CUAD scores **both**
  "did we retrieve the right region" (recall) **and** "is our cite offset correct" (the Citation Engine
  contract) against a human ground truth, with no eyeballing.

### 4c. EXACTLY how we use it

1. **Load N contracts into a matter.** For each chosen CUAD contract, write its `context` as a matter
   document through the **same ingest path** the harness already uses (`seed_multi_doc_matter` →
   `File`→`Document`→`DocumentChunk` with computed offsets, `harness.py:80-157`). One CUAD contract = one
   matter document; *N* contracts = one large-corpus matter. **The chunker under test is ours** (so chunking
   quality is *in* the measurement, per §2).
2. **Pose clause-finding questions.** For each `(contract, category)` with a gold answer, ask the agent the
   category question (lightly de-SQuAD-ified to natural counsel phrasing, e.g. *"What is the governing law,
   and quote the exact clause?"*). Drive it through `run_scenario` so it uses the **production retrieval tool
   path** (search→read→answer) and the gateway/brakes — i.e. we test the **agent's** retrieval, not a raw
   index call.
3. **Score retrieved/extracted spans against gold.** Two scoring layers (both objective, no LLM):
   - **Retrieval recall@k** — did the agent's retrieved chunk set (read from `agent_run_steps` /
     the tool's returned chunk ids) **overlap the gold `answer_start` span**? Recall@k over k∈{1,3,5,10}.
   - **Extraction precision/recall** — does the agent's *quoted* span overlap the gold text (Jaccard /
     char-overlap ≥ τ, or SQuAD-style token-F1)? And does the agent's **cited offset** match `answer_start`
     within tolerance (the Citation Engine check)?
   Aggregate across categories → **macro recall@k**, **precision**, and **AUPR** (precision-recall curve over
   the retriever's score threshold, the standard CUAD metric).

### 4d. Worked example (one contract, one category)

CUAD `LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT`, category **Governing Law**, gold =
`{"text": ["...governed by the laws of the State of Illinois..."], "answer_start": [N]}`.

- Seed the full distributor agreement as the matter's document (chunked by our pipeline).
- Ask: *"What law governs this distributor agreement? Quote the exact clause and give its location."*
- The agent runs `search_documents` (FTS-only today; hybrid after Slice A/C) → `read_document` → answers.
- **Retrieval recall@5**: is the chunk containing offset `N` in the top-5 retrieved? (objective)
- **Extraction**: does the agent's quoted clause char-overlap the gold ≥ τ? Does its cited offset land within
  ±W chars of `N`? (objective — `answer_start` is gold)
- **Negative control**: pick a category CUAD marks **absent** for this contract (empty `answers`) → the agent
  should say *"this agreement does not contain a [Non-Compete] clause,"* **not** fabricate one. Scored as a
  hard abstention check (CUAD gives us the absence label for free — the cleanest no-hallucination test).

Run this over *N* contracts × 41 categories and you have a **defensible, human-grounded** recall/precision
surface that no amount of Claude-reading could produce — exactly the 1000-doc case (§8).

---

## 5. The evaluation design — Track A: agentic vision (Claude-judged DeepSeek)

**What Track A proves:** that DeepSeek-as-agent, on our substrate, makes the **right agentic moves** —
chooses read vs retrieve vs fan-out, grounds answers in retrieved text, survives long multi-doc negotiation,
recalls across threads/within a chat, picks the right document version, and respects the gates. **Method:**
**Claude (the orchestrator) authors the tasks + long scenarios and JUDGES the outputs.** This is correctness
small enough to *read* — Claude's strength.

**Reuse (cite):** the rig is `api/tests/agents/scenarios/harness.py` — `run_scenario` drives the **production**
`compose_and_execute_run` against the **live gateway** and reads back settled `agent_run_steps` into a
`Receipt` with `tools_called`, `task_calls`, `delegated`, `ancestry`, latency, status (`harness.py:253-365`);
`seed_multi_doc_matter` plants a many-document matter (`harness.py:80-157`); `model_alias` points the run at
`deepseek` (`harness.py:279`). The **Claude-as-judge** call is the shipped pattern in
`commercial_redline_lib.py:223-277`: a gateway-routed `build_gateway_chat_model(purpose=...)` critic with a
system rubric that returns machine-readable header lines (`VERDICT:`/`SURGICAL:`) + prose, parsed into a
`CraftVerdict`. Track A = **generalise that judge** to a `RetrievalAgenticVerdict` and add the scenarios
below. The deterministic shape checks (`evaluate`, `scenarios.py:306-334`) run first; the **judge** runs only
where judgement is needed (f0-s9 L1-then-L2 discipline, `f0-s9-eval-reuse.md` §3).

> **Judge masking (carry the f0-s9 rule, `f0-s9-eval-reuse.md` §1):** the judge sees a **sanitised tool
> timeline + the answer + the scenario's expectations ONLY** — agent prompt/doctrine and model identity
> stripped, presentation order randomised, mapping logged out-of-band. Claude judges *behaviour*, not "did
> the agent we built do what we told it." Pre-registered rubric, verbatim-evidence quote, single-JSON verdict.

### Track-A scenario suite (each: setup → what DeepSeek does → Claude's rubric → pass criteria)

**A1 — Multi-doc deal Q&A (grounding under spread).**
- *Setup:* a matter seeded with 4-6 deal documents (MSA, SOW, DPA, an email thread) via `seed_multi_doc_matter`;
  the answer to the question lives in exactly one of them.
- *DeepSeek does:* `search_documents` → `read_document` → grounded answer with a cite.
- *Claude's rubric:* (i) **grounded** — the answer's claim is supported by a retrieved/read span (judge sees
  the span); (ii) **right document** — not the distractor; (iii) **cite present + plausible**; (iv) **no
  fabrication**. Verdict STRONG/ADEQUATE/WEAK + `GROUNDED: yes/no`.
- *Pass:* GROUNDED=yes AND verdict∈{STRONG,ADEQUATE} AND deterministic `search_documents` fired
  (`evaluate`).

**A2 — Long negotiation, redline round 1 (surgical craft).**
- *Setup:* the vendor-favoured MSA/licence corpus already in `test_commercial_redline_eval.py:89-106`
  (DataBridge licence + SecureScan MSA), plain redline task (no surgical-technique hints).
- *DeepSeek does:* read whole doc → `apply_redline` (tracked changes).
- *Claude's rubric:* the **shipped `craft_judge`** (`commercial_redline_lib.py:241-277`) — SURGICAL (narrow
  edits, boilerplate left bare) + BALANCE (right mechanism) + coverage.
- *Pass:* `is_surgical_pass` (surgical AND ≥ADEQUATE) — already the maintainer's bar.

**A3 — Respond-to-counterparty (round 2, the no-silent-action gate).**
- *Setup:* feed back a counterparty-marked-up document (Adeu-native tracked changes + comments) into the same
  matter (the C5a path — `extract_counterparty_position` + `respond_to_counterparty`).
- *DeepSeek does:* read every change/comment, respond to each under the **code-enforced** no-silent-action gate.
- *Claude's rubric:* (i) **coverage** — every counterparty change/comment addressed (judge cross-checks the
  list); (ii) **stance quality** — accept/counter/reject is defensible per our position; (iii) **comment
  survival** — no silently-orphaned reply (the C5b-1 guarantee). Verdict + `COVERAGE: full/partial`.
- *Pass:* COVERAGE=full AND verdict∈{STRONG,ADEQUATE}. (Deterministic backstop: the gate's own
  `evaluate_anchoring` receipt.)

**A4 — Which-version selection (the bi-temporal / latest-draft probe).**
- *Setup:* seed **three versions** of the same agreement into the matter (v1, v2-counterparty, v3-clean) +
  a matter fact recording which is current; ask *"Use the latest agreed version — what's the liability cap?"*
- *DeepSeek does:* must identify the **current** version (via `matter_facts_as_of` / the fact ledger or the
  document roster), not answer from a stale draft.
- *Claude's rubric:* (i) **picked the right version**; (ii) **grounded in it**; (iii) **named its basis**
  (why this version). Verdict + `VERSION: correct/wrong`.
- *Pass:* VERSION=correct AND grounded. **This is the scenario that proves the custom bi-temporal layer earns
  its keep** (native Store can't answer "which was current as of signing").

**A5 — Cross-thread conversation recall (the native-Store-conversation probe).**
- *Setup:* run thread #1 in a matter where the agent + user establish a fact in conversation (*"we agreed to
  cap exposure at 12 months' fees"*). Start a **fresh thread** #2 in the **same matter** and ask *"what did
  we decide about the liability cap last time?"*
- *DeepSeek does:* `search_matter_conversations` (the thin native-`store.asearch` tool, N3) → recalls the prior
  turn → answers, citing the prior thread.
- *Claude's rubric:* (i) **recalled the right prior turn**; (ii) **provenance-cited** (thread/date — not a
  byte-offset, by design §2); (iii) **didn't fabricate** if absent. Verdict + `RECALLED: yes/no`.
- *Pass:* RECALLED=yes AND provenance present. **This proves the native Store conversation substrate works
  end-to-end** (and is the regression that must stay green after N0/N2/N3).

**A6 — Within-chat recall after compaction.**
- *Setup:* a single long thread that crosses the compaction trigger (`SummarizationMiddleware`), where a fact
  stated early is asked about late.
- *DeepSeek does:* recall the early fact from the **verbatim offload artifact** (or compacted summary), not
  hallucinate.
- *Claude's rubric:* recalled correctly post-compaction; no fabrication. `RECALLED: yes/no`.
- *Pass:* RECALLED=yes. **Proves native compaction+offload (N2) preserves the conversation** — and tells us
  whether within-chat retrieval needs anything beyond native (the "measure before building" trigger, §7).

**A7 — Read-vs-retrieve-vs-fan-out strategy choice (the agentic-judgement centrepiece).**
- *Setup:* three sibling prompts in matters of different shape: (a) one short doc, whole-doc question
  → **read** is correct; (b) one fact buried in a large corpus → **retrieve** is correct; (c) "review every
  one of these 8 agreements for X" → **fan-out** is correct.
- *DeepSeek does:* picks a move per prompt.
- *Claude's rubric:* did the agent pick the **economical correct strategy** for each? (judge sees the tool
  timeline: did it fan out when it should, and *not* fan out when a single read suffices?) Plus deterministic
  `task_calls`/`delegated`/`ancestry` from the `Receipt` (`harness.py:340-351`).
- *Pass:* correct strategy on ≥2/3 (per-prompt verdict) AND the deterministic fan-out signal matches on the
  fan-out prompt. **This is the direct test of the retrieval-strategy-selection doc's thesis** — model-driven
  routing, judged.

**A8 — Negative control / honest refusal (anti-hallucination).**
- *Setup:* reuse `guard_refusal` + `no_tool_needed` + `ambiguous_clarify` (`scenarios.py:196-238`) — actions
  with no tool, general-knowledge with a no-docs framing, ambiguous referent.
- *DeepSeek does:* declines honestly / answers directly without burning a retrieval call / asks to clarify.
- *Claude's rubric:* honest decline with **no false confirmation**; correct abstention from retrieval.
- *Pass:* the existing deterministic `refusal_ok`/`forbidden_tools_absent`/`clarify_ok` (no judge needed —
  `evaluate`, `scenarios.py:317-324`). The hard 0-noise guard (f0-s9 §3 scenario 3).

**Track-A operating parameters (from f0-s9, `f0-s9-eval-reuse.md` §3):** pre-flight **N=5** on the
highest-variance (scenario × DeepSeek) cell, parameterised; PASS = ≤1 verdict disagreement per metric across
5 cycles; main run **N=10-20** per scenario; quote CI half-widths (±29pp at N=10). Per-cycle: assert a real
assistant message landed or a gateway error surfaced (the silent-403 lesson). Every run pinned to a commit
SHA. **Pass criterion for a slice (§7):** Track-A regression scenarios that were green stay green; new
behaviour ships only when its scenario passes at N≥10.

---

## 6. The evaluation design — Track B: retrieval at scale (CUAD-gold, objective)

**What Track B proves:** that the **retrieval stack** (chunking + FTS + dense + fusion + rerank + offsets —
the custom columns of §2c) actually **finds the right clause at corpus scale** — the 1000-doc case the
orchestrator **cannot judge by reading** (§8). **Objective**, against CUAD human gold. **No LLM judge** for
the core metric (the gold *is* the judge); an optional LLM-extraction-quality pass is secondary.

### 6a. The harness (new, thin — reuses the rig)

```
load_cuad(subset)            # download CUADv1.json (CC-BY-4.0) → fixture dir (gitignored); pick N contracts
  → for each contract: seed_multi_doc_matter(...)        # our ingest+chunker (harness.py:80-157)
  → for each (contract, category) gold:
        run_scenario(question, seeded, model_alias="deepseek")   # production retrieval path, gateway, brakes
  → score(retrieved_chunks, quoted_span, cited_offset  VS  gold.text, gold.answer_start)   # OBJECTIVE
  → aggregate: macro recall@k, precision, AUPR, abstention-on-absent
```

Two run modes so we can isolate the retriever from the agent:
- **Agent mode** — full `run_scenario` (what the user gets; includes the agent's tool-choice).
- **Retriever-only mode** — call the retrieval function directly (`hybrid_search` /the matter search tool)
  with the gold question, bypassing the LLM. **This is the cheap, deterministic mode** that gates the
  *retrieval* slices without spending DeepSeek tokens per query (run the LLM mode on a smaller subset).

### 6b. Metrics (objective)

- **Recall@k** (k∈{1,3,5,10}) — fraction of `(contract,category)` golds whose `answer_start` span falls in a
  top-k retrieved chunk. *The* headline retrieval metric.
- **Precision@k** — fraction of top-k chunks that overlap a gold span (penalises noisy retrieval).
- **AUPR** — area under the precision-recall curve as the retriever's score threshold sweeps (the standard
  CUAD reporting metric; comparable to the CUAD paper).
- **Extraction F1 / char-overlap** (agent mode) — agent's quoted span vs gold text (SQuAD-style token-F1).
- **Offset accuracy** — agent's cited `[start,end)` vs gold `answer_start` within ±W chars (Citation Engine
  check — *this is the column the native Store cannot fill*, §2b#5).
- **Abstention-on-absent** — on CUAD-absent categories (empty `answers`), did the agent correctly say "not
  present"? (hard no-hallucination gate, §4d).

### 6c. Baselines + what each comparison proves

Run the **same CUAD subset** through each configuration; the deltas are the decisions:

| Comparison | Configuration A | Configuration B | What the delta proves / decides |
|---|---|---|---|
| **B1 FTS-only baseline** | today's matter path (FTS, no vectors) | — | The floor. *Measure this FIRST, before building.* |
| **B2 + dense (hybrid)** | FTS-only | hybrid FTS+dense (`retrieval.py`, Slice C embedder on) | Gate for **shipping local embeddings**: ship only if recall@k beats FTS-only by ≥ X pp. |
| **B3 + rerank** | hybrid | hybrid + cross-encoder rerank (Slice D) | Gate for **shipping rerank**: ship only if precision@k (and recall@k) lifts by ≥ Y pp. |
| **B4 chunk-size sweep** | chunk size S1 | chunk size S2 | Tunes the **chunker** (a custom column native doesn't own). |
| **B5 α sweep** | α=1 (FTS) → α=0 (vector) | — | Tunes the **fusion weight** (`retrieval.py:79`); finds the legal-corpus sweet spot. |

**Gate language for the build (concrete, pre-registered):** *"Do not ship local embeddings (Slice C) unless
CUAD macro recall@5 in **agent mode** beats the FTS-only baseline by ≥ X pp on the agreed subset; do not ship
rerank (Slice D) unless it lifts precision@5 by ≥ Y pp without hurting recall@5."* X/Y are maintainer calls
(§9) — set **after** the B1 baseline, never a priori, never tighter than the metric's CI (the f0-s9
sanity-gate-waiver lesson, `f0-s9-eval-reuse.md` §1).

### 6d. Subset sizing (cost-aware — see §8)

- **Retriever-only mode** is cheap (one embed per query + DB) → run on a **large** subset (e.g. **100-200
  contracts**, all 41 categories) for stable recall@k/AUPR.
- **Agent mode** spends DeepSeek tokens per query → run on a **small** subset (e.g. **10-25 contracts ×
  ~10 high-value categories**) for extraction-F1/offset/abstention. The embed step at full-corpus scale is
  the dominant *compute* cost (local embedder = $0/token but CPU/GPU time; cap the subset).

---

## 7. How eval gates the build

The substrate-first decomposition is `native-fit-reconciliation-store-vs-custom.md` §7 (N0 store →
N1 MemoryMiddleware → N2 SummarizationMiddleware+offload → N3 thin conversation tool | Slice C local embedder
| Slice A wire docs retriever | Slice D rerank | recency/MAP gated). Each slice gets a **named eval gate**:

| Build slice | Validated by | Gate / regression baseline |
|---|---|---|
| **N0** wire Store + CompositeBackend (ADR-F049) | Track A **A5** (cross-thread recall lights up) + a prompt-equivalence regression | A5 goes from "can't recall cross-thread" → "recalls"; nothing previously green regresses |
| **N1** MemoryMiddleware digests | **prompt-equivalence regression** (the injected tier digests match the old hand-assembled prompt) | byte/semantic-equivalence of the system prompt; all Track-A scenarios stay green |
| **N2** SummarizationMiddleware + offload | Track A **A6** (within-chat recall post-compaction) | A6 passes; **measures** whether within-chat retrieval needs more than native (the prior "build only if measured" trigger) |
| **N3** thin `search_matter_conversations` | Track A **A5** (with the tool) | A5 recall via the tool; 404-conflation on cross-matter (security check) |
| **Slice C** local embedder (shared) | **Track B B2** (CUAD recall delta) **+** A5/A6 semantic recall | **ship iff** CUAD recall@5 beats FTS-only by ≥ X pp; conversation semantic recall improves |
| **Slice A** wire matter docs → `hybrid_search` | **Track B B1→B2** (agent mode) | matter Q&A recall@k matches the retriever-only numbers (no regression from wiring) |
| **Slice D** cross-encoder rerank | **Track B B3** | **ship iff** precision@5 lifts ≥ Y pp without hurting recall@5 |
| **Recency weighting** (deferred) | Track A A5 with **stale-turn** variant | **build only if** a measured stale-turn recall failure appears (now a *measured* trigger) |
| **Documents MAP** (deferred) | Track B large-corpus recall@k with/without MAP routing | build only if recall@k at scale degrades without it |

**Regression baseline:** freeze the **first full Track-A run** (all scenarios, DeepSeek, N≥10) + the **first
Track-B B1 run** (FTS-only, the agreed CUAD subset) as `docs/fork/evidence/retrieval-eval/baseline/`. Every
subsequent slice re-runs both; a slice that drops a green Track-A scenario or lowers a Track-B metric below
baseline (outside CI) is a **blocker**. This turns the prior docs' *assumptions* (recency matters;
within-chat retrieval needed; hybrid beats FTS; rerank helps) into **measured deltas** — the maintainer's
"measure before building" made literal.

---

## 8. What I (the orchestrator) can and cannot judge

Stated bluntly, because it determines why there are two tracks:

- **Claude CAN judge agentic quality.** Did the agent pick read vs retrieve vs fan-out, ground its answer,
  cover every counterparty change, decline honestly, recall the right prior turn? These are *behaviours over
  a readable timeline + a handful of documents* — Claude reads the sanitised tool timeline + answer +
  expectations and returns a rubric verdict (the shipped `craft_judge` shape, `commercial_redline_lib.py:223-277`).
  **This is Track A**, and it is genuinely Claude's strength.

- **Claude CAN judge small-corpus correctness by reading.** For a single contract or a 4-6 doc matter, Claude
  can verify "is this the right clause, is the quote faithful, is the cite plausible" directly. Track A's
  grounding/extraction checks live here.

- **Claude CANNOT eyeball 1000-doc recall.** "Across 200 contracts × 41 categories, did the retriever surface
  the gold clause in the top-5?" is **not** a reading task — it's thousands of span-overlap comparisons that
  must be **objective and reproducible**. No LLM judge (Claude or otherwise) should *be* the gold here; it
  would be slow, unfaithful, and unfalsifiable. **This is exactly the gap CUAD-gold fills** (§4): human
  annotations + `answer_start` offsets = an objective recall/precision/AUPR surface. **Track B is objective
  precisely because Claude can't and shouldn't judge it.**

- **Claude is not the agent-under-test.** DeepSeek is. Claude designs + judges; the **qualified provider**
  (DeepSeek; MiniMax out of quota) executes. Confounds (gateway think-handling, adapter bugs) are triaged
  against the *adapter first* before blaming the model (the f0-s9 lesson, `f0-s9-eval-reuse.md` §1).

- **Provider-quota + cost are real limits.** Every Track-A scenario and every Track-B **agent-mode** query
  spends DeepSeek tokens; long-negotiation scenarios (A2/A3) are the most expensive (whole-doc reads + redline
  generation). Track-B **retriever-only** mode avoids LLM cost (embed + DB only) — which is *why* it carries
  the large-subset recall numbers and agent-mode carries the small-subset extraction numbers (§6d). The
  embed step at full-corpus scale is the dominant compute cost even with a local $0/token embedder. **Budget
  is a maintainer call** (§9) — and a hard cap belongs in the runner (the R4 brake already caps per-run cost;
  the eval matrix needs its own ceiling).

---

## 9. Recommended next steps + open questions

### Recommended sequence (measure before building)

1. **Build the Track-B CUAD harness FIRST and get the B1 FTS-only baseline** — *before* any substrate/retrieval
   slice. Reuses `seed_multi_doc_matter` + `run_scenario`; new code is `load_cuad` + the objective scorer
   (span-overlap recall@k/precision/AUPR/abstention). Output: `docs/fork/evidence/retrieval-eval/baseline/`.
   This is the number every later slice must beat — without it, "Slice C helps" is an assumption.
2. **Build the first Track-A scenario suite (A1, A5, A7, A8) and run it on DeepSeek for a baseline** — generalise
   the shipped `craft_judge` into the masked retrieval judge; reuse the deterministic `evaluate`. This is the
   regression net the substrate slices (N0-N3) must keep green. Add A2/A3 (already largely built in
   `test_commercial_redline_eval.py` / the C5a path) for the long-negotiation coverage; add A4/A6 with the
   substrate slices they validate.
3. **Then build the substrate (N0 → N1 → N2 → N3), each gated by its named eval** (§7). N0+ADR-F049 first.
4. **Then the cost play (Slice C shared embedder), gated by Track-B B2;** wire docs (Slice A); rerank (Slice D)
   gated by B3. Recency/MAP only if measured.
5. **Freeze baselines; re-run both tracks per slice; block on regressions.**

### Genuine maintainer calls (only these are load-bearing)

1. **CUAD subset size** (the cost/stability trade): retriever-only large subset (proposed **100-200
   contracts**, all 41 categories) + agent-mode small subset (proposed **10-25 contracts × ~10 high-value
   categories** — cap, indemnity, IP, governing law, termination, exclusivity, change-of-control…). Confirm
   the numbers and the category shortlist.
2. **Track-B gate thresholds X (embeddings) and Y (rerank)** — set **after** the B1 baseline, never a priori,
   never tighter than the CI. Approve "set post-baseline" as the policy (the f0-s9 sanity-gate-waiver lesson).
3. **Track-A judge rubric strictness** — STRONG/ADEQUATE/WEAK with `is_surgical_pass`-style "≥ADEQUATE AND
   <flag>=yes" pass bars (the shipped craft-judge convention). Confirm the bar per scenario (esp. A3 coverage
   = full vs partial, A4 version = correct/wrong, A7 strategy ≥2/3).
4. **Eval-in-CI vs manual** — both tracks spend real DeepSeek tokens and need the live stack, so they are
   **provider-marked, CI-skipped** (the existing convention, `test_commercial_redline_eval.py:55-61`;
   `evals/README.md` "nothing here runs in CI"). The **retriever-only** Track-B mode and the **deterministic
   scorer unit tests** *can* run in CI ($0, no LLM). Confirm: live tracks manual/on-demand; scorer units + a
   tiny retriever-only smoke in CI.
5. **DeepSeek spend budget for evals** — a per-matrix ceiling (and whether the qualification matrix is a
   recurring artifact re-run per slice, or per-milestone). Track-A long-negotiation cells (A2/A3) and
   Track-B agent-mode dominate; retriever-only is near-free. Propose: a fixed $ ceiling per slice gate +
   retriever-only as the default day-to-day signal, agent-mode reserved for slice gates and milestone runs.
6. **Second model family for the agentic track?** f0-s9 recommends ≥2 families (the "model is dependency
   injection" finding). DeepSeek is the qualified provider today; a second family (Kimi K2.x via a gateway
   provider entry, `f0-s9-eval-reuse.md` §3) would harden Track A — but costs quota. Defer or include?
7. **Scenario coverage depth** — is A1-A8 the right v1 set, or add (e.g.) a *conflicting-documents* scenario
   (two docs disagree on a term — does the agent surface the conflict?) and a *cite-faithfulness adversarial*
   (does the agent ever cite a span it didn't retrieve?). Both are readable → Track A. Confirm the v1 cut.

### Open questions / thin spots (honest)

- **The agent's retrieved-chunk set may not be cleanly observable from `agent_run_steps`.** Track-B agent-mode
  recall@k needs the chunk ids the retrieval tool returned; the step `summary` is a bounded digest
  (`f0-s9-eval-reuse.md` §4 flags this for arg-correctness). **Mitigation:** Track-B **retriever-only** mode
  sidesteps it entirely (calls the retriever directly), and is the primary recall@k source; agent-mode then
  scores the *answer's quote/offset* (observable in `final_answer`) rather than the internal chunk set. If we
  want agent-mode recall@k too, a small structured `retrieved_ids` digest is a tiny migration (the f0-s9
  §4 `args_digest` option).
- **CUAD questions are SQuAD-phrased ("Highlight the parts…").** We rephrase to natural counsel questions for
  realism — but the rephrasing is a variable. **Mitigation:** keep a fixed, version-pinned rephrasing map
  (pin to SHA, like the agent-instruction variants) so reruns are comparable; report both raw-SQuAD and
  rephrased on a small subset once to show the gap is bounded.
- **No measured retrieval failure on our own data yet** (carried from `native-fit…md`). CUAD is *commercial
  contracts* — close to our Commercial area, weaker proxy for Privacy/Disputes. **Mitigation:** CUAD gates
  the *mechanism* (does hybrid+rerank+offset beat FTS objectively); area-specific quality stays a Track-A
  judged concern. Note MAUD/LEDGAR/ACORD as future objective corpora for other areas
  (`docs/LQVern/HANDOFFlavernevaluation.md:66`) — out of scope here.
- **Single-judge risk (Claude only) on Track A.** One judge can have systematic bias. **Mitigation:** the
  deterministic `evaluate` checks run first and gate the cheap cases without the judge; the judge is reserved
  for genuinely-judgement cases; masking + verbatim-evidence-quote + pre-registered rubric reduce drift
  (f0-s9 §3). A second-family *judge* (not just agent) is a possible hardening if the maintainer wants it.

---

### Honest limits of this dossier

- **OSS findings are web-sourced (June 2026), not all hands-on.** The deepagents examples README and the
  Milvus tutorial were read this session; the "no example does hybrid/rerank/offset" claim is from the
  examples README + the Milvus pattern — strong, but a deeper crawl of every example's code could surface a
  retrieval snippet I didn't open. The *substrate* APIs are verified at our pins via `native-fit…md`.
- **CUAD facts are from the Atticus/HF/Zenodo primary sources**; the exact train/test counts (22,450/4,182)
  are the HF `cuad-qa` QA build — we use the raw per-contract `CUADv1.json` grouping (510 contracts), so the
  per-contract×category counts are what we drive, not the flattened QA rows. Verify the raw JSON shape at
  fixture-build time.
- **The harness/judge/retriever claims are verified at `file:line` this session** (`harness.py`,
  `scenarios.py`, `commercial_redline_lib.py`, `knowledge/retrieval.py`). The *new* code (CUAD loader +
  objective scorer + the generalised retrieval judge) is **designed, not yet written** — the design reuses
  shipped seams, but the scorer's span-overlap τ and the AUPR computation need an implementation pass.
- **No numbers yet.** Every threshold (X, Y, τ, W, k, subset sizes, N, $ ceiling) is a *placeholder to be set
  against the first baseline* — by deliberate policy (never gate tighter than the CI; set bars post-baseline).
  This document specifies the *method and the gates*, not the results.
- **Cost is estimated, not measured.** "Agent-mode dominates; retriever-only is near-free" follows from the
  token model (whole-doc reads + redline generation vs embed+DB), not a billed eval run. The first baseline
  run is also the first real cost data point — treat its spend as the calibration for the §9.5 budget.
