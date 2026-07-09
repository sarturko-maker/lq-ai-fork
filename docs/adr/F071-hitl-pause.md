# F071 — Human-in-the-loop pause: deepagents-native `interrupt_on`, `awaiting_input` as a settled run state

- Status: proposed
- Date: 2026-07-08
- Deciders: maintainer + agent lead
- Slice: HITL-1 (substrate + pause; resume = HITL-2, cockpit/admin UI = HITL-3)
- Discharges: ADR-F067 D5 (the reserved "stop and ask before named tool classes" seam)

## Context

A practice area needs an enforceable "stop and ask before executing named tools" policy —
not a prompt-level request the model may ignore (retrieved documents are untrusted input;
under prompt injection a doctrine-only control fails first). The B-6 spike probed the
installed pins (deepagents 0.6.8, langgraph 1.2.x) live: deepagents already ships the whole
graph-level pause (`create_deep_agent(interrupt_on=…)` → langchain's
`HumanInTheLoopMiddleware`, hooked `after_model`), it pauses BEFORE any tool of the turn
executes (zero side effects pre-ask, including auto-approved siblings), the pause persists
as a normal checkpoint, and a nested pause inside a `task` subagent bubbles to the root
stream and resumes from the subagent's own namespaced checkpoint without re-billing
completed turns. Our runner today would MIS-SETTLE a pause: the stream ends cleanly at the
interrupt, `execute_agent_run` falls through to `completed` with a NULL answer, and the
next run's `repair_dangling_tool_calls` destroys the pending interrupt. So the runner's
pause handling and the first possible policy write must land in one slice.

## Considered Options

1. **deepagents-native `interrupt_on`** (pause at `after_model`, before any execution) —
   CHOSEN. The policy compiles at composition; every approved call still executes through
   `guarded_dispatch` unchanged (R6 grants / R5 halt / R4 budgets intact — an approval can
   never widen a grant). The payload/decision contract is shipped and tested upstream.
2. **`interrupt()` inside `guarded_dispatch`** (in-tool). Rejected: sibling tool calls of
   the same turn execute before the human decides ("stopped and asked" would be a lie for
   every parallel turn), and on resume the interrupted task re-executes from the top of
   the tool function — double guard checks, double audit rows, duplicate step rows.
3. **No graph surgery: end the turn and ask in text** (a fork after_model middleware that
   strips matching calls + a per-thread "recently approved" memo). Rejected: the approved
   action would be RE-DERIVED by the model after approval, not pinned — the re-issued call
   can differ from the reviewed one. F067 D2's own doctrine ("approval pins bytes") names
   why this fails; a doctrine sentence remains a complementary, not sufficient, control.

## Decision Outcome

Chosen: **option 1**, with the fork owning run-lifecycle + policy semantics:

1. **Policy v1 (schema)**: `practice_areas.hitl_policy JSONB NOT NULL DEFAULT '{}'`
   (migration 0093), shape `{"<exact granted tool name>": true}` and nothing else.
   Decisions `approve`/`reject` only (`edit`/`respond` deferred — arg-diff review UX
   first). No API write surface in HITL-1 (HITL-3 adds the admin card + 422 on names
   outside `hitl_eligible_tool_names()`); only tests and direct SQL can set a policy.
2. **Zero-config invariant (maintainer ruling 2026-07-08, HARD)**: `hitl_policy == {}` —
   or a policy that compiles to empty — means the `interrupt_on` kwarg is NEVER set, no
   `HumanInTheLoopMiddleware` attaches, subagent specs are untouched, and the agent graph
   is byte-identical to today's. The agent must work fully with zero admin setup;
   regression-pinned by tests.
3. **Compile = policy ∩ the run's actual grant set** (`compile_hitl_policy`,
   `app/agents/hitl.py`), computed AFTER the final tool list exists. Unknown/stale names
   drop with a structured warning (name only — a stale policy can never brick a run);
   malformed entries (non-string key, value ≠ `true`) skip the same way. deepagents
   builtins (`task`, `read_file`, …) are never in the grant set, so they are structurally
   ungateable in v1.
4. **The ask is fork-authored**: each gated tool's `description` is a static fork string —
   never model/skill/document text. The pending call's args ride the interrupt payload and
   the step row as data. The approved bytes remain the checkpointed tool call itself
   (never a model re-derivation), so "what the human saw is what runs" holds structurally.
