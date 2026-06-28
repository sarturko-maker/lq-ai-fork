# Research — When to fan out subagents for document knowledge work (vs code)

**For:** the upcoming **Phase-3 "strategy-selection + R4 token-budget" slice** (the §6 deferral in
[`retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md`](retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md)).
This note reframes the **E1 / A7 finding** — our DeepSeek agent did **not** autonomously fan out on a
bounded 4-doc legal-review task, even though the `task` tool + subagents were wired and it delegates when
coached; the masked judge rated inline synthesis appropriate (**8/10**), so the open question is **fan out
at the RIGHT TIME**, not *whether it can*.

**Method:** synthesis of parallel research sweeps (SOTA-pro, SOTA-con, document-specific) + cross-check
against the fork's own code seams and prior arc. The **harness-landscape sweep did not return structured
findings**, so §4's table is compiled from the synthesis model's knowledge + **targeted spot-verification**
(opencode's agent docs and the internal cross-refs/code seams were confirmed on 2026-06-28; closed-harness
internals remain **VERIFY** — §7). **Date:** 2026-06-28.
**Posture reminders baked in:** all LLM calls route through the gateway (sole egress, ADR-F010); every
tool dispatch goes through `guarded_tool_call` (R5/R6 enforced, **R4 is a no-op today** — `guard.py`);
fan-out is **deepagents-native + model-driven** with **zero** orchestration scaffolding (ADR-F034); a
fan-out shape-miss is **"a finding, not a failure"** (ADR-F015).

**Relationship to the existing arc:** the [retrieval-strategy doc](retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md)
already settled the **cost ladder** (cheap-retrieve → read-in-full → fan-out) and the **pre-flight
estimate vs remaining budget** rule. This note does **not** restate that. It adds the three things that
doc did not cover: **(1)** *why document work decomposes differently from code*, **(2)** *how other
agent harnesses expose/decide delegation*, and **(3)** *how to turn the A7 finding into an eval-gated
"right-time" signal* for the Phase-3 slice.

---

## 1. TL;DR — when should a document-work agent fan out?

