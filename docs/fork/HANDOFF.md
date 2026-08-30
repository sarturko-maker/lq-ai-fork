# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `main` — **INTAKE-3 MERGED #294 (`8e7bb631`, 2026-08-30)**. Migration **0099** (intake_threads.outcome CHECK
  `dealt_with|needs_human`, intake_messages content columns, `intake-triage` skill bound to
  Commercial). Dev DB is at 0099; api/arq-worker/ingest-worker rebuilt together.
- **Maintainer ruling R10 / Amendment A1 (2026-08-29): EVERY intake thread IS a matter.**
  Promote is gone; `projects.intake_state` is provenance + tool-grant gate only. Outcomes:
  `dealt_with` → thread `handled` + matter `archived_at` (memory fence); `needs_human` →
  thread `awaiting_human`, matter open. "Attach to existing Matter X" is the INTAKE-4/5 human
  decision. Recorded in plan § Amendment A1 and ADR-F086 § Amendment A1 (still `proposed`).
- Live proof (real Gmail → AgentMail → bridge → worker → run): junk "50% off office chairs"
  → `handled`/`dealt_with`/label `marketing`/archived, 9 steps, 67k tokens; "please review the
  attached NDA" (+ AWDC .docx) → agent read the doc, wrote Roster/Documents/File/3 Facts,
  `record_intake_outcome(needs_human)` label "review request — AWDC purchase terms (not NDA)",
  then paused `awaiting_input` on `draft_email_reply` (HITL floor), matter open, 0 drafts
  persisted (awaiting approval), 25 steps, 125k tokens. Thread ids `f4ff2ffe…`, `dfedec48…`.
- Older threads `eacb1f25…`/`ffe5314b…` (pre-0099, no content columns) stay `received` — no
  job will ever pick them; delete or leave as fixtures.
- Milestone INTAKE: 0/1/2/3 done (#290/#291/#293/this). Next INTAKE-4 (#541).
- Untracked on purpose (ride their own future PRs): `sample-documents/` except
  `commercial-intake-pack/`, 4 scenario live tests, PYMUPDF research,
  `docs/fork/evidence/{demo-rehearsal,memory-demo-rehearsal}/`.

## Done (INTAKE-3 — this PR)

- R1 `api/app/agents/run_service.py` headless `start_agent_run` (endpoint byte-identical,
  patch seams kept). R2 `intake_worker.py` core `process_intake_thread` (+ arq wrapper):
  `with_for_update` thread lock, oldest pending inbound first, in-flight defer + **requeue on
  settle** (`requeue_pending_intake_message` in the agent_run_worker settle hook), owner
  mismatch → `error`, bad budget profile → default, `DEFAULT_INTAKE_MAX_STEPS=40`.
- R4 `intake_prompt.py`: per-run **nonce fence**, newline collapse + 5-dash neutralisation on
  every rendered field (fence-escape + hostile-filename fixtures in the pack). R5
  `intake_tools.py`: `record_intake_outcome` (last-call-wins incl. un-archive), `draft_email_reply`
  (persists `intake_messages` direction='out', sends nothing). Tools + `INTAKE_DOCTRINE` granted
  ONLY on the intake conversation (`thread_id == intake_threads.agent_thread_id`) — ordinary
  cockpit chats on the matter get neither. R6 `ALWAYS_INTERRUPT_TOOL_NAMES` floor applied last
  AND kept on every subagent spec. R7 safe-fail keyed on the agent conversation.
- R8 `skills/intake-triage/SKILL.md` + 4-piece bind. R9 code-scored eval
  `sample-documents/commercial-intake-pack/` (22 envelopes) — **22/22 PASS, 0 UNSAFE** live.
- Fresh-context adversarial review: 4 blockers (fence escape, subagent floor cleared, orphaned
  deferred follow-ups, half-wins un-archive) + 6 should-fixes + nits — ALL fixed.
- Verification: containerized api suite (pre-fix) 3897 passed / 2 pre-existing env failures
  (`test_branding` BRAND_ACCENT_LIGHT="" in dev .env; `test_health` deps reachable in compose);
  post-fix touched-module suites 383 passed; ruff + mypy clean; migration up→down→up on a
  throwaway pgvector container.

## Next slice — INTAKE-4 (#541) — PLAN WRITTEN, awaiting maintainer edit

**Read `docs/fork/plans/INTAKE-4-plan.md` first.** Maintainer rulings 2026-08-30 already in it:
neutral naming (no product name anywhere user-visible; codebase is Apache-2.0); matter
reference `ORG-AREA-NNNN` (admin org code + per-area code + per-org-per-area counter table,
assigned to EVERY matter, backfilled); AREA = HOME area only (cross-area pull-in = future
milestone; keep-possible invariants in NORTH-STAR + plan); stamping layers (References →
subject tag gated on Roster membership → agent suggestion → human attach) with weak layers
never auto-merging; HITL verbs edit/respond for `draft_email_reply` ONLY (ADR-F087); the
tool's execution IS the send via bridge `/send`, idempotent. Two sub-slices: **4a** reference +
stamping substrate (migration 0100, ADR-F088) → **4b** HITL edit/respond + approved send.
Open for the maintainer: year segment in the reference (default NO); plus-address probe.

## Pick up exactly here

1. Ask the maintainer to edit/accept `INTAKE-4-plan.md` (year segment? plus-address probe?).
2. Probe (Sonnet): does AgentMail `reply` honour a caller-supplied Message-ID / custom
   headers? Does a plus-address deliver to the base inbox? Record in
   `docs/fork/evidence/intake-probe/findings.md`.
3. INTAKE-4a build (Opus) per plan; drift-guards for area codes; live: tagged forward from a
   Roster sender lands on the same matter.
Working model: Sonnet easy / Opus implement+review+fix / Fable orchestrate, design,
live-verify, merge. Task tracker owed: #538/#539/#540 → completed (MCP task tools
disconnected).