5. **Run state**: a pause settles as **`awaiting_input`** through the existing `settle_run`
   fence (`WHERE status='running'`), with `final_answer NULL`. `finished_at` IS stamped —
   it means "stopped executing", not "delivered"; HITL-2's resume decides what to do with
   it. The lease is not cleared (irrelevant: resume is a NEW run, never a re-claim).
   Nothing burns while paused: no lease-holder, no worker slot, no gateway spend; the
   orphan sweep only touches `running` rows, so a paused run is sweep-exempt by
   construction — and has NO auto-expiry TTL in v1 (a one-line sweep addition later if
   product wants one; not a correctness need).
6. **The settled ask row**: exactly one `agent_run_steps` row, kind **`hitl_request`**
   (migration 0093), written after the checkpointed state confirms the pause (state is
   authoritative; the in-stream `__interrupt__` chunk is only the fast signal) and BEFORE
   the settle. Summary = bounded JSON `[{"tool": name, "args": {...}}, ...]` — a
   display-only copy (ADR-F004: settled rows decide, streams animate). The langgraph
   interrupt id is NOT persisted — HITL-2 re-reads it from `aget_state` at resume time.
   The wire needs zero stream changes: the step mirrors as a generic `data-step`, and the
   terminal `data-run` frame carries `status="awaiting_input"` verbatim.
7. **Subagent scope: LEAD-only in v1.** When (and only when) a policy compiled, every
   fork-authored subagent spec is stamped `interrupt_on={}` (spec-level empty map
   suppresses inheritance); `_ALLOWED_SUBAGENT_KEYS` continues to reject `interrupt_on`
   from admin config. **Accepted exception**: the deepagents auto-added "general-purpose"
   subagent INHERITS the top-level policy — this closes the `task`-delegation bypass for
   lead-granted tools (a nested pause bubbles to the root and is detected identically).
   Residual, named: a gated tool granted to a fork-authored area subagent does not pause
   in v1 (subagent-scope policies are a non-goal).
8. **Paused thread is LOCKED in HITL-1**: `awaiting_input` does NOT join the continuable
   set — a follow-up POST on the thread 409s (`thread_not_continuable`). This deliberately
   guards the repair clash (a follow-up would run `repair_dangling_tool_calls`, which
   answers the pending tool calls and destroys the interrupt) with zero repair changes.
   Cancel stays running-only this slice (silent no-op on a paused run — deferred on
   record); **deleting the thread is the HITL-1 escape hatch** (the pause dies with the
   thread; the delete gate only blocks `running`). HITL-2 makes the thread continuable
   together with skip-repair-on-resume, dissolve-on-new-message, and cancel-while-paused.
9. **Resume (HITL-2, designed not built)**: a follow-up run whose graph input is
   `Command(resume=…)` on the same thread; owner-scoped endpoint mirroring cancel; audit
   `agent_run.hitl_decision` with tool name(s) + decision type(s) + run/step ids —
   counts/types/IDs, never args. Refuse is a first-class resume decision (the model closes
   the turn honestly), distinct from cancel. Pinning stays a human-only action (ADR-F042
   posture: approval is authenticated human input, never an agent tool).
