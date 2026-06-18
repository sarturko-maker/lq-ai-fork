# Fork milestones

Outcome-based milestones, not calendar sprints. Each milestone breaks into vertical slices
(end-to-end, runnable, testable, ≤2–3 days, one PR each). Re-plan at milestone boundaries.
Status: active — governed by accepted ADR-F001..F005. Merges per ADR-F005 (agent-merged, hardened gate).

## F0 — Agentic substrate (unblocks everything)

Outcome: a model drives a real tool-calling loop through the gateway, in a multi-turn conversation —
and the maintainer can SEE a deep agent working in the UI from S3 onward (re-sequenced 2026-06-10:
visibility pulled forward via the render-deterministic pattern, ADR-F004; SSE v2 upgrades it later).

- **S1 ✓ done** — langgraph 1.2.4 + `deepagents==0.6.8` substrate; gateway block-content + tools
  passthrough; live model-driven tool loop proven on MiniMax-M3 (PR #24).
- **S2 — gateway tools formalization + agent-run records.** Promote `tools`/`tool_choice` to typed
  request fields; streaming tool-call delta tests; routing-log `purpose='agent_loop'`. New
  `agent_runs` + `agent_run_steps` tables — each loop step persisted as it completes (the UI
  contract for S3 polling) — with POST/GET run endpoints and interim caps (max steps + wall-clock
  shipped; per-run cost caps land with F1 R4, full `guarded_tool_call` integration in F1). Carry-overs
  from the S1 review: factory key exposure (httpx client, not `default_headers`), subagent
  model-bypass guard in `build_deep_agent`, Anthropic `tool_use`/block-content translation,
  anonymization decision for block content.
- **S3 ✓ done — first visible agent (Agents tab v0).** One hardcoded preview area ("Commercial —
  preview"), one message box, capability rail v0: the agent's tools listed and lighting up as steps
  complete (polling the run record — no SSE needed), tool calls + final answer rendered.
  Render-deterministic: the UI reads settled run records, never the stream. (Artifact download
  deferred — runs expose no artifact surface yet; see Backlog.)
(S4+ re-sequenced 2026-06-10 after maintainer feedback on live S3: real tools before anything else —
"no point in testing demos"; the model itself refused the demo tool as self-described canned text.)

- **S4 ✓ done — real tools on real documents (demo DELETED).** Matter binding on POST /agents/runs
  (migration 0049); `search_documents` (FTS, embedding-free) + `read_document` over the matter's
  documents — membership = attach join ∪ upload-time `files.project_id` (live-verified gap);
  minimal `guarded_tool_call` chokepoint pulled forward (`agents/guard.py`: R6 grants, R5 status
  re-read, audit row per dispatch); matter tier floor/privilege on the gateway envelope (D1/M2-B3);
  factory key carry-over closed (key on the owned httpx client, never `default_headers`).
  Natural-language step titles + closing-turn dedup are client-side (rows stay honest).
- **S5 ✓ done — multi-turn + new chat + composer upload (ADR-F008).** `agent_threads` =
  conversation identity (migration 0050; thread id doubles as the langgraph checkpointer key);
  `AsyncPostgresSaver` wired at the composition root — the codebase's first checkpointer consumer;
  follow-ups continue the SAME agent state (`add_messages` appends onto the thread); follow-ups
  only on completed+checkpointed threads (409 otherwise — interrupted loops strand dangling tool
  calls); one running run per thread enforced by a partial unique index. UI: conversation view
  (turns = runs), follow-up composer, "New chat", conversations list. **Composer upload** (promoted
  from Backlog, 2026-06-11 — maintainer): attach + drop zone → `POST /files` with the bound
  matter's `project_id` (ADR-F007 path), ingestion chips pending → ready, Matter required.
  The legacy single-turn chat path (`chats.py:1370`) stays legacy.
- **S6 ✓ done — the shell shed (ADR-F006).** `web/` replaced in-place by a standalone lean
  SvelteKit SPA: lq-ai code carried verbatim (paths unchanged — imports, vitest globs, tsconfig
  intact), OpenWebUI husk + its Python backend + ~150 unused deps + the §4 branding obligation
  gone (~490k lines deleted). Per-file provenance pass 123/123 clean incl. conclusive SVG-icon
  checks (evidence: `docs/fork/evidence/f0-s6/provenance.md`); `app.html` theme script REWRITTEN;
  `app.css`/configs written fresh (gray-ramp constants carried for pixel parity). Container:
  node build → nginx on the same :8080 + `/health` contract; image builds in seconds (the
  stop-the-stack OOM dance is dead). NOTICES.md records the lineage; ADR-0009 superseded.
  Verified: svelte-check 0 errors, vitest 752/752, f0-s3 AND f0-s5 green on the new shell,
  screenshot parity (one intended delta: footer attribution).
- **S7 ✓ done — SSE v2: stream like Claude Code (ADR-F006 wire spec).**
  `GET /agents/runs/{id}/stream` emits the AI SDK UI Message Stream v1 (hand-rolled emitter):
  settled rows as `data-step` parts whose part id IS the row id (same-id reconciliation makes
  replay/races idempotent), live reasoning deltas per model turn, tool frames keyed by the settled
  `tool_call` row id, `write_todos` as `data-plan`, terminal text block = the settled
  `final_answer` (ADR-F004 intact). In-process `RunStreamBroker` bridges runner → endpoint; a
  DB-tail fallback serves subscribers with no live publisher, so the same stream survives the F1
  arq migration unchanged; orphaned-at-'running' runs close the stream at the poller's 330s
  cutoff. UI: collapsed-by-default thinking ribbon with shimmer fed only by reasoning deltas;
  polling parks while the stream is healthy and stays the fallback + contract. **Both pulled-
  forward MUSTs landed:** (a) migration 0051 `agent_run_steps.parent_step_id` — the runner
  resolves each event's innermost enclosing tool dispatch to its settled row (subagent fan-out
  no longer flat; nested steps render indented); (b) the conversation surface lives in
  `ConversationPanel.svelte` (lib), thread switching by `{#key}` remount, draft/matter selection
  survive as bound props — the agents route is chrome only. Server-clock skew (Date headers)
  closed the F0-S3 staleness carry-over. Verified: api agents suite 102 passed (live broker,
  DB-tail, orphan-cutoff, mid-run-attach seeding, wire-mirror through the real `task` subagent),
  web 773/773 + svelte-check 0 errors, timestamped live wire capture (reasoning deltas over ~8s
  of model time), NEW `f0-s7-stream` Cypress spec (ribbon live + polls parked, <5) + f0-s3 +
  f0-s5 green; 30-agent adversarial review — 24 confirmed / 0 blockers, all fixed or deferred
  on record. GOTCHA for spec authors: `cy.intercept` BUFFERS streamed responses — never
  intercept the SSE route you're asserting liveness on.
- **S8 ✓ done — matters without leaving the agent + conversation readability (maintainer
  directives, 2026-06-11).** "+ New matter" on the Agents tab reuses the SAME plumbing as the
  Matters tab: page-hosted `NewMatterModal` + `POST /projects`, full form (privileged ⇒
  tier-floor invariant rides along). Prereq landed: the modal's hardcoded post-create
  `goto('/lq-ai/matters/{id}')` moved to the Matters page's `onCreated` (the caller owns
  navigation); the Agents page binds the created matter in place through the bound
  `selectedMatterId` prop, whose reactive watcher also clears pending upload chips (F0-S5
  honesty invariant). "No matter — blank workspace" REMOVED (ADR-F002): Run stays disabled
  until a matter is selected or created; the server API is unchanged. **Folded-in readability
  feedback (maintainer, live on S7):** composer DOCKED at the bottom (sticky card), the
  conversation reads top-down above it, Conversations list moved to the side column; auto-scroll
  pins to the conversation tail inside the nearest scrollable ancestor (the shell scrolls
  `#lq-main`, html is overflow-hidden — document scrolling is a silent no-op, and the document
  bottom would over-scroll past the conversation since the side column is taller); thinking
  renders MARKDOWN (live ribbon + settled reasoning) through the same marked+DOMPurify
  `SANITIZE_OPTS` path as the answer; tool calls/results collapse to one-line `stepDigest`
  rows (full args/output one click away); the live ribbon is auto-expanded, tail-anchored and
  clamped like claude.ai, collapsing into the settled "Reasoning" row when the turn lands.
  Verified: web 778/778 + svelte-check 0 errors; f0-s3 (REWRITTEN: creates its matter through
  the new modal — self-sufficient again and the S8 live evidence), f0-s4, f0-s5, f0-s7 (ribbon
  assertion now proves VISIBLE streamed text) all green on the rebuilt stack; evidence
  screenshots in docs/fork/evidence/f0-s8/; 27-agent adversarial review — 22 findings raised,
  0 confirmed (all refuted on the actual code). NOTE: wave-c-matters test 3 (Matters-page
  create→redirect) fails IDENTICALLY on main's build — pre-existing environmental hang (the
  AUT's POST /projects never leaves the browser under Cypress on that surface); its inline
  login got the helper's 15s timeout (tests 1–2 now reliable); Backlog item below.
