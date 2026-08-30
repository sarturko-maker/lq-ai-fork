# INTAKE-5 — the inbox surface: see every email thread, act on the paused ones, attach to the right matter

Status: DRAFT for maintainer edit (written 2026-08-30 at the close of INTAKE-4b, PR #297;
revised same day after the maintainer reviewed the wireframe — ruling 7 summary-over-chain).
Wireframe: https://claude.ai/code/artifact/4b8923fa-3bb6-45cc-bcc8-3661c146c37f
Parent: `docs/fork/plans/INTAKE-INBOX-plan.md` (ACCEPTED) § Ruling 2 (native Svelte inbox) +
§ Amendment A1 (every thread is a matter); ADR-F086 + § A1; ADR-F087/F088 (shipped).
Tasks: #542 (INTAKE-5). New ADR drafted in the PR: **F089** (human attach — what moves with a
thread, what happens to the stub matter).

## In simple terms

After INTAKE-4 the machine works end-to-end, but the lawyer can only find out what happened by
opening a conversation they already know about. INTAKE-5 gives them the front door:

1. **An Inbox in the cockpit** — every email thread the intake mailbox has handled, the ones
   that need a human first ("needs your decision", "needs a human", "send failed"), each one
   saying which matter it landed in and what the agent concluded.
2. **The thread, summarised** — the agent has read the whole chain; the human should not have
   to. What is always visible is the agent's summary: **at most 5 bullets, each with a bold
   inline title** ("What they want.", "Where it stands.", "Proposed next step."). The raw email
   chain — often long — is hidden behind one click. Plus the label and note, and one click into
   the conversation where the existing Approve / Edit / Respond card already lives. No second
   approval surface.
3. **"This belongs to Matter X"** — the human operation A1 promised: move a thread (and its
   conversation) onto an existing matter when the agent opened a stub it shouldn't have, or
   when a stranger's email honestly claimed a reference (the `claimed_reference` note). The
   emptied stub is closed, not deleted.
4. **The admin can bind the mailbox in the UI** — the API exists since INTAKE-1; the page never
   did.

The one change to what the agent does: it now writes that summary every time it finishes reading a thread.

## What the code says today (ground truth, 2026-08-30)

- `intake_threads` has `status ∈ received|processing|awaiting_human|replied|handled|error`,
  `outcome ∈ dealt_with|needs_human`, `label`, `outcome_note`, `claimed_reference`,
  `auth_state`, `project_id` (SET NULL), `agent_thread_id` (SET NULL). **No index** on
  `project_id`, `status`, or `last_inbound_at`. `intake_messages` carries both directions with
  bodies, `send_error`, `run_id`.
- **No read endpoint exists** for threads or messages. The only intake routes are the
  bridge-auth'd landing `POST /internal/intake/emails` and admin mailbox CRUD
  (`/admin/intake-mailboxes`, no page in `web/`).
- The paused ask is DERIVED: `run_service.newest_live_run(agent_thread_id)` →
  `status == awaiting_input` → the run's last `hitl_request` step (`pendingHitlStep`), rendered by
  `HitlConfirmCard` inside `ConversationPanel` (last run only). `GET /agents/runs` has no status
  filter; there is no cross-matter "what needs me" query.
- `intake_threads.project_id` is set once at ingest and **never reassigned** anywhere; nor is
  `agent_threads.project_id`. Files from attachments were ingested project-scoped onto the stub.
- `projects.intake_state` CHECK still allows `promoted|dismissed`; A1 made it provenance only
  (`candidate` = "born from email"). No row carries the dead values.
- Cockpit = one URL-state route (`?area=&matter=&thread=&view=`; `CockpitView` in
  `cockpit/helpers.ts`); matter tab strip = literal union + array in `ConversationHost.svelte`
  (`conversation|register|memory|documents|grids|capabilities`); list precedent = `GridsPanel`
  + sibling pure `*-helpers.ts` (vitest without DOM).

## Rulings proposed (maintainer to confirm or edit)

1. **Two placements, one component family.** (a) Cockpit-level **Inbox view** (`view=inbox`,
   beside `unfiled`): all threads across the caller's matters, attention-first. (b) A matter-level
   **Inbox tab** in the strip: that matter's threads only. Same list component, `projectId`
   optional. Per A1 there is still NO parallel matter list — the Inbox lists *threads*, matters
   stay in the ordinary matter list (closed-by-intake under the archive filter).
2. **The decision stays in the conversation.** The Inbox never renders a second approval card.
   A row whose conversation has a live ask shows "needs your decision" and deep-links to
   `?matter=…&thread=<agent_thread>` where `HitlConfirmCard` already works (approve/edit/respond
   proven live in 4b). One resume path, one definition of "live ask" (`newest_live_run`).
