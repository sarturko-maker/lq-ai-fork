# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## MORNING REPORT — overnight autonomous run of 2026-06-12 (F0-S9)

The maintainer authorized a 5–6h autonomous run executing F0-S9 end-to-end.
Progress tracker (the run's own record; decisions taken on the maintainer's
behalf are flagged ⚖ and need morning ratification):

- [x] 0. Research docs + ADR-F004 read; branch `fork/f0-s9-eval-gate` from `bfb82be`
- [x] 1. Gateway conformance VERIFIED LIVE, both directions (probes archived in
      docs/fork/evidence/f0-s9/gateway-conformance.md). MiniMax-M3 supplies real stable
      tool-call ids; defensive id-synthesis added anyway (deepagents#3587, gateway-owned fix).
      `use_responses_api=False` + `max_input_tokens=200k` profile + empty MiniMax HarnessProfile
      (openai:{smart,fast,budget}) + langgraph floor >=1.2.4. ⚖ CORRECTION to the research doc:
      M3's native window is 1M tokens (the "<170k" claim was wrong) — the GATEWAY request cap is
      the binding constraint; 200k chosen from that envelope.
      Gateway adapter file 28 tests passed at the time; FULL gateway suite at gate time:
      576 passed/2 skipped + mypy --strict clean (39 files). api agents suite 107 passed/1 skipped.
- [x] 2. Fixtures: 2 matters seeded (idempotent uuid5 seeder, ingest pipeline bypassed,
      FTS verified) + 4 scenario JSONs with machine-checkable expectations.
- [x] 3. Harness end-to-end in api/evals/ (ZERO new deps ⚖ decision 3 taken): smoke cycle
      6.2s/$0.004; scorer unit tests 11/11. Telemetry: deepagents system prompt ≈6.5k input
      tokens per gateway call.
- [x] 4. Pre-flight N=5 (batch_fanout): variance gate PASS, ZERO disagreements on all 4 metrics.
      ⚖ BUDGET DECISION (rule 6c): full N=20x4 at projected ~$1.9 — authorized and run.
- [x] 5. **Baseline matrix COMPLETE: 80/80 cycles valid, zero timeouts, zero stranded runs.**
      fan-out 20/20 one_per_item · negative-control noise 0 · grounding 20/20 (args 18/18) ·
      mismatch: no-fabrication 20/20 BUT read-noise fired 19/20 — oscar's MiniMax
      wrong-grounding eagerness REPLICATED on M3 (eager verification, honest answers).
      ⚖ No threshold set (decision 1) — ratify bars against these numbers.
      Docs: docs/fork/model-compatibility.md + docs/fork/evidence/f0-s9/matrix.md.
- [x] 6. Full gate run: api suite 2036 passed/3 skipped; gateway 576 passed/2 skipped +
      mypy --strict clean; web untouched. Fresh-context adversarial review (35 agents,
      5 dimensions incl. the gateway security pass): 30 raised, 27 confirmed real —
      ALL fixed in-slice (stateful id-synthesis; answer metrics judge the visible answer
      with <think> stripped; routing-window double-count fixed and all 80 cycles' telemetry
      re-derived; failed runs no longer scored; paraphrase fragment dropped; docs honesty
      pass) — and the 80-cycle baseline RE-SCORED IDENTICALLY under the stricter scoring
      (zero metric changes; corrected spend $1.69). Services rebuilt on slice code +
      post-deploy spot-check. PR #41 — merged on green (see merge commit on main).
- [ ] 7. F1 re-plan draft PR (drafted at /tmp/s9-overnight/F1-replan.md → own PR after S9 merge)
- [ ] 8. F1-S1 exploration notes (only if context allows)
- **Spend tonight: ≈$1.75 standard-rate upper bound (≈$0.88 at the current launch promo)**
  of the $10 plan — probes $0.001 + smoke $0.004 + matrix $1.69 (corrected after the
  routing-window double-count fix) + post-deploy spot-check ~$0.05. Prior plan consumption
  from dev work is not visible to us; check the MiniMax console.

### Morning checklist (maintainer)

1. Ratify/override the ⚖ decisions above (esp.: empty-profile baseline, no-thresholds-yet,
   the mismatch read-noise signal — is 19/20 eager-read acceptable behavior or a bar?).
2. Add a second-family key to fill the Kimi K2.x row — the EXACT gateway recipe is in
   docs/fork/model-compatibility.md (provider entry + alias + profile key + L0 probes +
   `LQAI_EVAL_MODELS=kimi LQAI_EVAL_N=10`).
3. Review/edit the F1 re-plan draft PR before any F1 work.
4. Check MiniMax plan balance; top up if family-#2 cells + L2 judge runs are wanted.

## State (end of F0-S9)

- S9 = PR #41 (merged; main carries the squash commit). F0 closes with S9 — F1 re-plan
  drafted for ratification (CLAUDE.md: re-plan at milestone boundaries).
- Dev stack: 8 services healthy; DB at migration 0051 (NO migrations tonight — decision 4);
  eval fixture matters seeded in the dev DB ("S9 Eval — Single Doc 9001",
  "S9 Eval — Batch Fanout 9002" — re-seed anytime via `python -m evals.seed_fixtures`).
- Gateway aliases smart/fast/budget → minimax/MiniMax-M3; ONLY the MiniMax key is real.
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Web untouched this slice (bundle = merged S8).
- Suites at gate time: api 2036 passed/3 skipped; gateway 576 passed/2 skipped + mypy
  --strict clean; web gates not re-run (no web changes).
  ```bash
  docker run -d --name s9pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s9pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```

## Done (F0-S9, this slice)

- Gateway: defensive tool-call id synthesis for opening deltas (`_ensure_stream_tool_call_ids`),
  4 conformance tests pinning id-synthesis/pass-through/reasoning-round-trip both directions.
- api: `use_responses_api=False` + `profile={"max_input_tokens": 200k}` in
  `build_gateway_chat_model`; `api/app/agents/profiles.py` (empty MiniMax-M3 HarnessProfile —
  tuning enters this seam only WITH a measured delta); langgraph floor `>=1.2.4`.
- `api/evals/`: fixtures + idempotent seeder, 4 scenarios, runner, deterministic scorers,
  pytest driver, report generator, README. The model is a pytest parameter (DI).
- Baseline matrix N=20x4 (above) + `docs/fork/model-compatibility.md` +
  `docs/fork/evidence/f0-s9/` (probes, smoke, 80 cycle JSONs, matrix.md).

## Next slice — pick up exactly here

1. Maintainer ratifies morning checklist; F1 re-plan PR gets edited/merged.
2. First F1 slice per the (edited) re-plan: **F1-S1 run-lifecycle durability**
   (arq + `max_tries=1` + `durability="sync"` + heartbeat/lease + orphan sweep + cancel +
   #3789 cancel-mid-tool-call regression + checkpoint retention). Read the re-plan draft
   and `docs/fork/research/deepagents-ecosystem.md` §1.4 before planning it.
3. If a Moonshot key landed: fill the Kimi K2.x matrix row first (one pytest command).

## Carry-overs / review deferrals (unchanged from pre-S9 + new)

- NEW: mismatch read-noise (19/20) — candidate doctrine/threshold work, measurement-first
  (subtractive wording only, trigger-surface placement; ADR-F004).
- NEW: L2 masked judge designed but not run (budget); seam exists in the harness.
- NEW: eval scenarios cover no action-tool canary (no F0 action surface) and no compaction
  survival — both join the suite when their substrate lands (F1).
- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass) — F1 fan-out.
- Anthropic adapter: tool_use/tool_result translation pending — only matters if a Claude
  family joins the matrix.
- No cancel endpoint; stranded `running` runs deadlock threads — F1-S1 (first slice).
- Checkpoint rows invisible to alembic, not cleaned on delete — F1-S1.
- Conversation compaction (ADR-F003) — F2. No audit rows for run kick-off. MessageBubble
  legacy default-DOMPurify. Parallel-fan-out ribbon shares one buffer — F1-S4.
- wave-c-matters test 3 pre-existing hang — Backlog. S6 deferrals unchanged.

## Gotchas (carried + new)

- **`cy.intercept` BUFFERS streamed responses** — never intercept the SSE route under liveness test.
- **The shell scrolls `#lq-main`, NOT the document** — resolve the scroll container.
- **Cypress screenshots on the agents surface need `capture: 'viewport'`**.
- **Cypress memory-pressure recipe**: stop arq-worker;
  `ELECTRON_EXTRA_LAUNCH_ARGS='--js-flags=--max-old-space-size=512'`;
  `CYPRESS_LQ_AI_MATTER_NAME="S5 PreSeed 1781169832"` for f0-s4/s5/s7 (f0-s3 self-seeds);
  `--config video=false,numTestsKeptInMemory=0`; restart arq-worker after. Wedged workers:
  `docker compose restart ingest-worker arq-worker`.
- Web container serves a pre-built bundle — rebuild before debugging UI changes.
- `gh pr create` defaults to the FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork`
  AND `--head <branch>` (ADR-F001). jq is NOT installed — parse `gh --json` with python3.
- Branch switches with uncommitted edits destroy work; verify branch before committing.
- **.env S3 keys** stay commented out (backup `.env.bak-f0-s4`).
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. Containerized
  pytest needs `skills/` at `/skills`; ruff needs repo-root `ruff.toml`.
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers.
- NEW: **files written by containers into mounted volumes are root-owned** — `chown` inside
  the container (the README's run command now ends with the chown; the aggregate command
  writes via container stdout so `>` ownership is the host user's).
- NEW: **GET /agents/runs/{id} returns `{run, steps}`**, not a bare run row.
- NEW: **`files.ingestion_status` CHECK allows only pending/processing/ready/failed** —
  seeders use 'ready'. ORM models don't declare FK edges; flush per dependency level.
- NEW: eval runs and Cypress still never run simultaneously; eval cycles run SEQUENTIALLY
  (flood brake = 3; routing-log window correlation needs an idle stack).
- MiniMax-M3 emits `<think>` inline in content AND a `reasoning` delta field; both round-trip
  the gateway VERBATIM (verified live + pinned by tests). `final_answer` retains `<think>`.