- ✓ **S9 — model qualification gate (ADR-F004) — DONE 2026-06-12 (overnight run)**: gateway
  conformance verified LIVE first (streamed tool-call ids real+stable; `<think>` round-trips BOTH
  directions incl. history resend; defensive id-synthesis added per deepagents#3587;
  `use_responses_api=False`; `max_input_tokens` profile — the GATEWAY envelope binds, not M3's
  native 1M window; langgraph floor →1.2.4; evidence
  `docs/fork/evidence/f0-s9/gateway-conformance.md`). Harness `api/evals/` (plain pytest, ZERO
  new deps, never CI-collected): 4 scenario JSONs over 2 seeded fixture matters; deterministic
  L0/L1 scorers over settled `agent_run_steps`; runner-hygiene-only assertions; per-cycle
  routing-log token accounting. Pre-flight N=5 variance gate: ZERO disagreements. **Baseline
  MiniMax-M3 (empty harness profile), N=20×4, 80/80 cycles valid**: fan-out compliance 20/20
  `one_per_item`; negative-control noise 0; grounding 20/20 with args 18/18; mismatch:
  no-fabrication 20/20 but read-noise fired 19/20 (oscar's MiniMax wrong-grounding eagerness
  replicated — the gate's one discriminating signal; threshold deferred to maintainer per
  decision 1). Adversarial review (35 agents): 27 confirmed findings ALL fixed in-slice;
  the 80 cycles RE-SCORED IDENTICALLY under the stricter post-review scoring (think-stripped
  answers, distinct-call fan-out credit) — numbers robust. Session spend ~$1.69
  standard-rate upper bound (corrected after the routing-window double-count fix). Output:
  `docs/fork/model-compatibility.md` (per-model rows; Kimi K2.x row BLOCKED-ON-KEY with exact
  gateway recipe) + generated `docs/fork/evidence/f0-s9/matrix.md`. Deferred axes recorded:
  action-tool canary (no F0 action surface), compaction survival, L2 masked judge (budget rule).
  Original spec (design retained for re-runs): read
  `docs/fork/research/f0-s9-eval-reuse.md` FIRST — oscar-gc eval mining + ecosystem survey,
  synthesized; its §4 lists the open maintainer decisions (thresholds set AFTER the first
  baseline — never tighter than the CI; model shortlist; dep approval; arg-digest source;
  gateway pre-check scope; budget). Shape: **L0** serving conformance, zero-LLM (structural
  tool-call frames — never regex over text; schema validity ≈100%; trigger-F1; the gateway
  `<think>`-retention round-trip check is a PREREQUISITE to trusting any MiniMax-M3 number —
  triage low scores against the adapter before the model). **L1** deterministic uptake scored
  by plain Python over settled `agent_run_steps` rows: 4 scenarios (positive grounding,
  batch/fan-out, negative control, MISMATCH — the negative-guard discriminator), paired
  positive/noise fields per affordance, invoked vs invoked-correctly, S2N, task-scoped fan-out
  compliance via `parent_step_id` (open-ended delegation is settled capability-bound — measure
  compliance, never willingness). **L2** masked LLM judge ONLY for grounding substance
  (doctrine/prompt masked from the judge; structural rubrics need no LLM at all). N=20 primary /
  N=10 second family / pre-flight N=5 variance gate (≤1 verdict disagreement per metric;
  parameterised cell); per-run assertion that a real assistant message or gateway error landed
  (oscar's silent-403 lesson). Harness = plain pytest against our API through the gateway —
  ZERO new runtime deps (at most `openevals`/`agentevals`, MIT, dev-only, for the judge call).
  Capability priors are CITED from BFCL V4 (incl. relevance/irrelevance columns) + tau2
  leaderboards, never re-run — noting MiniMax-M3 has NO independent tool-calling prior and no
  public benchmark measures subagent uptake (both S9 measures are in-house by necessity).
  Second family recommendation: Kimi K2.x via an OpenAI-compatible gateway provider (avoids the
  Anthropic adapter tool_use blocker; thinking-style contrast isolates gateway confounds);
  alternates GLM-4.7+/Qwen3.x; anti-pick DeepSeek. Inherited oscar constraints (do NOT
  re-measure): doctrine wording = positive imperative + ≤1 collapsed exclusion (the +35pp/−20pp
  cross-family reversal, fixed by Candidate C); placement at the trigger surface beats wording;
  prompt iteration is subtractive-only. Output artifact = a model COMPATIBILITY MATRIX with
  per-model config notes (Goose/OpenHands style), not a pass/fail leaderboard.

## F1 — First practice area, end to end (ADR-F002)

- ✓ **F1-S1 — run-lifecycle durability (2026-06-12, PR #43, ADR-F009)**: runs execute on the arq
  worker at-most-once (`max_tries=1` verified at arq 0.26.3); lease + heartbeat + fenced writes
  (migration 0052); orphan sweep settles dead runs FAILED (stale heartbeat 120s + abort; unclaimed
  grace 1200s) — never auto-resumes; cancel endpoint (settle-first, idempotent); thread repair
  (pinned-checkpoint-view synthetic ToolMessages — deepagents #3789 regression-tested); any terminal
  status admits a follow-up; DELETE thread + daily checkpoint GC. Gate: api 2084/3 containerized;
  web 778/778; 44-agent adversarial review — 35 confirmed findings ALL fixed in-slice; live kill -9
  → sweep settle (+2m12s) → follow-up completed; cancel 0.53s; checkpoint rows 0 after delete
  (docs/fork/evidence/f1-s1/). Deferred on record: Redis pub/sub live deltas, flood-brake outage
  semantics, two-writers window (F1-S5).

Outcome: one configurable practice area (suggest: Commercial) with one Deep Agent and one unit-of-work
type ("Matter") usable for a real task (e.g. NDA review), with visible agent work in the UI — and
**users LAND in a cockpit where they run their matters and programmes** (maintainer, 2026-06-11).

- **F1 leads with Cockpit v0 — the landing IS the cockpit, built on the design system from day
  one** (ADR-F006 sequencing: panels land on the new system, never the S6 ad-hoc CSS — building
  cockpit panels pre-S7 on today's `ag-*` classes would mean a full rebuild here). Design-system
  foundation lands WITH it: shadcn-svelte + bits-ui + paneforge + Tailwind v4; semantic intent
  tokens (the Harvey pattern), light+dark, denser work-tool spacing; bespoke agent components
  (reasoning ribbon, plan/task/tool cards, subagent tree) with AI Elements / deep-agents-ui as
  semantic references. Benchmark bar: Harvey/Legora workspaces, Claude.ai thinking UX.
  The cockpit: **LEFT panel = practice areas listed from day-one `practice_areas` rows** (ADR-F002
  explicitly rejected frontend-only grouping) — the standard areas seeded with an honest
  configured / not-yet-configured state (unconfigured areas are INERT cards: no composer, no rail,
  no matter creation under them — the demo-tool rule applies to UI; only configured areas are
  enterable, Commercial first). Under an area: **the user's matters/programmes with activity
  rollups** (running / needs attention / last activity — `AgentThread` already carries
  `project_id` + `last_run_status`, a group-by away), pick-or-create in place (S8's plumbing),
  resume into the conversation. The unit-of-work noun renders from area config ("Matter" /
  "Programme — GDPR" is data, not code — ADR-F002/F004; today it's hardcoded in 4 places in the
  composer). An explicit "unfiled conversations" bucket holds legacy unbound threads (hiding them
  loses data visibility; F2 memory scoping needs their story). Login lands HERE — the tool-centric
  guided dashboard retires from `/`; F3 then only promotes routes, never rebuilds this surface.
- **Run-lifecycle durability precedes the cockpit** (audit 2026-06-11 — currently owned by no
  slice): agent runs move to arq with a startup sweep settling orphaned `running` runs (today a
  stranded run deadlocks its thread FOREVER — 409 thread_busy, no sweep, no cancel), a cancel
  endpoint, and thread repair for non-continuable threads (one failed/capped/timed-out turn
  currently kills the whole matter conversation; with a 300s wall clock and step caps, failures
  are routine — the opposite of a resident colleague). Without this the cockpit lands on zombie
  "running" matters. Ingest-job orphan sweep rides along (same fragility family).

- `practice_areas` schema + config/admin API (name, unit-of-work label, area profile, bound
  skills/playbooks/MCPs, default tier floor); `projects.practice_area_id` (nullable — legacy Matters
  unchanged); audit rows gain `practice_area_id`.
- Area config is declarative shape data (subject type, counterparty role enums, kind options,
  conditional extras, privileged defaults) consumed by one renderer — no per-area code branches;
  user-added areas can host units of work from day one (ADR-F004).
- Tool parameters classified A/B/C; matter/user/scope identifiers are B-class — runtime-injected,
  never LLM-visible (ADR-F004). Capability rail renders from settled state records, not the stream.
- **Agents tab = practice-area home** (maintainer layout 2026-06-10; realized as Cockpit v0
  above): LEFT areas → matters, CENTER conversation (the S7-extracted component re-homed),
  conversations bind to (practice area, Matter) — no free-floating agent chat. The cockpit lands
  on the AREA LIST, not auto-landed in Commercial (S3's auto-landing was flagged).
- **RIGHT panel restructure** (replaces S3's flat "Capabilities" list): three sections — **Skills**
  (existing LQ.AI skills bound to the area), **Playbooks** (existing LQ.AI playbooks), **Tools**
  (real legal capabilities: tabular review, Word redlining as they hook up); utility/workspace
  tools (file search, workspace ops) collapsed behind an expandable section. Dim → lit semantics
  carry over per section.
- Deep Agent per area via `create_deep_agent`: area system prompt, area-scoped skills, subagent
  fan-out; every tool dispatch through `guarded_tool_call` (R4/R5/R6 + audit preserved).
- **Glass-cockpit UX v1**: one message box (no model/skill pickers); capability rail — area's skills,
  playbooks, tools, dim → lit when loaded → animated in use, click-through to inspect; live activity
  feed on SSE v2; tier badge + receipts drawer carried over.
- **Decision inbox v1** on LangGraph interrupts: agent questions/approvals as cards, not chat scroll.
- **Auto-titling + auto-filing as a service-side, channel-agnostic resolver** (one-tap confirm
  when uncertain): inbound (message) → (practice area, unit of work, thread). North-star
  invariant 2 names this the embryo of inbound channel routing — the Slack/Teams bridge stubs and
  the `LQ_AI_BRIDGE_TOKEN` service-auth seam are its future callers; never web-UI-only logic.
- Extend `work_product_attributions` to multi-inference agent runs (fan-out-safe chain of custody).
- **Trust chrome reaches the agent surface** (audit 2026-06-11): the Citation Engine's only
  consumers today are legacy chat + tabular — agent runs emit ZERO citation/receipt/attribution
  records, while ADR-F002 requires tier badge, inline citations and a receipts drawer on this
  surface and the north star sells the trust stack as the product. Ordered AFTER the
  `work_product_attributions` extension above (receipts against the one-inference-per-message
  schema would write wrong rows — blocker #6).
- **Run artifact surface** (promoted from Backlog, audit 2026-06-11): ADR-F002 — "deliverables
  are artifacts, not chat text"; the rail already lists write_file/edit_file but nothing a run
  produces is user-visible. F1's real task (NDA review) must land its work product as files on
  the Matter, or the deliverable is chat-scroll copy/paste.

## F2 — Memory: 4 levels + conversation memory (ADR-F003)

Outcome: agent context assembled from company/client → practice area → user → Matter; conversations
compact, accumulate into Matter digests, and are searchable; agents propose, users curate.

- deepagents CompositeBackend: `/memories/{company,practice,user,matter}/` → StoreBackend namespaces
  keyed `(org_id, …)`; company + practice read-only to agents.
- Client/counterparty profiles (new entity — distinct from `organization_profile`).
- **In-chat compaction**: `SummarizationMiddleware` (+ `SummarizationToolMiddleware`) on the `budget`
  alias.
- **Matter digests**: `chats.summary` rolling updates; arq consolidation job on chat idle; digest
  stored at the matter memory level; powers the **"Where were we?"** card (done / in motion /
  waiting on you) on Matter open.
- **Chat search tools**: `search_chats` (FTS + pgvector hybrid) and `read_chat`, registered through
  the chokepoint; chat index inherits Matter privilege + tier floor (FTS-only fallback when no
  tier-compliant embedding provider).
- Wire kept user memory into prompts (today `load_kept_memory()` is uncalled); gentle memory UX —
  inline "keep / undo" + weekly batch review, never per-item nagging.
- **Memory manager in the right panel** (maintainer, 2026-06-10 — Claude.ai-style): click Memory →
  view/edit/delete matter memory and practice-area memory entries in place. "System proposes, user
  owns" (ADR-0013 D4) becomes a first-class UI surface, not just an API.
- Runtime isolation acceptance tests, not design verification (ADR-F004): a fact told in Matter A
  must not surface in Matter B; practice-area memory must not leak across areas; per-level
  read/write policy exercised end-to-end against the live stack.

## F3 — Practice-area IA re-centre

Outcome: the IA is practice areas → units of work; tool tabs become in-context capabilities.

- Promote area pages to the top-level IA (`/lq-ai/areas/:area/...`); area-scoped dashboards;
  matter-first navigation; Learn becomes per-area onboarding.
- **Heartbeat absorption (north-star invariant 1 — MUST, audit 2026-06-11):** autonomous watches
  (KB-attach events), schedules (arq cron), run-now, and the notification system (in-app + email
  — the codebase's ONLY one) RETARGET to agent runs/threads; they must never retire with the
  legacy autonomous surface (the retire-with-surface rule would otherwise silently delete the
  fork's only event/cron/notification plumbing). System-initiated threads need an origin answer:
  `agent_threads` bakes in a non-null `user_id` today and has no origin/trigger column.
- Playbooks + tabular review callable as agent tools inside a unit of work (unify the three
  substrates) — **absorbing the review/decision surfaces, not just the executors** (audit
  2026-06-11): the per-position match/deviate review UX and the tabular grid + per-cell citation
  modal are the legal decision surfaces lawyers actually use; wiring only executors while the
  tabs retire degrades deliverables to chat text. They become unit-of-work panels.
- MCP servers per practice area via `langchain-mcp-adapters` (scoped tool sets, not global).
- One search box across chats, documents, memory — matter-scoped by default, privilege-scoped always.
- Long tasks keep running when the laptop closes: background continuation + notification + finished
  artifact on the Matter.

## Oscar Edition — Agentic Modules (post-UX-B; ADR-F018)

Outcome: enterprises adopt **modules** — vertical capabilities where the agent *does the work* — on the
practice-area substrate. The fork is positioned as **LQ.AI Oscar Edition** (cutting-edge: Deep Agents +
modules; upstream stays reserved — rebrand its own ADR + slice when executed,
[[lq-ai-oscar-edition-rebrand]]). A **module** = a practice area + a **typed domain** + **code-validated
agent writes** (agent proposes, code disposes) + deliverables (ADR-F018). Built **short-slice → compact →
short-slice**.

- **Module 1 — Privacy / ROPA (FIRST, in progress).** Maintain a client's ROPA + privacy programme with the
  Privacy Deep Agent — a OneTrust-equivalent done LQ.AI-style. Reference-only: the maintainer's deployed
  **Oscar Privacy** product (take the idea + domain, reimplement + **improve** — code-validated entries over
  Oscar's trusted-model writes; ICO RAG + Oscar's engine dropped). Decomposition:
  `docs/fork/plans/PRIV-privacy-ropa-module-decomposition.md` — **PRIV-0 ✅ (plan+ADR, PR #98) → PRIV-1 ✅
  (ROPA domain spine + code validation: `processing_activities` table + `ProcessingActivityInput` Pydantic
  invariants + DB CHECK defense-in-depth, migration 0058) → PRIV-2 ✅ (validated agent write path:
  `propose_processing_activity`/`list_processing_activities` guarded ROPA tools on the Privacy area agent —
  validate against `ProcessingActivityInput` before commit, reject-back-to-model on failure; PR #100)** →
  **PRIV-3 ✅ (PR #101)** (two-tier RELATIONAL spine System↔ProcessingActivity M:N + deployment-global
  re-scope, **ADR-F019 accepted**; read API + the two-tier register read UI in F013 style; `propose_system`/
  `link`/`list_systems` tools; migration 0059) → **PRIV-4a ✅ (PR #102)** (Article 30 export — JSON/CSV/XLSX,
  shared-read; pure formatter + OWASP CSV-injection guard + honest Art-30 coverage note; openpyxl already a dep)
  → **PRIV-5 split into 5a + 5b (maintainer): PRIV-5a ✅ (PR #103)** (Vendor/recipient entity — name/role/country/
  DPA-status, lean: risk deferred to assessments; `processing_activity_vendors` M:N + `propose_vendor`/
  `link_vendor_to_activity`/`list_vendors` tools, migration 0060; read API + Vendors register tab; Recipients
  column + Vendors sheet in the Art 30 export; coverage note's "recipients" line dropped) → **PRIV-5b ✅ (PR #104)**
  (Transfer entity — child of a processing activity (CASCADE) + optional recipient vendor; the outside-UK/EEA⇒mechanism
  invariant as a declared `restricted` bool mirroring special_category⇔art9, in both `TransferInput` and a DB CHECK;
  `propose_transfer`/`list_transfers` tools (now 10), migration 0061; transfers ride `ProcessingActivityRead` + the
  activity-detail UI; Transfers column + Transfers sheet in the Art 30 export; coverage note's last transfer line
  dropped — now 2 lines, both → PRIV-6; **no standalone /ropa/transfers endpoint** — a transfer has no meaning detached
  from its activity) → PRIV-6 (data-flow view + Legal-Entity scope + programme dashboard)
  → **P1 flagship** PRIV-A1 (assessment domain+skill) / PRIV-A2 (**conversational-link external intake** — the
  differentiator, **ADR-F020**) → P2 tracks (DSAR, breach, DPA review, reg-gap, reporting). **Full capability
  plan: `docs/fork/plans/PRIV-onetrust-to-lqai-functionality-map.md`** (OneTrust→LQ.AI, P0–P3; **P3
  deferred/non-goals: consent platform, cookie CMP, data-store discovery, regulatory RAG**). **The
  differentiator** = assessments via a LINK to a conversation with the agent (vs OneTrust/TrustArc's static
  questionnaire) → agent files code-validated ROPA → queryable/extractable. **Module-UI requirement
  (2026-06-18):** render the domain UI like the reference product (SEE the register, not just an export) but in
  **LQ.AI's own F013 design language, NOT Oscar/OneTrust's look** (IA borrowed, style ours). MiniMax + DeepSeek
  are **dev models only**; clients run a Western model via the gateway.
- **Module 2 — Redlining (NEXT track, Commercial/M&A).** "Redline like a lawyer": **adeu** (MIT, mechanical
  OpenXML tracked-changes — clean, no LLM calls, no gateway entanglement) as the RENDER layer + a redlining
  skill / positions-playbook (acceptable terms, fallback language, defined-term + cross-ref consistency,
  clause-level rewrites/insertions, margin-comment rationale) + agent loop + harness calibration. adeu is weak
  at lawyering out-of-the-box; the intelligence is our build. Its own decomposition + ADR when it starts.
- **Substrate enablers (built in service of modules, not speculatively):** run-artifact surface (deliverables);
  playbooks-as-deliverables (skills with an explicit output artifact — the mike concept); MCP via gateway
  tool-egress (cf. upstream ADR 0014/0015) only when a module needs an external source.

## Backlog

(One line per idea surfaced out of scope; promote at milestone boundaries.)

- Project rename before public release (ADR-F001 obligation).
- Embedding provider strategy (KB + chat vector search currently lack one; MiniMax coding-plan key is
  chat-only — needs a dedicated embedding model, possibly local/Tier-1 for privileged matters).
- `<think>` block handling in MessageBubble for reasoning models (MiniMax-M3 emits them inline).
- Streaming anonymization rehydration end-to-end test (upstream defers the streaming response path).
- Per-phase / per-tool cost budgets inside a unit-of-work budget.
- **`user_sessions` deterministic-HMAC index** (the real fix flagged in PR #47 / auth.py `refresh()`):
  `/auth/refresh` bcrypt-scans every active session (per-row salt → no index lookup), an
  unauthenticated-input CPU amplifier and the cause of the expired-session blank screen (359 sessions
  ≈ 79s). PR #47 added a per-user active-session cap (bounds per-user accumulation + self-heals on
  login) but the scan is GLOBAL, so it doesn't close the bad-token-spam DoS. Add a keyed-HMAC column
  for O(1) lookup (miss → 401, zero bcrypt) — needs a migration (can't backfill plaintext → revoke-all
  on migrate) + security review. Would also let the cap's accepted same-user revoke race be removed.
- Configurable ethics gates per practice area (upstream's ethics_review is a stub).
- Email-grade entry points: forward an email into a Matter; Word add-in revival.
- Revisit third-party memory (Zep/Graphiti temporal graph) only if native consolidation proves
  insufficient (ADR-F003 option 3).
- ~~Run artifact surface~~ — PROMOTED into F1 (audit 2026-06-11).
- Thread management: rename (delete SHIPPED in F1-S1 with `adelete_thread` + daily GC cron),
  pagination past the 20-thread list cap (a cockpit grouping client-side from it under-reports
  older matters) — F1/F2.
- Redis pub/sub run-stream publisher (live token deltas across the api/worker boundary; F1-S1
  moved execution to arq, so live streams currently degrade to the 2s DB-tail — animation only).
- Checkpoint history pruning inside LIVE threads + ShallowPostgresSaver evaluation (needs a
  measured bloat problem AND a legal-retention policy decision; F1-S1 ships orphan-lineage GC only).
- Ingest-orphan cron (cut from F1-S1: `files` lacks `updated_at`, cron re-enqueue can race a live
  job; startup sweep remains the recovery path — needs a migration if promoted).
- Searchable recent-first matter picker with privileged marker (replaces the flat name-only
  `<select>`; one of the S6 bare-select deferrals) — F1 design system.
- Global notification bell in the chrome (DE-324 deferral) — cockpit-adjacent.
- Declare the F3 retire list explicitly when the IA re-centres: saved-prompts, guided-dashboard
  components, FeaturedToolsRow, learn-as-global-tab.
- **Minimalist "cleaned interface" pass (post-AE series) — PROMOTED to milestone F2 (ADR-F012,
  2026-06-15).** Maintainer likes the minimalist aesthetic + positioning of
  [`scira`](https://github.com/zaidmukaddam/scira). **scira is AGPL-3.0 → REFERENCE ONLY: study the look /
  IA / positioning, never copy code** (copying would force AGPL on our stack — stricter than ADR-F011: not
  even vendoring). ADR-F012 splits the work by dependency: **F2** = the visual pass (now, reversible, no IA
  retirement — slices F2-M0…M9 in `docs/fork/plans/F2-minimalist-pass-decomposition.md`); **UX-A** =
  navigational convergence (cockpit = single shell, legacy top-tab IA retired — own milestone after F2);
  **UX-B** = capability convergence (tools as in-context agent capabilities — folds into the pivot track,
  F1-S4/S5 + area activation + the practice_area/unit_of_work schema). UX-A/UX-B together are F002's F3
  commitment, now sequenced. F2-M0 (ADR + decomposition + baseline) shipping; AE0–AE7 already closed.
- **Tier-4 large-matter delegation (UX-B-4/6 open calibration question).** UX-B-4 proved the delegation
  machinery is correct + isolated (deterministic CI test), but MiniMax-M3 does not *elect* to fan out at
  the matter sizes tested (`task_calls=0` on a 4-doc RFQ — it reads them itself). Does a tier-4 model ever
  delegate on a genuinely large matter? Options (rough effort order): a conditional profile nudge naming the
  researcher for large/multi-thread matters; a larger fixture (dozens of docs); a stronger qualified model
  (S9/ADR-F015 gate first). Not a UX-B blocker; see `docs/fork/evidence/UX-B-MILESTONE-INDEX.md`.
- NewMatterModal's privileged InfoTip claims "defaults to Tier 2" — neither client nor server
  implements a default (the field is simply required); fix the copy on next touch (transparency).
- Pre-F1 guard: frontend-static practice-area identifiers must never leak into stored rows
  (thread metadata, project fields) — area ids stay presentation-only until the schema lands, or
  the F1 migration becomes a data-repair exercise.
- MessageBubble (upstream surface) shares the default-DOMPurify image-beacon exfil gap fixed on the
  Agents tab — harden when next touched (CLAUDE.md: model output is untrusted).
- ~~File upload directly in the agent composer~~ — PROMOTED into F0-S5 (2026-06-11).
- Matters-page file management: the Matter detail page has NO upload/attach UI at all today (the
  attach endpoint exists API-side only; only Chats/Knowledge/Playbooks surfaces upload) — proper
  file management belongs to F1's left-panel Matter view.
- Ingest-job robustness: a worker/DB hiccup mid-ingest strands files at `processing` forever (seen
  live in S4) — retry/orphan sweep alongside the agent-run arq migration.
- Reconcile upstream's two file↔project relations (`project_files` join vs upload-time
  `files.project_id` column) — S4's matter tools honor the union; the Projects UI lists only the join.
- Checkpoint-row retention/cleanup (ADR-F008): user/thread deletes orphan langgraph checkpoint
  rows that carry conversation content; `adelete_thread` exists, no delete surface calls it — F1.
- deploy/helm web values cleanup: the runtime `API_BASE_URL` env was always a no-op for the
  static bundle (S6 kept the :8080 + /health contract so helm/caddy still work untouched).
- Version-poll auto-reload died with the husk: a stale SPA persists until manual refresh after a
  web rebuild — recreate on the new shell if it bites (S6 note).
- wave-*/m*-* Cypress specs target legacy-executor surfaces that still render under /lq-ai —
  retire each spec together with its surface during the practice-area pivot.
- web lint harness is dead (pre-existing): `eslint .` crashes with a TypeError in
  no-unused-vars on SkillWizard.svelte (eslint 8 legacy config + svelte parser; reproduced on
  8.31 and 8.61) — migrate to eslint 9 flat config; lint is not a CI gate (S6 review deferral).
- nginx serves no CSP/frame-ancestors/Referrer-Policy — needs a path-scoped design
  (/word-addin/ must stay frameable by Office webviews); XSS defense is DOMPurify-only today
  (S6 review deferral).
- AliasForm/SkillInputForm bare `<select>`s render native UA chrome since S6 (the husk's
  global select restyle was not carried) — F1's design system rebuilds all controls anyway
  (S6 review deferral, accepted divergence).
- `docs/api/backend-openapi.yaml` is stale for the agents surface (runs since S2, threads since
  S5, the stream endpoint since S7) — regenerate or annotate when the surface settles.
- Thinking ribbon under PARALLEL subagent fan-out: one shared buffer means a sibling's settling
  model_turn wipes another sibling's live reasoning (animation-only loss; sequential fan-out today)
  — per-block ribbons land with F1's subagent tree (S7 review deferral).
- wave-c-matters test 3 (Matters-page create→redirect) hangs pre-existing on this box: the
  AUT's POST /projects (and the list GET) never leaves the browser under Cypress on that
  surface, while curl and the agents-page modal flow (f0-s3) work — fails identically on
  main's build (verified S8). Diagnose with the surface's pivot retirement or earlier if a
  REAL browser ever reproduces it.
- **Functionality candidates studied from `willchen96/mike` (AGPL-3.0 → REFERENCE-ONLY: study what it
  DOES, build independently, never copy code — same posture as scira/ADR-F012). 2026-06-17.** A parallel
  OSS legal-AI cockpit; the relevant capabilities, mapped onto our practice-area substrate:
  - **Playbooks-as-deliverables** (highest fit): named, user-authored/shareable templates that emit a
    DEFINED artifact (Word table / topic checklist / inline summary) — extends our skills/SKILL.md system
    with an explicit output contract. Seed examples for Commercial/M&A: CP-checklist extraction,
    credit-agreement 21-topic summary, shareholder-agreement governance summary. Ties to the existing
    "Run artifact surface" backlog item (ADR-F002).
  - **DOCX deliverables incl. tracked-changes / redline output** — produce a redlined Word doc; a
    high-value lawyer artifact we don't surface. Pairs with the artifact surface above.
  - **Tabular review inside a matter** (documents-as-rows × AI-extracted-fields-as-columns) — the
    capability is valuable even though we retired upstream's flat global Tabular tab; reframe as an
    in-matter agent capability, not a top-level tool. Needs a roadmap decision.
  - **Per-user/per-area MCP connectors + OAuth handshake** — concrete reference for our stated MCP
    direction (aligns with upstream ADR 0014/0015 gateway tool-egress + the agentic-modules milestone).
  - **Document versioning + soft-delete**, **GDPR data export/erasure** (fits the Privacy area), and
    **collaboration: sharing + org multi-tenancy** (we are single-operator-voice today) — each a gap.
  - **Inline citation / case-law panels** as a first-class structured response element — a UX pattern
    for Citation-Engine output.
  - **CONTRAST, do NOT copy:** mike holds LLM keys per-user client-side; our gateway is the sole
    egress + key-holder ([[llm-is-injected-replaceable]]) — keep that boundary.
