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
  - `profile={"max_input_tokens": 200_000}` — a conservative operating
    point under the gateway's DECLARED request cap (1e6 chars ≈ 250k
    tokens; config-only today, not yet enforced), not M3's native window,
    which is 1M tokens (research-doc correction: the
    `deepagents-ecosystem.md` "<170k window" claim was wrong for M3).
    Also makes post-compaction KEEP fraction-based — intended
  - `<think>` blocks must round-trip verbatim in history (verified live);
    never strip them api-side
  - deepagents system prompt overhead ≈ 6.5k input tokens per gateway call
- **L1 uptake (settled `agent_run_steps`) — baseline 2026-06-12, N=20 per
  scenario, 80/80 cycles valid** (full tables + telemetry:
  `docs/fork/evidence/f0-s9/matrix.md`; raw cycles in `results/`).
  Provenance notes, on the record: (a) the batch_fanout N=20 cell is the
  5 pre-flight cycles + 15 same-harness/same-SHA cycles (one session,
  same instruction sha — the manifest records the last invocation);
  (b) the N=20 baseline ran against the dev stack's PRE-SLICE service
  images — the slice's api/gateway pins are protective (Responses-API
  pin, compaction profile, id synthesis) and none alter MiniMax-M3
  request/response behavior on these scenarios; services were rebuilt
  on the slice code afterwards and a post-deploy N=1x4 spot-check
  confirmed identical behavior (results in `results-postdeploy/`);
  (c) after review-driven scoring fixes (answer metrics judge the
  visible answer with `<think>` stripped; fan-out strategy requires
  distinct per-item task calls; paraphrase-matchable fragment dropped)
  ALL 80 cycles re-scored IDENTICALLY — the numbers below are robust to
  the stricter scoring:
  - positive grounding: fired 20/20; `read_arg_correct` 18/18 (2 cycles
    answered from search alone — n/a, not misses); cap + exclusions
    quoted in the answer 20/20
  - task-scoped fan-out: `task` fired 20/20, strategy `one_per_item`
    20/20, all four laws AND terms assembled 20/20 — oscar's "prescribed
    procedure works" finding replicated on our substrate at N=20
  - negative control: ZERO noise across search/read/task, 20/20 each
    (oscar's 0/80 noise gate replicated)
  - **mismatch — the one discriminating signal**: `no_fabricated_esop_terms`
    20/20 (answers honestly that no such document exists) BUT
    `read_noise_on_mismatch` 1/20 — M3 read the irrelevant document in
    19/20 cycles before declining. This is oscar's MiniMax wrong-grounding
    eagerness (+25pp wrong-skill, MiniMax-only) replicated on M3: eager
    verification, honest answers. No threshold set tonight (decision 1 —
    bars never tighter than the CI and only after maintainer ratification);
    flagged as the metric to watch when family #2 lands.
  - durations: negative 6–18s, grounding 9–21s, mismatch 12–18s,
    fan-out 27–58s; zero timeouts, zero stranded runs, zero hygiene
    failures across 80 cycles.
- **L2 grounding-substance judge**: deferred (budget rule 6) — the masked
  judge is designed (`f0-s9-eval-reuse.md` §3) and the harness leaves the
  seam; run it when the matrix re-runs with a topped-up plan.
- **Cost telemetry**: standard rates $0.60/$2.40 per MTok (launch promo
  half); negative-control cycle ≈ $0.005 mean, fan-out ≈ $0.045 mean —
  full corrected telemetry in matrix.md (the original windows
  double-counted one row per cycle; fixed and re-derived in review).
  Cost accounting currently hardcodes MiniMax rates — add per-
  routed_model rates when family #2 lands (cycle JSONs record
  routed_model, so historic cells stay correctable).

## Kimi K2.x (Moonshot) — design target for family #2 — BLOCKED-ON-KEY

Recommended second family (`f0-s9-eval-reuse.md` §3: strongest
independently-verified open tool-calling record; OpenAI-compatible serving
avoids the Anthropic-adapter blocker; non-interleaved thinking gives
failure-mode contrast with M3's think-retention style).

**To fill this row** (the harness takes the model as a pytest parameter;
one known gap: cost accounting hardcodes MiniMax rates — add Moonshot
rates to `evals/runner.py` for honest spend numbers):

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
4. Run the two runnable curl probes now embedded in
   `docs/fork/evidence/f0-s9/gateway-conformance.md` (substitute the
   alias) — Moonshot's own K2-Vendor-Verifier is the upstream precedent
   for this exact check.
5. `LQAI_EVAL_MODELS=kimi LQAI_EVAL_N=10 pytest evals/test_qualification.py`
   (N=10 second-family per oscar-gc's ADR-109 cell-size shape — an
   EXTERNAL project's ADR, not in this repo's docs/adr/; quote ±29pp).

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
