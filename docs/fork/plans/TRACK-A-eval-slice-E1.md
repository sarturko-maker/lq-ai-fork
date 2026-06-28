# Plan — F2 Slice E1: Track-A masked-judge scenarios + Claude-judged baseline (ADR-F049)

## Context

E0 froze the **objective** Track-B retrieval floor (CUAD-gold, FTS-only: within-doc hit@8 0.39 / cross-doc
0.04). E1 builds the **subjective/agentic** arm — **Track-A**: live agent scenarios scored on a *masked*
view of what the agent did, so agent-mode behaviours (multi-doc grounding, read/retrieve/fan-out strategy
choice, anti-hallucination, cross-thread recall) get a frozen baseline too. Per ADR-F049 **eval-first**,
every later architecture slice (N0+) must beat measured numbers; E1 supplies the agentic half and is the
last Phase-E deliverable before the substrate work can be gated.

**The judge architecture (maintainer Q, 2026-06-28 — "why can't *you* be the judge?"):** you can, and you
are. `craft_judge` (`commercial_redline_lib.py:223`) routes to a *gateway* model only because it is called
**from inside a `pytest` process**, where the orchestrator (Claude) is not callable — so it needs an
in-process LLM, which must traverse the gateway (the only egress), which on the dev stack is `deepseek-pro`.
There is no deeper reason. E1 **flips it**: the harness emits a **masked judging packet** per run and
**Claude judges the packets** (in-session, or fanned out across Claude sub-agents). That is literally the
plan's *"Claude-judged DeepSeek"*, uses the strongest judge available, and costs **$0 on the gateway**. The
masking is what makes Claude-as-judge *fair* — the judge sees only the sanitised tool timeline + the visible
answer + the rubric/expectations, **never** the ground-truth documents, the agent's system prompt/doctrine,
`<think>` blocks, or `run_id` — so it cannot grade by leakage. A gateway `masked_judge()` (deepseek-pro)
ships **alongside** as the automated/reproducible fallback for CI-adjacent regression when no Claude session
is in the loop.

## Decisions (settled with maintainer, 2026-06-28)

- **Judge:** **Claude (orchestrator) is the primary judge** over masked packets; gateway `deepseek-pro`
  `masked_judge()` is the env-selectable automated fallback. *(answers the Q1 pushback)*
