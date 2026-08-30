# F087 — HITL verbs for `draft_email_reply`, and the approved send

- Status: proposed
- Date: 2026-08-30
- Slice: INTAKE-4b (task #541). Parent plan: `docs/fork/plans/INTAKE-4-plan.md`.
  **Amends ADR-F071** (HITL pause: `approve`/`reject` only, `edit` a named non-goal).
  Related: ADR-F086 + Amendment A1 (email intake, the structural HITL floor), ADR-F088
  (matter reference + stamping + the inbound trust ladder).
- Probe evidence: `docs/fork/evidence/intake-probe/findings.md` (§ INTAKE-4 probe).

## Context

ADR-F071 shipped the pause with exactly two verbs — approve and refuse — and named
`edit` a non-goal "until an arg-diff review UX exists". ADR-F086 then made
`draft_email_reply` the one tool gated *structurally* (`ALWAYS_INTERRUPT_TOOL_NAMES`),
and INTAKE-3 shipped it as a tool that records a draft and **sends nothing**.

INTAKE-4b closes that loop. Two things have to be decided together, because they are the
same decision seen from two sides:

1. **What can a lawyer do with a drafted reply?** Approving prose you cannot change is
   not review, it is a rubber stamp: the realistic outcome of reading an agent's draft is
   "nearly right — fix this clause", and the two verbs we have force that into either a
   flat refusal or an approval of words the lawyer would not have written.
2. **What does approval MEAN?** Until now, nothing: the tool wrote a row. If approval is
   to mean "this goes out", the send has to happen somewhere, and *where* decides what
   the human actually authorised.

Constraints inherited: nothing leaves the building without a click (ADR-F086 — the safety
line is structural, not policy); the api never holds mailbox credentials (the mail-bridge
does); the audit contract carries counts/types/ids, never addresses, subjects or bodies;
email content is untrusted; a double-send is unrecoverable in a way a double-write is not.

## Considered options

### Where the send happens

1. **The tool's execution IS the send.** Under the HITL middleware the tool body runs
   *only after* a human decision, and it runs with exactly the args the human saw (or
   edited). The bytes reviewed and the bytes sent are the same object.
2. **A separate `POST /intake/messages/{id}/send` the UI calls after resuming.** A second
   authenticated human action, independent of the agent loop.
3. **A worker that sweeps approved drafts.** Decouples the send from the run entirely.

### The verbs

A. **Approve / refuse only (status quo, F071).** No new surface, no arg-diff problem.
B. **Approve / edit / refuse, `edit` restricted to `draft_email_reply`.** The one tool
   whose args are prose a lawyer is qualified to rewrite; every other gated tool keeps
   the F071 pair.
C. **Approve / edit / refuse / respond, all four native decisions, for every gated tool.**
   deepagents' `HumanInTheLoopMiddleware` supports all four out of the box.

## Decision outcome

**Option 1 for the send; option B for the verbs, plus `respond` as a UI verb over
`reject`+`message`.**

### The tool's execution IS the send

`draft_email_reply` now (a) inserts the `intake_messages` `direction='out'` row with
`tag_subject(subject, project.reference)` and flushes so the row id exists, (b) calls the
mail-bridge `POST /send` through an injected client with `idempotency_key` = that row id,
(c) stores the provider-assigned `provider_message_id` on the row, (d) moves the thread to
`replied`.

Option 2 was tempting (a second human click is a second safety net) but it splits the
authorisation: the lawyer would approve a tool call and then separately authorise a
message, with a window in between where the approved draft sits sendable-but-unsent and
the agent has already told the lawyer what it did. Option 3 is worse on the same axis and
adds a queue whose failure mode is silent. Option 1 keeps one authorisation, one artefact,
and one moment: what you saw is what left the building.

Failure semantics, deliberately blunt: **no retries anywhere.** A non-2xx, a timeout or a
transport error leaves the out row in place with `intake_messages.send_error` set to an
error CLASS ONLY (`http_502`, `timeout`, `transport`, `duplicate`, `not_configured`,
`no_inbound_message`, `unexpected`) — never a body, an address or a provider string — moves
the thread to `error`, and returns a failure string to the model so it records
`needs_human`. A retry loop around an email send is how a counterparty receives the same
letter three times; the idempotency key exists to make the *client's* one attempt safe, not
to license a second one.

Idempotency has two independent guards: the bridge rejects a repeated
`idempotency_key` with 409 (in-memory bounded LRU, documented limit), and the same key is
handed to AgentMail's own `idempotency_key` parameter. A `reject` never reaches the bridge
at all — the tool body does not run.

**Attachments are not delivered in 4b.** `draft_email_reply` still accepts
`attachment_file_ids` (they are recorded on the row), but a call that names any is
REJECTED before anything is written, with a message telling the model to send without
them. Sending a reply that says "see attached" without the attachment is worse than
refusing; wiring object-storage bytes through the bridge is its own slice.

### The verbs

`edit` is enabled for `draft_email_reply` and for nothing else. `compile_hitl_policy` now
emits `allowed_decisions` **per tool**: the editable floor tool gets
`["approve", "edit", "reject"]`, every area-policy tool keeps `["approve", "reject"]`. The
list rides the interrupt payload, the `hitl_request` step digest and the SSE frame, so the
web renders exactly the buttons the server will accept, and the resume endpoint refuses an
`edit` (422) whose pending ask is not editable. Option C was rejected because `edit` on an
arbitrary tool is a licence to rewrite structured arguments a lawyer never sees rendered —
the F071 objection stands everywhere except the tool whose arguments *are* the artefact.

The edited args are re-validated twice: at the API boundary (`EditedEmailReplyArgs` —
`extra="forbid"`, the same size caps as `DraftEmailReplyInput`, no control characters
except `\n`/`\t`) and again by the tool's own `DraftEmailReplyInput` when it executes. The
edit merges over the model's original args (a field the human did not touch keeps the
model's value) and the tool NAME is taken from the pending action request, never from the
request body — deepagents' `EditDecision.edited_action` carries a name, and letting a
client choose it would turn "edit this draft" into "run any tool".

**Editable means subject and body — not recipients.** The mail-bridge is reply-only by
construction: it derives the recipients from the message being answered and is never handed
an address, which is the property that stops anything the agent produces from mailing a
third party (ADR-F086). A recipient editor would therefore be a control that does nothing,
so `to` is rejected by `extra="forbid"` at the boundary and the card renders the recipient
as read-only context ("Replying to …"). Honouring a human-chosen recipient is a widening of
the egress surface — a real option, but its own decision, not a UI detail.

**`respond` is a UI verb over `reject`+`message`, not a runner path.** Verified in the
installed `langchain.agents.middleware.human_in_the_loop`: a `reject` decision keeps the
tool call, skips execution, and appends a `ToolMessage(content=decision["message"],
status="error")` — i.e. the model already sees the lawyer's words as the tool's result and
can redraft. The native `respond` decision differs only in that it fabricates a
`status="success"` tool result, which for this tool would tell the model a reply was sent
when none was: a lie we decline to make expressible. The UI therefore labels
reject-with-message "Respond — tell the agent what to change" and reject-without-message
"Refuse", and `INTAKE_DOCTRINE` gains one sentence so a refusal carrying a message is
answered with a redraft rather than a closing turn.

### What is NOT stamped

The provider's `reply()` has no `subject` parameter (only the cold-send `send()` does, and
we deliberately expose no cold send). The delivered subject is therefore the provider's
`Re: <original>`; our `tag_subject(...)` value is what we persist on the out row. The
machine-readable stamp is the provider-assigned `provider_message_id` (layer 2) and the
human-readable one is the `Reply-To` plus-address `<local>+<REFERENCE>@<domain>`, which the
bridge composes from its OWN inbox address given a validated `reply_to_tag` — the api and
the agent can never choose an arbitrary Reply-To. Plus-address delivery to the base inbox
is PROVEN (findings.md, external send 2026-08-30). The residual gap: a third party who
receives a *forward* of our reply gets neither stamp. That is layer 3's job and layer 3
needs the tag in the subject — reopen it if AgentMail adds `subject` to `reply()`.

