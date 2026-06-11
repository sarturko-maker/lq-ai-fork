# F0-S9 pre-research — eval reuse + model qualification gate

Provenance: maintainer directive 2026-06-11 — "MiniMax evals have been ran [in oscar-gc] …
MiniMax is a dependency injection. Deep Agents should work with any good model. Ensure we do
not redo the work done [there] and run online research — model tool calling must have been
done by many open source projects."

Method: 5-agent research workflow (1 local miner over /home/sarturko/oscar-gc-review at
sprint 35 + 3 web researchers + 1 synthesizer), 2026-06-12. oscar-gc is AGPL-3.0: findings,
numbers and METHODOLOGY below are reusable; its CODE is never ported (ADR-F004 boundary).

Consumed by: the F0-S9 plan. The synthesis below is the slice's research input; §4 lists the
decisions only the maintainer can make.

---

# F0-S9 Synthesis — Model Qualification Gate (eval slice)

Sources: four research reports (oscar-evals, oss-benchmarks, oss-harnesses, model-qualification), cross-checked against the fork's own substrate (`api/app/models/agent_run.py`, ADR-F004 `docs/adr/F004-oscar-gc-adopted-logic.md`).

---

## 1. WHAT OSCAR ALREADY PROVED (do not redo)

Oscar-gc's `evals/matter-runtime` (Sprints 32–33, ADR-109) already ran the experiment S9 would otherwise have to run. The findings transfer as settled logic; only the substrate is rebuilt.

**Method that transfers wholesale (ADR-109 shape):**
- **Cell sizes:** N=20 primary model, N=10 second family, N=5 directional-only with CI caveats quoted (±43pp at N=5, ±29pp at N=10). 200-cycle matrix ran ~3.5h wall; MiniMax ~$0.08–0.23/cycle vs Haiku ~$0.40, Sonnet ~$1.33–1.68.
- **Pre-flight variance gate, concrete definition:** N=5 on the highest-discrimination cell; PASS = ≤1 verdict disagreement per affordance across 5 cycles; on FAIL escalate N or narrow the matrix (`pre-flight-n5.js`, `compute-variance.js`, SPRINT_32_BRIEF:222–226). Known gap to fix in our clean-room version: parameterise the cell (theirs was hardcoded).
- **Masked judge = programmatic extractor, for structural rubrics:** "did tool X fire with arg Y" needs no LLM — a zero-LLM extractor is doctrine-masked by construction (`judge-cycle.js`; 200/200 verdicts written programmatically). The mask that matters is *doctrine/prompt* masked from the judge (because the authoring model also judges), not model identity.
- **Rubric shape:** paired positive/noise fields per affordance (`*_when_applicable` vs `*_when_not_applicable`), *invoked* vs *invoked-correctly* (arg exactness), a strategy enum for fan-out (`one_per_item | partition | none`), S2N = fired_when_applicable / (fired_when_applicable + fired_when_not_applicable). Explicitly does NOT score legal substance or token efficiency (cost log separate).
- **Scenario taxonomy (4):** positive grounding scenario, positive batch/fan-out scenario, **negative control** (nothing should fire), and **mismatch** (relevant resources in scope, wrong task — "the cleanest negative-guard discrimination test", the one most teams forget). Negative guards held 0/80 across all noise fields.
- **Runner hygiene:** verify a real assistant message (or a gateway 4xx/5xx) landed per run — Sprint 32 silently ghosted 30 Haiku cycles on an HTTP 403 quota error because the runner trusted stream termination.