- **Model families (#6):** **single DeepSeek agent** for the E1 baseline; a 2nd family (e.g. Kimi K2.x) is a
  later one-env-var matrix expansion (the agent model is already `LQ_AI_SCENARIO_MODEL`).
- **Spend (#5):** **N=1 smoke default; N≥10 only for the explicit baseline freeze, under a per-matrix cycle
  cap.** Retriever-only (E0) stays the $0 day-to-day signal. Claude-judging is free; only the live *agent*
  runs spend tokens (~half the per-cycle cost vs a gateway judge).
- **Rubric strictness (#3):** **record rates as findings (ADR-F015), pass-bars unset this slice**; per-scenario
  bars get set at a later gating slice against this baseline.
- **Build location:** in-process under `api/tests/agents/scenarios/` (reuse `run_scenario` + the redline-eval
  harness, per the plan), **reusing the f0-s9 masking primitives** (`evals.runner.fetch_steps`,
  `evals.scoring.visible_answer/_task_strategy/_tool_calls`) — *not* the HTTP `api/evals/` path (it forks from
  the plan + `testpaths=["tests"]`). **No ADR. No migration. No new dependency.**

## Verified seams (all confirmed in code this session)

- **No gateway change** — unknown `lq_ai_purpose` falls back to `'chat'` (`gateway/app/api/inference.py:1351`);
  `craft_judge` already uses a non-allow-listed purpose. The gateway-judge fallback needs nothing new.
- **Masking is persist-time + transport-independent** — `_bounded` caps every step summary
  (`api/app/agents/runner.py:98`); `fetch_steps(engine, run_id)` returns only `seq/kind/name/summary/
  parent_step_id` (`api/evals/runner.py:127`, run_id *not* exported); `visible_answer` strips `<think>`
  (`api/evals/scoring.py:21`). All reusable in-process.
- **`evals` is an importable package** (`api/evals/__init__.py`) → reuse its masking/deterministic helpers
  from `tests/`. **`testpaths=["tests"]`** + the **`provider`** marker exist (`api/pyproject.toml:250/254`).
- **`Receipt` does not expose `run_id`** (`harness.py:201`) → the single additive harness change E1 needs.
- **judge≠agent model split precedented** — `LQ_AI_SCENARIO_MODEL`/`LQ_AI_JUDGE_MODEL`
  (`test_commercial_negotiation_eval.py:72-73`).

## Approach

**The shared substrate is the masked judging packet.** One run → one packet → consumed by *either* Claude
(primary) *or* the gateway judge (fallback). Building both modes is mostly the shared packet + a thin
gateway wrapper + a thin serializer.

### 1. Masked judging packet + verdict types — `track_a_lib.py` (NEW, `tests/agents/scenarios/`)
- `build_judging_packet(*, scenario_id, rubric, expectations, steps, final_answer) -> JudgingPacket` — projects
  the run to the **masked** shape: `steps` already in `fetch_steps` form (seq/kind/name/summary/parent_step_id),
  `visible_answer(final_answer)`, the rubric prose + `expectations`. **Asserts no leaking keys** (no run_id /
  prompt / doctrine / raw-doc text). Serializable to JSON for evidence + the Claude judge.
- `JudgeRubric` (per-scenario criteria prose + verdict field names) + `JudgeVerdict`
  (`{verdict, flags: dict[str,bool], evidence_quote, text}`). `evidence_quote` **must be a substring of the
  visible answer** (reject otherwise — prevents fabrication/leakage). Generalises `CraftVerdict`
  (`commercial_redline_lib.py:204`).
- `masked_judge(*, judge_model_alias, packet) -> JudgeVerdict` — the gateway fallback (generalises
  `craft_judge`): one `build_gateway_chat_model(purpose="track_a_masked_judge", …)` round-trip over the
  packet, regex verdict/flags parse, graceful `UNKNOWN` fallback, `http.aclose()` in `finally`. **Required
  param** for `judge_model_alias` (kills the silent-self-grading footgun).

### 2. Deterministic L1 metrics (free, run in CI over fixtures + on every live run)
- Reuse `evals.scoring._tool_calls`, `_task_strategy` (one_per_item|partition|none), `_contains`, plus E0's
  `retrieval_metrics` where chunk spans apply. Promote any reused `_private` helper to public in
  `evals/scoring.py` (thin, additive) rather than import underscores across packages.
- **Doc-level retrieval signal** (the agent-mode observability answer E0 deferred): fixtures give each fact a
  **unique, short, front-loaded filename**; score "did the right *document* enter the timeline" by substring
  over `tool_call`/`tool_result` summaries (same mechanism as `positive_grounding`). Chunk-level attribution
  (a `retrieved_chunks` column) is **deferred** — migration + rebuild, out of one-PR scope; recorded as the
  explicit E1→N0+ handoff.

### 3. The four scenarios — `Scenario` dataclass instances + a `TrackAScenario` wrapper (bundles
`Scenario` + `JudgeRubric` + `expectations` + `expected_outcome`). Seed via `seed_multi_doc_matter`
(`harness.py:80`); author distinct-fact fixtures (or reuse the subagent RFQ multi-doc fixture).

| Scenario | Seeds | Agent should | L1 (free) | Claude judge scores | Expected |
|---|---|---|---|---|---|
| **A1 multi-doc grounding** | 3–4 docs, distinct law/term each | search+read ≥2 docs; attribute each fact to the right doc | search+read fired; right filename in timeline | every claimed fact attributable to a doc in the (masked) timeline; no cross-doc bleed | **PASS** |
| **A5 cross-thread recall** | 1 matter, 2 threads; fact stated in T1, asked in T2 | recall T1's fact in T2 | T2 answer lacks the fact; **assert T1 fired no memory-write tool** (else fixture invalid) | did T2 honestly abstain vs hallucinate | **EXPECTED-FAIL** until N0/N3 (threads isolated, blocker #3) — frozen RED, not a green gate |
| **A7 strategy choice** | multi-doc + single-doc variants | pick single-read vs search-then-read vs `task` fan-out to fit the task | `_task_strategy` enum; `task` fired/not per variant | strategy-appropriateness for the task | **PASS** (fan-out native, proven C7b) |
| **A8 negative control** | single doc; ask a clause **not** present | abstain / honest absence; not fabricate | answer omits fabricated terms; read fired/no spurious task | honest-absence substance vs invention | **PASS** (oscar 0/80 noise) |

A2/A3 (long-negotiation) **already exist** (`test_commercial_redline_eval.py` + the C5a coverage path) —
cross-reference in the baseline doc, **do not rebuild**.

### 4. Harness change (the only one): expose `run_id`
- Add `run_id: str` to `Receipt` (`harness.py:201`), set from the existing `run_id` in `run_scenario`
  (`harness.py:298`). Additive; nothing else changes. The judging path calls
  `fetch_steps(test_engine, receipt.run_id)` → masked steps → `build_judging_packet`.

### 5. The eval test — `test_track_a_eval.py` (NEW, provider-marked)
- Mirror `test_commercial_redline_eval.py:55-73`: `pytestmark=[pytest.mark.provider, skipif LQ_AI_GATEWAY_KEY
  unset]`; env knobs `LQ_AI_SCENARIO_MODEL` (agent, default `deepseek`), `LQ_AI_TRACK_A_N` (default **1**;
  set ≥10 for the freeze), `LQ_AI_JUDGE_MODE` (`claude`=emit packets for Claude judging | `gateway`=run
  `masked_judge` inline), `LQ_AI_TRACK_A_EVIDENCE_DIR`. RIG-only assertions (ADR-F015) — loop ran, packets
  emitted, no crash; **never gate on a rate**. Writes packets + deterministic metrics to evidence; in
  `claude` mode the verdicts are filled by the Claude-judging step (below).

### 6. CI unit tests (free, Postgres-only — the safety net) — `test_track_a_unit.py` (NEW)
- `build_judging_packet` **masking assertion** (packet contains no run_id/prompt/doctrine/raw-doc keys);
  evidence-quote-must-be-in-visible-answer; `masked_judge` parse (verdict/flags + malformed→`UNKNOWN`) with a
  **fake gateway** (zero LLM); `visible_answer` stripping; deterministic-metric units (doc-level signal,
  `_task_strategy`); `TrackAScenario` structure validation. E0's `test_retrieval_metrics` +
  `test_cuad_retrieval_smoke` must stay green.

### 7. Claude-judged baseline freeze (primary judge)
- Run the live matrix on the dev stack (agent=`deepseek`, N≥10, capped) → emit masked packets.
- **Claude judges the frozen packets** — fanned out across Claude sub-agents (a Workflow: each judges a few
  packets under the per-scenario rubric, returns a `JudgeVerdict`); reproducible (packets are frozen,
  re-judgeable). Aggregate rates + CI half-widths (±~29pp at N=10) via the `report.py` pattern.
- Freeze under **`docs/fork/evidence/retrieval-eval/track-a/`**: `packets/` (masked inputs), `verdicts.json`,
  `track-a.md` (rates, CI, per-scenario expected/actual, A5 RED documented, judge = `claude-opus` + the
  same-family gateway-judge note). Optionally cross-check a sample with the gateway `deepseek-pro` judge and
  record agreement.

## Critical files
- **NEW:** `api/tests/agents/scenarios/track_a_lib.py` (packet + verdict + `masked_judge`),
  `…/track_a_fixtures.py` (4 `TrackAScenario` + seeds), `…/test_track_a_eval.py` (provider-marked matrix),
  `…/test_track_a_unit.py` (CI units).
- **EDIT (additive):** `…/harness.py` (`Receipt.run_id`); `api/evals/scoring.py` (promote reused helpers to
  public). **No** change to `Scenario`/`evaluate`, the gateway, or any product code path.
- **REUSE:** `commercial_redline_lib.py:223` (template), `evals/runner.py:127` (`fetch_steps`),
  `evals/scoring.py:21` (`visible_answer`/`_task_strategy`/`_tool_calls`), `harness.py:80/253`
  (`seed_multi_doc_matter`/`run_scenario`), `factory.py:36/58` (gateway client/model),
  `retrieval_metrics.py` (E0 scorers).
- **DOCS:** `docs/fork/evidence/retrieval-eval/track-a/` (frozen), plan→`docs/fork/plans/`,
  RETRIEVAL-MEMORY-eval-first.md (E1 ✅ + settle open-calls #3/#5/#6 + the judge decision), HANDOFF
  (E1 done → N0 next), MILESTONES (E1 line), memory.

## Non-goals (explicit)
- **No chunk-level retrieval attribution** (`retrieved_chunks` column / `_search` chunk-id trailer) — migration +
  rebuild; E1 proves doc-level + answer-substance scoring first, N0+ earns it if doc-level is too coarse.
- **No A2/A3 rebuild** (exist), **no 2nd model family** (later env expansion), **no R4 token-budget brake**
  (Phase-3 slice), **no wiring A5 to pass** (that's N0/N3).
- **No gateway change, no migration, no new dependency, no product code path** (the judge is dev/eval-time;
  the product never calls the orchestrator).
- **No a-priori pass-bars** (rates are findings; bars set at a later gating slice).

## Verification (DoD — shown, not asserted; ADR-F005 gate)
1. **CI units** (`test_track_a_unit.py`) green in the dev image — masking-leak assertion, evidence-quote check,
   `masked_judge` parse w/ fake gateway, deterministic metrics. **Full api suite green, counts quoted; ruff
   (repo-root) + mypy `app` clean.** E0 tests still green.
2. **Live matrix** on the dev stack (agent=`deepseek`, N≥10, capped): packets emitted; **Claude-judged**
   verdicts produced + frozen; A5 confirmed RED honestly (T1 wrote no memory). Evidence in the PR.
3. **Fresh-context adversarial review (ultracode dimensions × verify)** incl. the mandatory **security +
   simplification pass** — primary risk: **masking leak** via the packet/rubric/expectations path (the judge
   must never receive prompt/doctrine/raw docs/run_id); also: evidence carries verdicts + a quote-from-visible-
   answer only (counts/types/IDs, no raw clause text/secrets); no self-grading footgun; no dead/dup code
   (promote-not-duplicate). Blockers/should-fixes fixed or deferred on record.
4. **HANDOFF + MILESTONES + plan-doc + memory** updated; merge under the **ADR-F005 gate**
   (`gh pr create/merge --repo sarturko-maker/lq-ai-fork`).

## Recommended order
`Receipt.run_id` + promote `evals/scoring` helpers → `track_a_lib` (packet + verdict + `masked_judge`) →
`track_a_fixtures` (A1/A7/A8/A5 + seeds) → `test_track_a_unit` (CI net) green → `test_track_a_eval`
(provider-marked) wired → live matrix N≥10 on dev stack → Claude-judge the packets (Workflow) → freeze
evidence → docs/HANDOFF/MILESTONES/plan/memory → adversarial review → PR + merge.
