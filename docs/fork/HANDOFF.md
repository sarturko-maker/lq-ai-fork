# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `intake-5a1-uat-fixes` — **INTAKE-5a.1 built, reviewed, live-verified; PR #300**.
  Migrations **0103** (`projects.name_source`, `agent_runs.resumed_from_run_id` + index) and
  **0104** (`intake_threads.summarise_pass_run_id`). No new ADR (implements plan #298 rulings +
  maintainer UAT rulings recorded in the plan's memory note); F042 pattern extended to matter
  names. Dev DB at 0104; api/arq-worker/ingest-worker/web rebuilt from this branch.
- INTAKE milestone: 0..4b + 5 plan + 5a done (#290/#291/#293/#294/#296/#297/#298/#299),
  5a.1 = this PR. Next: **INTAKE-5b** (human attach, ADR-F089), then INTAKE-6 acceptance.
- Live evidence: `docs/fork/evidence/intake-5a1/` (P1 reproduction + recovery, agent-renamed
  matter, summarise-now with sticky status, the second live-found race fix `90c418bf`).
- Untracked on purpose: `sample-documents/` except `commercial-intake-pack/`, 4 scenario live
  tests, PYMUPDF + DEEPSEEK-HARNESS research, `docs/fork/evidence/{demo-rehearsal,memory-demo-rehearsal}/`.

## Done (INTAKE-5a.1 — this PR; maintainer UAT 2026-08-30)

- **A — agent names the matter.** `record_intake_outcome` requires `matter_title` (≤80, essence);
  rename only while `intake_state='candidate'` AND `name_source != 'human'` via one conditional
  UPDATE (human rename wins, race-safe); `PATCH /projects` stamps `'human'`; UI + agent prompt
  both render `REF · name`. A summarise pass notes the title but never renames.
- **B — honest deferred state + backfill.** `IntakeThreadRead.waiting_on {thread_id, subject}`
  ("Waiting for your decision on '…'"); `POST /intake/threads/{id}/summarise` queues a
  READ-ONLY conclude pass (marker `summarise_pass_run_id` written before enqueue; no draft
  tool, no area/matter-write tools — `SUMMARISE_PASS_TOOL_NAMES` pins the set; writes no
  thread status — `replied`/`handled` sticky; safe-fail exempt; refusals in English, 409/422
  taxonomy; archived matters refuse `matter_closed`).
- **C — readable side card.** Chips (outcome/sender check/label), 3-line clamped note with
  Show more, `REF · name` matter link.
- **D — P1: resume bound to the wrong sibling thread.** Two live approvals were consumed with
  nothing sent (delivered-row guard failed closed). `agent_runs.resumed_from_run_id` recorded
  by the resume endpoint; `load_intake_thread_for_run` layer 1b walks the resume lineage
  (bounded, cycle-safe); legacy layer 2 kept only for historic rows. Recovery: un-stamp the
  inbound message (`run_id=NULL`) + `enqueue_intake_email_job` — both threads re-read, summaries
  written, matter renamed; agent judged no further reply needed (clarification already sent).
- **Live-found #2 (`90c418bf`):** lost start race errored the thread — `AgentThreadBusy(str(thread.id))`
  read an expired ORM attr after the failed flush (async lazy-refresh → PendingRollbackError).
  Busy id now read before the flush, rollback before raise, worker defers PendingRollbackError.
- Review (fresh-context Opus): 1 BLOCKER (resumed summarise pass regained full tools + legacy
  binding) + S2–S6 — all fixed; verified chain-walk safety, marker-before-enqueue, fences.
- Suites: full api `-m "not provider"` on `53245e19` 4254/10 (2 env, 1 sighup load-flake green
  in isolation, 7 fixed since); touched on `4b8ae843` 310 passed; worker+tools+lifecycle on
  `90c418bf` **150 passed** (incl. the race regression); migrations 0103+0104 up→down²→up on
  throwaway pgvector; mypy 259 files clean ×3; ruff clean; web check 0 errors, vitest 1466.

## Next slice — INTAKE-5b — human attach (1 day)

Plan #298 ruling 4 + ADR-F089 to draft: `POST /intake/threads/{id}/attach {project_id}` moves
thread + `agent_threads.project_id` + the thread's ingested files onto an OPEN owned matter
(cross-owner 404); 409 while `is_conversation_in_flight`; clears `claimed_reference`; archives
an intake-born now-empty source matter (note "merged into <ref>"); audit ids/counts only.
Web: "Attach to matter…" + `AttachToMatterDialog`. Live script: stranger's tagged email → stub
with claim → attach → stub archived → sender's next reply continues the SAME conversation.
Then INTAKE-6 acceptance; demo-prep pass (seed pack + reply signature/tone doctrine) is on
offer to the maintainer before or after 5b.

## Pick up exactly here

1. Merge PR #300 when CI is green (gate evidence in the PR body; wait for green — repo has NO
   required checks, `--auto` merges instantly).
2. Draft ADR-F089 + build INTAKE-5b, review, live, merge.
Working model: Sonnet easy / Opus implement+review+fix / Fable orchestrate, design, live-verify,
merge.

## Gotchas

- **`gh pr merge --auto` merges IMMEDIATELY here** (no required checks). Wait for CI green.
- **Prod rebuilds overwrite `lq-ai-api`** → dev image tag `lq-ai-api-dev` + override file
  (`services.api.image: lq-ai-api-dev`, `build: !reset null`); run compose from the MAIN
  checkout (worktrees lack `.env`), and remember the Bash cwd PERSISTS between commands.
- **`&` backgrounds the whole preceding `&&` chain** — a `git checkout && … && setsid … &`
  backgrounds the checkout too (a rebuild once built `main` silently). Verify `git log -1`
  before building; `--force-recreate` after a wrong-image `up`.
- **Async-ORM trap (bit twice):** never read an ORM attribute after a failed flush or
  rollback — capture scalars first. A lost `uq_agent_runs_thread_running` race must surface
  as AgentThreadBusy/defer, never thread `error`.
- **`pgrep -f`/`pkill -f` match your own shell** — anchor (`^/bin/bash <script>`).
- Long jobs: `setsid nohup <script> >> log & disown` + Monitor; `sleep` is blocked — use
  until-loops in Monitor/background Bash. Python run by path doesn't put cwd on sys.path —
  `docker compose exec -e PYTHONPATH=/app api python /tmp/x.py`.
- Requeue surgery: pending = inbound `run_id IS NULL`; un-stamp + `enqueue_intake_email_job
  (thread_id, provider_message_id=…)`; arq job id deterministic per message, `keep_result=0`.
- Synthesising inbound mail: python INSIDE mail-bridge container (`LQ_AI_BRIDGE_TOKEN` stays
  in its env) → `POST /api/v1/internal/intake/emails` with `InboundEmailEnvelope`.
- Headless shots: puppeteer-core + `/usr/bin/chromium`, `lq_ai_auth` localStorage token
  (minted in the api container to a file; expires — re-mint per session).
- Many threads share ONE conversation → `live_ask` true on every sibling while paused;
  `waiting_on` names the ask's thread. Sent `intake_messages` rows have NO
  `provider_timestamp` (coalesce created_at). Summarise pass: marker column, not arq payload.
- `ruff` from repo root with `--no-cache` (`.ruff_cache` is root-owned). Bare `pytest` in the
  api container runs provider tests — `-m "not provider"`. `docker compose exec` supports `-w`.
- AgentMail traps: `reply()` takes no subject; plus-addressing → base inbox; provider
  lowercases addresses; provider `message_id` canonical.
- INTAKE tripwires: `draft_email_reply` hitl-gated UNCONDITIONALLY, execution IS the send, no
  retries; weak stamps never auto-merge; AgentMail creds never in `api`; summaries/titles are
  agent text about untrusted mail — text interpolation only, sizes capped, bidi rejected.
