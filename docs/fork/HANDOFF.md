# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `intake-4a-reference-stamping` — **INTAKE-4a built, reviewed, live-verified; PR open** (this
  PR). Migration **0100** (`organization_profile.org_code`, `practice_areas.area_code`,
  `matter_reference_counters`, `projects.reference` UNIQUE + backfill, `intake_messages`
  in_reply_to/references, `intake_threads.claimed_reference`). Dev DB is at 0100; api/arq-worker/
  ingest-worker/mail-bridge/web rebuilt. ADR-**F088** proposed. Plan: `docs/fork/plans/INTAKE-4-plan.md`.
- Dev data after 0100: 12 matters backfilled `ORG-COM-0001..0012`, counter `COM next=13`; org code
  then set to `NWT` via the admin PUT (new matters mint `NWT-COM-0013+`; existing references are
  immutable and stay `ORG-…`). Practice-area codes COM/DIS/MNA/PRV/EMP.
- Live proof (Gmail → AgentMail → bridge → api resolver): with the sender CONFIRMED on the NDA
  matter's Roster (`ORG-COM-0011`, project `fe6f5eda…`), (a) a fresh mail with subject tag
  `[ORG-COM-0011]` and (b) a mail to `oscar-lq+ORG-COM-0011@…` with no tag both landed as NEW
  `intake_threads` rows (`a3df5fcc…`, `a1850a71…`) on that project with the SAME
  `agent_thread_id` (`23b2e471…`); the worker returned `deferred` because the conversation's run
  `9e9ed16d…` is `awaiting_input` (HITL pause on `draft_email_reply`) — they requeue on settle.
  Plus-address probe thread `9a08f4c2…` (`handled`) is also a real record. Probe facts in
  `docs/fork/evidence/intake-probe/findings.md` (INTAKE-4 section).
