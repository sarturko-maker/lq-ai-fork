# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `intake-5a-inbox-surface` — **INTAKE-5a built, reviewed, live-verified; PR #299**.
  Migration **0102** (`intake_threads.summary` + `summary_run_id`, read indexes, `intake_state`
  CHECK narrowed to `NULL|candidate`). No new ADR — the slice implements the accepted plan
  `docs/fork/plans/INTAKE-5-plan.md` (#298) rulings 1–3 and 6–9 under ADR-F086. Dev DB at 0102;
  api/arq-worker/ingest-worker/web rebuilt from this branch.
- **Live proof** (`docs/fork/evidence/intake-5a/`): a synthesised Contoso email produced a
  five-bullet summary on new matter `NWT-COM-0013` with a paused draft; the cockpit Inbox lists
  four live-ask threads first with the first bullet as the row's grey line; the thread view opens
  on the summary with the chain collapsed; matter Inbox tab and admin mailbox page render.
- Found live and fixed (`b0303f54`): sent replies have no `provider_timestamp` → chain sorted
  them after every inbound; order now `coalesce(provider_timestamp, created_at)`.
- Milestone INTAKE: 0/1/2/3/4a/4b done (#290/#291/#293/#294/#296/#297), 5 plan #298, 5a = this PR.
  Next: **INTAKE-5b** (human attach, ADR-F089).
- Untracked on purpose: `sample-documents/` except `commercial-intake-pack/`, 4 scenario live
  tests, PYMUPDF + DEEPSEEK-HARNESS research, `docs/fork/evidence/{demo-rehearsal,memory-demo-rehearsal}/`.

## Done (INTAKE-5a — this PR)

- `record_intake_outcome` requires `summary` (1–5 `{title ≤40, text ≤300}`, plain text, control
  chars rejected, `extra=forbid`), full rewrite each call, `summary_run_id` stamped; safe-fail
  leaves the previous summary; doctrine `skills/intake-triage/SKILL.md` § "The summary" coaches
  the shape (spam = one bullet naming the category, nothing quoted).
- `GET /intake/threads` (owner fence: project owner, or mailbox owner for orphaned threads;
  attention rank 0..5 per ruling 3 computed once for ORDER BY + `attention=true`; `live_ask`
  from `newest_live_run` semantics via lateral joins, no N+1; offset cursor opaque, capped 10k;
  limit ≤100) + `GET /intake/threads/{id}` (newest 200 messages kept, `messages_truncated`;
  `file_ids` parallel to `attachment_filenames`, filename-matched within the matter only).
  Zero logging in the router; log-capture test proves no body/address/subject/summary in records.
- Web: `CockpitView 'inbox'` (`?view=inbox&intake=<id>`), Inbox nav entry + attention badge,
  `IntakeInboxPanel` / `IntakeThreadDetail` / `intake-panel-helpers.ts` (vitest), matter tab
  `inbox` (shown for every matter — `MatterActivity` carries no thread count), admin
  `intake-mailboxes` page over the INTAKE-1 CRUD. F013 tokens + primitives only; no `{@html}`.
- Review (fresh-context Opus): no blockers; fixed in `cdd391c9`: bounded file lookup, newest-200
  truncation, honest summary label ("last email"), dead duplicate helpers removed, web
  `pendingHitlStep` = FIRST hitl step (matches the server gate), badge boundary, cursor cap.
- Suites: api full `-m "not provider"` on `619b8e2f` 4210 passed / 7 failed (2 pre-existing env
  `test_branding`/`test_health` + 5 test-maintenance fixed in `a1fa3f1b`); touched suites on
  `a1fa3f1b` 228 passed; `test_intake_threads_api.py` on `b0303f54` 41 passed; migration 0102
  up→down→up on throwaway pgvector; mypy 259 files clean; ruff clean; web check 0 errors, vitest
  116 files / 1452.

## Next slice — INTAKE-5b — human attach (1 day)

Plan ruling 4 + ADR-F089 to draft: `POST /intake/threads/{id}/attach {project_id}` moves the
thread, its `agent_threads.project_id` and the files ingested from its attachments onto an OPEN
matter the caller owns (404 otherwise); 409 `thread_busy` while `is_conversation_in_flight`;
clears `claimed_reference`; archives an intake-born source matter only when it is now empty
(note "merged into <ref>"); audit row ids/counts only. Web: "Attach to matter…" on the thread
detail + `AttachToMatterDialog` (owner's open matters, consequences spelled out). Live script:
stranger's tagged email → stub with claim → attach to `ORG-COM-0011` → stub archived → next reply
from that sender continues the SAME conversation. Then INTAKE-6 acceptance (5-email pack).

## Pick up exactly here

1. Merge PR #299 when CI is green (gate items in the PR body).
2. Draft ADR-F089 + build INTAKE-5b (Opus backend, Sonnet dialog), review, live, merge.
Working model: Sonnet easy / Opus implement+review+fix / Fable orchestrate, design, live-verify,
merge.

## Gotchas

- **Prod rebuilds overwrite the `lq-ai-api` tag** → no pytest in the container. Build the dev
  image as `lq-ai-api-dev` and run suites with an override file
  (`services.api.image: lq-ai-api-dev`, `build: !reset null`) via
  `docker compose -f docker-compose.yml -f <override> run --rm -T -v <tree>:/repo -w /repo/api api pytest …`.
- **`pgrep -f`/`pkill -f` match your own shell** on this box — anchor patterns (`^/bin/bash <script>`)
  or you kill the caller / wait forever.
- **Background Bash commands get stopped early** — long jobs run as `setsid nohup … & disown`
  scripts writing a log, watched with Monitor; builds of 5 services exceed 10 min (two groups).
- **The full api suite mounts a worktree** — never edit that tree during the run.
- Synthesising an inbound email for live tests: run a python snippet INSIDE the mail-bridge
  container (`docker compose cp` + `exec`) so `LQ_AI_BRIDGE_TOKEN` stays in its env; envelope =
  `InboundEmailEnvelope` (`provider`, `inbox_id`=mailbox address, `thread{provider_thread_id,
  subject}`, `message{provider_message_id, from_addr, to, timestamp, text, auth_state}`).
- Headless screenshots: puppeteer-core (in the job tmp dir) + `/usr/bin/chromium`, login by
  writing `lq_ai_auth` `{access_token, refresh_token:null, expires_at, user:null}` to
  localStorage; token minted inside the api container into a file, never printed.
- Many intake threads share ONE agent conversation → `live_ask` is per conversation and is
  legitimately true on every sibling thread while a run is paused.
- Sent `intake_messages` rows have NO `provider_timestamp` — sort with the created_at fallback.
- **A paused HITL run row is never mutated**: "live ask"/"in flight" derive from
  `run_service.newest_live_run`; the web `pendingHitlStep` takes the FIRST hitl step like the
  server gate. arq deterministic ids need `keep_result=0`.
- Roster PATCH `side` ∈ `ours|counterparty|other|unknown`; layer-3 attach needs `trust='confirmed'`
  AND an `@` alias. `ruff` from the repo root with `--no-cache` (the `.ruff_cache` dir is
  root-owned). Bare `pytest -q` in the api container runs provider tests — use `-m "not provider"`.
- AgentMail traps: `reply()` takes no subject; plus-addressing delivers to the base inbox; provider
  lowercases addresses; caller Message-ID stored but provider `message_id` canonical.
- INTAKE tripwires: project row created EAGERLY at ingest; `draft_email_reply` hitl-gated
  UNCONDITIONALLY and its execution IS the send; AgentMail creds never in `api`; weak stamps never
  auto-merge; no retries around a send, ever; summary is agent text about untrusted mail — text
  interpolation only.
