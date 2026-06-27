# Research — The retrieval-STRATEGY-SELECTION layer: when to retrieve passages, read in full, or fan out

**For:** the maintainer's follow-up to the retrieval-at-scale pass
(`document-retrieval-at-scale-and-cost.md`) and the discovery pass (`document-discovery-and-map.md`).
Those two built the **funnel** — L1 documents MAP narrows 1000 → a handful, L2 local-embedding hybrid
retrieval pulls passages, L3 reads within a document. **They stopped one layer short.** Once the
funnel has narrowed the corpus to **K candidate documents**, *how should the agent consume them*?
There are three answers — pull cheap passages, read the relevant ones in **full**, or **fan out
subagents** that each read in full — and they trade **cost** against **quality** very differently.
The maintainer's thesis: the agent should **have the choice** and be **self-aware** — estimate the
cost, know its budget, pick the right mode, and escalate. Two concrete proposals to engage head-on:
*"fan-out preferred unless it would likely cost >~100k tokens"* and *"a hybrid mode with the option to
read the relevant documents in full."* This document is the **strategy-selection layer** that sits
above L2.

**Method:** codebase re-discovery (LQ.AI fork, branch `fork/c3-update-memory-ux`, head `1f8fc87`;
code claims re-read at the cited `file:line`, several verified live against the running dev stack) +
web research on fan-out vs RAG vs long-context, adaptive/self-routing retrieval, and the multi-agent
token multiplier (URLs inline). **Date:** 2026-06-27.

**Posture reminders baked into every recommendation:** all external-provider LLM calls route through
the in-house gateway (sole key-holder + only egress, ADR-F010); a per-action grant/halt chokepoint
exists on every agent tool call (R5/R6 — and R4 *by design*, but **R4 is a no-op today**, see §6 —
ADR-F002); fan-out is **deepagents-native + model-driven** and the fork added **zero** orchestration
scaffolding for it (ADR-F034); unit-of-work memory is auto-write-then-correct (ADR-F042); a fan-out
shape-miss is **"a finding, not a failure"** (ADR-F015); new dependencies are SBOM/supply-chain
surface and must be justified.

**What carries forward (right):** the **funnel** is correct and is the precondition for everything
here — L1 map → L2 hybrid → L3 read. **What this doc adds:** the *selection policy between the funnel
and the answer*. The prior two docs implicitly assumed one consumption mode each (the discovery doc:
"just read the one document"; the scale doc: "retrieve passages"). The maintainer is right that this
is a false binary — and right that the agent should choose. The job here is to make that choice
**cheap, defensible, cost-aware, and guard-railed**, and to refine the two specific proposals with
evidence rather than rubber-stamp them.

---

## 1. Executive summary

- **Core verdict: COMPOSE the three modes; do not pick one.** Cheap passage retrieval, read-relevant-
  in-full, and subagent fan-out are **not competitors** — they are three rungs of a cost/quality
  ladder that the agent climbs *only as far as the question requires*. The literature's strongest
  result on exactly this question — **Adaptive-RAG** — is a three-class router (no-retrieval /
  single-step / multi-step) that **matches always-expensive baselines at substantially lower cost**
  ([arXiv 2403.14403](https://arxiv.org/abs/2403.14403)). The maintainer's "give the agent a choice"
  instinct is the published state of the art; our job is to wire it to *our* funnel and *our* brakes.

- **The three modes (each precise on cost):** **(a) cheap passage retrieval** — L2 hybrid returns
  top-k chunks (~8 × ~1.5k chars ≈ **~3k tokens**), near-zero $, tens of ms; recall-bounded, *can
  silently miss paraphrase* — the maintainer's central worry, and it is real. **(b) read-relevant-in-
  full (inline)** — read K candidate docs into the lead's own context (each ≤40k chars / ~10k tokens,
  `tools.py:65`); highest single-thread fidelity, **no recall gap within a read doc**, but bounded by
  the ~170k-token compaction floor (`factory.py:33`). **(c) subagent fan-out** — N parallel subagents
  each read a slice in full and return a *compressed* finding; reads far more total text than the
  window holds, but costs **~15× the tokens of a single chat** ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)) and the returns are **lossy** (collapsed to one ToolMessage,
  ADR-F034).

- **Retrieval/map is the NARROWING step that precedes all three — it is not a fourth competing mode.**
  L1 (map) + L2 (hybrid) take 1000 → K. The strategy layer chooses how to consume those K. Even
  fan-out reads *candidates*, not the whole corpus; even full-read reads the *narrowed* set. Conflating
  "retrieve" (narrow) with "retrieve-passages-as-the-answer" (consume) is what made the prior docs read
  like a binary.

- **The decision rule is keyed on a PRE-FLIGHT cost estimate, which we can compute for free.** Every
  ingested document stores `character_count` (`document.py:82`). Summing the candidate set's
  `character_count` and dividing by ~4 chars/token gives a **token estimate before reading a single
  byte**. Compare it to the **remaining budget** (~200k window, ~170k compaction floor, 40k/doc read
  cap). That one number drives the choice — and it is a local Postgres `SUM`, zero inference, zero $.

- **Refining the maintainer's "~100k threshold":** the instinct is sound but the variable is wrong.
  The gate should be **the candidate set's estimated tokens against the *remaining* window**, not a
  fixed 100k. Concretely: **read-in-full when the set fits comfortably inside the remaining context**
  (a working rule: ≲ **half** the post-compaction floor, ~**85k tokens**, leaving headroom for prompt
  + reasoning + output); **fan-out when the set EXCEEDS the window but decomposes into independent,
  parallelizable reads**; **retrieval passages when the set is too large *and* not cleanly
  parallelizable, or when the question is a narrow lookup**. "~100k" is a reasonable *order of
  magnitude* for "doesn't fit, consider fan-out" — but it should be expressed as a fraction of the
  live budget and gated on **independence**, because fan-out's whole win-condition is parallelizable
  breadth, not raw size (§3, §4).

- **Fan-out is NOT the default — cheap-first is.** Anthropic's own data: token usage explains **80%**
  of multi-agent performance variance, and the economics only clear "when task value > token cost"
  ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). Defaulting to
  fan-out spends 15× on questions a single full-read or a passage pull would answer. The published
  win-condition is **breadth-first, independent directions** — *not* "any large question." Inverting
  the maintainer's framing slightly: **fan-out is the escalation, not the baseline**; reach for it when
  the set won't fit *and* splits cleanly, not by default-unless-expensive.