## Consequences

- The lawyer's edit is what is sent, and the row, the audit trail and the mailbox agree.
- One new outbound dependency in `api/`: the mail-bridge, reached with the bridge token
  the api already holds. No AgentMail credential moves. `LQ_AI_MAIL_BRIDGE_URL` follows
  the `LQ_AI_GATEWAY_URL` precedent (a plain base URL with a compose default); an
  unconfigured deployment fails honestly (`send_error='not_configured'`) rather than
  pretending to send.
- `agent_runs.resume_decision` now stores the human's edited text (JSONB). It is human
  prose, never logged and never audited — the audit row still carries the decision type,
  the resume run id and the tool name only.
- The `hitl_request` step digest gets its own, larger bound (the pause is the one step a
  HUMAN acts on, and an editor needs the whole pending draft). Still bounded, still
  truncation-safe: a truncated digest degrades the card to approve/refuse.
- ADR-F071's "approve/reject only" line is superseded for this one tool. Any future `edit`
  candidate must be added to `EDITABLE_TOOL_NAMES` deliberately, with the same question
  asked: are these arguments something the lawyer is looking at, or something they are
  guessing at?
- Migration 0101 adds `intake_messages.send_error` (error class only, ≤100 chars,
  CHECK-bounded). No `provider_thread_id` column: the reply lands in the thread we replied
  into, `intake_threads.provider_thread_id` already holds it, and a mismatch is logged
  rather than duplicated into a second source of truth.
