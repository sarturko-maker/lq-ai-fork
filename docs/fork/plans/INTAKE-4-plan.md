# INTAKE-4 — reply with a human in the loop, and stamp every email so replies land in the right matter

Status: DRAFT for maintainer edit (written 2026-08-30 at the close of INTAKE-3, PR #294).
Parent: `docs/fork/plans/INTAKE-INBOX-plan.md` (ACCEPTED) + § Amendment A1; ADR-F086 + § A1.
Tasks: #541 (HITL edit/respond + send). New ADRs drafted in the PRs: **F087** (HITL verbs for
`draft_email_reply`), **F088** (matter reference + neutral email stamping + resolver).

## In simple terms

Today the intake agent stops at "here is what I would reply" and the run freezes for a human.
INTAKE-4 is the human's side of that, and the plumbing that keeps a conversation together:

1. The lawyer sees the agent's draft reply on the matter.
2. They **Approve** (send as-is), **Edit** (fix wording, then send) or **Respond** ("no — say we
   need the DPA first"; the agent redrafts and pauses again).
3. On approve/edit the api asks the mail-bridge to **send** it as a reply on the original email
   from the intake address. The outbound row gets the provider message id; the thread → `replied`.
4. Every email we send is **stamped** with the matter reference, so when the counterparty
   answers — even from a fresh email or a forward — it lands in the same matter and the **same
   agent conversation** continues (INTAKE-3's `agent_thread_id` reuse).

Nothing leaves the building without a click.

## Maintainer rulings (2026-08-30, binding)

- **Neutral naming.** Nothing user-visible, in headers, subjects, Message-IDs or reference
  numbers carries our product name. The codebase is Apache-2.0; tenants make it their own.
- **Matter reference = `ORG-AREA-NNNN`** (e.g. `NWT-COM-0042`, `NWT-PRV-0007`):
  - `ORG` — short code the admin sets once (setup wizard + House Brief admin page; default
    derived from the org name, uppercase, 2–6 chars, `[A-Z0-9]`).
  - `AREA` — short code per practice area, admin-editable; shipped defaults in the profile
    manifests (`COM`, `PRV`, `AIC`, …); admin-created areas choose their own.
  - `NNNN` — per-org-per-area counter, zero-padded (grows past 4 digits), never reused.
    Counter TABLE with a row lock (`matter_reference_counters(org_id, practice_area_id, next)`
    `SELECT … FOR UPDATE`), not a Postgres sequence — per-tenant stacks and migrations stay simple.
  - Assigned to EVERY matter (intake-born or cockpit-created) at creation; backfilled once in
    the migration in `created_at` order. Column `projects.reference` UNIQUE per org; immutable.
  - Open question for the maintainer: a year segment (`NWT-COM-2026-0042`) — common in legal
    ops; default in this plan is NO year (shorter to say and type).
- **AREA is the matter's HOME area** (the one that owns it, runs intake, accumulates its
  memory). Keep-possible invariants for the future cross-area case (a Commercial matter pulls
  in the Privacy agent — a named future milestone, NOT built here): (i) a matter never gets a
  second reference when a helper area joins; (ii) "which areas touch this matter" lives in a
  future `matter_areas` relation, separate from the reference — `projects.practice_area_id`
  stays the home area; no code in INTAKE-4 may assume one-area-per-matter beyond that column.

## Stamping and resolution (ADR-F088)

Layers, strongest first. Weak layers NEVER auto-merge on their own (email content is
untrusted — a subject tag is sender-controlled text and must not inject a stranger's email
into a matter that may hold privileged material).

| # | Signal | Survives | Trust | Action at ingest |
|---|---|---|---|---|
| 1 | Existing `(inbox, provider_thread_id)` | same thread | — | continue thread (today) |
| 2 | `References`/`In-Reply-To` contains one of OUR outbound Message-IDs | replies, reply-all | strong (they received our mail) | attach to that matter; NEW `intake_threads` row on the same `project_id` |
| 3 | Subject tag `[ORG-AREA-NNNN]` | replies AND forwards | weak | if sender is on that matter's Roster → attach; else new matter + `needs_human` note "claims ORG-AREA-NNNN — attach?" |
| 4 | Agent suggestion (Roster sender match; hybrid search over open matters) | anything | proposal | note on the outcome (INTAKE-5 surfaces it) |
| 5 | Human "attach to Matter X" | anything | authoritative | INTAKE-5 operation (A1) |

Outbound stamping: subject `Re: <original> [ORG-AREA-NNNN]` (tag appended once, idempotent);
Message-ID `<m.<ORG-AREA-NNNN>.<uuid>@<inbox domain>>` — the bridge must let api choose the
Message-ID (probe: does AgentMail `send`/`reply` honour a caller-supplied Message-ID or custom
headers? If NOT, fall back to persisting the provider-assigned id and matching on it — layer 2
still works, only the id is opaque). Persist every outbound `provider_message_id` on
`intake_messages`; layer 2 lookup = `intake_messages.provider_message_id IN (References)`.
Optional 10-minute probe, decide before build: **plus-addressing** (`inbox+ORG-AREA-NNNN@…` as
Reply-To) — the recipient address survives every client; only worth it if AgentMail delivers
plus-addresses to the base inbox.

## HITL verbs for `draft_email_reply` (ADR-F087, amends F071)

- `ResumeDecision` gains `edit` (edited `to/subject/body` args → the tool executes with the
  edited args) and `respond` (free text handed to the model as the tool result → it redrafts and
  pauses again). `approve`/`reject` unchanged. **Only `draft_email_reply` may be edited**
  (`allowed_decisions` per tool: floor tool gets all four; area-policy tools keep approve/reject).
- Verify before building: `reject` with `message` may already behave as `respond` (model sees
  the refusal and can call again) — if so, `respond` is a UI verb over `reject`+message, not a
  new runner path. Do not duplicate.
- The tool's execution IS the send: after approval it (a) inserts the `intake_messages`
  direction='out' row with the stamped subject, (b) calls bridge `POST /send`
  (`reply_to_provider_message_id`, bearer `LQ_AI_BRIDGE_TOKEN` — api holds only the bridge
  token, never AgentMail creds), (c) stores the returned `provider_message_id`, (d) thread →
  `replied`. Send failure → row kept with `send_error` (counts/types only), thread `error`,
  tool returns the failure so the model can record `needs_human`. No retries that could
  double-send: idempotency key = the out row id, sent to the bridge; bridge rejects a repeat.
- Web: `HitlConfirmCard` gains an args editor for `draft_email_reply` only (to/subject/body),
  and a "Respond" text box. Reuse the existing approve/reject card; no new surface (INTAKE-5).

## Slices (one PR each, full ADR-F005 gate)

- **INTAKE-4a — matter reference + stamping substrate (1–2 days).** Migration 0100:
  `organization_profile.org_code`, `practice_areas.area_code` (manifest defaults + drift-guard),
  `matter_reference_counters`, `projects.reference` UNIQUE + backfill; `allocate_reference()`
  in a small service called from every project-creation path (cockpit + intake). Resolver
  layers 2+3 in `intake_emails.py` landing (new thread on existing project; Roster check).
  Admin: org code on the House Brief page + wizard step. ADR-F088. Tests + live: forward an
  old thread's email with the tag from a Roster sender → lands on the same matter.
- **INTAKE-4b — HITL edit/respond + approved send (2–3 days).** ADR-F087; `ResumeDecision`;
  `_build_resume_command`; per-tool `allowed_decisions`; `draft_email_reply` executes the send
  via the bridge; `HitlConfirmCard` editor. Live: approve → counterparty receives the reply
  with the tag and our Message-ID; reply to it → lands on the same matter, same agent
  conversation; edited text is what gets sent; `respond` yields a redraft.

## Non-goals (INTAKE-5 / later)

Cockpit inbox surface, matter view listing all its threads, the human "attach to Matter X"
operation, agent-proposed attach, multi-area matters (`matter_areas`), auto-ack templates,
retiring `intake_state` enum values `promoted/dismissed`.

## Security posture (reviewed in every slice)

Subject tags and References are untrusted input — parse with a strict regex, never trust
alone (layer 3 needs Roster membership). Outbound body is human-approved text; still cap
size and reject control chars. The bridge token is the only credential in api. Idempotent
send (no double-send on retry). Logs/audit: reference ids, counts, decision names — never
email bodies or addresses. Cross-user: 404. Edited args re-validated by the tool schema.

## Verification

Unit: allocator concurrency (two allocations under `FOR UPDATE` → consecutive numbers);
resolver table-driven (each layer, spoofed tag from a stranger → needs_human); stamping
idempotent; `ResumeDecision` edit only for the floor tool. Live on dev via the running bridge:
the four scenarios in the slice bullets. Eval pack: add 2 envelopes (tagged reply from Roster
sender; tagged email from stranger).
