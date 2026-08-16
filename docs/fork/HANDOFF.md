# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `intake-0-adr` (INTAKE-0 PR — docs-only) off `main` `803364b0`. ADEU-2 (#288) and the
  SSE stall-watchdog (#289) are MERGED; dev stack healthy on adeu 2.4.0; demo matter wiped for
  re-recording (`sample-documents/commercial-redline-brief/`).
- **Milestone: INTAKE** — agent-monitored legal-intake inbox. Plan ACCEPTED 2026-08-16 after
  maintainer phone review (all 6 decisions resolved IN the plan: `docs/fork/plans/
  INTAKE-INBOX-plan.md` — read § Ruling 1 + § Doctrine first: no deterministic classifier, no
  fixed taxonomy; ONE deep-agent run per email thread → structural `record_intake_outcome`
  [dealt-with / paused-for-HITL / candidate matter]; categories emerge post-v1). CUSTODIAN
  queues behind INTAKE. Slice tasks #537–#543.
- Untracked on purpose (ride their own future PRs): `sample-documents/`, 4 scenario live
  tests, PYMUPDF research, `docs/fork/evidence/demo-rehearsal/`.

## Done (INTAKE-0 — ADR + re-sequence; this PR)

- **ADR-F086** (proposed; substance maintainer-ruled — flip on maintainer read): one run per
  thread on the bound area agent; eager project + `intake_state` lifecycle; doctrine-not-config
  with emergent taxonomy; unconditional HITL gate on outbound tools; mail-bridge as sole
  mailbox-credential holder with a provider-agnostic envelope; native Svelte inbox on F071.
- MILESTONES.md: INTAKE milestone entry added; CUSTODIAN queue note gains "⑤ INTAKE first".
- Committed the accepted plan + all 5 research reports (`docs/fork/plans/research/INTAKE-*`).

## Next slice — INTAKE-1 (substrate; key-free) — task #538

Migration: `projects.intake_state` (nullable enum candidate/promoted/dismissed) +
`intake_mailboxes` (no policy JSONB) + `intake_threads` (free-text `label`, `outcome_note`,
status enum) + `intake_messages` (idempotency uniques). Extract `ingest_bytes()` from
`api/app/api/files.py:upload_file` (HTTP route reuses it; tests). `POST /internal/intake/emails`
behind `require_bridge_auth`: idempotent envelope → thread upsert → eager project → attachment
ingest → enqueue `intake_email_job` (`arq:m3a6`). Admin CRUD for `intake_mailboxes`.
Curl-testable with synthetic envelopes — NO AgentMail, NO LLM. Migration rules: throwaway
pgvector verify, rebuild api + arq-worker + ingest-worker together, `docker image prune -f`.

## Pick up exactly here

If the INTAKE-0 PR is unmerged: finish its F005 gate (CI green + adversarial review findings
fixed/deferred on record) and squash-merge via `gh pr merge --repo sarturko-maker/lq-ai-fork`.
If merged: start INTAKE-1 from `main` per the block above; the plan file is the spec. Before
INTAKE-2 (probe + bridge — the ONLY AgentMail-touching slice): confirm `AGENTMAIL_API_KEY` +
dedicated inbox address are in the dev env; if missing, ask the maintainer THEN (account
exists; inbox to be created) and read `docs/fork/plans/research/INTAKE-agentmail.md` for the
probe surface.

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
