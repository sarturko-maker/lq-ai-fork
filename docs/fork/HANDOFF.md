# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## OVERNIGHT AUTONOMOUS RUN (2026-06-12, maintainer-authorized)

The maintainer is asleep and directed: run autonomously as long as possible (5–6h target), get as
much done as possible. NOBODY is available for questions: any choice only the maintainer can make →
take the pre-made default below, record it in § Decisions taken, and keep moving — never block.
Update the § Progress tracker after EVERY completed step and rewrite this file before any
compaction; compaction will happen several times tonight and this file is the only thread.

### Pre-made decisions (defaults taken on the maintainer's behalf — ratify in the morning)

These resolve `docs/fork/research/f0-s9-eval-reuse.md` §4 for tonight:

1. **Thresholds**: hard bars only where variance is known — L0 schema validity ≈100%, noise on
   negative scenarios 0 (or ≤1/N with the cycle logged). L1 uptake bars are set AFTER the first
   MiniMax-M3 baseline, never a priori, never tighter than the CI.
2. **Second family**: Kimi K2.x is the design target, but **only MINIMAX_API_KEY is real in .env**
   (Anthropic/OpenAI/Azure are placeholders — verified 2026-06-12). Build the harness fully
   multi-model (model alias is a pytest parameter; gateway provider entry shape documented) and
   leave family #2 cells BLOCKED-ON-KEY. Do NOT add keys or providers pointing at unpaid endpoints.
3. **Dependencies**: ZERO new deps tonight. Hand-roll the single L2 judge call (one gateway chat
   completion). `openevals` adoption stays a maintainer decision.
4. **Arg-correctness source**: parse doc IDs from the existing `agent_run_steps.summary` digest
   (option a). NO migration tonight (avoids the rebuild-3-workers dance unattended).
5. **Gateway `<think>` pre-check**: in-slice, FIRST task (see sequence). Gateway is
   security-sensitive — if it needs a fix, give the diff the extra security review pass (ADR-F005).