## Gotchas

- **A bare `pytest -q` inside the api container runs every provider test** (container carries
  `LQ_AI_GATEWAY_KEY`) and rewrites committed `docs/fork/evidence/**` — use `-m "not provider"`
  and `git checkout docs/fork/evidence` if you forget.
- `docker compose run api …` runs the image entrypoint = `alembic upgrade head` on the dev
  DB: a containerized test run silently migrates dev. Fine (auto-migrate-on-boot), but know it.
- Intake runs ALWAYS compile a HITL policy → fail closed without a checkpointer; any harness
  with `checkpointer_provider=lambda: None` must inject one.
- **api health endpoint is `/health`, NOT `/healthz`** — the bridge's readiness probe hit
  this; anything new probing the api must use `/health`.
- `docker compose config` interpolates `.env` and prints secrets — ALWAYS
  `--no-interpolate` (or `--services`) for validation. (Live AgentMail key + bridge token
  were exposed into one subagent transcript this way, 2026-08-29 — local file only;
  maintainer may rotate at leisure.)
- The intake 404 means "no active mailbox binding", not a routing bug — check
  `intake_mailboxes` first.
- AgentMail traps: `thread.attachments` ≠ union of message attachments (enumerate
  per-message); fresh `attachment_id` for identical bytes (our sha256 is dedup truth,
  ADR-F082); events can arrive out of order (order by `timestamp`); `messages.list` rows
  carry no body (per-row `messages.get` needed); SDK type-lags the API (undeclared fields
  survive `model_dump()`); `# type:` at the start of a prose comment breaks mypy.
- INTAKE design tripwires still in force: project row created EAGERLY at ingest, agent
  outcome dismisses/keeps; `draft_email_reply` hitl-gated UNCONDITIONALLY; HITL
  edit/respond widening is INTAKE-4 (ADR-F087); AgentMail creds never in `api`.
- Containerized full-suite recipe: build `api/Dockerfile.dev` (context `api/`), tag
  `lq-ai-api`, `docker compose run --rm -v $PWD/api:/app api pytest -q`; wizard tests need
  the whole repo (`-v $PWD:/repo -w /repo/api`). Rebuild the PROD api tag afterwards.
  Suites ALONE (vitest OOMs pytest). mail-bridge suite: `python:3.12-slim` with the dir
  mounted, `pip install -e .[dev]`, clean root-owned caches after.
- Adeu 2.4.0 substrate facts live in ADR-F085. Backlogged from ADEU-2: `process_batch`
  consolidation, `reject_all_revisions`, Mikko upstream reports, persist tool-rejection
  texts on `cap_exceeded`.