3. **Attention order** is computed server-side and fixed: live ask → `error` (send failed) →
   `awaiting_human` (no live ask: agent said needs a human, or safe-fail) → `processing`/`received`
   → `replied` → `handled`; ties by `last_inbound_at desc`. Chips: status, `auth_state` (a `fail`
   shows a warning banner in the detail — spoof risk), label (free-form agent tag, display only,
   rendered as text never HTML).
4. **Human attach = authoritative, owner-fenced, moves the whole bundle (ADR-F089).**
   `POST /intake/threads/{id}/attach {project_id}`:
   - target must be an OPEN matter the caller owns (else 404 — never 403; the picker lists only
     the caller's own open matters, so no reference-existence probe is added);
   - refused 409 `thread_busy` while the thread's conversation is in flight
     (`is_conversation_in_flight`) — a paused ask counts as in flight; answer it first;
   - moves `intake_threads.project_id`, the bound `agent_threads.project_id` (the email
     conversation keeps its history and INTAKE-3's reuse keeps working on the target), and the
     `files` ingested from this thread's attachments (owner unchanged);
   - clears `claimed_reference` (the claim was honoured or overruled by a human);
   - if the **source** matter was intake-born (`intake_state='candidate'`) and is now empty
     (no other intake threads, no other conversations, no other files) → archive it with
     `archived_at` + note "merged into ORG-AREA-NNNN by <user>" — closed, never deleted; the
     stub's Matter File / Facts stay with the archived stub (memory fence = archive, A1); the
     target's memory is rebuilt by the agent from the moved conversation on its next run.
     Otherwise the source stays open untouched;
   - audit row: thread id, source/target project ids, counts moved — never addresses/bodies;
   - allowed regardless of thread status (a `handled` thread can still be re-filed).
   Cross-area attach (a Commercial-mailbox thread onto a Privacy matter) is ALLOWED but the
   MAILBOX's bound area agent keeps running intake on it (F086) — the matter's home area only
   governs its memory. F089 records this as the keep-possible seam for `matter_areas`.
5. **Agent-proposed attach is NOT built here** (parent plan layer 4). Keep-possible: a future
   `intake_threads.proposed_project_id` + a tool arg; the human attach endpoint above is what
   such a proposal would resolve into. One line in the backlog.
6. **Retire the dead enum values now**: migration 0102 narrows the `projects.intake_state`
   CHECK to `NULL|candidate` (assert no rows carry `promoted|dismissed`; fail loud otherwise),
   adds the read indexes (`ix_intake_threads_project_id`,
   `ix_intake_threads_status_last_inbound` on `(status, last_inbound_at desc)`), and adds
   `intake_threads.summary` JSONB nullable + `summary_run_id` (ruling 7).
7. **Summary over chain (maintainer ruling 2026-08-30).** The thread detail opens on the
   agent's summary — `intake_threads.summary` JSONB, a list of ≤5 `{title, text}` items
   (title ≤40 chars, text ≤300 chars, plain text, control chars rejected) — with the email chain
   collapsed (`<details>`), "Show the N emails". The summary is written by
   `record_intake_outcome` gaining a required `summary` arg (the same call that already ends
   every intake run) and is REWRITTEN in full on every run so it always describes "the thread
   so far"; the doctrine skill coaches the bullet shape (what they want / what we did / where
   it stands / open points / proposed next step). Safe-fail (run ended without an outcome)
   leaves the previous summary in place and shows "Summary not updated — the agent's last run
   did not finish"; a thread that never had one shows the chain expanded instead. The summary
   is agent-written text about untrusted mail: rendered as text, never HTML; the human corrects
   nothing here (the conversation is where they steer). Row `meta` in the list = the FIRST
   bullet's text, so the inbox itself reads as a digest.
8. **Bodies are shown to the owner, never logged.** The thread detail returns `body_text`
   (their own mail; untrusted for the model, ordinary for the human). Rendered as plain text
   with preserved line breaks — no HTML, no link auto-activation of anything but bare `https`
   URLs shown as text. Attachments appear as filenames linking to the file already in the
   matter's Documents (`files` id), no new download path.

## Endpoints (owner = `Project.owner_id` of the thread's matter; threads whose project was
deleted are visible to the mailbox `owner_user_id` only)

- `GET /intake/threads?project_id=&status=&attention=true&limit=&cursor=` →
  `IntakeThreadListResponse{items:[IntakeThreadRead], next_cursor}`. `IntakeThreadRead`:
  id, mailbox address, subject (single-line neutralised), status, outcome, label, outcome_note,
  auth_state, claimed_reference, `summary[]`, `summary_stale` (last run settled without
  rewriting it), message_count, last_inbound_at, `project{id, name, reference,
  archived}`, `agent_thread_id`, `live_ask{run_id, tool_names, allowed_decisions}|null`
  (from `newest_live_run` via one window-function query, not N+1), `last_send_error`.
- `GET /intake/threads/{id}` → thread + `messages:[IntakeMessageRead]` (direction, from, to,
  subject, body_text, attachment_filenames + resolved `file_ids`, provider_timestamp, run_id,
  send_error) ordered by provider_timestamp.
