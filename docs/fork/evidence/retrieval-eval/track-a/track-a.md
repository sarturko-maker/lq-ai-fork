# Track-A agentic baseline (F2 slice E1, ADR-F049)

The **subjective/agentic** arm of the eval-first plan. Four live scenarios run
through the production agent loop (DeepSeek `deepseek-v4-flash`), scored on a
**masked** view of what the agent did:

- **L1 (deterministic, free):** `evals.scoring.score_all` over the sanitised
  `agent_run_steps` timeline — did the right tools fire, did the answer carry the
  expected facts, what fan-out strategy was used.
- **L2 (masked faithfulness judge):** the orchestrator (Claude) judges a **masked
  judging packet** — the sanitised tool timeline + the visible answer + the
  rubric/expectations, and *nothing else* (no source documents, no system
  prompt/doctrine, no `run_id`, no `<think>`). The judge therefore grades the
  answer's **faithfulness to what the agent actually surfaced**, not against
  outside knowledge. The gateway fallback judge (`deepseek-pro`) exists for
  automated runs but the frozen baseline below is Claude-judged.

Per ADR-F015 these are **recorded findings, not gates**. N=10 reps per scenario;
agent = DeepSeek single family (a 2nd family is a later one-env-var expansion).
Reproduce: see [`../README.md`](../README.md). Raw masked inputs in `packets/`;
machine verdicts in `verdicts.json`; deterministic rows in `track-a-report.json`.

## Headline (the floor every later agentic slice must beat)

| Scenario | expected | L2 PASS | Wilson 95% CI | key signals |
|---|---|---|---|---|
| **A1** multi-doc grounding | pass | **8/10** | [0.49, 0.94] | grounded 9/10 · no cross-doc bleed 10/10 |
| **A5** cross-thread recall | expected-fail | **10/10** | [0.72, 1.00] | recall **0/10** · honest abstention 10/10 · hallucination 0/10 |
| **A7** read/retrieve/fan-out strategy | pass | **8/10** | [0.49, 0.94] | no *autonomous* fan-out (0/10) but inline strategy judge-appropriate 8/10 |
| **A8** negative control | pass | **10/10** | [0.72, 1.00] | honest absence 10/10 · fabrication 0/10 |

(The ±~22pp half-widths at N=10 are wide by design — the baseline is a floor to
beat, not a pass/fail line; later slices set deltas, never tighter than this CI.)

## What the baseline says

1. **Anti-hallucination is already strong.** A8 (asked about a clause that is not
   in the document) and A5-abstention (asked to recall a fact from a conversation
   it cannot see) are **10/10 honest** — DeepSeek does not fabricate absent terms
   or invent a missing detail; it states the absence and asks. Fabrication 0/10
   on both. This is the safety floor; later slices must not regress it.

2. **Grounding is faithful, but gated by convergence.** A1's two failures are
   **empty answers from cap-exceeded runs** — the masked timeline shows the agent
   *correctly retrieved and attributed both facts*, but the run hit the step cap
   before a user-visible answer was produced. So the gap is delivery/convergence,
   not grounding (grounded 9/10, cross-doc bleed 0/10). Better retrieval (fewer
   steps to the facts) should lift this toward 10/10.

3. **DeepSeek does not *autonomously* fan out on a bounded task — and that may be
   correct.** A7 (a broad four-document comparison) drew **zero subagent
   delegations across all 10 reps** (`task_strategy` = `none` 10/10); the agent
   gathered all four documents and synthesised *inline*. This is **not** a
   capability limit and **not** a harness gap — it was investigated (2026-06-28):
   the `document-researcher`/`clause-drafter`/`clause-reviewer` subagents (mig
   0073) **were wired and the `task` tool *was* available** to this run, and the
   same model **delegated 3× when coached** in C7b (`test_commercial_fan_out_
   scenario.py`). The difference is **coached vs uncoached**: A7's prompt does not
   instruct delegation, and for a bounded 4-document matter the model's inline
   strategy is reasonable — the masked judge rated it `appropriate_strategy` **8/10**
   (the 2 fails are cap-exceeded *empty answers*, not bad strategy). So the open
   question this frames for the Phase-3 *strategy + R4* slice is **at what corpus
   scale autonomous fan-out becomes necessary** (and whether doctrine should nudge
   it), *not* whether DeepSeek can delegate. (Web check: DeepSeek V4 is built for
   delegation — V4-Flash parallel subagents / RLM fan-out — no documented
   reluctance.)

4. **Cross-thread recall is the honest RED.** A5 recall is **0/10** — a fact
   stated only in conversation thread 1 is unreachable in thread 2 (threads are
   isolated; CLAUDE.md blocker #3). This is the scenario that should **turn green
   with N2/N3** (the native conversation Store). It is frozen RED on *recall*
   while green on *honesty* (the agent abstains rather than guessing), so the
   later substrate slice has an unambiguous before/after.
   - *Method note:* A5 plants a deliberately **non-matter** aside (an office
     location) the agent should not file as a matter fact. Cross-thread recall of
     genuine *matter* facts already works via the matter-memory tier — the agent
     auto-writes them (ADR-F042). The fixture asserts thread 1 fired **no**
     matter-memory write tool (10/10 valid here); had it written, thread 2 would
     surface the fact from memory, not from conversation recall.

## Method (so later slices compare apples to apples)

- **Masking is the contract.** The judge input is built by
  `track_a_lib.build_judging_packet` — it projects every step to the five audited
  fields (`seq/kind/name/summary/parent_step_id`) and strips `<think>` from the
  answer. The unit net (`test_track_a_unit.py`) asserts no `run_id` / raw tool
  payload / system prompt / reasoning can reach a judge.
- **L1 ≠ L2 by design.** L1 is the answer-key check (did the facts/tools appear);
  L2 is faithfulness (is every claim traceable to a retrieval the agent shows;
  did it abstain honestly). A7 is the clearest split: L1 `delegated` 0/10 (strict
  fan-out signal) vs L2 `appropriate_strategy` 8/10 (inline multi-step accepted).
- **Variance is the point.** Run-to-run, the same scenario flips
  (completed↔cap_exceeded); N=10 + the recorded rate + the CI is the discipline,
  not any single run.
- **Judge:** `claude-opus` (orchestrator) over the frozen `packets/`, one
  independent fresh-context judgement per packet. Same-family note: the gateway
  fallback judge would be `deepseek-pro` (the dev stack has no cross-family
  judge); the Claude orchestrator judge avoids grading DeepSeek with a DeepSeek
  relative. The packets are frozen, so the verdicts are re-judgeable.
