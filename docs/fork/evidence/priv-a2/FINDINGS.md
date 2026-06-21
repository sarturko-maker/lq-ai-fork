# PRIV-A2 — assessment build loop, live findings (2026-06-20)

The proof deferred since PRIV-A2: that the assessment **write loop** works end to end on a
**real model**, not a scripted one. A lawyer asks, in plain language, for a DPIA on a new
piece of processing; the Privacy agent composes the assessment tools
(`propose_assessment` → `link_assessment_to_activity` → `add_risk` → `complete_assessment`),
code-validated at every step (ADR-F018), and lands a coherent, completed assessment in the
deployment-global register (ADR-F019) satisfying the ADR-F027 completion invariant.

**Rig:** `tests/agents/scenarios/test_assessment_build_scenario.py` (provider-gated, self-skips
in CI). One plain-language ask on clearly high-risk processing (an AI profiling layer on product
analytics — churn prediction driving automated pricing/offer decisions). Three arms:
`deepseek` (flash) no-skill / `deepseek` + `pia-generation` / `deepseek-pro` + `pia-generation`.
Run live against the dev gateway → DeepSeek V4, on a throwaway `lq_ai_test_*` DB (the dev
register was never touched). Per **ADR-F015** this is **not** a model pass/fail gate — the hard
asserts are only that each run is terminal, took a model turn, and that the completion-rule
integrity holds on the persisted record; everything else is kept **verbatim**. DeepSeek is **not**
scenario-qualified — these results are honest observations, not tuned-green.

## Result: the loop works, on every arm

All three arms built a defensible, **completed** DPIA whose every risk carries a **documented,
design-tied mitigation**, and the **ADR-F027 completion integrity held in all three** (read back
off the DB: no completed DPIA/high-rated assessment lacks a mitigation).

| Arm | assessments | completed | risks (all mitigated) | linked | run status | steps | latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| flash · no-skill | 2 (1 completed, **1 stray draft**) | 1 | 6 | 0.5 | `cap_exceeded` | 100 | 117s |
| flash · pia-generation | 1 | 1 | 5 | 1.0 | `completed` | 75 | 88s |
| pro · pia-generation | 1 | 1 | 6 | 1.0 | `completed` | 95 | 110s |

The mitigations are genuinely substantive (the flash+skill arm, verbatim): an Art-22(3)
human-intervention + privacy-notice update for the unawareness-of-profiling risk; a pre-deployment
+ quarterly bias audit with a statistical-parity threshold for discriminatory pricing; a
precision/recall accuracy gate with a support-override fallback for misclassification; a
purpose-boundary access-control guard against sensitive inferences. See each arm's
`build-*/behavior-report.md`.

## Findings (verbatim, ADR-F015)

1. **The validated write loop is solid.** A real model reliably orients (lists the register),
   proposes the assessment, links it to a ROPA activity, adds scored risks with mitigations, and
   completes under the F027 rule — composing the A1/A2 tools with no scripting. The headline
   invariant is honoured on every persisted record.
2. **The `pia-generation` skill earns its place through FOCUS, not necessity.** Even the no-skill
   baseline produced a valid completed DPIA (DPIA method is well-represented in the base model) —
   but it also spun up a **second, dangling draft DPIA**, linked only half its assessments, and ran
   out of budget before reporting. **Both skilled arms produced a single, clean, completed, linked
   DPIA and reported back within budget.** The skill keeps the agent on one coherent assessment.
3. **Report-back headroom (acted on).** The first arms at `max_steps=80` reached `cap_exceeded`
   *after* completing the assessment but *before* the final summary (the DPIA was built and
   coherent; only the user-facing report was cut). Raised the scenario's `max_steps` to **100**
   (the production cockpit ceiling, ADR-F026); the skilled arms then complete and report cleanly.
   A no-skill run can still exhaust 100 by over-exploring — a model-efficiency observation, not a
   loop defect (the record it leaves is still valid).

## Reproduce (local, no exposure)

Throwaway pgvector + the dev gateway (DeepSeek); the dev DB is never touched:

```
# api/tests/agents/scenarios/conftest.py creates/drops its own lq_ai_test_* DB
# from DATABASE_URL; point it at a throwaway pgvector, not the dev postgres.
pytest -m provider tests/agents/scenarios/test_assessment_build_scenario.py -q
```

CI runs the pure scorer (`test_assessment_eval.py`, 7 tests) and self-skips this provider test.