- `POST /intake/threads/{id}/attach {project_id}` → `IntakeThreadRead` (ruling 4).
- `GET /intake/matters/{project_id}/threads` is NOT added — the list endpoint's `project_id`
  filter covers the matter tab.
All under the `_active` user deps; `MutatingUser` on attach; cross-user 404.

## Web

- `cockpit/helpers.ts`: `CockpitView` gains `'inbox'`; nav entry beside Unfiled with an
  attention count badge (from the list endpoint's `attention=true` head request, polled on the
  existing cockpit reload cadence — no new SSE).
- `components/intake/IntakeInboxPanel.svelte` (list; `projectId?`), `IntakeThreadDetail.svelte`
  (messages + chips + "Open conversation" + "Attach to matter…"), `AttachToMatterDialog.svelte`
  (ModalShell + owner's open matters, searchable by name/reference), `intake-panel-helpers.ts`
  (pure: attention rank, chip tone via `TONE_TO_DOT`, subject/preview, relative time) with vitest.
- `ConversationHost.svelte`: `matterTab` union + `matterTabs` + `matterPanelOpen` gain `inbox`;
  tab hidden when the matter has zero intake threads AND is not intake-born.
- Admin: `routes/lq-ai/(app)/admin/intake-mailboxes/+page.svelte` over the existing CRUD
  (create/list/edit/soft-delete; area + owner pickers; token/keys never shown — there are none
  in this API). Nav entry "Intake mailboxes" next to "Intake bridges".
- F013 tokens, primitives (`PageShell`, `SectionHeader`, `StatusDot`, `ModalShell`), light and
  clean; Agent Inbox UX (attention-first queue, decision deep-link) as the reference, not code.

## Slices (one PR each, full ADR-F005 gate)

- **INTAKE-5a — read surface (2–3 days).** Migration 0102 (indexes + enum narrowing + summary
  columns); `record_intake_outcome` `summary` arg + doctrine coaching + safe-fail stale flag;
  list + detail endpoints; cockpit Inbox view + matter Inbox tab + summary-first detail with
  collapsed chain; admin mailbox page. Tests:
  ownership (cross-user 404, deleted-project fallback to mailbox owner), attention ordering
  table-driven, summary schema rejects >5 / oversize / control chars, safe-fail keeps the
  previous summary and flags stale, `live_ask` derived from `newest_live_run` (paused run present / superseded /
  failed), body never in logs/audit (log-capture test), helpers vitest. Live: dev inbox shows
  the 4b threads with `ORG-COM-0011`; the replied thread's messages in order; the paused ask
  deep-links to the card; a rerun on the NDA thread rewrites the summary to ≤5 titled bullets
  that a fresh reader can act on; screenshots in `docs/fork/evidence/intake-5a/`.
- **INTAKE-5b — human attach (1 day).** ADR-F089; endpoint + dialog; stub archive rule;
  audit row. Tests: moves thread+conversation+files; clears claim; busy → 409; cross-owner
  target → 404; archived target → 404; stub archived only when empty; non-stub source
  untouched; audit carries ids/counts only. Live: send a stranger's tagged email (opens stub
  with `claimed_reference`) → Inbox shows the claim → Attach to `ORG-COM-0011` → stub archived,
  next reply from that sender threads onto `ORG-COM-0011` and continues the SAME conversation.

Builders: Opus for endpoints + attach + migration; Sonnet for the admin page and the list/detail
Svelte once the API is fixed; Fable rulings, reviews, live verification, merge.

## Non-goals (backlog lines in MILESTONES.md)

Agent-proposed attach (ruling 5); merging two stubs into each other; multi-area matters
(`matter_areas`); SSE push for inbox counts; reply composer outside the HITL card (the human
never writes a fresh outbound email here — only approves/edits the agent's); search across
email bodies; the craft items seen live in 4b (signature block + tone hint in the doctrine;
double `Re:` in the recorded draft subject) — small, separate PR, not this slice.

## Security posture (reviewed in every slice)

Owner fence on every read (thread → project owner; orphaned thread → mailbox owner); cross-user
404; attach target validated as caller-owned + open BEFORE any write, all moves in one
transaction; `label`/`subject`/`outcome_note`/`claimed_reference`/bodies rendered as text
(Svelte escapes; no `{@html}`); `auth_state=fail` banner so a spoofed sender is visible before
a human attaches it; no email address or body in logs, audit, or error messages (counts/ids);
list endpoints paginated and bounded; admin page carries no secrets (the API has none).
Attach never touches `intake_messages` provider ids (layer-2 threading keeps working) and
never deletes anything.

## Verification

Suites (api `-m "not provider"`, web check + vitest, mail-bridge untouched) with counts in
the PR; migration 0102 up→down→up on throwaway pgvector; the two live scripts above with
screenshots; HANDOFF updated per slice.