**Results that transfer as standing constraints:**
1. **The +35pp/−20pp reversal** (Sprint 32, ADR-108): the same slug-exactness NEVER-list doctrine moved MiniMax-M2.5 skill-arg-correct 30%→65% (N=20) while moving Haiku 4.5 50%→30% (N=10). **Same paragraph, opposite signs across families.** This is the empirical origin of "the model is dependency injection" and the reason ADR-F004 mandates ≥2 families. Sprint 33 Candidate C (positive imperative + one targeted exclusion + concrete example) reversed it: MiniMax held 65%, Haiku recovered to 60% (ADR-110). Wording rule for every S9 instruction surface: positive imperative, ≤1 collapsed exclusion, no stacked NEVER lists.
2. **Open-ended delegation is capability-bound, not doctrine-bound** (Sprints 30–32, ADR-107): 5–25% uptake on MiniMax no matter the doctrine. **Task-scoped fan-out works**: Sprint 35's prescribed per-document procedure got MiniMax to fan out 15/15 on real CUAD contracts. This is already adopted in ADR-F004 ("task-scoped fan-out"). S9 therefore *prescribes* the procedure and measures compliance — it does not measure open-ended delegation willingness.
3. **Placement beats wording:** doctrine must precede the surfaces it references; late-flow behaviour (turn-5 action) only moves when the instruction lives at the trigger surface (the tool's own description) — 0pp otherwise on both families. And verify the field you write to actually reaches the model (oscar's extension `description` was UI-only).
4. **No absolute thresholds a priori:** matter-runtime gated on A/B deltas + hard 0-noise expectations; the one hard numeric gate in the lineage (oscar-llp's ±2pp sanity gate) failed on N=6 noise and was waived — **never gate tighter than the metric's CI**.
5. **Adding prompt text makes things worse by default:** lavern-jv's added 45-line verification loop *reduced* grounded citations 0.96→0.71 (Δ −3.8pp headline); oscar-llp's subtractive-only iteration took DELIVERED 30%→95%. S9 failures get fixed by cutting/moving text, not adding.
6. **MiniMax quirk catalogue** (all M2.5 — re-verify on M3): text-shaped `[TOOL_CALL]` pseudo-calls under misconfiguration (assert structural tool-call frames, never regex text); `"None"` instead of null in structured output; bare-filename paths breaking path-keyed grounding gates (fix model-agnostically — bounded basename fallback); skill-noise eagerness (+25pp wrong-skill, MiniMax-only); delegate-shyness.

**Contradictions / corrections from the web reports:** none material, two flags. (a) The "BFCL 76.8" figure for MiniMax-M2.5 floating around is **vendor self-reported** — no MiniMax model appears on the official Berkeley leaderboard or in SUPPORTED_MODELS.md (verified 2026-06-11); any oscar-era assumption that MiniMax has an external tool-calling prior is wrong. (b) Oscar never surfaced the **`<think>`-retention requirement** (MiniMax M-series demands thinking blocks be retained verbatim in history across tool turns; Goose handled it invisibly). Our gateway must be checked for this before any M3 number is trusted — a degraded-uptake result is triaged against the adapter first (the vLLM/K2 post showed a model "failing" at <20% tool-call parse rate purely from serving-layer bugs).

**License boundary:** oscar-gc is AGPL-3.0; per ADR-F004, logic only, never code. The scripts are small (run-cell ~300 LOC, judge ~220, variance ~107) — clean-room reimplementation against our API is ~600 LOC.

---

## 2. WHAT THE ECOSYSTEM PROVIDES

**Capability priors — cite, don't run:**
- **PRIMARY: BFCL V4** (Berkeley; Apache-2.0; leaderboard CSV downloadable at gorilla.cs.berkeley.edu/data_overall.csv). Cite three columns per candidate model: Overall Acc, Multi-Turn Acc, and **Relevance/Irrelevance Detection** — the last is a direct published proxy for S9 measure (a), tool-call uptake/abstention. Screening heuristic from current data: credible open-weight tool-callers sit ≥~60% multi-turn (GLM-4.6: 68.0%); weak ones ~44% (DeepSeek-V3.2, Qwen3-235B).
- **SECONDARY: tau2-bench leaderboard** (Sierra; MIT; taubench.com, submission JSONs in-repo) — pass^k is the only major board publishing *consistency*, matching ADR-F004's variance concern. Cross-check vendor claims against **Artificial Analysis tau2-Telecom** (independently run; the only independent source that covers the MiniMax family at all).
- **Structural gap that justifies S9:** MiniMax-M3 (our dev model) has **no independent tool-calling prior** — not on BFCL, not on tau2; all M3 numbers are vendor-run ("independent verification still pending"). And **no public benchmark anywhere measures subagent/delegation uptake** (the deepagents `task` tool). Both S9 measures are in-house by necessity, not preference. Published scores are a screening prior only — exactly how the field uses them (Goose's docs point users at BFCL as *guidance*, then gate on `goose bench`).
- Exclusions, for the record: ToolBench (API rot), API-Bank (dead 2023), AgentBench (wrong axis), ComplexFuncBench (no LICENSE + RapidAPI paywall), NexusBench (dead), Apple ToolSandbox (custom license — cite-only), Galileo leaderboard (vendor-curated, corroboration only). MCP-Universe/MCPMark (both Apache-2.0, active, gateway-compatible) become relevant later when practice areas consume MCP servers — noted for the backlog, not S9.

**Harness — verdict: BUILD (plain pytest), adopt at most one micro-library.**
The decisive architectural fact (oss-harnesses report): S9 must score from **our settled `agent_run_steps` rows**, which means the deepagents loop must run inside **our** stack — API, worker, gateway, brakes, audit. Every framework that wants to own the loop fights this: Inspect's agent bridge re-routes SDK calls to its own model provider (bypassing the gateway-audit path the eval exists to exercise); DeepEval wants tracing decorators. What's left is (a) a loop driver, (b) deterministic Python over DB rows, (c) one judge call — none of which needs a framework. This also matches field practice: Goose, aider, Roo, OpenHands all run their *own* containerized harness on their *own* loop and publish a matrix.
- **Adopt (optional, one):** `openevals`/`agentevals` (MIT, standalone without LangSmith, langchain-native — we already ship langchain/langgraph; judge accepts a plain OpenAI client pointed at the gateway). Justifiable as the single new dependency; `autoevals` (MIT) is the fallback (pin `base_url` explicitly — its default falls back to Braintrust's gateway).
- **Reject:** LangSmith self-host (paid Enterprise — violates no-SaaS), Arize Phoenix (Elastic-2.0 — fails prefer-MIT/Apache), DeepEval (Apache but telemetry + SaaS gravity; its ToolCorrectness metric is ~30 lines of plain Python), RAGAS (big tree for what we can compute ourselves), lm-eval-harness (no agent/tool support), openai/evals (dormant), promptfoo (capable — Python provider + metadata asserts + `--repeat` prove the pattern — but Node/YAML outside our pytest world).
- **If a fuller harness is ever justified:** inspect-ai first (MIT, UK AISI, epochs+reducers for variance, custom solver calling our API — never the bridge); promptfoo second. Copy Inspect's epochs/reducers *idea* now, not the dependency.
- **Judge masking:** no framework ships it. It is our prompt-construction protocol per ADR-F004, identical in any tooling.
- **L0 pattern to copy:** Moonshot's **K2-Vendor-Verifier** shape — a samples.jsonl fired at any OpenAI-compatible `--base-url`, reporting **tool_call trigger F1** + **schema accuracy**. That metric pair *is* "zero-LLM grounding checks first" at the serving layer.

---

## 3. RECOMMENDED S9 SHAPE

**Gate definition:** `qualified(model) = external screening prior (cited, not run) + three-layer on-stack suite through the gateway`. Output artifact is a **model compatibility matrix** with per-model config notes (parser/think-retention/streaming/cost), Goose/OpenHands style — not a single pass/fail leaderboard.

**Layer L0 — serving conformance (zero-LLM, ~hours, disqualifying):**
- Structural tool-call frames asserted at the protocol level — never regex over text (oscar's `[TOOL_CALL]` lesson). Schema-valid arguments (hard bar ≈100%, K2-Vendor-Verifier precedent: official baseline had zero schema errors). Small trigger-F1 sample set (call when needed / abstain when not).
- **Gateway round-trip check for reasoning content**: MiniMax M-series requires `<think>` blocks retained verbatim across tool turns; GLM has the same class ("Preserved Thinking"). A low L0/L1 score indicts the adapter before the model (vLLM/K2: <20% parse rate from three serving bugs, model blameless).
- No toolshim ever: a model failing L0 is disqualified, not patched (Goose toolshim ceiling ~41–48%).

**Layer L1 — deterministic uptake from settled `agent_run_steps` (the core of S9):**
Scored by plain Python over rows `(seq, kind ∈ {model_turn, tool_call, tool_result}, name, summary, parent_step_id)`. Metric dictionary (oscar's affordance mapping, field-for-field):
- `search_documents_fired_when_needed` / `search_noise_on_no_grounding_prompt` (paired positive/noise)
- `read_document_arg_correct` — right document, parsed from the step's bounded summary digest (see caveat in §4)
- `task_fired_on_batch` (count ≥2, via `parent_step_id` ancestry from F0-S7) + `task_strategy ∈ {one_per_item, partition, none}` — fan-out **prescribed** as a task-scoped procedure; we measure compliance, not initiative
- one **late-flow action-tool canary** (oscar's hardest affordance, 0–15% until the instruction moved into the tool description)
- S2N per affordance per cell; per-run cost/tokens/latency logged (M3 is extremely verbose in reasoning tokens — interacts with the R4 cost cap; log it, gate on it later if needed).

**Scenarios (4, JSON expectations: should_fire / should_not_fire / canonical_arg / fire_on_turn / min_count / rationale):**
1. Matter-bound question requiring grounding (search + read expected)
2. Batch task over a multi-doc matter (task tool ≥2, strategy enum)
3. Negative control — no matter docs / drafting ask (nothing fires; hard 0-or-near-0 noise gate, oscar held 0/80)
4. Mismatch — documents present, question doesn't need them (the negative-guard discriminator)

**Layer L2 — masked LLM judge, only where judgment is needed** (grounding substance / answer-actually-uses-retrieved-text). Judge sees a sanitized tool-timeline reconstructed from `agent_run_steps` + scenario expectations ONLY — agent prompt/doctrine and model identity stripped, presentation order randomized, mapping logged out-of-band. Judge call routes through the gateway (one `openevals create_llm_as_judge` call or hand-rolled). Pre-registered rubric + verbatim-evidence-quote + single-JSON output, copied from lavern-jv's judge shape.

**N and variance:** pre-flight N=5 on the highest-discrimination (scenario × model) cell, parameterised; PASS = ≤1 verdict disagreement per metric across 5 cycles; FAIL → escalate N or narrow matrix, logged either way. Main run N=20 primary (MiniMax-M3), N=10 second family. Quote CI half-widths next to every small-N number (±29pp at N=10). Optional worst-of-3 (open-model-gym) for hard noise gates.

**Runner:** plain `pytest.mark.parametrize(scenarios × models × N)` → POST run to our API → poll until the run settles → score rows. Per-run assertion that a real assistant message exists or a gateway error is surfaced (silent-403 lesson). Agent instructions under eval pinned to commit SHA (oscar's variant-pinning). Zero new runtime dependencies in `api/`; at most one dev-dependency (openevals or agentevals, MIT).

**Second model family — recommendation: Kimi K2.x (Moonshot), via a new gateway provider entry pointing at Moonshot's OpenAI-compatible API** (or an OpenAI-compatible reseller), keys held in the gateway only. Rationale: strongest independently-verified open tool-calling record (OpenHands Index 57.1, #2 open; AA 54 ≈ M3's 55); purpose-trained for tool use; ships its own conformance harness (K2-Vendor-Verifier validates our L0 through our own pipe); modified-MIT is pure MIT at our scale; and **its non-interleaved-thinking instruct variants give failure-mode contrast with MiniMax's think-retention style** — a gateway think-handling bug would not confound both families identically. Critically, OpenAI-compatible serving avoids the known blocker that our Anthropic adapter is text-only (CLAUDE.md blocker #2) — picking a Claude family (oscar's choice, Haiku 4.5) would make S9 depend on building Anthropic tools support first. Alternate: GLM-4.7/5.1 (pure MIT, top open agentic score 58.2 — but shares the think-retention quirk class, weakening the confound isolation). Third/self-host control: Qwen3.x (Apache-2.0; pin non-streaming tool calls — vllm#31871/#20611). Anti-pick: DeepSeek (45.7 OpenHands Index, historically toolshim-class).

**Explicitly NOT building (exists elsewhere or is settled):**
- No BFCL/tau2 re-implementation or general capability benchmark — cite the boards (vendor the CSV row into the S9 doc)
- No eval framework adoption (Inspect/promptfoo/DeepEval/RAGAS/Phoenix) and no SaaS eval platform (LangSmith, Confident AI, Braintrust platform)
- No doctrine A/B program — oscar already ran it; we inherit Candidate-C wording style and placement rules as constraints
- No open-ended delegation eval — settled as capability-bound (ADR-107/F004); S9 measures task-scoped compliance only
- No toolshim for non-tool-calling models — L0 disqualifies
- No judge-masking framework — it's ~30 lines of our prompt protocol
- No search for a subagent-uptake benchmark — none exists (verified across both web reports)
- No porting of AGPL oscar code — clean-room ~600 LOC against our API/`agent_run_steps`

---

## 4. OPEN DECISIONS FOR THE MAINTAINER

1. **Pass thresholds.** Proposal: hard bars only where variance is known — L0 schema validity ≈100%, noise on negative scenarios = 0 (or ≤1/N with the cycle logged); L1 uptake bars set **after** the first N=20 MiniMax-M3 baseline, not a priori (oscar precedent + the sanity-gate-waiver lesson: never gate tighter than the CI). Reference points if you want provisional floors now: oscar best-doctrine uptake 60–65%; BFCL open-weight "good" line ~60% multi-turn. Ratify or set numbers.
2. **Model shortlist.** Confirm Kimi K2.6 as family #2 (and the gateway provider addition it implies); GLM vs Qwen as alternate; whether a third family is in-scope for S9 or deferred. Note: choosing any Claude family instead pulls "Anthropic adapter forwards tools" into the slice.
3. **New dependency.** Zero vs one: approve `openevals` (or `agentevals`) as a dev-only MIT micro-dependency for the L2 judge, or hand-roll the judge call. Separately: approve/defer a one-time **anchor run** of bfcl-eval or EvalScope (both Apache-2.0, OpenAI-compatible) through the gateway to sanity-check our pipe against one published number.
4. **Arg-correctness data source.** `agent_run_steps.summary` is a bounded ~2000-char *digest* of tool args (`api/app/models/agent_run.py`). Decide: (a) parse doc IDs from the digest and guarantee the digest format keeps them (cheap, slightly brittle), or (b) add a structured `args_digest` (counts/types/IDs only, audit-contract-compatible) column for deterministic scoring. (b) is a small migration with rebuild obligations per CLAUDE.md dev rules.
5. **Gateway pre-check scope.** The reasoning/`<think>` round-trip verification is a prerequisite to trusting any M3 number — decide whether it's an S9 sub-task or a separate micro-slice landing first.
6. **Budget/quota** for second-family cells (oscar's reference: ~$0.40/cycle Haiku-class; N=10 × 4 scenarios is tens of dollars) and whether the qualification matrix becomes a recurring artifact (re-run per model/gateway change) or a one-shot S9 deliverable.
