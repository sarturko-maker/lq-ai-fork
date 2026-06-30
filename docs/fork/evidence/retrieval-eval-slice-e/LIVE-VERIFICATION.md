# Slice E — cost-aware fan-out + a fan-out-quota brake: verification (ADR-F049, ADR-F015 finding)

**What.** F2 Phase-3 Slice E adds (S1) a per-document `~k tokens to read` estimate in the matter
inventory, (S2) an `estimate_read_cost` guarded tool, (S3) the `retrieval-strategy` doctrine, and
(S4) a `FanOutQuotaMiddleware` that caps subagent (`task`) dispatches per run. S5 (wiring R4 into a
live per-run token budget) is deferred. Gate (`plans/RETRIEVAL-MEMORY-eval-first.md`): *A7 strategy
choice; a runaway-fan-out cost test* — the runaway-fan-out cost test is the hard, CI-enforced gate;
A7 strategy is an ADR-F015 finding.

## The hard gate — deterministic, $0, zero-LLM (CI-enforced)

The runaway-fan-out cost test is `tests/agents/test_fan_out_middleware.py`:

- **Unit (real `FanOutQuotaMiddleware`):** allows exactly `quota` `task` dispatches, then DENIES the
  next with a model-visible refusal `ToolMessage` (`status="error"`) — the handler never runs, so no
  subagent spawns; non-`task` tools pass straight through and never count against the quota;
  `quota <= 0` disables the brake; the sync path matches the async path.
- **Integration (REAL deepagents graph + a subagent):** proves the builtin `task` tool — which
  bypasses the `guarded_dispatch` chokepoint — IS routed through our `awrap_tool_call`, so the quota
  can deny fan-out before a subagent runs. This is the load-bearing assumption of the whole slice,
  confirmed both at the source (`langchain.agents.factory` builds the `ToolNode` with a
  `wrap_tool_call` chain from every middleware overriding the hook, over `available_tools` which
  includes the `SubAgentMiddleware`'s `task` tool) and end-to-end here.

Plus `tests/agents/test_agent_tools.py`: the read-cost render in the inventory; `estimate_read_cost`
SUM/cap math, whole-matter vs named, matter+owner scope isolation (a sibling matter and a
foreign-owner file maliciously joined in are both invisible — 404-conflated), read-in-full vs
fan-out suggestions, audit body-free; the grant set + model-facing schema include the new tool.

**A real bug the tests caught:** Postgres `LEAST(NULL, n)` returns `n` (LEAST/GREATEST skip NULL
args), so an un-ingested file's NULL `character_count` phantom-counted as the read cap (40 000) —
fixed with `coalesce(character_count, 0)` before `least`.

**Suite:** full `tests/agents/` **683 passed / 38 skipped / 0 failed** (up from Slice D's 671);
`ruff check api scripts` + `ruff format --check api scripts` + `mypy app` (209 files) all clean.

## Live verification — dev stack, real DeepSeek (best-effort finding)

The provider-marked live scenario `tests/agents/scenarios/test_subagent_scenarios.py` runs the
multi-document **RFQ** matter (buyer instructions + two vendor proposals + draft terms) through the
production loop against the dev-stack gateway (`deepseek-pro`). This exercises the slice end-to-end:
the new `RETRIEVAL_STRATEGY_DOCTRINE` is injected, `estimate_read_cost` is granted, and the
`FanOutQuotaMiddleware` (default ceiling 8) is active for the run (the area configures a
`document-researcher` subagent, so the quota middleware is installed).

**Result: PASS** (`1 passed in 43.96s`). The real agent run completed without crash or regression —
the new doctrine + the new tool + the fan-out quota integrate cleanly, and the default ceiling of 8
did not impede normal delegation behaviour on this matter. (Per ADR-F015 the *delegation shape* is a
recorded finding, not a pass/fail bar; the live signal here is that the slice's three changes are
live and benign end-to-end.)

## A7-large — designed, deferred (honest scope)

The strategy research (`research/fanout-for-document-work-vs-code.md` §6) designs an **A7-large**
Track-A variant — an over-window corpus where inline analysis must miss documents and fan-out must
win — as the measurement for "fanned out at the right time." It is **deferred** as its own eval
finding: (a) DeepSeek's tier-4 model does not autonomously fan out even on the small A7 corpus (E1
baseline: A7 autonomous-fan-out 0/10, judged inline-appropriate), so a live A7-large would largely
re-confirm that strategy-selection finding rather than gate this slice; (b) building a 30–100-doc
over-window fixture and a live matrix freeze is its own slice. The live RFQ subagent scenario above
is the strategy live finding for Slice E; the deterministic quota test is the safety gate.

## The honest R4 gap (S5 deferred)

R4 (the per-action cost cap, `guard.py`) is still a documented **no-op**: there is no per-run
token/dollar budget enforced anywhere. Slice E makes runaway fan-out *unlikely and bounded* (the
pre-flight estimate + the doctrine + the quota ceiling) but **not impossible** — a hard token stop
needs S5 (aggregate `inference_routing_log` tokens per run + halt at a ceiling; `agent_runs.cost_usd`
exists but is NULL and the runner captures no usage today). Recorded so cost-safety is not
over-claimed.