10. **Budget across the pause**: brakes are per run row, so one logical turn can spend up
    to 2× its envelope across a pause (each row reports its own spend honestly — ADR-F009
    lifecycle unchanged). Optional tightening (seed the resume run's budget from the
    paused run's `total_tokens`) is named, not required.

## Consequences

- Migration 0093 widens `chk_agent_runs_status` (+`awaiting_input`) and
  `chk_agent_run_steps_kind` (+`hitl_request`) and adds `practice_areas.hitl_policy`.
  **Downgrade is documented-lossy**: `awaiting_input` runs are UPDATEd to `failed` (never
  deleted — run history is audit-adjacent), `hitl_request` step rows are deleted, then the
  CHECKs re-narrow and the column drops.
- The partial unique index `uq_agent_runs_thread_running` (predicate `status='running'`)
  stops covering a paused thread — the API-level 409 is the only second-run brake until
  HITL-2 (no path creates a second run in HITL-1).
- A paused run parks indefinitely (no TTL); the pending-approval surface is HITL-3. Until
  then a paused thread reads `continuable=false` and the cockpit shows a neutral
  "Waiting" badge (defensive web hardening only — no confirm card yet).
- Eval/scenario paths never arm (`interrupt_on` requires checkpointer + thread_id;
  `execute_agent_run` refuses to arm without both, since a pause without a checkpoint is
  unrecoverable).
- Named non-goals for this substrate (all possible later): `edit`/`respond` decisions,
  subagent-scope policies, per-matter policy overrides, arg-conditional (`when`)
  predicates, auto-expiry TTL, multi-interrupt resume UI.

## Addendum — HITL-2 (resume round-trip), 2026-07-09

HITL-2 discharges decision 9 ("Resume, designed not built") and retires the HITL-1 R11
interim lock. Backend only; the confirm card + admin policy write + LLM-driven live verify
remain HITL-3.

1. **Run-per-resume, decision durable on the row (migration 0094).** Resolving a paused run
   creates a NEW `AgentRun` on the SAME thread; the paused run is NEVER mutated — it stays
   `awaiting_input` as the durable record of the ask. The worker only ever receives `run_id`
   and reads everything else from the row, so the human's choice lives on the new row:
   `agent_runs.resume_decision` — nullable JSONB, migration 0094. Its PRESENCE marks the run
   as a resume (composition keys off it); NULL for every ordinary run (zero-config: ordinary
   runs are byte-identical). No CHECK — dict-typed at the ORM boundary; a malformed value
   degrades the run to `failed` in the runner, never raises (mirrors `hitl_policy`).
   Downgrade drops the column (no data migration — a NULL-or-decision column loses nothing
   the older schema needs).
2. **Endpoint `POST /agents/runs/{run_id}/resume`.** Owner-scoped 404 (never 403); closed-enum
   Pydantic body `{decision: {type: approve|reject, message?}}` (`extra="forbid"`). Guards:
   409 `run_not_awaiting_input` (not paused); 409 `run_superseded` (the paused run is no
   longer the thread's tail — already resolved, or dissolved by a follow-up); 409 `thread_busy`
   (a concurrent resume — DB-enforced by `uq_agent_runs_thread_running` on the flush); 429 at
   the running-run cap. One `agent_run.hitl_decision` audit row: decision type + tool name +
   resume-run id — counts/types/IDs only, NEVER the tool args or the reject message.
3. **Single decision, fanned across the turn (v1).** The body carries ONE decision (one
   Approve/Refuse pair — no per-call granularity until `edit` lands). At resume time the runner
   re-reads the pending interrupt(s) from `aget_state` (`_pending_interrupts` — the interrupt id
   is never in our schema) and builds `Command(resume={interrupt_id: {"decisions":
   [{"type": …}] × n_action_requests}})`, fanning the one decision across every gated call in
   the paused turn. Probed shapes (spike §3.1): approve `{"type":"approve"}`, reject
   `{"type":"reject","message":…}`.
4. **Skip repair on resume.** The resume path SKIPS `repair_dangling_tool_calls` — repair would
   answer the gated tool_call with a synthetic ToolMessage and destroy the pending interrupt.
   The guard is `resume_decision is None` (not merely "checkpointer + thread present"). A
   no-longer-present interrupt (raced with a cancel, or dissolved) settles the resume run
   `failed` — never a silent mis-completion.
5. **`awaiting_input` joins the follow-up-admission set (`_TERMINAL_STATUSES`).** Two effects,
   both wanted: (a) a NEW-message follow-up on a paused thread is admitted and DISSOLVES the
   pause — the NON-resume path repairs (synthesises answers for the gated calls) and the model
   responds to the new message (spike §3.3, "a new user message dissolves the pause"); (b)
   `continuable` reads true for a paused thread (advisory; HITL-3 decides composer-vs-card UX).
   This RETIRES the R11 lock.
6. **Cancel-while-paused.** Cancel now settles `awaiting_input → cancelled` (abandons the ask —
   distinct from `reject`, which lets the model close the turn). A paused run has no live worker,
   so the arq abort fires only for the `running` transition.
7. **Budget across the pause is honest** (already noted in HITL-1): the resume run arms its own
   envelope, so one logical turn can spend up to 2× across a pause — recorded, not tightened.
8. **Verification:** the resume mechanism is proven end-to-end against the REAL
   `HumanInTheLoopMiddleware` on a REAL Postgres test DB (approve executes the gated call;
   reject closes the turn without executing; skip-repair asserted on the resume path and NOT on
   the follow-up path; no-pending-interrupt → failed). Migration 0094 up/down/up on a throwaway
   pgvector. The LLM-driven confirm-card round-trip is HITL-3's live gate.

## Addendum — HITL-3 (confirm card + admin policy write), 2026-07-09

HITL-3 is the final rung: it makes the pause/resume loop usable by a lawyer who never touches
the API, and gives the admin a switch for WHICH tools pause. Web-heavy + one admin endpoint +
the LLM-driven live gate. No migration.

1. **Confirm-card vocabulary (maintainer decision).** Title **"Waiting for your go-ahead"**;
   buttons **Approve** · **Refuse**. "Refuse" (not "Cancel") reads as a deliberate, first-class
   decision — distinct from cancelling, which abandons the whole ask (decision 6 above). The
   backend enum stays `approve`/`reject`; the card is pure presentation.

2. **The card renders off the SETTLED `hitl_request` step — NOT a transient frame; the api
   needs no change.** ADR-F004 (settled rows decide) is load-bearing here: the card must persist
   until the human answers and survive a page reload while the run sits `awaiting_input`, so it
   reads the durable `hitl_request` step (`name` = gated tool, `summary` = the bounded
   `[{tool,args}]` JSON digest — parsed DEFENSIVELY, rendered ESCAPED as untrusted model output).
   HITL-1 already emits everything the card needs on the wire (proven by
   `test_pause_wire_tail_carries_awaiting_input`), so HITL-3 adds **no new stream frame and no
   backend change for the card**. Two one-line web validator widenings (`isStepKind` +
   `parseRunPayload` in `run-stream.ts`) stop the generic `data-step`(hitl_request) /
   `data-run`(awaiting_input) frames from being dropped, so the card also arrives + animates
   (CSS mount keyframe, motion-guarded) on the LIVE stream, not only on the reconcile poll. A
   dedicated `data-hitl-request` frame was rejected as redundant with the settled step and
   against the ADR-F004 "transient frames are animation-only / a late subscriber may miss them"
   invariant — the opposite of what a confirm card needs.

3. **Actionable pending-approval chip — one edit, every surface.** `statusBadge('awaiting_input')`
   flips from `{Waiting, neutral}` to **`{Needs you, warn}`** (amber attention). Because every
   cockpit rail / matter-list / thread badge routes through `statusBadge` → `StatusPill`, the one
   change propagates everywhere; the in-conversation card carries the actual Approve/Refuse
   actions (the list rows hold only `last_run_status`, not the paused run id — a passive
   deep-link indicator by construction).

4. **Admin write: `PUT /practice-areas/{key}/hitl-policy` (AdminUser-gated).** PUT-replace: the
   body is the COMPLETE desired `{tool: bool}` map; the stored column keeps only the enabled
   entries, so `{}` stays the zero-config default (no `interrupt_on` → byte-identical graph).
   Keys are validated against the GLOBAL `hitl_eligible_tool_names()`; an unknown name is
   **rejected with a 400** (`ValidationError`, matching the `agent_config` admin-validation
   posture — NOT a schema 422; the HITL-3 kickoff said "422" but the app's `ValidationError`
   maps to 400, and consistency with the sibling admin write wins). The runtime side stays
   lenient (HITL-1's `compile_hitl_policy` drops stale/unbound names with a warning and
   intersects with the run's ACTUAL grants), so the strict write-time guard only catches typos.
   One `practice_area.hitl_policy` audit row: the sorted enabled tool NAMES (app identifiers, not
   user data). The admin card's checklist offers the AREA's gate-able DOMAIN tools —
   `hitl_eligible_tools` on the read model = the union of the area's bound tool-group grants
   (`area_hitl_eligible_tool_names`); matter-scope reads (search/read/memory) are globally
   eligible but deliberately not surfaced (pausing a read is rarely wanted). There was NO
   pre-existing "F067-D5 placeholder" card — HITL-3 creates the admin section outright.

5. **Live gate (the MODULES-milestone proof).** A Commercial `hitl_policy={"apply_redline":true}`
   stops `apply_redline`; the lawyer sees the card, clicks Approve; the redline applies and the
   run completes — driven by a real gateway model (DeepSeek/Adeu path). This is the milestone's
   acceptance evidence, run in the browser, not a unit test.

6. **Verification (deterministic).** Backend: the admin PUT is proven on a real Postgres test DB
   (sets + persists + audits; PUT-replace normalises `false`→absent; unknown tool → 400 and
   nothing persisted; non-admin → 403; unknown area → 404), plus a `area_hitl_eligible_tool_names`
   unit test. Web: the card's parse/vocabulary helpers, `resumeRun`, the widened validators,
   `pendingHitlStep`, the `Needs you` badge, and the admin `hitlEnabledTools`/`hitlPolicyDirty`
   helpers are unit-tested (module-script pattern, no `@testing-library/svelte`). The five
   endpoint/RBAC drift guards move by the AdminUser route: `test_mutation_rbac` 136→137 +
   185→186 (get_mutating_user `gated` UNCHANGED at 70), `test_openapi` 185→186 + EXPECTED_PATHS,
   `test_endpoints` IMPLEMENTED_ROUTES.
