# PRIV-9 — cockpit: watch the agent change the register

**Status:** **PRIV-9a DELIVERED** (co-visible + run-lock + live-refresh; evidence
`docs/fork/evidence/priv-9a/`, measured commit→visible ≈ 1.1 s; full ADR-F005 gate + adversarial review)
· PRIV-9b PENDING (changed-row highlight + the agent→register change-signal + ADR-F024) · **Date:** 2026-06-19 ·
**Decisions taken (maintainer, this session):** (1) **two slices** — 9a (co-visible + run-lock +
live-refresh, frontend-only, no ADR) then 9b (changed-row highlight + the backend change-signal + ADR-F024);
(2) **poll-while-running** — the register re-reads live as the agent works, not only once on settle.

## Context — the payoff half of the group-chat ask

The group-chat thesis had two halves: **(A)** a lawyer says *"we moved off Mixpanel, we use Hotjar now"* and
the register actually changes — **DONE** (PRIV-8a capability + PRIV-8b live proof on DeepSeek), and **(B)** a
side-panel chat where **the UI updates as the agent works**. PRIV-9 is half (B), sharpened by the maintainer
into a concrete experience:

> You ask the agent to change a system. The chat **locks** (only a Stop button is clickable). As the agent
> makes each change, the user **sees where in the UI the change lands**, and the changed row is **highlighted**.

Three pillars: **co-visible** chat + register · **run-lock** (chat → Stop) · **live highlight** of changed rows.

### What already exists (we reuse, not rebuild) — verified by a 6-reader frontend map

- **The home is `ConversationHost.svelte`** (the cockpit matter workspace), *not* the legacy
  `/lq-ai/matters/[id]` page (bugfix-only, `--lq-*` tokens — wrong place). It already imports `RopaRegister`,
  already gates on `isPrivacyMatter = matter.practice_area_key === 'privacy'` (L114), and already has a
  `matterTab` toggle `conversation | register` (L115, tablist L321-344, branch L346-367). Today the two are
  **mutually exclusive**; co-visibility replaces the toggle's `{#if}` with a split.
