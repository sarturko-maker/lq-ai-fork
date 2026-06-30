# Slice F — per-run token-budget brake (R4 realised): verification (ADR-F051, ADR-F015 finding)

**What.** F2 Phase-3 Slice F makes R4 a real per-run **token-budget** brake: the runner sums each
model turn's `usage_metadata.total_tokens` (lead + subagents) and halts the run (`cap_exceeded`,
`error=token_budget_exceeded`) once the cumulative total crosses `Settings.run_token_budget` —
mirroring `max_steps`, never mid-final-answer. The enabler is `stream_usage=True` on the api-side
gateway model (the gateway already forwards the usage chunk). In-memory enforcement, no migration.
Gate (`plans/RETRIEVAL-MEMORY-eval-first.md`, "Strategy + safety"): *a runaway-fan-out token-budget
halt* — an ADR-F015 finding; the deterministic halt test is the hard CI gate.

## The hard gate — deterministic, $0, zero-LLM (CI-enforced)

`tests/agents/test_agent_runner.py` (mirrors the `max_steps` cap test):

- **`test_token_budget_halts_run_before_max_steps`** — a looping model reporting 100 tokens/turn with
  `token_budget=250` and `max_steps=50` halts as `cap_exceeded` with `error="token_budget_exceeded"`
  (told apart from the step cap, which leaves `error` NULL), `final_answer` NULL, and far fewer than
  50 steps — the budget tripped first.
- **`test_token_budget_zero_disables_the_brake`** — with `token_budget=0`, a normal run completes even
  while reporting 10,000 tokens/turn.
- **`test_run_under_token_budget_completes_normally`** — usage accumulation does not disturb a normal
  run that stays under budget.
- **`test_token_budget_never_halts_mid_final_answer`** — the not-mid-final-answer guard: a final-answer
  turn that pushes cumulative tokens over the budget still completes with its deliverable.

The fake `ScriptedToolCallingModel` gained `usage_per_turn`, emitting a trailing usage chunk per turn
(mirroring ChatOpenAI's final include-usage chunk). An in-container probe confirmed the load-bearing
mechanism: `usage_metadata` set on a streamed `AIMessageChunk` surfaces **summed** on the merged
`on_chat_model_end` event (so the runner reads it) — the same path nested subagent turns report on.

**Suite:** full `tests/agents/` **688 passed / 38 skipped / 0 failed** (684 at Slice E + 4 token-budget
tests); `ruff check api scripts` + `ruff format --check api scripts` + `mypy app` (209 files) all clean.

## Live verification — dev stack, real DeepSeek (the enabler works end-to-end)

A live probe built the production `build_gateway_chat_model(model_alias="deepseek-pro")` (now with
`stream_usage=True`) against the dev-stack gateway and streamed a prompt via `astream_events`, reading
`usage_metadata` off the merged `on_chat_model_end` message:

```
LIVE usage_metadata: {'input_tokens': 12, 'output_tokens': 26, 'total_tokens': 38,
                      'input_token_details': {'cache_read': 0},
                      'output_token_details': {'reasoning': 24}}
VERDICT: PASS — real gateway run reports usage with stream_usage=True
```

So a real model call through the gateway populates `usage_metadata.total_tokens` — the exact value the
runner accumulates for the budget. Before this slice the field was absent (the gateway forwarded usage
but the api-side model never asked for it). The brake therefore has real token data to act on in
production; the deterministic tests above prove the halt logic on that data.

## Honest limits (recorded)

- **The default ceiling is uncalibrated.** `run_token_budget=2,000,000` is a conservative runaway
  backstop (~10× the 200k window), not a tuned cap — generous enough not to clip a legitimate
  multi-turn / bounded-fan-out run, low enough to bound a pathological loop. Precise calibration needs
  per-run token telemetry, which is the deferred persistence follow-up below.
- **Token totals are not persisted yet.** Enforcement is in-memory; a settled run shows
  `cap_exceeded` + `token_budget_exceeded` but not its token count, and `agent_runs.cost_usd` stays
  NULL. Persisting `total_tokens` (+ deriving `cost_usd`) is a recorded follow-up (a migration) that
  also unlocks calibration and a cockpit cost surface.
- **Fail-open on missing usage.** A provider that returns no `usage_metadata` yields 0 from
  `_usage_total`, so the brake never fires spuriously — the run stays bounded by `max_steps`/wall-clock.
  A provider that under-reports usage weakens the brake (the honest limit of trusting provider-reported
  tokens; a tokenizer-side estimate is a possible future hardening).
