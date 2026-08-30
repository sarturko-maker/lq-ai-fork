# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `intake-4b-hitl-send` — **INTAKE-4b built, reviewed, live-verified; PR open** (this PR).
  Migration **0101** (`intake_messages.send_error`). ADR-**F087** proposed (HITL verbs for
  `draft_email_reply` + the approved send; amends F071). Dev DB at 0101; api/arq-worker/
  ingest-worker/mail-bridge/web rebuilt from this branch. INTAKE-4a merged #296 (`7db6b0cd`).
- **Live proof on dev (matter `ORG-COM-0011`, conversation `23b2e471…`):**
  1. Approve on the pre-4b paused ask (run `9e9ed16d…`) → resumed run `267fac3d…` `completed`;
     `intake_messages` out row with provider id `<010001a0…>`, subject stamped `[ORG-COM-0011]`,
     bridge `POST /send 200`, thread → `replied`; the reply arrived in the maintainer's Gmail on
     the original thread with `Reply-To: oscar-lq+org-com-0011@…` (verified via the SDK).
  2. Maintainer replied from Gmail → landed on the SAME intake thread `dfedec48…` (layer 1; its
     `In-Reply-To` = our sent id, so layer 2 would match too) → requeue → run `05db8b6f…` read
     it, wrote a Fact + Matter File, `record_intake_outcome`, paused on a NEW draft whose ask
     carries `allowed_decisions: [approve, edit, reject]`.
  3. **`edit`** on that ask → resumed run `e3c82460…` `completed`; the out row body carries the edit and the maintainer's Gmail received exactly the edited text (14:56 UTC).
  A pre-4b ask degrades to approve/reject (422 `decision_not_allowed_for_pending_tool` on
  `edit`) — by design (digest has no `review_configs`).
- Three bugs found ONLY live and fixed in this PR: (a) one agent conversation now has MANY
  intake threads (4a layers 2/3) → `load_intake_thread_for_run` `MultipleResultsFound`; runs now
  bind to their thread via `intake_messages.run_id` + conversation lineage, fail closed on
  ambiguity; (b) the paused HITL row stays `awaiting_input` forever → intake worker saw the
  conversation as in-flight forever; now ONE helper `run_service.newest_live_run` /
  `is_conversation_in_flight` shared with the resume guard; (c) arq kept
  `arq:result:intake-email:*` for 1h and `enqueue_job` silently returned None on the reused
  deterministic id → requeue-on-settle was a no-op for an hour; intake job registered
  `keep_result=0`, helper returns `job is not None`, refused requeue logs WARNING.