- **No IA / ADR landmine for co-visibility.** There is **no ROPA tab or route** in `tabs.ts` — the register
  lives *only* inside a Privacy matter (ADR-F019). So side-by-side touches **zero** top-tab IA and retires
  nothing. (ADR-F014's IA boundary is untouched.)
- **Backend cancel is production-grade and DONE** (F1-S1 / ADR-F009): `POST /api/v1/agents/runs/{id}/cancel`
  (`api/app/api/agent_runs.py` L988-1044) — idempotent, first-writer-wins `running→cancelled`, **404 on
  cross-user**, audited, aborts the arq job *after* the durable settle. `'cancelled'` is wired end-to-end in
  `AgentRunStatus`. The cockpit just has no caller.
- **The active-run signal exists** as derived state: `shouldContinuePollingThread(detail, nowMs)`
  (`web/src/lib/lq-ai/agents/helpers.ts` L500) and the composer **already disables the input while running**
  (`ConversationPanel.svelte` textarea `disabled={submitting || !canSend}` L906). It just relabels the submit
  button — **no Stop button**.
- **The poll to mirror exists:** `ConversationPanel`'s self-rescheduling `setTimeout` loop
  (`poll`/`schedulePoll`/`stopPolling` L215-255), `POLL_INTERVAL_MS = 2000`, gated on run-active, with a
  `pollGeneration` guard against out-of-order responses and robust `onDestroy` teardown. On clean stream end
  it does **one reconcile `getThread` then `dispatch('settled')`** (L378-385) — ADR-F004 ("settled rows
  decide, streams animate").
- **`paneforge` (`Resizable`)** is already wired at the shell (`(app)/+layout.svelte` L20, L159-186) — a nested
  PaneGroup inside `ConversationHost` follows an in-repo pattern, no new dependency. Responsive collapse
  machinery (`isStacked` <720px, `showList`/`showPanel`, L104-109) is reusable for the stacked fallback.
- **Semantic tokens are fully in place** — a transient highlight reuses `--status-completed-wash`
  (`app.css` L322-323; `bg-status-completed-wash`), decayed with `--motion-*` + `motionMs()`
  (reduced-motion-safe). **No new token to mint.**

### The one genuinely hard part — *which row changed?*

Highlighting the touched row needs a signal naming the exact entity. Two were evaluated:

- **Client-side timestamp diff — ❌ not viable as built.** `updated_at` has **no `onupdate`** on any ROPA
  model (`api/app/models/ropa.py`; `grep onupdate` = 0 hits) — it is stamped at INSERT and **never advances**.
  A diff keyed on it would miss every **retire, unlink, re-tag**. Pure link/tag changes touch only the M:N
  join tables — **no timestamp at all**. `TransferSummary` exposes only `retired_at`. Making this route work
  needs a migration (`onupdate`) **and** bumping parents on link/tag **and** exposing timestamps on transfers
  — strictly more work, still blind to link/tag, and only *infers* "changed since I last looked," not
  "changed by this run."
- **Tool-call SSE stream — ✅ the honest signal, after one contained change.** The agent streams over the AI
  SDK UI Message Stream (`api/app/agents/stream.py` → `web/.../sse/ui-message-stream.ts`) and **already emits
  per-tool frames** with a stable `toolCallId` + `toolName`. The gap: every ROPA tool returns *prose*
  ("Recorded vendor 'Hotjar' …") and **never the UUID**; `propose_*` doesn't even know the server-generated
  id. So the fix is to have the tools **return the entity id + verb**, surface it as a **structured
  `{kind, id, verb}` field** on the tool-output frame, and have the client lift touched ids into a
  "recently-changed" set that drives the highlight. This is the only signal that covers **creates + links +
  tags + retires** and proves *"changed by this run, just now."* Ids are **explicitly allowed** by the audit
  contract (counts/types/**IDs**, never raw values), so it is audit-safe.

> **NB the map corrected the brief:** the legacy `web/.../sse/parser.ts` (start/delta/complete/error) is the
> *single-turn chat* stream — **not** the agent loop. PRIV-9b must target `ui-message-stream.ts` /
> `run-stream.ts`.

Because that change creates an **agent-run → register change-signal contract that crosses a module boundary**
(write path → stream → UI) and would surprise a future reader, **it warrants ADR-F024**. Co-visibility,
run-lock, and live-refresh do **not** need an ADR (they sit inside ADR-F019's "register inside a Privacy
matter" + ADR-F009/F004 run semantics).

## Goals

1. **Co-visible** chat + ROPA register inside a Privacy matter — both on screen at once, resizable, with a
   stacked fallback on narrow viewports (keep the toggle as the narrow fallback, not a third state).
2. **Run-lock**: while the agent works, the composer collapses to a single **Stop** control that calls the
   real backend cancel (not just a client-side stream abort), then re-syncs to the `cancelled` terminal state.
3. **Live-refresh**: the register quietly re-reads on the conversation's ~2s cadence **while the run is
   active**, plus a guaranteed reconcile on settle — so changes appear **as the agent commits them**.
4. **Live highlight (9b)**: the row(s) the agent just created/changed get a transient highlight, driven by a
   structured change-signal on the agent stream; the refetched register stays the source of truth.

## Non-goals (explicit)

- **No new top-tab / route, no IA retirement** — co-visibility lives inside `ConversationHost`; `tabs.ts`
  unchanged (no ROPA tab exists). The legacy `/lq-ai/matters/[id]` workspace is untouched (bugfix-only).
- **No direct human edit controls in the register view.** The *agent* remains the only writer — every ROPA
  change goes through the guarded, code-validated tool path (ADR-F018) and lands an **audit row** (tool / IDs /
  size, never raw values), so nothing changes silently. PRIV-9 adds **no** edit/delete/add buttons to
  `RopaRegister` itself; the human drives changes by **asking the agent in chat** (audited), not by editing the
  table directly (which would be an un-guarded, un-audited side channel). PRIV-9 is the surface that makes
  those *already-audited* agent writes **visible live** — its register code only ever GETs, never writes.
- **No stream-delta *data* rendering** — the register's data source of truth is the settled re-read
  (ADR-F004). The stream signal only *targets the highlight + triggers the refetch*; a missed frame loses a
  highlight, never data.
- **No `updated_at onupdate` migration / timestamp-diff route** (rejected above as non-viable + less honest).
- **No `include_retired` audit toggle UI** in v1 — deferred to Backlog (the client DTOs gaining `retired_at`
  in 9b is enough; a retiring row simply leaves the live view).
- **No change to the legacy single-turn `ChatPanel`** beyond using it as copy-reference for the Stop pattern.

## Key decisions

### D1 — Co-visible split inside `ConversationHost`, stacked fallback
Replace the mutually-exclusive `matterTab` branch (L321-367) with a **two-pane** layout for Privacy matters:
chat (`ConversationPanel`) | register (`RopaRegister`), using a nested `Resizable.PaneGroup` (shell pattern).
Below a width breakpoint, fall back to the **existing toggle** (reuse `isStacked`/`showPanel`, L104-109) so
narrow viewports keep one-at-a-time. Reversible: the toggle code path stays as the fallback.

### D2 — Run-lock = real cancel, derived from run state
Add `agentsApi.cancelRun(runId)` → `POST /agents/runs/{id}/cancel`. Add a derived
`agentWorking = !threadOpening && shouldContinuePollingThread(detail, nowMs)`. While `agentWorking`, the
composer renders **only a Stop button** (Square icon, `aria-label="Stop generating"`, `data-testid`, mirroring
`ChatPanel.svelte` L1144-1155) in place of the input/Run button. Stop → read the live run id
(`streamRunId ?? latestRunOf(detail)?.id`) → `cancelRun` → `stopStream()` + `startPolling(threadId)` so the UI
re-syncs to the `cancelled` row (ADR-F004: never optimistically mutate; let the settled row decide).

### D3 — Live-refresh = poll-while-running + reconcile-on-settle (maintainer choice)
`RopaRegister` gains (a) an exported/reactive **quiet `reload()`** that swaps state in place and does **not**
flip `loading=true` (no skeleton flash — mirror the conversation poll, which never blanks `detail`), and (b)
its own self-rescheduling `setTimeout` poll **copied from `ConversationPanel`** (generation guard + `onDestroy`
teardown), gated on a `runActive` prop. `ConversationHost` owns the truth: it relays run-active (bound from
`ConversationPanel`) into `RopaRegister`, and `handleSettled` (L159-162) fires one final reconcile `reload()`
alongside its existing `loadThreads()`/`onActivity()`. Co-visibility means `RopaRegister` is **mounted while
chatting** (it isn't today — plain `{#if}`), so the live view and any highlight state survive naturally.

> **Cost noted:** `load()` fans out 7 endpoints (in parallel — one round-trip); a 2s poll during a run repeats
> that. Privacy runs are short and the refresh is quiet. v1 keeps the full reload for correctness; the
> per-list/conditional (ETag/`If-None-Match` or "only refetch lists whose tool fired") optimization is a
> **separate Backlog slice** (maintainer). But 9a still **measures** the perceived latency now (see *UX
> acceptance* below) so we ship a responsive UX *before* the optimization — optimization is for cost/volume,
> not for the user-facing wait. **Surfaced, not silently capped.**

### D4 — Highlight signal = structured change on the agent stream (ADR-F024)
ROPA tools return the affected **entity id + verb + kind** (keep the human prose too); `stream.py`'s
`tool-output-available` carries a structured `changed: {kind, id, verb}` payload (not buried in the 2000-char
prose summary). The client lifts touched ids into a **`recentlyChangedIds` set hoisted to `ConversationHost`**
(robust to any register remount; fed from the stream consumed in `ConversationPanel`). `RopaRegister` accepts
that set and applies a transient highlight to matching `{#each}` rows (already keyed by entity id:
L268/308/347/379/404).

### D5 — Highlight presentation
Transient `bg-status-completed-wash` on the matched row, fading via `--motion-*` through `motionMs()`
(reduced-motion → no animation, just a brief static wash). **Creates/links/tags** → highlight the new/changed
row. **Retires/unlinks** → the row leaves the live view (the disappearance *is* the signal); a brief
"removed" outro using `include_retired` is **deferred** (needs the client `retired_at` DTO, which 9b adds, but
the animation itself is Backlog). The refetched register is authoritative; the highlight is best-effort.

## Slice decomposition

### PRIV-9a — co-visible + run-lock + live-refresh (frontend only, no ADR)
The whole watch-it-happen foundation, no backend or schema change.
- `web/.../api/agents.ts`: add `cancelRun(runId)` (mirror `tabular.ts cancelTabularExecution`).
- `web/.../components/agents/ConversationPanel.svelte`: derived `agentWorking`; Stop affordance replacing the
  composer while working; `cancelCurrentRun()` handler (cancel → `stopStream` → `startPolling`); expose
  `runActive` (bindable) for the host.
- `web/.../components/ropa/RopaRegister.svelte`: quiet `reload()`; `runActive` prop; self-rescheduling poll +
  generation guard + teardown (copied from `ConversationPanel`).
- `web/.../cockpit/ConversationHost.svelte`: two-pane split for Privacy matters (nested `Resizable.PaneGroup`)
  with the toggle as the stacked fallback; relay `runActive` to `RopaRegister`; `handleSettled` fires a final
  `reload()`.
- **Tests:** vitest for `cancelRun` client + the `agentWorking` derivation + the poll start/stop on run-active
  (helpers); component tests that the composer swaps to Stop while working and that a settle triggers a register
  reload. `npm run check` clean.
- **Verification:** rebuild the `web` container; headed Cypress before/after screenshots (light+dark ×
  wide+narrow) showing (i) chat+register side by side, (ii) chat locked to Stop mid-run, (iii) the register
  changing live across a (mocked or live) run; copy to `docs/fork/evidence/priv-9a/`.

### PRIV-9b — live changed-row highlight + the change-signal (backend + client + ADR-F024)
- `api/app/agents/ropa_tools.py`: tool results carry `entity id + verb + kind` (propose_* return the flushed
  id; link/unlink/retire/tag echo affected ids). Prose unchanged for humans.
- `api/app/agents/stream.py` (+ `runner.py` `_step_from_event` as needed): structured `changed: {kind, id,
  verb}` on the `tool-output-available` frame / step row.
- `web/.../sse/ui-message-stream.ts` + `agents/run-stream.ts`: parse `changed`; accumulate into
  `recentlyChangedIds`, hoisted to `ConversationHost`.
- `web/.../api/ropa.ts`: add `retired_at` to `ProcessingActivityRead`/`SystemRead`/`VendorRead` (client lags
  the backend, which already emits it).
- `web/.../components/ropa/RopaRegister.svelte`: accept `changedIds`; transient highlight + motion decay on
  matched rows (D5).
- **ADR `docs/adr/F024-agent-run-register-change-signal.md`** (new): the change-signal contract, considered
  options (timestamp-diff rejected, prose-parsing rejected, structured stream field chosen), consequences,
  the ADR-F004 "stream animates / settled read decides" boundary, the audit-contract safety of emitting ids.
- **Tests:** api unit tests that each ROPA tool result includes the id/verb/kind and the stream frame carries
  `changed`; web tests that the highlight set is built from frames and applied to the right rows; a missed
  frame degrades gracefully (no highlight, data still correct via reload).
- **Verification:** live run on the dev gateway (reuse the PRIV-8b mixpanel→hotjar flow) screenshotted with
  rows highlighting as the swap lands; evidence to `docs/fork/evidence/priv-9b/`.

## UX acceptance — measured in 9a, not deferred (maintainer: "we don't want users waiting for minutes")
Optimization (conditional/ETag refetch) is a **separate** Backlog slice, but 9a's tests must *capture the
perceived latency now* and prove the wait is never dead time:
- **Time-to-visible ≤ one poll interval (~2 s):** a committed agent change (a row appearing / disappearing)
  shows in the register within ≤~2 s of the tool committing — **not** only at run end. Verified
  deterministically with a scripted/mocked run that commits at known instants and measures
  commit→row-visible, **plus** the live mixpanel→hotjar run for realism. The measured intervals go in the
  evidence as **numbers**, not just screenshots.
- **No frozen screen during a long run:** the user always sees forward progress — streamed tool-call steps in
  the chat **and** rows updating live in the register — so a long *run* never reads as a hung *UI*. (The
  run's total length is the model's; the UX bar is continuous visible feedback, not a blank wait.)
- **No skeleton flicker:** the quiet `reload()` swaps state in place; the register never blanks to its
  "Loading the register…" skeleton on a refresh (only on first mount). Asserted in a component test.
- **Stop stays responsive throughout:** the Stop control is clickable and cancels within one round-trip at
  any point in the run — the user is never trapped waiting for the agent to finish.

## Verification (per slice, ADR-F005 full gate)
`cd web && npm run check` (0 errors) + `npx vitest run` (counts shown) · rebuild the `web` container before
screenshotting · headed before/after matrix (light+dark × wide+narrow) → `docs/fork/evidence/priv-9{a,b}/`,
**including the measured time-to-visible from *UX acceptance*** · fresh-context adversarial **+ security +
simplification** pass (read-only invariant held — register code only GETs, no human-edit controls; cancel
re-sync can't be spoofed cross-user — 404 already enforced server-side; no leaked secrets; no new
`{@html}`/`--lq-*`) · 9b additionally: the change-signal is audit-safe (ids only, no raw values) and the ADR
is drafted · HANDOFF updated · merge per ADR-F005 against `sarturko-maker/lq-ai-fork`.

## Risks / edges
- **Poll volume** (7 endpoints × 2s during a run) — accepted for v1 (short runs, quiet refresh); conditional
  refetch is a Backlog follow-up, logged not hidden (D3).
- **ADR-F004 determinism** — the highlight is animation; the settled re-read is truth. A dropped frame loses a
  highlight, never corrupts the register (D4/D5).
- **Selected detail row vanishes on reload** (e.g. the open vendor gets retired) — `selectedActivity/System/
  Vendor` `.find` returns null silently; 9a should surface a gentle "this record was just retired" empty state
  rather than a blank panel (map gap).
- **Register is deployment-global** (ADR-F019) — a highlight reflects a *firm-wide* record mutation, not
  matter-local state; fine to show to any firm user, no per-user authz subtlety, but the copy shouldn't imply
  "your matter changed this."
- **Narrow-viewport co-visibility** — chat already wants ≥720px before it stacks; chat+register needs its own
  breakpoint + the toggle fallback (D1), or it crushes both panes.