- **Confidence-based ESCALATION ties the rungs together.** Start cheap (passages); if the agent's own
  coverage/confidence self-check says "this is thin / I'm missing context," escalate to full-read of
  the top candidates; if *those* won't fit, escalate to fan-out. This is **Self-RAG's** reflection-
  token pattern ([arXiv 2310.11511](https://arxiv.org/abs/2310.11511)) expressed in prose + a tiny
  self-check, not a trained classifier. It directly answers the paraphrase-miss worry: cheap retrieval
  is the *first* probe, never the *only* one, and the agent is taught to distrust thin retrieval on
  meaning-questions.

- **It rides existing machinery — almost no new engine.** Fan-out is the deepagents `task` tool,
  already model-driven, already wired, **zero orchestration added** by the fork's roster slice
  (ADR-F034). The choice is **mostly prose** (a strategy skill + prompt doctrine). The only genuinely
  new *code* is small: surface per-doc size in the inventory and an `estimate_read_cost` helper (a
  Postgres `SUM` + arithmetic), and — to make the guardrail real — a fan-out **quota** and (the honest
  gap) **wire R4 into an actual per-run token budget**, which is *deferred today* (§6). Next fork ADR
  is **F049**; no migration is required for the cheap-wins.

- **Honest thin spots.** (1) The cost cap **R4 is a documented no-op** right now (`guard.py:19-22,128-129`); the brakes that actually fire are `max_steps`/`recursion_limit`/wall-clock — *step* caps, not
  *token* caps (§6). (2) Fan-out's quality edge is established on **research/browse** tasks; its
  transfer to *legal meaning-extraction over a deal* is plausible but **unmeasured on our corpus**
  (§3). (3) We have **no labelled retrieval eval** yet, so "passages silently miss paraphrase" is a
  structural argument (lexical-vs-dense) + the cited literature, not a number on our documents — the
  same honest gap the scale doc flagged (§9).

---

## 2. The three consumption modes

**First, the framing the prior docs blurred.** Retrieval/map is the **narrowing** step; it is not one
of the three consumption modes. The pipeline is:

```
1000 docs ──[L1 MAP: which docs are even relevant]──▶ K candidates
            ──[L2 HYBRID: rank passages/docs within K]──▶ ranked K (+ passages)
                                                              │
                         ┌────────────────────────────────────┼────────────────────────────────────┐
                         ▼                                     ▼                                     ▼
                (a) CHEAP PASSAGES                    (b) READ-RELEVANT-IN-FULL              (c) SUBAGENT FAN-OUT
                 use the top-k chunks                  read the K (or top few) docs            N subagents each read a
                 L2 already returned                   into the LEAD's own context             slice in full, return a
                                                                                               compressed finding
```

All three consume **the narrowed set**, never the raw 1000. The decision (§4) is purely: *given K
candidates and their sizes, which consumption mode?*

### (a) Cheap passage retrieval

- **What:** the L2 hybrid (`hybrid_search`, `retrieval.py:71`, once wired — scale doc Slice A) returns
  the top-k fused+reranked chunks; the agent reasons over those passages. Today the matter path is
  FTS-only top-8 (`_search`, `tools.py:161`; `_SEARCH_LIMIT = 8`, `tools.py:61`).
- **Quality profile:** **precise for lookups, recall-bounded for meaning.** Excellent when the answer
  is a named clause, a defined term, a party, a dollar figure, a date — anything lexically or densely
  *anchored*. **Its failure mode is exactly the maintainer's worry:** a meaning-question over
  paraphrase ("where do we grant audit rights?" vs a doc that says "the Provider shall permit
  inspection of its records upon thirty days' notice") can be **silently missed** — the top-k simply
  doesn't contain the relevant chunk, and the agent never knows it's missing. Dense embeddings (L2)
  shrink this gap versus FTS but **do not close it**; rerank precision helps recall→precision, not the
  tail of true misses. This is *the* structural argument for not making passages the only mode.
- **Cost profile (token math):** result ≈ **8 chunks × ~1.5k chars** (`_SNIPPET_LIMIT = 1500`,
  `tools.py:62`) ≈ **~12k chars ≈ ~3k tokens** into context. Index cost is one-time and (with local
  embeddings, scale doc §5) **$0**. Per-query: a pgvector scan + FTS scan + rerank of ~40 candidates =
  **tens of ms, ~$0** ([rerank latency, arXiv 2409.07691](https://arxiv.org/pdf/2409.07691)).
- **Latency:** **milliseconds.**
- **Right tool when:** the question is a **targeted lookup**; the candidate set is **too large to read
  in full and not cleanly parallelizable**; or as the **cheap first probe** before escalating.

### (b) Read-relevant-in-full (inline)

- **What:** read the K candidates (or the top few) **into the lead agent's own context** via
  `read_document` and reason over the *whole* text. Each read is capped at **40,000 chars ≈ ~10k
  tokens** (`_READ_LIMIT`, `tools.py:65`); over-cap reads truncate with an honest notice steering back
  to search (`_read`, `tools.py:249-255`).
- **Quality profile:** **highest single-thread fidelity, no within-doc recall gap.** Reading a
  document whole preserves cross-clause structure (definitions ↔ liability cap ↔ governing law) that
  chunking fragments, and there is **no retrieval miss** *within a document the agent actually reads* —
  the paraphrase that passage-retrieval drops is simply *present*. The literature backs this: long-
  context "consistently outperformed RAG when ample resources were available"
  ([arXiv 2501.01880](https://arxiv.org/abs/2501.01880)), and "In Defense of RAG" itself frames the
  win as *order-preserving* full-context reading
  ([arXiv 2409.01666](https://arxiv.org/pdf/2409.01666)). **The catch — `lost-in-the-middle`:** the
  quality is real *only inside the high-attention region*. Accuracy is U-shaped and degrades **>30%**
  when the needle sits mid-context, replicated across six model families ([Liu et al., TACL 2023](https://cs.stanford.edu/~nfliu/papers/lost-in-the-middle.tacl2023.pdf)). So **reading one or a few
  in-scope documents in full is the quality sweet spot; stuffing many is not** — past a point, full-
  read *degrades* into a worse version of retrieval.
- **Cost profile (token math):** **K × min(char_count, 40k) / 4** tokens, *paid into the lead's window
  every turn the content is live*. One ~10k-token contract is trivial. Five 40k-char docs = **~50k
  tokens** — comfortable. **The binding constraint is the ~170k post-compaction floor**
  (`factory.py:33` — compaction at 0.85 × 200k), shared with the prompt, the injected memory tiers,
  reasoning, and output. Beyond ~half that floor for *reads alone*, fidelity starts paying the lost-
  in-the-middle tax and compaction starts churning. Per-query $: just the model's input tokens (no
  retrieval infra).
- **Latency:** one DB fetch per doc (ms) + the model ingesting the tokens (seconds, scales with size).
- **Right tool when:** the candidate set **fits comfortably in the remaining window** (§4) — the
  single-document common case the discovery doc nailed, and the **2–6 medium-document** case (the
  maintainer's "hybrid with the option to read the relevant documents in full"). This mode IS that
  hybrid: narrow with the map/L2, then read the survivors whole.

### (c) Subagent fan-out

- **What:** the lead dispatches N subagents via deepagents' model-driven **`task`** tool; each reads a
  slice (a document, a document-group, a sub-question) **in full** in its **own** context window, then
  returns a **compressed** finding. The fork already runs this — `agent_config.subagents`
  (`composition.py:554`), a drafter/reviewer roster (ADR-F034), nesting under `parent_step_id`. The
  win is **aggregate reading capacity far beyond one window**: N × ~170k tokens of reading, condensed.
- **Quality profile:** **highest *coverage* for breadth, but lossy and coordination-bounded.**
  Anthropic's multi-agent system **outperformed a single agent by 90.2%** on a breadth-first research
  benchmark precisely because subagents "operate in parallel with their own context windows, exploring
  different aspects... before condensing the most important tokens"
  ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). **But two quality
  caveats are load-bearing for us:** (1) **returns are lossy** — deepagents collapses a whole subagent
  run into a *single* `ToolMessage` (the last AIMessage text), and our subagent spec forbids
  `response_format` for the ADR-F010 model-free guarantee (ADR-F034) — so the lead sees the subagent's
  *summary*, not its evidence, and may have to re-encode. (2) The published win-condition is **narrow**:
  fan-out excels on "breadth-first queries that involve pursuing multiple **independent** directions
  simultaneously" and fails where "all agents [must] share the same context or involve many
  dependencies between agents" ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). A question whose sub-answers *interact* (a definitional cross-reference threaded through ten
  documents) is exactly the dependent case fan-out is *worst* at.
- **Cost profile (token math):** **~15× the tokens of a single chat** (and a single subagent step ~4×)
  ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). Token usage alone
  explained **80%** of performance variance there — i.e. you are mostly *buying quality with tokens*.
  For us: N subagents, each potentially filling its window with reads, plus the lead's orchestration
  and the re-encoding of lossy returns. This is **by far the most expensive mode**, and the only one
  where cost can run away (§6).
- **Latency:** subagents run **in parallel**, so wall-clock can *beat* sequential full-reads of the
  same volume — fan-out's one latency advantage. But total *work* (and $) is highest.
- **Right tool when:** the candidate set **exceeds the window** *and* the question **decomposes into
  independent, parallelizable reads** (per-document position-extraction across a deal; "summarize each
  of these 12 documents' position on X"), *and* the task value justifies the 15× spend. **Not** the
  default; **not** for dependent/cross-referential questions; **not** for sets that fit (read those in
  full — cheaper and higher-fidelity).

### The three modes at a glance

| Mode | Quality edge | Quality risk | Tokens into context | $ / query | Latency | Best when |
|---|---|---|---|---|---|---|
| (a) Passages | precise lookups | **silent paraphrase miss** | ~3k | ~$0 | ms | targeted lookup; set too big & not parallel; cheap first probe |
| (b) Read-in-full | full fidelity, no within-doc miss | lost-in-the-middle if many | K×≤10k | model input only | s | set fits remaining window (1–6 medium docs) |
| (c) Fan-out | breadth coverage beyond window | lossy returns; bad on dependencies | **~15×** a chat | highest | parallel (can be fast) | set exceeds window **& independent**, high task value |

---

## 3. The cost–quality evidence

What the literature actually shows — grounded, with the disagreements kept honest.

### 3a. Full-read / long-context beats RAG on quality *when it fits* — capacity- and order-dependent

- "Long-context LLMs consistently **outperformed RAG when ample resources were available**, but RAG
  was undoubtedly **far more cost-efficient**" ([arXiv 2501.01880](https://arxiv.org/abs/2501.01880)).
  The gap is **capacity-dependent**: weaker/open models benefit *more* from retrieval (limited long-
  context ability); stronger models exploit long context better. **Relevant to us because the model is
  injected and replaceable** (MiniMax-M3 today, tier-4-weak per ADR-F015): on a weaker model, retrieval
  earns its keep *more*, and full-read's quality edge is *smaller* — the decision rule must key on the
  *active* model's effective window, not a constant.
- **Order matters as much as inclusion.** "Preserving the order of retrieved chunks in the original
  text rather than... relevance-descending order significantly improves answer quality"
  ([arXiv 2501.01880](https://arxiv.org/abs/2501.01880); echoed by "In Defense of RAG",
  [arXiv 2409.01666](https://arxiv.org/pdf/2409.01666)). Full-read gets document order **for free** —
  a structural reason it beats passage-stitching on cross-clause legal reasoning.
- **Lost-in-the-middle caps the benefit.** >30% mid-context degradation, six model families
  ([Liu et al., TACL 2023](https://cs.stanford.edu/~nfliu/papers/lost-in-the-middle.tacl2023.pdf)).
  So "read more in full" is **not monotonic** in quality: one in-scope doc → great; ten stuffed docs →
  worse than retrieving from them. This is the evidence that **full-read is a *bounded* mode, not an
  always-better one** — and the precise refutation of "just read everything you can."

**Net for the paraphrase worry:** the maintainer is right that passage-retrieval *can* silently miss
meaning, and that reading in full removes that miss *for the documents actually read*. The evidence
**supports** preferring full-read over passages **when the set fits** — and **stops supporting it**
once the set is large enough to push content into the lost-in-the-middle zone, at which point you want
*selective* reading (back to the funnel) or fan-out (independent slices), not a bigger stuff.

### 3b. Fan-out's quality win is real — but its win-condition is *narrow* and its cost is ~15×

- **The headline:** Anthropic's multi-agent research system **beat a single agent by 90.2%** on an
  internal breadth-first research eval; **multi-agent used ~15× the tokens of a chat** (a single
  subagent step ~4×); **token usage explained 80%** of performance variance (95% with tool-calls +
  model choice) ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)).
- **The stated win-conditions** (quote): "breadth-first queries that involve pursuing **multiple
  independent directions simultaneously**," "heavy parallelization, information that **exceeds single
  context windows**, and interfacing with numerous complex tools."
- **The stated anti-conditions** (quote): "domains that require **all agents to share the same context
  or involve many dependencies between agents** are not a good fit... most coding tasks involve fewer
  truly parallelizable tasks than research, and LLM agents are not yet great at coordinating and
  delegating... in real time."
- **The economic rule** (their framing, widely quoted): multi-agent wins **"when [task] value > token
  cost"** ([summary](https://x.com/codingscape/status/1937503477971697684)). They name the qualifying
  tier explicitly: **legal due diligence**, competitive intelligence, biomedical literature review —
  *exactly our domain*, which is the strongest external signal that fan-out belongs in the toolkit at
  all. But "high-value research" ≠ "every matter question"; a one-clause lookup is not due diligence.

**Honest transfer caveat:** this is **research/browse**, not legal meaning-extraction over a fixed
deal corpus. The *mechanism* (parallel independent reads → compressed findings) transfers cleanly to
"extract each document's position on X across the deal"; it transfers *poorly* to dependent,
cross-referential legal reasoning (the anti-condition). We have **no measurement on our own corpus** —
so fan-out's quality edge here is **argued, not proven** (§9). The fork's own experience corroborates
the *cost* risk: ADR-F015 saw a model **over-explore and hit `cap_exceeded`** after reconciling — i.e.
fan-out/exploration *can* and *did* blow the step budget in practice.

### 3c. Where RAG / cheap retrieval still wins — and why it stays the floor

- **Cost-efficiency, decisively** ([arXiv 2501.01880](https://arxiv.org/abs/2501.01880)) — near-zero
  per-query vs model-input-per-read vs 15×.
- **Dynamic/diverse corpora** — "RAG performs better when datasets are dynamic or diverse"
  ([Vellum](https://www.vellum.ai/blog/rag-vs-long-context)); a 1000-doc growing deal is more dynamic
  than a single static contract.
- **Targeted lookups** — when the answer is a named, anchored span, retrieval is *both* cheaper *and*
  often more precise (no mid-context dilution).
- **The adaptive result that unifies all of this:** **Adaptive-RAG** routes among **no-retrieval /
  single-step / multi-step** by predicted query complexity and **matches always-multi-step quality at
  much lower cost** ([arXiv 2403.14403](https://arxiv.org/abs/2403.14403)); **Self-RAG** trains
  reflection tokens to decide *when* to retrieve and to *self-critique* relevance/factuality
  ([arXiv 2310.11511](https://arxiv.org/abs/2310.11511)); **Self-Routing RAG** binds selective
  retrieval to the model's own knowledge-verbalization ([arXiv 2504.01018](https://arxiv.org/html/2504.01018v3)). **The consistent finding across this line: a cheap-first, escalate-on-need policy
  recovers the expensive mode's quality at a fraction of its cost.** That is the empirical backbone of
  §4 — and the evidence-based version of the maintainer's "give the agent a choice."

**Synthesis of the evidence:** quality ranks roughly **fan-out (breadth) ≳ full-read (depth, if it
fits) > passages** on *recall/coverage*; cost ranks **passages ≪ full-read ≪ fan-out**. There is **no
dominant mode** — which is *why* the answer is a **router**, and why "fan-out by default" (pure quality
framing) and "retrieve by default" (pure cost framing) are both wrong. Adaptive selection is the only
position the evidence supports.

---

## 4. The decision rule (the heart)

A concrete, defensible policy. It keys on **one pre-flight number we can compute for free** and the
**live remaining budget**, and it is expressed so the agent can follow it as prose (§5) while a thin
helper supplies the signal.

### 4a. The pre-flight cost estimate (free, no inference)

Every ingested document stores **`character_count`** (`document.py:82`). For a candidate set S (the
docs L1/L2 narrowed to):

```
est_read_tokens(S) = Σ_{d∈S} min(character_count(d), 40_000) / 4        # 40k = read cap; ~4 chars/token
```

- The `min(…, 40_000)` is honest: `read_document` truncates at 40k chars (`tools.py:65`), so a doc
  *cannot* cost more than ~10k tokens to read, no matter its size. (A doc that truncates is itself a
  **signal**: full-read will be partial → prefer passages or a within-doc nav for that one.)
- This is a **Postgres `SUM` over already-stored integers** — zero inference, zero $, sub-ms. It is the
  single cheapest high-leverage signal in this whole document.

### 4b. The live budget constants

- **Window:** `DEFAULT_MAX_INPUT_TOKENS = 200_000` (`factory.py:33`) — *injected/replaceable*; read
  the active model's value, never hard-code 200k.
- **Compaction floor:** deepagents compacts at **~0.85× → ~170k** (`factory.py:33` comment).
- **Already spent:** base prompt + the injected tiers (client context, matter wiki ≤16k chars,
  corrections, roster — `composition.py:218-254`) + conversation history (checkpointer-replayed) +
  headroom for reasoning and output. Call the live remainder **`R`** (≈170k minus the above; in
  practice often **~120–150k** free at turn start for a fresh-ish thread).
- **Per-doc read cap:** **40k chars / ~10k tokens** (`tools.py:65`).

### 4c. The rule

> Let `E = est_read_tokens(S)` and `R` = remaining budget (post-compaction floor minus what's already
> committed this turn). Pick the **cheapest mode that the question's *kind* and the set's *shape*
> justify**, then escalate on a confidence/coverage self-check.

1. **Targeted lookup (any size set) → PASSAGES (mode a).** If the question is a narrow, anchored
   lookup ("what's the liability cap in the MSA?", "who signed the SOW?"), use L2 passages regardless
   of `E`. Cheapest, and often *most* precise. *(This is Adaptive-RAG's "single-step.")*

2. **Meaning/comparison question AND `E ≲ ½R` → READ-IN-FULL (mode b).** If the set fits **comfortably**
   inside the remaining window — a working threshold of **`E ≤ ~85k tokens`** *and* `E ≤ ½R`, leaving
   half the floor for prompt+reasoning+output and dodging lost-in-the-middle — **read the candidates in
   full** and reason over whole text. This is the maintainer's "hybrid with the option to read the
   relevant documents in full," made concrete: the funnel picks the survivors, full-read consumes them.
   *Prefer reading the **top few** (by L2 rank) over the literal K when K is borderline — quality is
   U-shaped, so fewer-whole beats more-stuffed.*

3. **Meaning question AND `E > R` AND the set is INDEPENDENT/PARALLELIZABLE → FAN-OUT (mode c).** If the
   set won't fit *and* the question decomposes into independent per-document (or per-group) reads
   ("across all 12 deal documents, extract each one's audit-rights position"), **fan out** one subagent
   per slice, each reading in full, returning a compressed finding; the lead reconciles
   (`reconcile_positions`, ADR-F034). Gate on **independence**, not size alone — fan-out is bad at
   dependent questions (§3b).

4. **Meaning question AND `E > R` AND NOT cleanly parallelizable → PASSAGES, with the funnel tightened
   (mode a + re-narrow).** A large, cross-referential question that won't fit and won't split: fall
   back to L2 passages, but **lift recall** (more candidates, rerank, then read the *very* top few in
   full — a hybrid of a+b). Escalate to fan-out only if a coverage self-check still says "thin."

5. **ESCALATION overlay (Self-RAG-style, all branches).** After a cheap pass, the agent runs a
   **coverage/confidence self-check** ("did the retrieved passages actually contain the answer, or am I
   inferring from absence?"). Low confidence on a *meaning* question → **escalate one rung**: passages →
   read-top-few-in-full → fan-out. This is the safety valve against the silent-paraphrase-miss: cheap
   retrieval is always allowed to be **wrong-but-cheap first**, never **wrong-and-final**.

### 4d. Refining the maintainer's "~100k threshold" — explicitly

The maintainer proposed *"fan-out preferred unless it would likely cost >~100k tokens."* Two
refinements, both evidence-driven:

- **Flip the polarity.** "Fan-out preferred unless expensive" makes the **15× mode the default** —
  which spends 15× on questions a full-read or passage pull answers, and contradicts the Adaptive-RAG /
  Self-RAG result that cheap-first recovers expensive-quality at a fraction of cost (§3c). **Cheap-first
  with escalation** is the better default. Reach for fan-out as the **escalation for breadth that won't
  fit**, not the baseline.
- **Re-key the number from absolute to relative, and add the independence gate.** "~100k" is a fine
  *order of magnitude* for "**this set won't fit, stop trying to read it whole**" — but it should be
  **a fraction of the live remaining window** (≈ "`E` approaches `R`"), because the budget is the
  injected model's, not a constant, and because the same 100k means very different things at turn 1
  vs turn 8 of a long thread. And the trigger to fan out (rather than fall to passages) is
  **independence/parallelizability**, per Anthropic's own win-condition — *size alone is necessary but
  not sufficient*. So the refined rule is: **read-in-full while `E` fits (≲½R, with ~85k as a concrete
  anchor under a 170k floor); when `E` exceeds the window, fan out IF the work is independent, else
  retrieve passages; escalate on a coverage self-check.** The maintainer's instinct (a token threshold
  gates the expensive mode) is *correct*; the refinement is *which* threshold (relative, not 100k
  absolute) and *which* expensive mode it gates *into* (fan-out only if parallelizable).

### 4e. Worked example — "audit rights across the deal" (use case 2)

*Setup:* matter with ~40 documents; L1 map + L2 hybrid narrow to **K = 9 candidates** plausibly
touching audit/inspection/records-access (the map's descriptions + a dense pass catch the paraphrases
FTS alone would miss — scale doc §3b).

- **Pre-flight:** `est_read_tokens` over the 9 → say their `character_count`s sum, capped per-doc at
  40k, to **~150k chars ≈ ~38k tokens**. Remaining budget `R ≈ 140k` at turn start.
- **Apply the rule:** it's a **meaning/comparison** question (not a lookup) → not mode a by default.
  `E ≈ 38k ≤ ½R (~70k)` and `≤ ~85k` → **mode (b) READ-IN-FULL.** Read the 9 (or the top ~6 by L2 rank)
  in full; reason over whole text; **no audit-rights paraphrase is silently missed**, because every
  candidate is actually read. Total read cost ~38k tokens — comfortable, single-thread, highest
  fidelity. **This is the maintainer's "read the relevant documents in full" — and it's the *cheapest
  correct* mode here, not the expensive one.**
- **If instead K = 30 candidates (~300k tokens):** `E ≫ R`. The question **is** cleanly parallelizable
  ("each document's audit-rights position" is independent per doc) → **mode (c) FAN-OUT:** one subagent
  per document-group, each reads its slice in full and returns "Doc X: audit right = inspection on 30d
  notice, §7.2"; the lead reconciles into one cross-deal answer. Pay the 15× knowingly — this is the
  due-diligence tier where Anthropic says it clears.
- **If instead the question were "trace how the *defined term* 'Audit' flows from the MSA definitions
  through every schedule"** (dependent, cross-referential): even at K=30 this is the **anti-condition**
  for fan-out → stay in **mode (a/b hybrid)**: retrieve the definition + cross-references, read the few
  linking documents in full; escalate only if coverage is thin. Independence, not size, made the call.

The same number (`est_read_tokens`) and the same three branches handle all three shapes — which is the
point: **one cheap signal, one rule, three modes.**

---

## 5. Making the agent self-aware

The maintainer wants the agent to **estimate cost, know its budget, pick, and escalate.** Here is
exactly which signals it needs, and the tool-vs-prose split (the fork's standing doctrine: a
*single-dispatch predicate* is a tool; *method/guidance* is prose — ADR-F034).

### 5a. Signals the model needs (and where each comes from)

1. **Per-document size, in the inventory.** Today `_inventory` renders `- {filename} ({N} pages)`
   (`tools.py:535-555`). Add the char/token estimate: `- {filename} ({N} pages, ~{chars/4//1000}k
   tokens to read)`. **`character_count` is already stored** (`document.py:82`) — this is a one-line
   render change, no schema, no migration. *Effect:* the agent sees the cost of reading each candidate
   **before** it reads, which is the precondition for choosing.
   **This is the single highest-leverage self-awareness change and it is nearly free.**

2. **An `estimate_read_cost` helper tool.** A guarded read-only tool: given a list of filenames (or
   "all candidates"), return `{n_docs, est_tokens, fits_in_remaining_budget: bool, suggestion}`. Body =
   the §4a `SUM(min(character_count, 40_000))/4` + a compare to the live budget. Zero inference, zero $.
   *Why a tool, not prose:* it's a **single-dispatch computation** the model invokes to get a number —
   the textbook tool-gate shape. It makes the pre-flight estimate a *first-class action* with an audit
   row (counts only), not a guess the model does in its head (which it does badly).

3. **Remaining-budget visibility.** The model should know `R`. Two cheap options: (i) the
   `estimate_read_cost` tool returns `remaining_budget_tokens` alongside the estimate (preferred —
   one tool surfaces both halves of the comparison); (ii) a short line in the system prompt stating the
   operating window and that compaction trims at ~170k. The agent doesn't need a live token counter —
   it needs to know the *order of magnitude* it's working within so "this set is ~40k of my ~140k" is a
   judgement it can make. *(Honest limit: exact live remaining is hard to expose mid-turn; an estimate
   is enough for a rung-choosing decision.)*

4. **A coverage/confidence self-check (the escalation trigger).** **Prose, not a tool** for v1: a skill
   instruction — *"after a passage search on a meaning question, ask yourself: did the passages
   actually contain the answer, or am I inferring from their absence? If thin, read the top candidates
   in full before answering."* This is Self-RAG's reflection step ([arXiv 2310.11511](https://arxiv.org/abs/2310.11511)) without a trained classifier. *(A later, optional `assess_retrieval_coverage`
   tool-gate could make it auditable — backlog, §8.)*

### 5b. The strategy itself: PROSE (a skill + prompt doctrine), not an engine

The **policy of §4 is taught, not hard-coded** — consistent with how the fork ships method (surgical-
redline, negotiation-review, deal-review are all SKILL.md craft layers under ADR-F041, no runtime
gate). A `retrieval-strategy` skill (or a section folded into the existing matter skill) teaches:

- the three modes and their cost/quality trade (§2);
- the decision rule keyed on `estimate_read_cost` vs remaining budget (§4c);
- **cheap-first, escalate-on-thin** (§4c.5) — the explicit antidote to silent paraphrase-miss;
- **fan out only for independent/parallelizable breadth that won't fit** — and the explicit
  anti-pattern ("don't fan out a dependent, cross-referential question; don't fan out a set that
  fits — read it");
- the worked shapes of §4e.

**Why prose and not a deterministic router:** (1) The fork has **no post-fan-out / pre-consumption
deterministic hook** — `task` is invoked at the model's discretion and the runner just continues the
model loop (ADR-F034). A *guaranteed* "always estimate then route" flow would require re-introducing
langgraph orchestration (the deferred O-series). (2) Mode choice is genuinely **judgement** (is this
question a lookup? is it parallelizable?) — the same kind of judgement the craft skills already
delegate to the model, with a tool supplying the *facts* (the cost estimate) and prose supplying the
*method*. (3) It matches the published result: Self-RAG/Adaptive-RAG put the *decision* in the model
(reflection tokens / a light classifier), not in rigid control flow. **So: the estimate is a tool; the
budget is a tool-return + a prompt line; the policy and the escalation are prose.**

### 5c. Reuse, not new engine

- **Fan-out = deepagents `task`** — already model-driven, already wired (`composition.py:554`, ADR-F034).
  The strategy layer adds **prose telling the model *when* to use it**, plus the cost number to decide
  with. **Zero new orchestration**, exactly as the C7b roster slice added zero.
- **The brake = R5/R6 + audit** on every tool call (`guard.py`) — `estimate_read_cost` and every read
  flow through it unchanged. **R4 (cost) is where the real gap is** (§6).
- **Reconciliation = `reconcile_positions`** (ADR-F034) already turns lossy fan-out returns into one
  position per head — the strategy layer doesn't re-solve that; it just routes *into* fan-out more
  deliberately.

---

## 6. Guardrails against runaway fan-out

This section is deliberately blunt about a gap the maintainer's framing assumes is closed but **is
not.**

### 6a. What actually stops a run today (verified)

The brakes that **fire in practice** are **step/time caps, not token/cost caps**:

- **`max_steps`** — settled-step ceiling; exceeding it ends the run `cap_exceeded`
  (`runner.py:421,674`). This is the brake that caught the ADR-F015 over-exploration.
- **langgraph `recursion_limit`** — pinned to `max(50, max_steps × 4)` so langgraph's default 25 never
  pre-empts our brakes (`runner.py:64-80,318-320`). A *graph-step* ceiling.
- **Wall-clock timeout** (ADR-F026) — `runner.py:56`.
- **Compaction** — deepagents trims context at ~170k (`factory.py:33`). This **bounds context size**
  but **does not halt** the run or cap *cumulative* token spend; it summarizes and continues.

### 6b. The honest gap: R4 (cost) is a NO-OP

The context for this research describes "a per-tool-call cost cap/halt/grant (R4/R5/R6)." **R5 (halt)
and R6 (grant) are real and enforced** (`guard.py:97-123`). **R4 (cost) is explicitly a no-op:**

> "R4 (cost) — honest no-op: the matter document tools are local Postgres reads with zero marginal
> inference cost. Per-run budgets aggregating gateway routing-log costs are F1 (`cost_usd` NULL until
> then)." — `guard.py:19-22,128-129`

So **there is no per-run *token* or *dollar* budget enforcement anywhere today.** A fan-out that
spawns many subagents, each filling a window, is bounded only by `max_steps` (a *count*, which one
fan-out dispatch can blow past in *tokens* well before it blows past in *steps*) and compaction (which
just summarizes). **This is the single most important guardrail finding in this document, and it must
be stated plainly: the cost brake the maintainer's plan leans on does not yet exist.**

### 6c. The layered guardrail this work should ship

Defense in depth, cheapest first — and **closing 6b is part of it**:

1. **The pre-flight estimate as the *first* guard (cheap, ship now).** Before fanning out, the agent
   (taught by the skill, armed by `estimate_read_cost`) sees that reading the set is ~300k tokens and
   that fan-out is ~15× — and *chooses* not to over-commit. **Prevention beats interdiction**: the
   cheapest way not to blow the budget is to *estimate before spending*. This is prose+tool, no engine.

2. **A fan-out QUOTA (small code, the real new guardrail).** Cap concurrent/total `task` dispatches per
   run (e.g. ≤ N subagents, configurable per area). Today **nothing caps fan-out breadth** except
   `max_steps`. A quota is a single-dispatch predicate → a **tool-gate** on `task` (or a counter
   checked in the guard), the same shape as `reconcile_positions`. This is the direct antidote to the
   ADR-F015 over-exploration: bound the *fan*, not just the *steps*.

3. **Wire R4 into an actual per-run token budget (the deferred real fix).** Aggregate the gateway
   routing-log token/cost per run and **halt at a ceiling** — turning R4 from a no-op into a genuine
   cost brake (the `cost_usd` work `guard.py:21` defers). This is the principled backstop: even if the
   model ignores the estimate and the quota, the run stops at a hard token budget. **Needs the
   routing-log aggregation plumbing — likely its own slice/ADR**; flag it as the honest prerequisite
   for "the agent is cost-safe," not something the strategy skill alone delivers.

4. **Cheap-first defaults (prose).** The skill defaults to passages/full-read and treats fan-out as the
   escalation (§4) — so the expensive mode is entered *deliberately*, not by habit. A fan-out
   shape-miss remains "a finding, not a failure" (ADR-F015) — the guardrails make over-fan-out *rare
   and bounded*, not *impossible*, which is the honest posture on a model-driven substrate.

**Bottom line for the maintainer:** the estimate + quota + cheap-first defaults are shippable now and
make runaway fan-out *unlikely and bounded*. But the *hard* cost stop (R4) is **not built** — the plan
should either fund that slice or accept that "cost-safe" rests on the model honoring the estimate +
the step/quota caps, not on a token budget. Saying otherwise would overstate the current safety.

---

## 7. How it composes with L1/L2/L3 and conversations

### 7a. The strategy layer sits between the funnel and consumption

```
USER QUESTION
   │
   ├─ L1 MAP        : 1000 → K relevant documents (descriptions as router signal)   [discovery doc]
   ├─ L2 HYBRID     : rank passages/docs within K (local dense + FTS + rerank)      [scale doc]
   │
   ▼
 ★ STRATEGY-SELECTION (THIS DOC) ★
   pre-flight estimate (Σ character_count → tokens) vs remaining budget
   → choose:  (a) passages  |  (b) read-in-full  |  (c) fan-out      (+ escalate on coverage)
   │
   ▼
 L3 WITHIN-DOC NAV : inside a chosen big doc, read_document / in-doc FTS / (later) section map
```

The funnel is **upstream and unchanged**; this layer is the **router on its output**. Crucially, the
strategy layer is *why L2 is not the whole story*: L2 hands up ranked passages *and* ranked docs *and*
sizes — and the strategy layer decides whether to consume the passages (mode a) or escalate to reading
the ranked docs whole (mode b) or fanning out over them (mode c). **L2's ranked-DOCS output (scale doc
§7) is the input the strategy layer reads; L2's passages are just mode (a)'s payload.**

### 7b. It applies to CONVERSATION retrieval too — same three modes

The parallel research (`conversations-as-retrievable-knowledge-and-upstream-awareness.md`) establishes
that retrieval must span **documents + conversations + distilled memory**, and that the agent path
already does multi-turn via the langgraph checkpointer (window-replay of the *current* thread), while
**cross-thread semantic conversation retrieval is the open need**. The three modes map **directly**:

- **(a) passages → retrieve TURNS:** dense/FTS over past conversation turns, pull the top-k relevant
  exchanges. Cheap; same silent-paraphrase-miss risk.
- **(b) read-in-full → read a whole THREAD:** when a prior thread is in-scope and fits, replay it whole
  (the checkpointer already does this for the *current* thread; the strategy is "which *other* threads
  to read whole"). The `est_read_tokens` math applies to a thread's serialized turns just as to a
  document's `character_count`.
- **(c) fan-out → subagents over THREADS:** "summarize each of these 8 past matters' position on the
  indemnity ask" is the conversation analogue of the deal-document fan-out — independent, parallelizable,
  fan-out-shaped.

The same decision rule, the same pre-flight estimate (serialized-turn chars / 4), the same cheap-first
escalation. **One strategy layer governs both corpora** — which is the unifying point the conversation
doc's §"the embedding/index strategy must span documents + conversations + distilled memory" was
reaching toward. The distilled memory tier (the matter wiki, ≤16k chars, always injected) is the
*already-consumed* layer — it's the cheapest rung of all (pre-summarized), and the strategy layer reads
*it* first before deciding whether to retrieve/read/fan-out the raw corpora behind it.

### 7c. Budget competition (the honest cross-doc constraint)

Retrieved conversation turns, retrieved document passages, full-read documents, **and** the always-
injected tiers (client context, matter wiki, corrections, roster — `composition.py:218-254`) all
**compete for the same ~170k post-compaction floor**. The pre-flight estimate must therefore account
for what's *already* injected, not just the candidate reads (§4b's `R`). This is exactly the open
question the conversation doc raised ("retrieved conversation turns compete for the same context budget
as documents and the injected distilled tier") — and the strategy layer is where it gets *resolved*: by
estimating total committed tokens before choosing how much *more* to pull.

---

## 8. Recommended decomposition

Vertical slices, dependency-ordered, ≤2–3 days each, one PR each — **folded into the prior plan**
(scale doc: Slice A wire hybrid → B coverage signal → C local embeddings → D rerank → E enrichment;
discovery doc: documents-map slices). The strategy layer's slices **interleave** with those.
**Next fork ADR is F049** (highest accepted F048); **next migration 0078** (highest applied 0077).

### Cheap wins (prose + tiny code, no migration)

- **Slice S1 — Per-doc size in the inventory (one-line render, no schema, no ADR).** Render the
  token-to-read estimate in `_inventory` (`tools.py:535-555`) from the stored `character_count`
  (`document.py:82`): `- {file} ({N} pages, ~{k} tokens to read)`. **Highest leverage per byte of
  diff** — it's the precondition for the agent choosing at all. Folds the standard security +
  simplification pass. *Ships independently of everything else.*

- **Slice S2 — `estimate_read_cost` helper tool (small code, no migration, no schema).** A guarded
  read-only tool returning `{n_docs, est_tokens, remaining_budget_tokens, fits, suggestion}` over a
  candidate filename list (§5a.2) — `SUM(min(character_count,40_000))/4` + budget compare. Zero
  inference. Add to `MATTER_TOOL_NAMES`. *Depends on nothing; pairs with S1.*

- **Slice S3 — The retrieval-strategy SKILL / prompt doctrine (prose; **ADR-F049 drafted here**).**
  A `retrieval-strategy` skill (or a section in the matter skill, ADR-F041 craft pattern) teaching the
  three modes, the decision rule (§4), cheap-first escalation, and the fan-out anti-patterns. **Needs
  ADR-F049 ("retrieval-strategy-selection: the three consumption modes + the cost-aware router")**
  because it makes the architectural call that mode-selection is *prose+a cost tool*, not a
  deterministic engine, and records the refined threshold and the cheap-first-not-fan-out-first
  default. *Depends on S2 (the skill references the tool). Implementation is prose; the ADR is the
  durable artifact.*

### Guardrails (the real new safety — sequence deliberately)

- **Slice S4 — Fan-out quota (small code; ADR-F049 covers it or a thin addendum).** Cap total/concurrent
  `task` dispatches per run, configurable per area, enforced as a tool-gate/counter in the guard (§6c.2).
  The direct, shippable antidote to ADR-F015 over-exploration. *Depends on nothing; ship alongside S3.*

- **Slice S5 — R4 as a real per-run token budget (its OWN slice + ADR; the deferred hard stop).**
  Aggregate gateway routing-log tokens/cost per run; halt at a ceiling (§6c.3) — turning `guard.py`'s
  R4 no-op into a genuine cost brake (`cost_usd`, deferred since F0-S4). **This is larger** (routing-log
  aggregation plumbing) and is the honest prerequisite for claiming "cost-safe." *Separate ADR; sequence
  after the cheap-wins prove the behaviour, but do not pretend the cheap-wins make the run cost-bounded
  without it.*

### Later / optional

- **Slice S6 — `assess_retrieval_coverage` tool-gate (optional, after S3).** Promote the prose coverage
  self-check (§5a.4) to an auditable single-dispatch tool that records a counts-only receipt when the
  agent escalates cheap→expensive. Makes escalation *observable*; not required for v1.

- **Backlog (gated on measurement) — a recall/coverage eval on our corpus.** The "passages silently
  miss paraphrase" and "fan-out beats full-read on breadth" claims are **argued, not measured** here
  (§9). A small labelled eval (corpus questions × known-relevant docs, run across modes) converts the
  policy thresholds (½R, ~85k, the independence heuristic) from defensible rules of thumb into numbers.
  Ship it with Slice C (local embeddings) of the scale plan, which already proposed a recall eval.

**Prose-only:** S3 (skill/doctrine), the escalation overlay. **Needs code:** S1 (render), S2 (estimate
tool), S4 (quota), S5 (R4 budget), S6 (coverage gate). **Needs an ADR:** S3 draws **F049** (the
strategy-selection decision); S5 needs its own (the cost-budget enforcement is a distinct architectural
call). **No migration** for S1–S4/S6 (all read already-stored data or add prose/guards); S5's routing-
log aggregation may need one. **Triggers:** S1+S2+S3+S4 ship as soon as the funnel (scale doc Slice A)
lands — they are the strategy layer the funnel was built to feed; S5 triggers when a real matter's
fan-out spend needs a hard ceiling (or proactively, since R4 is the named gap); the eval triggers with
local embeddings.

**Dependency order:** (scale doc A wire-hybrid) → **S1 ∥ S2** → **S3** [ADR-F049] ∥ **S4** → **S5**
[own ADR] → S6; eval with scale-doc C.

---

## 9. Open questions for the maintainer

1. **Default mode — confirm cheap-first, not fan-out-first?** The evidence (Adaptive-RAG / Self-RAG /
   the 15× cost) says **start cheap, escalate on need** beats "fan-out unless expensive." This *inverts*
   the polarity of your "fan-out preferred unless >100k" instinct (while keeping its substance: a token
   threshold gates the expensive mode). **Accept cheap-first-with-escalation as the default, or do you
   want fan-out genuinely preferred for the due-diligence tier (where Anthropic says the 15× clears)?**

2. **The thresholds — relative-to-budget, or a fixed number you can reason about?** I recommend keying
   read-in-full on **`E ≤ ½R` with ~85k as a concrete anchor** (under a 170k floor) and fanning out only
   when `E > R` **and** the work is independent. Your "~100k" is a fine order of magnitude for "won't
   fit." **Do you want the *relative* rule (adapts to the injected model + thread length), or a fixed
   token cut (simpler to predict, wrong as the model/thread changes)?** And **what fraction** — ½ is a
   guess balancing fidelity against lost-in-the-middle; it's untuned.

3. **Fan-out quota — what N, and per-area or global?** §6c.2 caps `task` breadth (the real ADR-F015
   antidote). **What's the default cap (≤3? ≤5?), and should it be per-practice-area config** (Disputes
   discovery may want more breadth than a Commercial redline)?

4. **Model-self-select vs deterministic policy.** I recommend **model-self-select** (prose skill + a
   cost *tool*), because (a) the substrate has no pre-consumption deterministic hook (ADR-F034) and (b)
   mode-choice is judgement. The alternative — a deterministic router that *forces* the mode from the
   estimate — needs the deferred O-series langgraph orchestration. **Accept model-self-select-with-a-
   cost-tool, or do you want the deterministic router on the roadmap (and the O-series prerequisite
   funded)?**

5. **The R4 gap — fund the hard cost stop now, or accept bounded-by-estimate-and-steps for now?** Be
   clear-eyed: **R4 is a no-op today** (§6b); the only real brakes are step/time caps + compaction.
   The cheap-wins (estimate + quota + cheap-first) make runaway fan-out *unlikely and bounded* but not
   *impossible*. **Do you want Slice S5 (R4 as a real per-run token budget) funded as part of this work,
   or is "the model honors the estimate, bounded by max_steps + a fan-out quota" acceptable until a real
   matter forces the issue?** (My recommendation: ship the cheap-wins now; schedule S5 next — but don't
   *claim* cost-safety until S5 lands.)

6. **Per-area tuning.** Thresholds and the default mode plausibly differ by practice area — Disputes
   (broad discovery, fan-out-friendly) vs Commercial (focused redline, read-in-full-friendly) vs Privacy
   (ROPA population, structured fan-out). **Tune the policy per area in their `profile_md`/skill (more
   work, better fit), or one global policy to start (simpler, calibrate later)?**

7. **Coverage self-check — prose now, tool later?** §5a.4 starts the escalation trigger as a prose
   instruction (Self-RAG-style) and proposes an optional `assess_retrieval_coverage` tool-gate (S6) to
   make it auditable. **Prose-only for v1 (cheaper, model-driven), or do you want the auditable tool
   from the outset because "the agent escalated because retrieval was thin" is a receipt worth keeping?**

---

### Honest limits of this dossier

- **The cost cap R4 is a no-op today** (`guard.py:19-22,128-129`) — the guardrail story (§6) is built on
  step/time caps + compaction + the *proposed* estimate/quota, not an existing token budget. Stated
  plainly because the research brief assumed R4 already enforces cost; it does not.
- **No measured quality on our corpus.** "Passages silently miss paraphrase" (§2a, §3c) and "fan-out
  beats full-read on breadth" (§3b) are the lexical-vs-dense structural argument + cited research
  (Anthropic/Adaptive-RAG/Liu et al.), **not** a labelled retrieval eval on this fork's documents —
  the same gap the scale doc flagged. The thresholds in §4 (½R, ~85k, the independence heuristic) are
  **defensible rules of thumb to calibrate, not laws** (backlog eval, §8).
- **Fan-out's win-condition is established on research/browse tasks** ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)); transfer to *legal meaning-extraction over a deal*
  is argued from the mechanism (parallel independent reads), not measured. The anti-condition
  (dependent/cross-referential questions) is the honest counterweight and is built into the rule (§4c.3).
- **The pre-flight estimate is approximate.** `character_count / 4` is a tokenizer-agnostic estimate;
  legal text tokenizes slightly denser, and the per-doc 40k cap means the estimate *understates* the
  information in a truncated big doc (which is itself a signal to prefer passages for that doc). Good
  enough to *choose a rung*; not a billing-grade number.
- **Latency figures are directional.** Fan-out's parallel-wall-clock advantage depends on subagent
  concurrency the runner permits; "tens of ms" for retrieval is the local-rerank figure from the scale
  doc, not measured on our hardware.
- **The strategy layer presumes the funnel.** Everything here assumes scale-doc Slice A (wire the
  hybrid retriever) and the documents map land — without L1/L2 narrowing first, "choose a consumption
  mode over K candidates" has no K. This doc is explicitly the layer *above* that work, not a substitute
  for it.