- Milestone INTAKE: 0/1/2/3/4a done (#290/#291/#293/#294/#296), 4b = this PR. Next INTAKE-5.
- Untracked on purpose: `sample-documents/` except `commercial-intake-pack/`, 4 scenario live
  tests, PYMUPDF research, `docs/fork/evidence/{demo-rehearsal,memory-demo-rehearsal}/`.

## Done (INTAKE-4b — this PR)

- `ResumeDecision` gains `edit` + `edited_args` (subject/body; `to` unreachable — the bridge
  derives recipients); per-tool `allowed_decisions` (floor tool approve/edit/reject; every other
  gated tool approve/reject) enforced in schema, endpoint (422) and runner (`EDITABLE_TOOL_NAMES`);
  `_build_resume_command` emits `edited_action`; `respond` = reject+message (UI verb, no runner
  path; doctrine coaches the redraft). Middleware contract verified against installed langchain.
- `draft_email_reply` executes the send: out row first (keyed `draft:<sha256(thread+tool_call_id)>`,
  `InjectedToolCallId`), bridge `POST /send` via constructor-injected `MailBridgeClient`
  (api holds only `LQ_AI_BRIDGE_TOKEN`; `LQ_AI_MAIL_BRIDGE_URL` in compose), idempotency key =
  that per-ask hash, `reply_to_tag` = the reference (bridge composes the plus-address from ITS
  inbox), stores provider id, thread → `replied`, `db.commit()` before returning; failure →
  `send_error` class only, thread `error`; delivered-row guard; no retries anywhere.
- mail-bridge: `idempotency_key` required (bounded per-process LRU, 409 on repeat, also passed
  to the provider), `reply_to_tag` pattern-validated, no subject on `reply()` (SDK has none —
  wire subject is the provider's `Re: <original>`; the tag rides Reply-To + our provider id).
- Web `HitlConfirmCard`: draft editor (subject/body) for `draft_email_reply` only, "Approve &
  send" (approve or edit), "Respond" (reject+message, disabled when empty), "Refuse".
- Reviews (fresh-context, Opus): 1 blocker (row-id idempotency key could not stop a genuine
  re-execution → double send) + 4 should-fix + 5 nits — all fixed; then the three live-only bugs.
- Suites: api containerized `-m "not provider"` (pre-live-fix commit `eef2150b`) **4141 passed /
  2 pre-existing env failures** (`test_branding`, `test_health`) / 4 skipped; touched suites after
  each fix 302/303/277 passed; mail-bridge 115; web check 0 errors, vitest 114 files / 1401;
  ruff + mypy clean (api, bridge). Migration 0101 up→down→up on throwaway pgvector.

## Next slice — INTAKE-5 — the inbox surface

Not yet planned. Candidates from the plan's non-goals: cockpit inbox listing threads + paused
asks across matters (Agent Inbox UX as the reference, Svelte on the F013 tokens); matter view
listing its threads; human "attach to Matter X" (A1); agent-proposed attach; retire
`intake_state` `promoted/dismissed`. Craft backlog seen live: reply signature block + tone hint
in the doctrine; drafts double the `Re:` prefix in the recorded subject (wire subject is fine).

## Pick up exactly here

1. Merge this PR when CI is green (gate items 1–5 in the PR body).
2. Write the INTAKE-5 plan (maintainer edits), then build.
Working model: Sonnet easy / Opus implement+review+fix / Fable orchestrate, design, live-verify,
merge. Task tracker owed: #538/#539/#540/#541 → completed (MCP task tools disconnected).

## Gotchas

- **Background Bash commands get stopped early on this box** — run anything long as a `nohup`
  script writing a log and watch it with Monitor; builds of 5 services exceed 10 min (two groups).
- **The full api suite mounts the WORKTREE**: any edit to that worktree during the run poisons
  the result (45 spurious failures once). Run the suite on a quiet tree; needs the dev image
  tagged `lq-ai-api` (`docker build -f api/Dockerfile.dev -t lq-ai-api api`), the repo mounted
  at `/repo` with `-w /repo/api` (wizard/profile tests), and compose run from the MAIN checkout
  (the worktree has no `.env`). Rebuild the prod api tag afterwards.
- **A paused HITL run row is never mutated**: "live ask" and "in flight" are DERIVED from the
  newest non-failed/cancelled run on the conversation (`run_service.newest_live_run`). Never add a
  second definition.
- **arq deterministic job ids + kept results = silent dedup.** Any job whose id is legitimately
  reused must be registered `keep_result=0`; `enqueue_job` returning None is a refusal.
- Minting an admin token for live checks: inside the api container
  `app.security.jwt.create_access_token(user_id, email, is_admin=True)`; write to a file, never
  print. The Gmail API reply tool ignores `Reply-To` (addresses `From`) — mail clients honour it.
- Roster PATCH `side` ∈ `ours|counterparty|other|unknown`; any PATCH (re)confirms → opens the
  layer-3 gate. Layer-3 attach needs `trust='confirmed'` AND an `@` alias.
- `ruff.toml` at repo root: run ruff from the root, never inside the api container.
- **Bare `pytest -q` inside the api container runs every provider test** — use `-m "not provider"`.
- `docker compose run api …` auto-migrates the dev DB. Intake runs ALWAYS compile a HITL policy →
  need a checkpointer. api health endpoint is `/health`. `docker compose config` → ALWAYS
  `--no-interpolate`. The intake 404 = "no active mailbox binding".
- AgentMail traps: `thread.attachments` ≠ union of message attachments; fresh `attachment_id`
  for identical bytes; events out of order; `messages.list` rows carry no body; SDK type-lags;
  provider LOWERCASES addresses; caller Message-ID header stored but provider `message_id`
  canonical; `reply()` takes no subject; plus-addressing delivers to the base inbox.
- INTAKE tripwires: project row created EAGERLY at ingest; `draft_email_reply` hitl-gated
  UNCONDITIONALLY and its execution IS the send; AgentMail creds never in `api`; weak stamps
  never auto-merge; no retries around a send, ever.
- Adeu 2.4.0 substrate facts live in ADR-F085.
