# INTAKE-5a.1 — live evidence (dev stack, 2026-08-30)

Slice: maintainer UAT fixes on the 5a Inbox + the P1 resume-binding bug, PR #300, branch
`intake-5a1-uat-fixes`, dev DB at migration 0104. Screenshots headless (puppeteer-core +
chromium, minted owner JWT in `lq_ai_auth` localStorage; no credential in this directory).

## The P1, reproduced and recovered

Maintainer approved two paused drafts (AWDC `a3df5fcc…`, purchase-terms `a1850a71…`); both
resumes bound to the WRONG sibling thread (the NDA thread, whose delivered reply tripped the
send guard) — approvals consumed, nothing sent, guard failed closed. After the fix
(`agent_runs.resumed_from_run_id` + lineage binding) the two inbound messages were un-stamped
and requeued: each run re-read its thread on the new code, wrote a 5-bullet summary, RENAMED
the matter (`ORG-COM-0011` → "AWDC Supplementary Terms of Purchase — review request" — the
agent discovered the "NDA" is actually AWDC purchase terms) and concluded `needs_human`
WITHOUT redrafting — its judgment: the clarification reply already sent covers both messages.
No redundant email was proposed; the original approvals resolve as "nothing further to send".

## What the screenshots show

- `inbox.png` — attention-first list; Contoso `NWT-COM-0013` first bullet as row meta; the two
  recovered threads amber "Needs a human"; badge 3.
- `thread-summary.png` — the maintainer-ruled card layout live: "THE THREAD SO FAR · LAST
  EMAIL 3H AGO" (honest label), five bold-titled bullets, chain collapsed; side card as chips
  (Handed to a human / Sender check passed / label) + 3-line clamped note with Show more +
  `NWT-COM-0013 · Renewal of the Contoso hosting agreement — notice period` matter link.
- `thread-nda.png`, `matter-inbox-tab.png`, `admin-mailboxes.png` — unchanged surfaces on the
  new build.

## Also proven live

- **Summarise now**: `POST /intake/threads/{dfedec48…}/summarise` → `queued:true` → the pre-5a
  NDA thread gained its summary and its status stayed `replied` (sticky — the read-only pass
  wrote no status).
- **Matter naming**: `projects.name` now agent-written (`name_source='agent'`) on both
  intake-born matters; reference + name render together in UI and agent prompt.
- **One more live-found bug, fixed in `90c418bf`**: the two requeued sibling jobs raced; the
  loser's run INSERT hit `uq_agent_runs_thread_running`, and reading `thread.id` for the busy
  signal after the failed flush lazy-refreshed on the poisoned async session
  (PendingRollbackError) — the thread was marked `error` instead of deferring (it self-healed
  on the next settle). Fix: busy id captured before the flush, rollback before
  `AgentThreadBusy`, worker defers `PendingRollbackError` too; regression test
  `test_a_lost_insert_race_is_busy_and_leaves_the_session_usable`.

## Not proven live

`waiting_on` (the deferred-sibling line) — the deferred window closed before capture; covered
by the list-query tests (incl. self-exclusion). The summarise-pass HITL-resume path (B1) —
covered by composition/binding tests; no admin gates `record_intake_outcome` on dev.
