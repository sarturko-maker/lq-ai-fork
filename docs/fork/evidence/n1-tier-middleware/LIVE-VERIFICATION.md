# N1 live verification (ADR-F049) — read-only DATA tiers on the fork TierMemoryMiddleware seam

Dev stack, 2026-06-28. Four read-only DATA memory tiers (House Brief, Matter File, Matter Corrections,
Matter Roster) moved off the static system prompt onto a fork `TierMemoryMiddleware`. No migration, no new
dependency. IDs/counts only — no secrets, no clause text.

## 1. Deterministic gate (in the dev image, throwaway test DBs)

- **Full api suite:** `2857 passed, 38 skipped, 0 failed` (N0's 2851 + 6 new `test_tier_middleware.py`,
  which then grew to 7 with the folded ordering-lock test).
- **`tests/agents/test_tier_middleware.py`:** 7 passed — the pure appender (None / str / multi-block),
  the middleware through the REAL deepagents graph (async + sync paths), a **real-assembly ordering lock**
  (`system_prompt_for` base + `render_memory_tiers` → area method precedes both data tiers), and an
  empty-tier no-op-vs-no-middleware equality.
- **`tests/agents/test_agent_composition.py`:** all prompt-equivalence tests green (the pure-function
  oracle tests on `system_prompt_for` unchanged + byte-identical; the e2e `seen_messages` tests prove the
  tiers reach the model via the middleware, with the two ad-hoc joins hardened to `_seen_system_text`).
- **ruff** (root config) + **mypy `app`** (205 source files): clean.

## 2. Track-A live no-regression smoke (real DeepSeek through the gateway)

`LQ_AI_TRACK_A_N=1`, agent=`deepseek`, judge=`deepseek-pro`, N1 code mounted:
`1 passed in 108.82s` — all four Track-A scenarios (A1/A5/A7/A8) ran **terminal** through the full
`compose_and_execute_run` path with `TierMemoryMiddleware` live; no crash. Rig-hygiene assertions held.
Per ADR-F015 rates are findings and N1 is **not** a baseline freeze, so the N=1 packets are not re-frozen.

## 3. Rebuilt production image — clean boot (api + arq-worker)

Rebuilt `api` + `arq-worker` on the N1 code (`docker image prune -f` → 6.23 GB reclaimed):
- **api:** Healthy; no import/traceback at boot (the new `tier_middleware` import resolves);
  `agent checkpointer ready` + `agent memory store ready (AsyncPostgresStore, filter-only)`;
  `Application startup complete`.
- **arq-worker:** no import error; `Starting worker for 9 functions: … agent_run_job …`.

## 4. Real run through the rebuilt arq worker (the production path)

A real matter-bound run (`POST /api/v1/agents/runs`, matter `S4 Acme MSA`, `model_alias=deepseek`,
`max_steps=4`, prompt "Reply with exactly the single word: ack."):

- **Accepted:** `202`, `run_id = 4e3b0bda-…`.
- **Worker:** `agent_run_job` executed in **5.17s** (`executed: True`).
- **Run row:** `status = completed`, `final_answer = "ack"`, 1 step, no error.

This exercises the entire N1 production path **in the rebuilt worker**: `compose_and_execute_run` →
`render_memory_tiers` → `TierMemoryMiddleware` → `execute_agent_run(middleware=…)` → `build_deep_agent`
(`**kwargs`) → `create_deep_agent` → the middleware's `awrap_model_call` appends the tier block on the real
gateway call — completing cleanly with a real model.

## Gate status

- Prompt-equivalence (tiers render byte-identical + reach the model, same inter-tier order, degradation):
  ✅ deterministic (`test_tier_middleware.py` + composition e2e) + ✅ live.
- Nothing regresses: ✅ full api suite 2857/38/0; Track-A live smoke green.
- Adversarial review (4-dim × verify, 15 agents): **0 blockers / 0 should-fixes**; 4 nits folded; 7 refuted.
- One documented, benign delta: the tiers now render after `BASE_AGENT_PROMPT` + the area suffix.
