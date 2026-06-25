# F024 — Agent-run → register change-signal (live changed-row highlight)

- Status: accepted
- Date: 2026-06-19
- Extends: ADR-F004 (render-deterministic UI — settled rows decide, streams animate), ADR-F006 (the AI SDK UI
  Message Stream wire spec), ADR-F018/F019 (agentic ROPA module — code-validated agent writes over the
  deployment-global register), ADR-F023 (the change verbs the signal reports on)
- Milestone: PRIV-9b (cockpit — *watch* the agent change the register: the changed row is highlighted live)

## Context

PRIV-9a put the conversation and the read-only ROPA register **side by side** and made the register re-read
live (~2s) while the agent works, so a row the agent adds/retires appears within ~1s of commit. The remaining
half of the maintainer's ask — *"as the agent makes each change, the user sees **where** the change lands, and
the changed row is **highlighted**"* — needs a signal that names the **exact entity** that just changed.

The register reload alone can't supply this honestly. The settled `agent_run_steps` rows carry only a bounded
prose summary of each tool result ("Recorded vendor 'Hotjar' …"); they don't carry the entity id. So a
re-reading register knows the new *set* of rows but not *which* one this run just touched (a create adds a
row, but a link/tag/retire changes a row's contents or removes it — not detectable by a naive set-diff).

This is a new contract: an **agent-run → UI change-signal** that crosses the write path → stream → client
module boundary. It would surprise a future reader ("why do the ROPA tools talk to the SSE stream?"), so it
gets an ADR.

Constraints it must honour:

- **ADR-F004** — the highlight is *animation*; the settled re-read remains the source of truth. A dropped (or
  even a spurious) signal may lose or mis-fire a flash, but must never corrupt the register or render a
  pending change as real.
- **ADR-F019** — the register stays read-only in the UI; the signal is a *rendering* hint, never a write path.
- **The audit contract** — audit rows (and anything secret-adjacent) carry counts/types/**IDs**, never raw
  values. Emitting an entity id is explicitly inside that envelope; emitting the proposal's content would not
  be.

## Considered Options

1. **Client-side `updated_at` timestamp diff.** Have the register infer "changed since I last looked" from
   row timestamps. Rejected: no ROPA model has `onupdate` (`updated_at` is stamped at INSERT and never
   advances), so it would miss every retire/unlink/re-tag; pure link/tag changes touch only the M:N join
   tables (no timestamp at all); and it only *infers* "changed since," never proves "changed **by this run,
   now**." Making it work needs a migration **and** parent-bumping on link/tag **and** transfer timestamps —
   strictly more work, still blind to links.

2. **Parse the entity id out of the tool's prose result.** The `tool-output-available` frame already carries
   the tool's prose ("Recorded vendor 'Hotjar' …"). Rejected: the prose carries the *name*, not the id, and
   is bounded to ~2000 chars (a multi-category tag truncates); parsing localized prose for a machine signal is
   fragile and couples the UI to wording.

3. **Return the id through the tool / piggyback on `tool-output-available`.** Make the tools return a
   structured `(content, artifact)` (langchain `content_and_artifact`) or stuff `{kind,id,verb}` into the
   tool-output frame, correlated by `toolCallId`. Rejected on two counts: (a) the guarded tool contract is
   `-> str` (the model reads prose), and the event-output shape that would carry an artifact is version-coupled
   to our deepagents/langchain pin (fragile); (b) correlating a drained change to a *specific* `toolCallId`
   mis-attributes under the known concurrent-tool execution (the find-or-create parallelism), since one
   tool-output frame would then claim another tool's change.

4. **A run-scoped change ledger → a dedicated transient stream frame (CHOSEN).** The tools record their
   affected `(kind, id, verb)` into a run-scoped ledger (injected, never model-visible); the runner drains it
   onto a dedicated `data-ropa-change` frame the client lifts into a recently-changed set.

## Decision Outcome

**Option 4.** The honest, contained signal — it covers creates **and** links/tags/retires/unlinks, proves
"changed by this run, just now," needs no migration, keeps the model-facing prose byte-for-byte unchanged, and
stays inside both the ADR-F004 boundary and the audit contract.

- **Producer — `RopaChangeLedger`** (`api/app/agents/ropa_changes.py`): a per-run, append-only,
  cursor-draining list of `RopaChange{kind, id, verb}`. Created at the composition point **only for Privacy
  runs**, injected into `build_ropa_tools` as a **B-class** dependency (ADR-F004 — runtime-injected, never in
  a model-visible tool signature). Each mutating ROPA tool body records its change **after a successful
  flush** (so the id is real) and **only on a real change** — an idempotent no-op (re-link, re-retire,
  re-tag) or a validation rejection records nothing, so the highlight never fires on a non-change.
  - **`kind ∈ {processing_activity, system, vendor}`** — the three top-level register tables the UI renders.
    A link records **both** ends (activity + system/vendor); a tag records the **activity**; a transfer
    (which has no top-level row of its own) records its **parent activity**. Every change therefore washes a
    visible top-level row.
  - **`verb ∈ {create, retire, link, unlink, tag}`** — carried for honesty/auditing and future per-verb
    treatment; the v1 highlight is verb-agnostic (any change washes the row).

- **Transport — a dedicated transient `data-ropa-change` frame.** `_drive_agent` drains the ledger at each
  `tool_result` step and calls `RunStreamPublisher.ropa_changed(kind, id, verb)`, which emits
  `{type: "data-ropa-change", transient: true, data: {kind, id, verb}}` — the AI SDK `data-*` extension (the
  same shape as the existing `data-plan`). A **dedicated** frame (not piggybacked on `tool-output-available`)
  **decouples the signal from `toolCallId`**, so the cursor-draining ledger emits each change exactly once
  regardless of which (possibly concurrent) tool result triggered the drain. **Transient** ⇒ not tracked as an
  open block, so a mid-run subscriber simply never sees an already-emitted change (animation only).

- **Consumer — a host-hoisted recently-changed set.** `parseRopaChangePayload` (web `run-stream.ts`) validates
  the frame (id load-bearing; malformed → dropped). `ConversationPanel` dispatches a `ropachange` event per
  frame; `ConversationHost` accumulates ids into a `$state` set **hoisted at the host** (survives any register
  remount) and clears it after a decay window (**5s** — comfortably greater than the ~2s register poll, reset
  on each new change so a burst stays lit then fades together). `RopaRegister` takes the set and applies a
  transient `--status-completed-wash` to the matching `{#each}` rows, fading via a CSS transition on the base
  row (reduced-motion → instant, no animation).

## Consequences

- **Honest "watch it happen."** A swap (add Hotjar → link → unlink Mixpanel → retire Mixpanel) washes the new
  vendor row green as it lands, and the retired row drops out on the next reload — the lawyer sees *where*
  each change happened, live.
- **Determinism preserved (ADR-F004).** The signal only targets the highlight; the register's poll/reconcile
  carries the true rows. A missed `data-ropa-change` frame (late subscriber, poll-only mode, transport blip)
  loses a flash, never data. A spurious entry (e.g. the rare audit-failure rollback after a tool body recorded
  its flush) self-corrects: the reloaded register has no matching row, so nothing washes.
- **Read-only register intact (ADR-F019).** The signal is a one-way rendering hint; `RopaRegister` still only
  GETs. No human-edit controls, no un-guarded write path.
- **Audit-safe (the contract).** The signal — and the ledger — carry only `(kind, id, verb)`: ids and types,
  never the proposal's values. No new secret/raw-value surface.
- **No schema change.** Purely in-flight (the ledger lives for the run; the frame is transient). `retired_at`
  is deliberately **not** added to the web Read DTOs in 9b — reads exclude retired rows by default, so a
  retire simply drops the row on reload; adding the field now would be dead code until the deferred "removed
  outro" animation that would consume it (Backlog).
- **Non-Privacy runs unaffected.** The ledger is `None` for every non-Privacy run; the drain is skipped and
  the qualified default loop is unchanged.
- **Known limits / Backlog.** Category-vocabulary rows (data-subject / data-category tables) don't wash on a
  tag — the *activity* does (the user's mental model: "activity X now has these categories"); washing a newly
  created vocabulary term too is a possible follow-up. The "removed outro" animation for a retired row (needs
  the `retired_at` DTO + `include_retired` read) stays deferred.

## Addendum — C5b-3 (2026-06-25): the ledger seam is now area-agnostic

The Commercial negotiation loop became the **second** consumer of this ledger→drain→transient-frame seam
(inline live verdict chips — `data-deal-change`, ADR-F032), and the composition root already anticipated a
**third** (the assessment register). So the seam was generalised rather than duplicated:

- **`app/agents/live_changes.py`** defines two tiny Protocols — `LiveChange` (`publish(publisher)`) and
  `ChangeLedger` (`drain() -> Sequence[LiveChange]`). The runner's drain at each `tool_result` is now
  `for change in change_ledger.drain(): change.publish(publisher)` — area-agnostic, one loop for all.
- `RopaChange` gained a 2-line `publish` (→ `publisher.ropa_changed`); behaviour and the
  `data-ropa-change` frame are byte-identical (the existing ropa tests are unchanged and green). The new
  `DealChange` (`app/agents/deal_changes.py`) publishes `data-deal-change`.
- Each area still creates its **own** concrete ledger at the composition point (Privacy →
  `RopaChangeLedger`, Commercial → `DealChangeLedger`), left `None` for areas that produce no signal — the
  "non-Privacy runs unaffected" property generalises to "areas without a ledger are unaffected".

No schema change, no frame-shape change, no new gate. The render-determinism + audit-safety properties
above hold verbatim for `data-deal-change` (it carries only `{ref, verdict}`).
