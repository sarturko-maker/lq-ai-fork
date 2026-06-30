# Slice G — persist per-run token usage (ADR-F051 follow-up): verification

**What.** Migration **0079** adds `agent_runs.total_tokens` (nullable INTEGER). The runner's
cumulative model-token total (the value the Slice-F R4 brake already computes) is persisted at the
fenced terminal write (`settle_run`) on the normal path, exposed on `AgentRunRead.total_tokens`.
Closes the Slice-F observability deferral; enables calibrating `run_token_budget`. No new dependency,
no behavioural change beyond the additive column + persistence. `cost_usd` (dollars) stays NULL.

## Gate — deterministic, $0, zero-LLM (CI-enforced)

`tests/agents/test_agent_runner.py` (the existing token-budget tests, extended): a completed run
persists `total_tokens == 200` (2 turns × 100); a budget-disabled run persists `20,000` (proves
persistence is independent of the brake); a capped run persists `300` (the total that tripped the
budget). The fake `ScriptedToolCallingModel.usage_per_turn` drives deterministic per-turn usage.

**Migration round-trip (throwaway pgvector container — the dev DB is never touched, per CLAUDE.md):**
`alembic upgrade head` (0078→0079) → `downgrade 0078` (0079→0078, column dropped) → `upgrade head`
(re-added). Column verified present: `total_tokens | integer | nullable=YES`.

**Suite:** full `tests/agents/` green; `ruff` + `ruff format --check` + `mypy app` (209 files) clean.
The test-suite conftest runs `alembic upgrade head` on a fresh DB, so 0079 is exercised automatically.

## Honest limits

- **`cost_usd` (dollars) stays NULL** — deriving it needs per-model rates the runner does not see
  (the gateway computes per-call cost; attributing that to a run is the rejected routing-log-join).
- **Timeout / generic-error runs persist NULL** `total_tokens` — those paths bypass the normal return
  that carries the cumulative total (best-effort; the common completed/capped paths persist it).
- **No deploy was performed** — a real deploy needs the migration applied (rebuild api+arq+ingest);
  the gate covers it via the throwaway-pgvector round-trip + the conftest migration run.
