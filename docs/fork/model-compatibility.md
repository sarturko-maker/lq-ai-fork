# Model compatibility matrix (F0-S9 qualification gate)

`qualified(model) = external screening prior (cited, not run) + three-layer
on-stack suite through the gateway` (ADR-F004; design in
`docs/fork/research/f0-s9-eval-reuse.md` §3). Per-model rows with config
notes, Goose/OpenHands style — NOT a leaderboard. Qualification is always
per-(model, harness-profile) pair; the profile each row was measured with is
named. Re-run the suite on any model, gateway, or deepagents change
(`api/evals/README.md`).

Harness comparability: LangChain's own `libs/evals` suite is
pytest-parametrized test functions filtered by category (`tool_use` 53,
`memory` 22, `file_operations` 13…) — our harness is the same shape; our
four scenarios sit in their `tool_use`/`retrieval` categories. No public
benchmark measures subagent/task uptake; that axis is in-house by necessity.

## MiniMax-M3 (gateway `minimax/MiniMax-M3`, aliases smart/fast/budget)

- **Harness profile measured**: the EMPTY baseline profile
  (`api/app/agents/profiles.py` — deliberate; tuning enters with a measured
  delta, never before).
- **External prior**: NONE — MiniMax-M3 appears on no independent
  tool-calling board (not BFCL, not tau2; all published numbers are
  vendor-run). This absence is why the on-stack suite is load-bearing.
- **L0 serving conformance — PASS** (live probes 2026-06-12,
  `docs/fork/evidence/f0-s9/gateway-conformance.md`):
  - streamed tool-call frames structural; opening deltas carry real,
    stable ids; arguments schema-valid JSON
  - reasoning is dual-channel (inline `<think>` in content + `reasoning`
    delta field); both survive the gateway in BOTH directions, including
    history resend with tool results (the deepagents#1630 failure class
    does not occur on this stack)
  - `finish_reason=tool_calls` correct; usage block carries
    `reasoning_tokens` detail
- **Config notes (required for any M3 deployment)**:
  - `use_responses_api=False` on ChatOpenAI (deepagents#3190)
  - `profile={"max_input_tokens": 200_000}` — the GATEWAY envelope is the
    binding constraint (1e6-char request cap ≈ 250k tokens), not M3's
    native window, which is 1M tokens (research-doc correction: the
    `deepagents-ecosystem.md` "<170k window" claim was wrong for M3)
  - `<think>` blocks must round-trip verbatim in history (verified live);
    never strip them api-side
  - deepagents system prompt overhead ≈ 6.5k input tokens per gateway call
- **L1 uptake (settled `agent_run_steps`)**: see
  `docs/fork/evidence/f0-s9/matrix.md` — numbers land with the baseline run.
- **L2 grounding-substance judge**: deferred (budget rule 6) — the masked
  judge is designed (`f0-s9-eval-reuse.md` §3) and the harness leaves the
  seam; run it when the matrix re-runs with a topped-up plan.
- **Cost telemetry**: standard rates $0.60/$2.40 per MTok (launch promo
  half); negative-control cycle ≈ $0.004; fan-out cycle cost in matrix.md.

## Kimi K2.x (Moonshot) — design target for family #2 — BLOCKED-ON-KEY

Recommended second family (`f0-s9-eval-reuse.md` §3: strongest
independently-verified open tool-calling record; OpenAI-compatible serving
avoids the Anthropic-adapter blocker; non-interleaved thinking gives
failure-mode contrast with M3's think-retention style).

**To fill this row** (everything else is ready — the harness is
model-parametric):

1. Add the provider to `gateway.yaml` (key stays gateway-only):

   ```yaml
   - name: moonshot
     type: openai
     base_url: https://api.moonshot.ai/v1
     api_key_env: MOONSHOT_API_KEY
     tier: 4
     models:
       - kimi-k2.5  # pick the current K2.x instruct id
   model_aliases:
     kimi:
       primary: {provider: moonshot, model: kimi-k2.5}
       fallback: []
   ```

2. `MOONSHOT_API_KEY` into `.env`, restart the gateway.
3. Register a harness-profile key for the alias in
   `api/app/agents/profiles.py` (`openai:kimi`, empty baseline first).
4. Run L0 probes (the two curl probes in
   `docs/fork/evidence/f0-s9/gateway-conformance.md`) — Moonshot's own
   K2-Vendor-Verifier is the upstream precedent for this exact check.
5. `LQAI_EVAL_MODELS=kimi LQAI_EVAL_N=10 pytest evals/test_qualification.py`
   (N=10 second-family per ADR-109 shape; quote ±29pp).

## Disqualifying conditions (any model)

- L0 failure (malformed/text-shaped tool calls, empty streamed ids the
  gateway must not have to synthesize for correctness, schema-invalid
  args) — disqualified, never toolshimmed (Goose toolshim ceiling ~41–48%).
- Hard noise-gate breaks on negative scenarios (>1/N with cycles logged).
- A low score indicts the SERVING LAYER first (vLLM/K2 precedent: <20%
  parse rate from serving bugs) — re-run L0 before reading L1.

## Deferred axes (recorded, not measured tonight)

- **Late-flow action-tool canary** (oscar's hardest affordance): F0 has no
  action-tool surface (matter tools are read-only; R6-granted action tools
  land in F1) — the canary joins the suite then.
- **Compaction survival** (does the model behave through a summarization
  event): needs a long-context fixture matter; the `max_input_tokens`
  profile landed tonight makes the trigger window-relative and testable.
- **L2 masked judge** on grounding substance — budget rule 6.