6. **BUDGET — the binding constraint**: the MiniMax key is a USD 10 TOTAL token plan, partially
   consumed by all dev work to date. Rules: (a) pre-flight N=5 on ONE highest-discrimination cell
   first; (b) estimate spend from the gateway routing-log token counts × MiniMax published prices
   before every escalation; (c) full matrix N=20×4 ONLY if projected total stays under ~$5;
   otherwise run N=10×4 or N=5×4 and quote CI half-widths honestly (±29pp at N=10, ±43pp at N=5 —
   oscar's numbers); (d) if the key dies mid-run (4xx from provider), ship the harness + completed
   cells with honest counts — a partial baseline with a working harness is a SUCCESS.

### Sequence (each step independently shippable; commit early and often)

0. Read `docs/fork/research/f0-s9-eval-reuse.md` (the S9 design), then
   `docs/fork/research/deepagents-ecosystem.md` (Deep Agents ecosystem survey — check ADOPT-NOW
   and LANDMINES sections before writing harness code), then ADR-F004. Branch
   `fork/f0-s9-eval-gate` from main.
1. **Gateway conformance — THREE tests, all prerequisites to any score being real**
   (sources + issue links in deepagents-ecosystem.md §1.3):
   (a) every streamed tool-call delta carries a non-empty, unique, STABLE id — synthesize if the
   provider omits it (empty ids hard-fail the deepagents `task` tool; upstream put the fix on
   gateways); (b) our ChatOpenAI construction sets `use_responses_api=False` against the gateway
   (newer langchain-openai defaults to the Responses API → "No generations found in stream");
   (c) reasoning/`<think>` content round-trips the FULL loop — not stripped from deltas AND
   accepted echoed back on assistant messages with tool results (the risk is the HISTORY we
   resend, not the response). Fixes are security-pass diffs (gateway), rebuild + verify live.
   ALSO from the research: set `model.profile["max_input_tokens"]` on the gateway-injected model
   (deepagents falls back to a 170k summarization trigger for unprofiled models — past M3's real
   window, compaction never fires); write a MiniMax-M3 `HarnessProfile` — qualification is
   per-(model, profile) pair, untuned scores are noise (LangChain measured 10–20pt profile
   swings); raise the `langgraph` floor in api/pyproject.toml to `>=1.2.4` (subagent-interrupt
   fix needs deepagents 0.6.7 + langgraph 1.2.4 TOGETHER; we run 1.2.4 but the floor says >=1.0).
   Check deepagents' `libs/evals` tool_use category for scenario/metric shapes worth mirroring
   (comparability) before authoring ours — adopt shapes, not the package.
2. **Scenario fixtures**: deterministic seed script for 2 matters (one single-doc with the
   f0-s4-msa.pdf-style liability-cap fixture; one multi-doc ~4 small contracts for fan-out) +
   the 4 scenario definitions (positive grounding / batch fan-out / negative control / MISMATCH)
   as JSON expectations (should_fire / should_not_fire / canonical_arg / min_count / strategy).
3. **Harness** in `api/evals/` (NOT under api/tests/ — must not collect in CI): pytest
   parametrize(scenario × model × N) → POST /agents/runs → poll to settle → score. L1 scorers =
   plain Python over settled `agent_run_steps` rows (paired positive/noise fields, invoked vs
   invoked-correctly, S2N, `parent_step_id` ancestry for task compliance). L0 checks = structural
   tool-call frames + schema-valid args (never regex over text). Runner hygiene: every run asserts
   a real assistant message or a surfaced gateway error (oscar's silent-403 lesson). Pin the agent
   instruction SHA into results. Results land as JSON + a generated markdown matrix in
   `docs/fork/evidence/f0-s9/`.
4. **Pre-flight N=5** on the highest-discrimination cell (batch fan-out × MiniMax-M3). Variance
   gate: ≤1 verdict disagreement per metric. Then the budget decision (rule 6) and the baseline
   matrix at the chosen N. L2 masked judge only on grounding-substance fields, only if budget
   allows after L1.
5. **Compatibility matrix** doc (per-model rows; MiniMax-M3 filled, Kimi K2.x row present and
   marked blocked-on-key) + MILESTONES S9 ✓ entry + this file rewritten for end-of-S9.
6. **Full ADR-F005 gate + PR + merge**: containerized api suite (the harness must not break it),
   web untouched (state it), fresh-context adversarial review workflow on the diff, live evidence
   = the eval results themselves + the <think> verification, merge on green
   (`--repo sarturko-maker/lq-ai-fork --head fork/f0-s9-eval-gate`; parse checks with python,
   jq is NOT installed, awk breaks on spaced check names).
7. **STRETCH 1 (docs-only)**: F0 milestone close-out + F1 re-plan draft — F0 ends with S9, and
   CLAUDE.md re-plans at milestone boundaries. Draft the F1 slice list (run-lifecycle durability
   first per the #36 re-plan: arq migration, orphan sweep, cancel; then Cockpit v0; check the
   deepagents-ecosystem research's IMPACT section for shape changes) as a PR for the maintainer's
   morning edit. Do NOT start F1 implementation tonight.
8. **STRETCH 2 (only if all above merged and context is fresh)**: F1-S1 exploration notes
   (read-only: arq patterns in the existing workers, runner seams for worker migration) appended
   to the F1 re-plan PR.

### Hard rules for the night (violations corrupt the stack — CLAUDE.md, restated)

- NEVER `docker compose down -v`; NEVER host-side alembic against the dev DB; no migrations
  tonight (decision 4 avoids the need).
- Eval runs hit the LIVE dev stack — do not run Cypress and the eval matrix simultaneously
  (memory pressure); stop arq-worker only during Cypress, never during eval runs (uploads/ingest
  not needed for evals, but a wedged worker poisons later steps — restart pattern is in Gotchas).
- If the stack wedges and one targeted service rebuild doesn't recover it: record exact state in
  § Progress tracker, commit everything shippable, end the run cleanly. A clean stop beats a
  thrashed stack.
- Provider keys exist only inside the gateway; cross-user = 404; audit rows carry counts/types/IDs
  only; model output is untrusted input — unchanged, always.

### Progress tracker (update after every step — the morning report reads this)

- [ ] 0. Research docs + ADR-F004 read; branch created
- [ ] 1. Gateway <think> round-trip: verified OK / fixed (which?)
- [ ] 2. Scenario fixtures seeded
- [ ] 3. Harness runs end-to-end (one smoke cycle)
- [ ] 4. Pre-flight N=5 passed variance gate; budget decision: N=__ (projected $__)
- [ ] 5. Baseline matrix complete: cells __/__; matrix doc written
- [ ] 6. S9 PR #__ merged
- [ ] 7. F1 re-plan draft PR #__
- [ ] 8. F1-S1 exploration notes
- Spend estimate at end of night: $__ of the $10 cap

### Morning checklist for the maintainer

1. Ratify/override the 6 pre-made decisions above (esp. thresholds-after-baseline and zero-dep).
2. Add a second-family key if you want family #2 cells: Moonshot (Kimi K2.x) direct or via an
   OpenAI-compatible reseller — gateway provider entry shape will be documented in the S9 PR;
   then `pytest api/evals -k kimi` fills the matrix row.
3. Review the F1 re-plan draft PR (if the night got there) and edit slices before any F1 work.
4. Check § Progress tracker + spend estimate; top up the MiniMax plan if the baseline was cut to N<20.

---

## State (2026-06-12, after F0-S8 + S9 re-scope)

- Merged to main through **#39** (`263705a`): #38 = F0-S8 (matter create-in-place + conversation
  readability — composer docked bottom, markdown thinking, claude.ai-style folding, ADR-F002
  blank-workspace removal); #39 = S9 re-scope docs (model qualification gate).
- **S9 is re-scoped by maintainer directive** (2026-06-11): the model is dependency injection; do
  NOT redo oscar-gc's evals (local AGPL clone at `/home/sarturko/oscar-gc-review` — findings yes,
  code never); capability priors cited from BFCL V4/tau2; harness = plain pytest over settled
  `agent_run_steps`. Full design + open decisions: `docs/fork/research/f0-s9-eval-reuse.md`.
- **Deep Agents ecosystem survey**: `docs/fork/research/deepagents-ecosystem.md` (official
  middleware/backends state vs our 0.6.8 pin, community landmines, memory adopt-vs-build for F2,
  durability patterns for F1) — read before S9 harness code and before the F1 re-plan.
- Dev stack: 8 services healthy; DB at migration **0051**; gateway aliases `smart`/`fast`/`budget`
  → `minimax/MiniMax-M3`; ONLY the MiniMax key is real (USD 10 token plan — budget rules above).
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Web gates: `cd web && npm run check` (0 errors) + `npm run test:frontend -- --run` (778/778).
- API suites containerized (no host 3.12):
  ```bash
  docker run -d --name s9pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s9pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```

## Done (F0-S8 + research, this week)

- F0-S8 (#38): "+ New matter" in place (modal goto lifted to callers); blank workspace REMOVED
  (ADR-F002); composer docked bottom + auto-scroll to conversation tail in the `#lq-main` scroll
  container; thinking = markdown (mdSafe path); tool steps collapsed to stepDigest rows; live
  ribbon auto-expanded/clamped. f0-s3 rewritten (creates its matter via the modal). Web 778/778;
  f0-s3/s4/s5/s7 green; 27-agent review 22 raised / 0 confirmed.
- S9 re-scope (#39): research doc + MILESTONES/HANDOFF aligned to the qualification-gate design.

## Carry-overs / review deferrals

- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass) — before F1 fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block translation pending; anonymization decision
  pending. S9 avoids it (OpenAI-compatible families only).
- No cancel endpoint; stranded `running` runs deadlock their thread (UI offers New chat) — F1
  run-lifecycle durability (arq + sweep + cancel) is the first F1 slice.
- Checkpoint rows invisible to alembic, not cleaned on delete — F1.
- Conversation compaction (ADR-F003) — F2.
- No audit rows for run kick-off (tool dispatches ARE audited).
- MessageBubble legacy default-DOMPurify — harden when next touched.
- Parallel-fan-out thinking ribbon shares one buffer — F1 subagent tree.
- wave-c-matters test 3 hangs pre-existing (fails identically on main; AUT's POST /projects never
  leaves the browser under Cypress there) — Backlog.
- S6 deferrals unchanged: eslint-9 flat config; path-scoped CSP; bare-`<select>` restyle;
  version-poll auto-reload.

## Gotchas

- **`cy.intercept` BUFFERS streamed responses** — never intercept the SSE route under liveness test.
- **The shell scrolls `#lq-main`, NOT the document** (`html{overflow-y:hidden}`) — resolve the
  scroll container (see ConversationPanel `scrollContainer()`).
- **Cypress screenshots on the agents surface need `capture: 'viewport'`** (sticky composer breaks
  full-page stitching).
- **Cypress memory-pressure recipe** (zero pg crashes): stop arq-worker;
  `ELECTRON_EXTRA_LAUNCH_ARGS='--js-flags=--max-old-space-size=512'`;
  `CYPRESS_LQ_AI_MATTER_NAME="S5 PreSeed 1781169832"` for f0-s4/s5/s7 (f0-s3 self-seeds);
  `--config video=false,numTestsKeptInMemory=0`; restart arq-worker after. Wedged workers
  ("connection is closed"): `docker compose restart ingest-worker arq-worker`.
- Web container serves a pre-built bundle — `docker compose build web && docker compose up -d web`
  before debugging UI; builds in seconds with the stack up.
- `gh pr create` defaults to the FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork`
  AND `--head <branch>` (ADR-F001).
- **jq is NOT installed** — parse `gh --json` with python3. `gh pr checks | awk '{print $2}'`
  breaks on spaced check names.
- Branch switches with uncommitted edits + `git checkout -- <file>` on the other branch DESTROY
  the edit (bit us in S8). Background merge-watchers may end on `git checkout main` — verify the
  branch before committing.
- **.env S3 keys** stay commented out (MinIO root-creds fallback; backup `.env.bak-f0-s4`).
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. Containerized
  pytest needs `skills/` at `/skills`; ruff needs repo-root `ruff.toml` (mount the REPO,
  workdir `/repo/api`).
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers. MiniMax-M3 emits
  `<think>` blocks — UI collapses them; never strip them in the API; the gateway must round-trip
  them in HISTORY (tonight's step 1 verifies).