- Milestone INTAKE: 0/1/2/3 done (#290/#291/#293/#294), 4a = this PR. Next INTAKE-4b (#541).
- Untracked on purpose: `sample-documents/` except `commercial-intake-pack/`, 4 scenario live
  tests, PYMUPDF research, `docs/fork/evidence/{demo-rehearsal,memory-demo-rehearsal}/`.

## Done (INTAKE-4a — this PR)

- `api/app/matters/reference.py`: neutral `ORG-AREA-NNNN`; counter table keyed by area CODE
  (not id) with insert-if-absent + `SELECT … FOR UPDATE` inside the caller's transaction; `GEN`
  for area-less matters; default org code `ORG` until the admin sets one (no company-name column
  to derive from); `allocate_reference` on EVERY `Project(...)` site (cockpit + intake); sandboxes
  get none. Immutable: write schemas `extra="forbid"`; org/area code settable, never clearable.
- `api/app/matters/stamping.py`: `tag_subject` (idempotent), `parse_reference_tags`,
  `parse_plus_tag(s)`, `parse_references_header` (tail-kept), `looks_like_address`.
  `make_message_id` DROPPED — AgentMail assigns the canonical id regardless of a caller header.
- Resolver in `intake_emails.py` (ADR-F088 ladder): layer 2 = References/In-Reply-To naming an id
  we SENT (`direction='out'`, owner-fenced); layer 3 = subject tag OR plus-tag, attach ONLY if the
  sender is a `confirmed` roster alias that looks like an address (display-name aliases and
  `inferred` rows never open the gate); otherwise new matter + `claimed_reference` note rendered
  through the prompt sanitisers. Cross-owner reference = silence. No bridge change needed: it
  already forwards the headers; References cap 500→2000 both sides, trimmed from the head.
- Admin: org code on House Brief page + wizard step; area code on the area form; manifests
  `code:` REQUIRED on every `kind: area` (fail-loud); reference read-only in `MatterRailMetadata`.
- Review (fresh-context, Opus): 1 blocker (layer 2 matched INBOUND ids — a Cc'd stranger could
  self-file into a matter) + 3 should-fix + 7 nits — all fixed. Suites: api containerized
  `-m "not provider"` 4109 passed / 4 skipped / 42 deselected; mail-bridge 108; web check 0 errors,
  vitest 114 files / 1385; ruff + mypy clean; migration up→down→up on throwaway pgvector
  (`docs/fork/evidence/intake-4a/`).

## Next slice — INTAKE-4b (#541) — HITL edit/respond + approved send (ADR-F087)

Spec: `INTAKE-4-plan.md` § HITL verbs + § Slices/4b. Settled design facts (do not re-derive):
- `respond` = UI verb over `reject`+`message` — `_build_resume_command` (`runner.py:684`) already
  passes the message as the tool result the model sees; NO new runner path. Coach the redraft in
  `INTAKE_DOCTRINE` if needed.
- `edit` = deepagents-native decision (`{"type":"edit","edited_action":{"name","args"}}`): widen
  `ResumeDecision` + `_ALLOWED_DECISIONS` per tool (floor tool `draft_email_reply` gets
  approve/edit/reject; area-policy tools keep approve/reject), pass `edited_action` through in
  `_build_resume_command`, re-validate edited args against the tool schema.
- The tool's execution IS the send: `draft_email_reply` (on approve/edit) inserts the out row with
  `tag_subject(...)`, calls bridge `POST /send` with `reply_to_provider_message_id`, bearer
  `LQ_AI_BRIDGE_TOKEN`, idempotency key = out row id (bridge rejects a repeat — add that to the
  bridge), sets `reply_to` = `<inbox-local>+<reference>@<domain>` (plus-addressing PROVEN), stores
  the returned `provider_message_id` (this is what layer 2 matches), thread → `replied`.
  Failure → row kept with `send_error` (counts/types), thread `error`, tool returns failure.
- Web: `HitlConfirmCard` gains an args editor (to/subject/body) for `draft_email_reply` only + a
  Respond text box. First user-visible intake moment.
- Live: approve on run `9e9ed16d…` (matter `ORG-COM-0011`) → the two deferred threads requeue →
  Gmail receives the tagged reply from the plus-address → reply to it → lands on the same matter
  via layer 2 (References). Edited text is what gets sent; `respond` yields a redraft.

## Pick up exactly here

1. Merge this PR when CI is green (gate items 1–5 all in the PR body).
2. Brief Opus for INTAKE-4b with the "settled design facts" above; ADR-F087 in the same PR.
3. Live-verify 4b on dev (bridge is live; the paused NDA run is the fixture).
Working model: Sonnet easy / Opus implement+review+fix / Fable orchestrate, design, live-verify,
merge. Task tracker owed: #538/#539/#540 → completed (MCP task tools disconnected).

## Gotchas

- **Minting an admin token for live checks**: no admin password in env (bootstrap generates
  one) — inside the api container `app.security.jwt.create_access_token(user_id, email,
  is_admin=True)` for the first `is_admin` user; write it to a file in the container, never print.
- Roster PATCH `side` values: `ours|counterparty|other|unknown` (not `theirs`); any PATCH
  (re)confirms the entry — that is how a lawyer opens the layer-3 gate for a sender.
- `docker compose up -d --build` of 5 services exceeds the 10-min Bash cap — build in two
  groups (`build api arq-worker ingest-worker`, then `build mail-bridge web`), then `up -d`.
- `ruff.toml` lives at the repo root: ruff run INSIDE the api container reports hundreds of
  bogus errors — run from the repo root. `test_profile_loader` needs `-v $PWD/profiles:/profiles`.
- Layer-3 attach requires `trust='confirmed'` AND an `@` alias; an agent-inferred roster row is
  NOT enough (untrusted document metadata).
- **A bare `pytest -q` inside the api container runs every provider test** and rewrites committed
  `docs/fork/evidence/**` — use `-m "not provider"`.
- `docker compose run api …` runs `alembic upgrade head` on the dev DB (auto-migrate).
- Intake runs ALWAYS compile a HITL policy → fail closed without a checkpointer.
- api health endpoint is `/health`, NOT `/healthz`.
- `docker compose config` interpolates `.env` — ALWAYS `--no-interpolate`.
- The intake 404 means "no active mailbox binding" — check `intake_mailboxes` first.
- AgentMail traps: `thread.attachments` ≠ union of message attachments; fresh `attachment_id`
  for identical bytes (sha256 is dedup truth); events out of order (order by `timestamp`);
  `messages.list` rows carry no body; SDK type-lags the API; provider LOWERCASES recipient
  addresses (plus-tags compare case-insensitively); a caller-supplied Message-ID header is stored
  but the provider's own `message_id` stays canonical.
- INTAKE design tripwires: project row created EAGERLY at ingest; `draft_email_reply` hitl-gated
  UNCONDITIONALLY; AgentMail creds never in `api`; weak stamps never auto-merge.
- Containerized full-suite recipe: build `api/Dockerfile.dev` (context `api/`), tag `lq-ai-api`,
  `docker compose run --rm -v $PWD/api:/app api pytest -q -m "not provider"`; suites ALONE
  (vitest OOMs pytest). mail-bridge suite: `python:3.12-slim` with the dir mounted,
  `pip install -e .[dev]`. Rebuild the PROD api tag afterwards.
- Adeu 2.4.0 substrate facts live in ADR-F085.
