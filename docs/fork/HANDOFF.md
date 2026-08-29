# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `main` — **INTAKE-2 (AgentMail probe + mail-bridge) implemented and LIVE-VERIFIED
  2026-08-29**, this PR. New top-level service `mail-bridge/` (compose profile `mail`, host
  port 8004) + `mail-bridge-checks` CI job + api-side envelope-bounds drift-guard test.
- Live end-to-end PROVEN on the dev stack: a real external Gmail email → AgentMail →
  bridge reconciliation → normalize + presigned-URL attachment fetch →
  `POST /internal/intake/emails` → intake thread (`auth_state=pass`) + candidate project +
  .docx ingested `ready` (12,775 bytes, byte-exact). Idempotency replay verified (restart →
  `duplicate delivery`, no new rows). `/readyz` green incl. subscription age.
- **Persistent dev config created (NOT smoke — keep):** `intake_mailboxes` row
  `557264d0-43c9-47bd-ab34-d30f085af51a` binding (agentmail, oscar-lq@agentmail.to) →
  Commercial area, owner admin@lq.ai. AgentMail creds live in the gitignored dev `.env`
  (lines ~401-403: `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ADDRESS`,
  commented `AGENTMAIL_WEBHOOK_SECRET`) — consumed ONLY by mail-bridge, never api.
- Probe evidence: `docs/fork/evidence/intake-probe/` (findings.md + captured websocket
  frames, incl. a live external `message.received`). Ground truth over the research doc.
- **Milestone: INTAKE** — plan `docs/fork/plans/INTAKE-INBOX-plan.md` (ACCEPTED). Slice
  tasks #537–#543; #539 (INTAKE-2) closes with this PR. CUSTODIAN queues behind INTAKE.
- Untracked on purpose (ride their own future PRs): `sample-documents/`, 4 scenario live
  tests, PYMUPDF research, `docs/fork/evidence/{demo-rehearsal,memory-demo-rehearsal}/`.
  Memory-video pivot (2026-08-24) delivered earlier — runbook/discussion docs in
  `sample-documents/commercial-redline-brief/`, maintainer records at leisure.

## Done (INTAKE-2 — this PR)

- **Live AgentMail probe** (all semantics verified against the real API, SDK 0.5.9):
  self-send fires `message.sent`+`delivered`, NEVER `message.received` (loop guard is a
  plain event_type filter); attachment download = presigned CloudFront URL (~1h TTL,
  unauthenticated — the URL IS a credential); reply threads by message_id alone; websocket
  subscribe acks fast but has NO replay (durable events API logs only `label.added`).
- **`mail-bridge/`** (slack-bridge pattern, DI via lifespan composition root): websocket
  dev ingress with real-uptime-gated backoff + best-effort reconciliation poll
  (`after=` high-water mark, explicit `include_spam/blocked/unauthenticated=False`);
  Svix-verified prod webhook (mounted only when secret set; Content-Length cap; 5xx →
  Svix retries); normalize → `InboundEmailEnvelope` (NUL strip, truncate-with-marker,
  caps restated from api schema + drift-guard test `api/tests/test_intake_envelope_bounds_drift.py`);
  streaming attachment fetch with hard per-item/aggregate abort; bearer-gated reply-only
  `/send` (nothing calls it until INTAKE-4). 105 tests; ruff + `mypy --strict` clean.
- Fresh-context adversarial review: 2 blockers (clean-close reconnect storm; presigned URL
  leaking through exception chains into tracebacks) + 9 should-fixes ALL fixed; deferred on
  record: Dockerfile root/install-order (pre-existing bridge convention).
- Security posture: API key + presigned URLs never logged (httpx/httpcore muted to WARNING —
  httpx logs full request URLs at INFO; audit backlogged for gateway/api); logs carry
  counts/types/IDs only; `/readyz` status words never exception text.

## Next slice — INTAKE-3 (the intake run) — task #540

One deep-agent run per email thread on the bound Commercial agent (normal `agent_loop`
purpose — NO gateway purpose edit): fill the stub `intake_email_job` (re-derive everything
from DB; payload is thread_id only), structural `record_intake_outcome` tool
(dealt-with → auto-dismiss project / paused-for-HITL / candidate matter), free-form
`intake_threads.label`, intake SKILL doctrine (taxonomy = examples only), lean budget +
low step cap. Read plan § Ruling 1 + § Doctrine first. Consider the doctrine note on
unsupported attachment types (txt/images settle `failed/unsupported_type`).

## Pick up exactly here

If this PR isn't merged yet: full-suite containerized api run + merge gate, then merge.
After merge: rebuild api + arq-worker + ingest-worker together (drift-guard test rides in
api/tests), `docker image prune -f`, bring mail-bridge back up
(`docker compose --profile mail up -d mail-bridge`). Then start INTAKE-3 per the block
above. Task tracker: mark #539 completed; #540 = next (also still owed: #538 → completed
from 2026-08-24 — MCP task tools were disconnected).

## Gotchas

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
