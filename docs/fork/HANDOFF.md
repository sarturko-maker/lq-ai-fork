# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `intake-1-substrate` (INTAKE-1 PR) off `main` `9d4620a4` (INTAKE-0 merged #290).
  Dev stack healthy on adeu 2.4.0; demo matter wiped for re-recording
  (`sample-documents/commercial-redline-brief/`). **After this PR merges: rebuild
  api + arq-worker + ingest-worker together (migration 0098 applies on api boot), then
  `docker image prune -f`.**
- **Milestone: INTAKE** — agent-monitored legal-intake inbox. Plan ACCEPTED 2026-08-16 after
  maintainer phone review (all 6 decisions resolved IN the plan: `docs/fork/plans/
  INTAKE-INBOX-plan.md` — read § Ruling 1 + § Doctrine first: no deterministic classifier, no
  fixed taxonomy; ONE deep-agent run per email thread → structural `record_intake_outcome`
  [dealt-with / paused-for-HITL / candidate matter]; categories emerge post-v1). CUSTODIAN
  queues behind INTAKE. Slice tasks #537–#543.
- Untracked on purpose (ride their own future PRs): `sample-documents/`, 4 scenario live
  tests, PYMUPDF research, `docs/fork/evidence/demo-rehearsal/`.

## Done (INTAKE-1 — substrate; this PR)

- Migration **0098** + models: `projects.intake_state` (candidate/promoted/dismissed, CHECK) +
  `intake_mailboxes` (partial-unique live binding) + `intake_threads` (free-text `label`,
  status enum, auth_state) + `intake_messages` (UNIQUE (thread_id, provider_message_id) =
  idempotency anchor). Verified up/down/up on a throwaway pgvector container.
- `app/ingest.py`: `register_ingested_file()` (row + enqueue, shared) + `ingest_bytes()`
  (bytes-in-hand path, self-cleans its own object on registration failure). HTTP
  `upload_file` STILL STREAMS via `stream_upload` (C4 invariant kept).
- `POST /api/v1/internal/intake/emails` (`require_bridge_auth`, no user gate): **claim-first**
  idempotency (IntakeMessage flush is the arbiter — concurrent duplicates upload nothing),
  thread-race rollback+re-select, eager candidate project, per-request storage-path tracking
  with best-effort blob cleanup on any failure. Envelope schema rejects NUL bytes, >10 or
  >25MB-each or >50MB-aggregate attachments, >512k body. Deterministic arq job id per
  (thread, hashed message id); stub `intake_email_job` (INTAKE-3 fills body — must re-derive
  from DB, payload is thread_id only). Admin CRUD `/admin/intake-mailboxes`.
- Two fresh-context reviews (correctness + security): 2 blockers + 5 should-fixes ALL fixed
  (streaming restore; claim-first + leak-free cleanup; NUL/aggregate caps; content-free logs;
  job-id determinism) + lead-found residual (failing attachment's own blob leak → ingest_bytes
  self-cleanup) + MissingGreenlet on post-rollback `mailbox.*` access (capture scalars first).
  Deferred on record: mailbox-scoped tokens (M3-D1 precedent), tailscale-edge `/internal`
  deny + body cap (MILESTONES backlog), practice-area usability check on binding (INTAKE-3),
  PATCH explicit-null owner no-op.
- Verification: targeted containerized suite **127 passed, 1 skipped** (all new + files +
  drift-guards); earlier FULL suite on the pre-fix commit 3810 passed / 54 pre-existing-
  environmental fails (categorized in PR); ruff CI-exact clean; in-container `mypy app`
  clean (251 files); prod api image rebuilt after dev-image test runs.

## Next slice — INTAKE-2 (AgentMail probe + mail-bridge) — task #539

THE ONLY AgentMail-touching slice. FIRST confirm `AGENTMAIL_API_KEY` + dedicated inbox address
are in the dev env — if missing, ask the maintainer (account exists; inbox to be created) and
STOP. Then: scripted probe (websocket subscribe, webhook payload capture, attachment download
bytes-vs-signed-URL, reply-with-docx round-trip) → evidence `docs/fork/evidence/intake-probe/`;
then the bridge microservice (slack-bridge pattern; websocket loop dev / Svix webhook prod;
envelope normalization + attachment fetch → `POST /api/v1/internal/intake/emails` with
`LQ_AI_BRIDGE_TOKEN`; `POST /send` for INTAKE-4). Read
`docs/fork/plans/research/INTAKE-agentmail.md` first.

## Pick up exactly here

If the INTAKE-1 PR is unmerged: finish its F005 gate and squash-merge
(`gh pr merge --repo sarturko-maker/lq-ai-fork`). Immediately after merge: rebuild
api + arq-worker + ingest-worker together, `docker image prune -f`, verify `alembic current`
in the api container reports 0098, then run the live curl smoke (synthetic envelope with the
bridge token → thread/project/file rows appear → hard-delete the smoke rows) and attach
evidence to the PR. Then start INTAKE-2 per the block above.

## Gotchas

- INTAKE design tripwires: intake runs are normal `agent_loop` purpose (NO gateway purpose
  edit); the project row is created EAGERLY at ingest and the agent's outcome dismisses or
  keeps it; `draft_email_reply` is hitl_policy-gated UNCONDITIONALLY (no category mechanism
  exists to unlock it); AgentMail creds live ONLY in the future mail-bridge, never `api`;
  HITL edit/respond widening is INTAKE-4 (ADR-F087) — keep approve/reject the default compile
  everywhere else.
- Adeu 2.4.0 substrate facts live in ADR-F085 (mapper staleness → fresh engine per call;
  comment-only edits = range annotation idiom; anchor comments on target_text never new_text).
- Containerized full-suite recipe: build `api/Dockerfile.dev` (context `api/`), tag
  `lq-ai-api`, `docker compose run --rm -v $PWD/api:/app api pytest -q`; wizard tests need the
  whole repo (`-v $PWD:/repo -w /repo/api`). Rebuild the PROD api tag afterwards. Suites ALONE
  (vitest OOMs pytest). Host ruff: `pip install --user --break-system-packages ruff==0.16.3`,
  run with `--no-cache`.
- Backlogged from ADEU-2 (MILESTONES § Backlog): `process_batch` consolidation,
  `reject_all_revisions`, Mikko upstream reports (maintainer contacts personally), persist
  tool-rejection texts on `cap_exceeded`.