- **Fan out for breadth, stay inline for synthesis.** The cross-source consensus is a **READ/WRITE
  split**: parallel subagents win at *gathering/reading/extracting* independent facts across many
  sources, and degrade sharply on *coupled writing/synthesis* where conflicting implicit choices
  produce incoherent output ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system),
  [Cognition](https://cognition.com/blog/dont-build-multi-agents)). For a legal matter: fan out the
  **extraction** (one reader-extractor per document), keep the **reconciliation/drafting** single-minded.

- **The real trigger is corpus-vs-window AND independent-sub-question count — not document count.**
  Fan out when the relevant evidence **exceeds one (effective) context window** *and* decomposes into
  genuinely **independent** reads; a handful of docs that fit in one window should **not** be fanned out
  (single-mind wins on cost, latency, fidelity, and avoids merge-induced loss).

- **A7's inline answer was CORRECT for a 4-doc task.** Fanning out a bounded set that fits the window
  buys ~**15× tokens** ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system))
  and, on document benchmarks, **near-zero accuracy** (+0.014 F1 for ~1.84× speed —
  [financial-doc benchmark](https://arxiv.org/html/2603.22651)). The judge was right; A7 measures the
  **wrong-time** miss, not a capability gap. The gap to close is **the agent recognising the large-corpus
  regime where inline *should* fail.**

- **Document work ≠ code.** Code's seams are structural and **interdependent** (a change in one module
  breaks another) — which is why even Anthropic keeps coding single-minded. Document work splits on a
  **LOCAL vs GLOBAL** axis: per-doc extraction is embarrassingly parallel ("local"); cross-doc
  reconciliation of cross-references is "global" and needs one mind ([GraphRAG](https://www.themoonlight.io/en/review/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization)).

- **Make the right-time choice model-autonomous (doctrine nudge) with a harness-enforced ceiling.** A
  prompt/skill doctrine ("estimate the corpus; fan out only when it won't fit and splits cleanly")
  guides *when*; a **fan-out quota + a real R4 token budget** bounds the blast radius if the model
  over- or under-reaches. Doctrine for *judgment*, the brake for *safety* — never the brake for *taste*.

- **Eval-gate it like everything else in F2.** Extend Track-A with a **large-corpus A7 variant where
  inline must fail and fan-out must win**, alongside the existing **small-corpus A7 where inline is
  correct and fan-out is wasteful**. "Fanned out at the right time" is a *measurable* property; the
  Phase-3 slice must move a number, not assert a vibe (ADR-F015 / ADR-F049 eval-first).

---

## 2. SOTA: when fan-out helps vs hurts

### The pro case — orchestrator-worker for breadth-first, read-heavy work

The strongest production datapoint is Anthropic's Research system: a lead agent fans out 3–5 subagents,
each in its **own context window**, to pursue **independent directions in parallel**. Their
multi-agent setup beat single-agent Opus 4 by **90.2%** on an internal research eval and cut research
time up to **90%** on complex queries; the win-condition is explicitly *"breadth-first queries that
involve pursuing multiple independent directions simultaneously"* and tasks whose evidence *"exceeds a
single context window"*
([How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)).
The mechanism that matters for documents: **subagents are context compressors** — each reads its slice
and returns only the *condensed* tokens, so the lead never holds raw text. The established
document-pipeline shape mirrors this exactly: **per-document parallel extraction → one cross-document
synthesizer** that consolidates patterns and conflicts (literature-synthesis and DD systems —
[ResearchPilot / ARCADE class](https://arxiv.org/html/2603.22651), and the legal-DD analogue at
[Harvey M&A DD](https://www.harvey.ai/blog/ai-due-diligence-for-m-and-a): per-clause NLP across every
contract, then cross-document pattern recognition, e.g. "12 of 500 contracts have change-of-control
termination = 28% of revenue").

Anthropic's **effort tiers** are the concrete dial: *simple fact-finding = 1 agent, 3–10 tool calls;
direct comparison = 2–4 subagents; complex research = 10+ subagents with divided responsibilities.*
And decomposition must be **explicit** — each subagent needs an objective, an output format, allowed
tools/sources, and **disjoint** boundaries, or subagents duplicate work.

### The counter case — context fragmentation, one mind for synthesis

Cognition's *Don't Build Multi-Agents* is the sharpest objection, on two principles: **(1)** share full
context/traces, not isolated messages; **(2)** *actions carry implicit decisions, and conflicting
decisions carry bad results.* Their Flappy-Bird example — one subagent builds a Mario-style background,
another a mismatched bird, and the assembler cannot reconcile two miscommunications — is the
**document analogue** of a legal opinion where each subagent makes its own implicit interpretive choice
(how to read a defined term, which clause governs) that no downstream assembler can reliably reconcile
([Cognition](https://cognition.com/blog/dont-build-multi-agents)). Their **refined** position softened
but kept the core rule: multi-agent works today only when **writes stay single-threaded** and extra
agents *"contribute intelligence rather than actions"*
([Multi-Agents: What's Actually Working](https://cognition.com/blog/multi-agents-working)).

The empirical counterweight: *Towards a Science of Scaling Agent Systems* (Google DeepMind/MIT,
[arXiv 2512.08296](https://arxiv.org/abs/2512.08296), **cited via secondary summary —
[VERIFY against the primary](https://dev.to/ai_agent_digest/more-agents-worse-results-google-just-proved-that-multi-agent-scaling-is-a-myth-59b9)**)
reports multi-agent **degrading sequential/dependent tasks by up to 70%**, ~**5× worse token
efficiency**, and a usable gate: **once a single agent already exceeds ~45% accuracy, adding agents
tends to hurt.** And the Berkeley **MAST** study ([arXiv 2503.13657](https://arxiv.org/abs/2503.13657))
finds most multi-agent failures are **coordination/design failures, not capability failures** — step
repetition (17%), spec disobedience, information withholding, missing verification (~13%); a multi-level
**verification pass** bought **+15.6%**. Even Anthropic states the boundary: domains *"requiring all
agents to share the same context or involving many dependencies between agents are not a good fit."*

### The reconciliation

The two camps are not in conflict once you split by **phase**: **research/extraction** (independent
breadth) parallelizes; **synthesis** (dependent reconciliation) does not. "Never fan out" is too strong;
"always fan out" is 15× waste. The precise rule is **phase-specific** — fan out breadth, single-mind the
synthesis — plus a **verification/reconciliation pass** because that is the highest-leverage fix and the
top measured failure mode.

---

## 3. Document knowledge work ≠ code

Code and documents both decompose, but along different axes:

| | **Code** | **Document knowledge work** |
|---|---|---|
| Natural seams | files, modules, tests — pre-existing, structural | documents, clauses, fact-types |
| Default coupling | **interdependent** (a change ripples; shared schema/interface/state) | **mixed** — per-doc extraction independent; cross-doc synthesis dependent |
| Global consistency check | the **compiler / test suite** provides it for free | a **human or one synthesizing mind** must provide it |
| Decomposition axis | structural (which file) | **LOCAL vs GLOBAL** (this clause vs the whole corpus) |
| Fan-out verdict | mostly single-minded — *"fewer truly parallelizable subtasks than research"* ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)) | **fan out extraction, single-mind synthesis** |

**The LOCAL/GLOBAL axis is the document-specific insight.** "What is the indemnity cap in contract X?"
is **local** — answerable from one region, embarrassingly parallel across documents. "Across all 200
vendor contracts, which change-of-control clauses trigger on this deal and what % of revenue do they
cover?" is **global** — it needs one mind seeing the full extracted set, and naive per-chunk fan-out
demonstrably fails on it because retrieval is *locally biased and cannot guarantee whole-corpus
coverage* ([GraphRAG](https://www.themoonlight.io/en/review/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization)).
Code has no clean analogue: code is almost all "local" edits with a mechanical global check (the
compiler); documents have aggregate risks that are **only visible across the full set** and have **no
mechanical check** — the synthesis mind *is* the check.

**The real triggers (not document count):**

1. **Corpus vs EFFECTIVE context window.** "Effective" windows are far smaller than advertised and
   degrade with the **number of distinct elements** being tracked — exactly the legal-synthesis case.
   Thomson Reuters (legal): effective windows *"are often much smaller than their available context
   window"*, and complex multi-element tracking *"struggles with recall to a greater degree"*; "lost in
   the middle" drops >30% when the answer sits mid-context
   ([TR legal long-context benchmark](https://www.thomsonreuters.com/en-us/posts/innovation/legal-ai-benchmarking-evaluating-long-context-performance-for-llms/)).
   So **"it fits in the window" ≠ "it will be reasoned over reliably."**

2. **Count of genuinely INDEPENDENT sub-questions/documents.** Fan-out's win-condition is parallelizable
   breadth, not raw size. If sub-question B needs A's output, parallelism degenerates into expensive
   serial execution ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)).

3. **Task value vs the ~15× token cost.** High-stakes DD over a data room clears the bar; a quick 2–3
   doc lookup does not.

**The legal-matter angle — a few docs vs hundreds:**

- **Small matter** (an NDA review, an MSA pair — fits ~one window): **single agent, single context,
  no fan-out, often no RAG.** Single-mind wins on cost/latency/fidelity; adding agents *regresses*
  accuracy once a single agent already does the job (returns plateau ~4 agents). **This is the A7
  4-doc case — inline was correct.**
- **Large matter** (dozens–hundreds of contracts, a data room): **two-phase** — *map* (parallel
  per-document extraction into **typed facts + citations**) then *reduce* (one synthesizing mind reads
  the **artifacts**, not raw text or summaries-of-summaries). Feeding the reduce stage durable
  structured facts (not lossy NL re-summaries) keeps its effective context small and dodges
  "lost in the middle" — and **mirrors the fork's own bi-temporal fact ledger** (C3b-1): fan-out
  writes typed facts, the reduce reads the ledger, not 200 free-text blobs.
- **A single long agreement** whose later clauses depend on earlier ones (definitions, amendments,
  schedules) is **refine/sequential**, not fan-out — chunk-level fan-out would sever the
  cross-references ([Map-Reduce vs Refine](https://www.toolify.ai/ai-news/langchain-summarization-mapreduce-vs-refine-methods-3395910)).

---

## 4. Harness review — how other agents expose and decide delegation

How the document/code agent ecosystem handles "should I spawn a subagent?" — to calibrate where the
fork sits. (Public behavior / docs as of mid-2026; **the deeper internals of closed harnesses (Devin,
Claude Code) are VERIFY** — only published behavior is reflected.)

| Harness | Autonomous vs orchestrated fan-out | How delegation is exposed | When-to-delegate guidance |
|---|---|---|---|
| **opencode** | Model-autonomous (primary→subagent via the Task tool) + `@`-mention; `primary`/`subagent`/`all` modes ([docs](https://opencode.ai/docs/agents/)) | `task` tool gated by `permission.task`; each subagent runs in its own context/session, possibly a different LLM | Model discretion + per-agent config; **now adding call-budgets + depth-limits** for subagent→subagent delegation ([PR #7756](https://github.com/sst/opencode/pull/7756)) — independent corroboration of the §5 quota brake |
| **Claude Code** (public) | **Model-autonomous** via the **Task tool**; subagents have isolated context | Task tool spawns a subagent; `.claude/agents/*` define named subagents (description-routed); output returns as one result | Doctrine in the system prompt/subagent descriptions; lead decides — *this is the fork's substrate model* (deepagents `task`) |
| **Aider** | **Single-agent, no fan-out** | Pair-programming edit loop (architect/editor *modes*, not parallel agents) | N/A — deliberately single-minded; the "code is interdependent → single mind" stance in product form |
| **OpenHands** (ex-OpenDevin) | Mostly single-agent loop; **delegation is orchestrated** (explicit delegate action / micro-agents) | A delegate/sub-agent action in the event stream; specialized micro-agents | Triggered by the controller/agent rules, not a free cost-gated choice — **VERIFY current state** |
| **Cline / Roo** | Single-agent edit loop; Roo adds **modes** + an explicit "new task"/subtask hand-off | Mode switching + a subtask tool (Roo "Boomerang"/orchestrator mode) | User/mode-driven orchestration more than autonomous cost gating |
| **Devin** | **Orchestrated/managed** — a planned, multi-step autonomous engineer; parallel "Devins" are user-spawned | Plan + managed execution; parallelism is product-level (run multiple Devins), not in-task model fan-out | Proprietary planner decides; **internals VERIFY** |
| **smolagents** (HF) | **Both** — code-agents single by default; **managed-agents** = explicit hierarchical fan-out | `ManagedAgent` wraps a worker; a manager agent calls it as a tool | Library leaves the policy to the builder; docs caution managed-agents add cost/complexity — use when subtasks are separable |
| **Claude Agent SDK** | **Both** — single-agent default; **subagents** are a first-class primitive | Subagent definitions + a Task tool; isolated context per subagent; programmable orchestration | SDK gives the primitive + guidance ("subagents for parallelizable, context-isolating work"); policy is the builder's |
| **deepagents / LangGraph** | **Model-autonomous** `task` tool (deepagents) **or** graph-orchestrated (LangGraph) | deepagents: built-in `task` sub-agent tool, model-driven, lossy single-`ToolMessage` return; LangGraph: explicit supervisor/worker graph | deepagents: lead decides at discretion; LangGraph: you encode the policy in the graph — **the two ends of the autonomy spectrum** |

**Our approach (publicly documented model only):** we are on the **Claude-Code / deepagents
model-autonomous end** — fan-out is the deepagents-native `task` tool, model-driven, with **zero
orchestration scaffolding added** (ADR-F034). Subagent steps nest under the dispatch via
`parent_step_id` and stream to the UI. The subagent return is **lossy** (deepagents collapses the run
into one `ToolMessage`), and a *guaranteed* "always reconcile before emit" flow **cannot** be built on
this substrate without re-introducing LangGraph orchestration (the deferred O-series) — so C7b shipped
reconciliation as a **single-dispatch tool gate** (coached), not a deterministic flow. **Takeaway from
the table:** the harnesses cluster into *model-autonomous* (opencode, Claude Code, deepagents `task`)
vs *orchestrated* (LangGraph graphs, Devin, OpenHands delegation). The fork is firmly model-autonomous —
which means **the "when" lives in doctrine + a brake, not in a planner.** That is the right axis for
Phase-3 to work on.

---

## 5. A decision framework for LQ.AI

### The signals (what the agent should weigh, in order)

1. **Pre-flight corpus estimate (free, zero inference).** Sum the candidate set's stored
   `character_count` (`document.py:82`) ÷ ~4 → tokens, compared to the **live remaining budget `R`**
   (post-compaction floor ~170k minus prompt/reasoning/output headroom — see the strategy doc §4).
   This is a local Postgres `SUM`; it already exists as a design.
2. **Fits-the-window test.** If `est ≲ ~half of R` → **read-in-full, single mind, no fan-out** (the
   small-matter / A7 case). If `est >> R` → the window is the constraint → consider fan-out.
3. **Independence test.** Fan out **only if** the over-window set **decomposes into independent reads**
   (per-document extraction, disjoint clause-types). If the sub-questions are coupled / sequential →
   it's a *global synthesis* task → **do not fan out the synthesis**; if it's also over-window, narrow
   first (map/hybrid retrieval) then single-mind the reduce.
4. **Task type — extract vs synthesise.** `extract/find X across N docs` → fan-out candidate.
   `reconcile / what conflicts / aggregate exposure across the set` → single mind, always.
5. **Value gate.** Reserve the ~15× cost for high-stakes matters where breadth genuinely exceeds one
   mind's reliable reach.

### Model-autonomous (doctrine nudge) **and** harness-enforced (quota + R4) — both

This is the load-bearing design call, and the answer is **both layers, with distinct jobs**:

- **Doctrine nudge = the "when" (judgment).** Put the framework above into the practice-area agent's
  prompt/skill as readable prose: *"Estimate the candidate corpus. If it fits the window, read it in
  one mind. Fan out only when it won't fit AND splits into independent reads. Never fan out the final
  synthesis — one mind reconciles."* This is the **right primary lever** because (a) the fork is on the
  model-autonomous substrate (§4), (b) the choice is genuinely contextual judgment, and (c) ADR-F015
  treats a shape-miss as a *finding*, not a *failure* — a brake that *forces* fan-out would be taste
  enforced by code, which we explicitly reject.
- **Harness-enforced = the "how much" (safety ceiling).** Two brakes bound the blast radius:
  - **A fan-out QUOTA** — a single-dispatch tool-gate on `task` (the C5a `evaluate_*` gate shape)
    capping total/concurrent subagent dispatches per run. Small code, real guardrail; stops a runaway
    fan-out loop the step cap would let run long. (Strategy doc §6c.2, Slice S4.)
  - **R4 as a real per-run token budget** — the **honest gap**: R4 is a documented **no-op** today
    (`guard.py`); the only brakes that fire are `max_steps` / `recursion_limit` / wall-clock (*step*
    caps, not *cost*). Aggregating gateway routing-log tokens/cost per run and halting at a ceiling is
    the deferred hard stop (strategy doc §6b, Slice S5) — its **own slice + ADR**.

  **Division of labour:** doctrine decides *whether/when* to fan out; the quota + R4 ensure that even if
  the model misjudges (over-fans a small matter, or loops), the run is **bounded and cannot run away**.
  Doctrine for taste, brake for safety — never the reverse.

### How this ties to A7

A7 froze at **0/10 autonomous fan-out, judged inline-appropriate (8/10 grounding)** on a **4-doc**
matter ([E1 baseline](../evidence/retrieval-eval/track-a/), MILESTONES E1 line). Read through this
framework, **that is the framework working, not failing**: 4 docs fit one window (signal 2 → read
inline), and the masked judge confirmed inline synthesis was right. A7 is the **small-matter control**.
What it **cannot** tell us is whether the agent would *escalate* in the large-matter regime — the case
the doctrine is actually for. So A7's role in Phase-3 is twofold: it is the **"don't over-fan-out"
guard** (inline must stay correct when the corpus fits), and it **defines the missing scenario** — a
large-corpus variant where inline *should* fail. The Phase-3 slice's success metric is **moving the
large-corpus variant from inline-fail to fan-out-win while keeping A7-small at inline-correct.**

---

## 6. How to MEASURE it (Track-A extension)

"Fanned out at the right time" is a **two-sided** property — fan out when you should, *and* don't when
you shouldn't. Track-A already has the masked-judge substrate (E1: `track_a_lib.py`, masked packet,
deterministic `_task_strategy` enum). Extend it with a **paired A7** so the Phase-3 slice is eval-gated
like everything else in F2 (ADR-F049 eval-first):

| Scenario | Seeds | Inline expectation | Fan-out expectation | "Right-time" verdict |
|---|---|---|---|---|
| **A7-small** (the shipped A7) | 3–4 docs, fits one window | **PASS** — complete, grounded inline | **WASTEFUL** — 15× tokens, no quality gain | inline-correct; fan-out is the *wrong* time |
| **A7-large** (NEW) | 30–100+ docs / >window total `character_count`, distinct fact per doc, breadth question | **FAIL** — inline misses docs (coverage gap, "lost in the middle") | **WIN** — per-doc extraction covers the set | fan-out-correct; inline is the *wrong* time |
| **A7-coupled** (NEW, optional) | over-window but a *global* reconciliation question (conflicting clauses across the set) | **FAIL** — too big for one read | **FAN-OUT-THEN-SYNTHESISE** — parallel extract, single-mind reduce; *parallel-write must lose* | fan out *extraction* only; synthesis stays single-mind |

**Metrics (mostly free, deterministic — the L1 layer):**

- **`_task_strategy` enum** (already in `evals.scoring`): did `task` fire, and with what breadth, per
  variant. **Right-time = `none` on A7-small, `partition`/`one_per_item` on A7-large.**
- **Doc-level coverage** (E1 mechanism): did the right *filenames* enter the timeline? On A7-large,
  inline should miss documents; fan-out should hit (near-)all. This is the **objective discriminator**
  that makes "inline fails at scale" measurable without a judge.
- **Pre-flight estimate vs actual** (free): log the `Σ character_count → tokens` estimate and whether
  the chosen strategy matched the framework's prescription. This directly scores the **doctrine**.
- **Token/cost per run** (gateway routing-log, the same accounting f0-s9 used): quantify the **15× tax**
  on A7-small if it over-fans, and confirm A7-large's fan-out clears the value gate.
- **Masked-judge substance** (Claude primary, `deepseek-pro` fallback — E1 architecture): grounding +
  honest-coverage on the *visible answer*, judge blind to docs/prompt/run_id (no grading by leakage).

**Gating shape (ADR-F015):** record rates as **findings**, no a-priori pass-bars this slice; the
"right-time" pass-bar (e.g. A7-small `_task_strategy=none` ≥ X%, A7-large coverage ≥ Y%) is set against
*this* baseline at a later gating slice. The slice ships green if the loop runs, packets emit, and the
**paired numbers move in the predicted directions** — never on an asserted vibe.

**Reuse, don't rebuild:** A7-large is a `seed_multi_doc_matter` fixture scaled up + the existing
`TrackAScenario` wrapper; the quota/R4 brakes get unit tests with a **fake gateway** (zero LLM, the E1
pattern). No new dependency, no migration for the eval itself.

---

## 7. Open questions / what to VERIFY

- **The strongest "multi-agent hurts" numbers are second-hand.** The up-to-70% degradation, ~5× token
  efficiency, the **45% single-agent threshold**, and 17× error amplification come via a **secondary
  summary** of [arXiv 2512.08296](https://arxiv.org/abs/2512.08296) (Google DeepMind/MIT), and the
  benchmarks were **coding/planning** (PlanCraft), not legal-document synthesis. **VERIFY against the
  primary paper** before quoting, and treat doc-domain transfer as inference, not measurement.

- **No source directly studies legal multi-document analysis.** The "single-mind for legal synthesis"
  conclusion is an **extrapolation** via the shared-context/interdependency mechanism. The mechanism is
  general; the **magnitude in legal is unverified** — which is exactly why §6's paired A7 exists. Treat
  the small-vs-large boundary as a **tunable in our harness, not a literature constant** — verify on the
  fork's own CUAD/Track-A evals.

- **Numeric thresholds are workload/model-specific.** The ~45% baseline, ~4-agent plateau, the financial
  benchmark's F1/cost/latency, and the "effective window" cutoff are setup-dependent. Test the **specific
  model routed through our gateway** (DeepSeek today) for many-element recall before deciding a matter
  "fits" — fitting the window ≠ being reliably synthesised over it.

- **Vendor figures are illustrative.** Anthropic's 90.2% / 90%-time and Harvey's "500-contract /
  28%-revenue" are **self-reported product evidence**. The *architectural shape* (per-doc extract →
  cross-doc synthesise → human review) is corroborated across independent sources; the **specific
  numbers are not independently verified.**

- **Closed-harness internals are guesses.** The §4 rows for **Devin, Claude Code internals, opencode and
  OpenHands current delegation behavior** reflect **published behavior only** — VERIFY against current
  docs/releases before relying on any "when-to-delegate" claim for a specific harness; these move fast.

- **The capability era moves the boundary.** Cognition itself softened from "don't build multi-agents"
  to "writes single-threaded + intelligence-only helpers." As models improve at coordination/long-context
  discourse, the small/large boundary shifts — **re-check before treating any of this as a permanent
  architectural law.**

- **The R4 dependency is real and unbuilt.** §5's harness-enforced ceiling assumes **R4 becomes a real
  per-run token budget** — it is a **no-op today** (`guard.py`). The quota (Slice S4) is shippable now;
  the hard cost stop (Slice S5) is **its own slice + ADR** (strategy doc §6b). Stating the safety story
  as "bounded" requires landing at least the quota; "impossible to run away" requires R4.

---

*Sibling docs: the cost-ladder/estimate/quota mechanics live in
[`retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md`](retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md);
the native-substrate decision in [ADR-F049](../../adr/F049-native-memory-substrate-and-eval-gated-retrieval.md);
fan-out infra + reconciliation-as-tool-gate in [ADR-F034](../../adr/F034-fan-out-roster-and-reconciliation.md);
the eval-first arc index in [`RETRIEVAL-MEMORY-INDEX.md`](RETRIEVAL-MEMORY-INDEX.md).*
