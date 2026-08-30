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

`draft_email_reply` now (a) writes the `intake_messages` `direction='out'` row with
`tag_subject(subject, project.reference)` and commits it before any network call, (b) calls
the mail-bridge `POST /send` through an injected client with a per-ask `idempotency_key`
(see **Idempotency, precisely** below), (c) stores the provider-assigned
`provider_message_id` on the row — the id an inbound `References` header will name, so
layer 2 can thread the counterparty's answer home (ADR-F088) — and (d) moves the thread to
`replied`. It replies to the newest inbound the agent has actually PROCESSED, not simply
the newest one: a pause can last days, and a follow-up that lands meanwhile is text the
lawyer never read and a sender they never approved replying to.

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

**Idempotency, precisely.** The hazard is not a retry (there are none) — it is
*re-execution*: a worker killed between a successful send and the checkpoint write settles
the run `failed`, a `failed` successor deliberately does not supersede the pause (so a
resume that never consumed the interrupt stays re-approvable), and the card is still live.
Approve then runs the tool body a second time on the same checkpointed call. So the key
must be a property of the ASK, not of the attempt: it is
`sha256(thread_id + tool-call id)` — the checkpointed `tool_call["id"]`, which the HITL
middleware preserves when it rebuilds an edited call and which a re-approval resumes
unchanged. (Verified: an `InjectedToolCallId` parameter is populated through this
codebase's real `build_deep_agent` wiring, and stays out of the schema the model sees.)
A freshly minted row id — the first cut — would have minted a *new* key on the second
attempt and bought nothing.

Three guards, in order, none of them a retry:

1. a delivered outbound row newer than the newest inbound short-circuits before the bridge
   is touched at all ("a reply already went out on this thread");
2. the outbound row is keyed by the same per-ask value while it is undelivered, so a
   second execution updates that row instead of inserting a twin;
3. the bridge refuses a repeated `idempotency_key` with 409 from a bounded in-process LRU
   (documented limit: per process, forgotten on restart), and hands the same key to
   AgentMail's own `idempotency_key`, whose guarantee survives a bridge restart.

Consequence, accepted: re-approving an ask whose send failed ambiguously (a timeout) does
NOT get a second attempt — it gets `duplicate`. That is the intended direction. The lawyer
is told delivery is unconfirmed and can check the mailbox; a second letter cannot be
withdrawn. A `reject` never reaches the bridge at all — the tool body does not run.

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

### One conversation, many intake threads — binding a run to its thread

Found by the first live approval on dev (run `9e9ed16d` → resume `997bd4a5`), which died
with `MultipleResultsFound` before anything was sent. INTAKE-4a's own design is the cause:
the layer-2/3 resolver attaches a reply or a tagged mail arriving on a *fresh provider
thread* as a NEW `intake_threads` row on the same matter, carrying the SAME
`agent_thread_id` so the agent conversation continues. The matter in question had three
(one `awaiting_human`, two still `received`). Every helper keyed on "the thread whose
`agent_thread_id` is this run's conversation" — a `scalar_one_or_none()` that had silently
become a multi-row query, in the tool-grant path, in `safe_fail_intake_thread` and in
`requeue_pending_intake_message` alike.

`LIMIT 1` is not the fix: it turns a crash into a coin flip about which counterparty
thread a reply is sent on. The run is bound to ONE thread explicitly, resolved once at the
composition root and handed to the tools as an id (they may not re-derive it), by:

1. **this run's own work** — the worker stamps `intake_messages.run_id` when it starts a
   run for a message, so that message names the thread;
2. **the conversation's lineage** — a resume is a new `agent_runs` row with no messages of
   its own, so fall back to the newest inbound processed by ANY run on the same agent
   conversation, which is exactly what the paused run was working on;
3. **the single working thread** — with nothing processed yet, the one thread not still
   `received`.

Anything still ambiguous is a bug, not a state to guess through: it logs an ERROR with
counts and ids and returns `None`, which fails CLOSED (no intake tools, no doctrine, no
thread flipped). No new column and no migration: the binding already exists in
`intake_messages.run_id`; it simply was not being read.

Two consequences follow from the same fact. `requeue_pending_intake_message` now hands back
the oldest pending inbound **across every thread on the conversation** — a mail that lands
mid-run is attached to a *sibling* thread and deferred there, and settling the in-flight
run is the moment the whole conversation is free, so a per-thread requeue would strand it
exactly as B3 described. And `safe_fail_intake_thread` parks only the bound thread: the
pending siblings have not been looked at by anyone, and marking them "waiting for you"
would invent a decision nobody was asked for.

### "In flight" is the newest live run, not any live run

The second live finding, after the send itself worked end to end: the requeue hook fired
for the sibling thread and the worker deferred it *again*, permanently. HITL-2 never
mutates a paused row — "superseded" is derived, not written — so run `9e9ed16d` sits at
`awaiting_input` for the life of the conversation. The intake worker asked "does ANY run
here sit at `running`/`awaiting_input`?", which from that moment on is always yes: every
sibling thread starved, however long ago the resume actually completed the work.

The resume endpoint had already needed the right rule and hand-rolled it inline (its
stale-resume guard: the newest run excluding `failed`/`cancelled`, by `started_at desc,
id desc`). Two copies of one rule, and the copy that drifted is the one that starved a
mailbox — so the rule now lives once, in `run_service.newest_live_run` /
`is_conversation_in_flight`, and both call sites use it:

* **the conversation is in flight** iff its newest live run is `running` or
  `awaiting_input`;
* **a pause is still the live ask** iff the newest live run *is* that paused run.

`failed`/`cancelled` stay excluded in both directions, for the same reason in both: a
resume that died before driving the graph never consumed the interrupt, so the ask is
still answerable and the conversation is still busy.

### The requeue that never ran: a deterministic job id plus an arq result key

Third live finding, and the last one between the send and a working loop. With the
in-flight rule fixed the worker no longer saw the conversation as busy — but the sibling
thread still never ran, because the requeue never actually reached the queue.

`enqueue_intake_email_job` keys the job on a deterministic `_job_id` (thread + message) so
a redelivered webhook cannot double-queue an email. arq enforces that by refusing an id
while it is *known*, and "known" includes `arq:result:<job_id>`, which the default
`keep_result` holds for an **hour after the job finishes**. The requeue-on-settle hook
exists to re-run exactly the (thread, message) an earlier attempt returned `deferred` for
— the one id guaranteed to still be in Redis. `pool.enqueue_job` returned `None`, and the
helper returned `True` regardless, so the hook logged a successful requeue and nothing
was queued. Redis on dev held ~10 such `arq:result:intake-email:…` keys.

Three changes, none of which removes the dedup:

1. the worker registers the job as `func(intake_email_job, keep_result=0)`, so a finished
   job (`deferred`/`noop`/`started`) leaves no result key and the id is reusable
   immediately — the dedup window narrows to what it is for, a job still QUEUED or
   RUNNING;
2. the enqueue helper returns `job is not None` and logs `intake_enqueue_deduped` with the
   thread id when arq refuses — a refusal is a fact the caller needs, not noise;
3. `requeue_pending_intake_message` treats a refusal as a real failure (WARNING with the
   thread and run ids). It is the only producer left for a deferred message — the landing
   endpoint already burned its own enqueue — so a silent `False` there is an orphaned
   email.

**`agent_run_job` does not share the trap** and is deliberately left alone: its job id is
keyed on a run id, a run row is enqueued exactly once (a resume is a NEW row with a NEW
id), so a lingering result key can never block a legitimate enqueue — and it already
treats `None` as fatal (ADR-F009: an unqueued run is settled `failed`, never a zombie).
The rule to carry forward: a deterministic job id is safe only while the id is never
legitimately reused; the moment it is, `keep_result` becomes part of the contract.

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
