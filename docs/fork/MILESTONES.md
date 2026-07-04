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
  carry over per section. **(→ pulled forward + made concrete with two-layer per-matter toggles in
  the "Capability panel + in-matter Tabular review" milestone, 2026-06-30.)**
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

> **Architecture DECIDED (2026-06-27): [ADR-F049](../adr/F049-native-memory-substrate-and-eval-gated-retrieval.md)
> — adopt the native langgraph Store + deepagents CompositeBackend/middleware substrate (we're off-substrate
> today: checkpointer only); keep custom only the bi-temporal fact ledger + the documents hybrid retriever
> (chunking/embedding-at-scale/fusion/rerank/citation-offsets); conversations on native `store.asearch` +
> summarization-offload; one shared local embedder; PageIndex backlog. Built EVAL-FIRST + eval-gated.** Seven-
> doc research arc: [`research/RETRIEVAL-MEMORY-INDEX.md`](research/RETRIEVAL-MEMORY-INDEX.md). Decomposition:
> [`plans/RETRIEVAL-MEMORY-eval-first.md`](plans/RETRIEVAL-MEMORY-eval-first.md) (Phase E eval instrument →
> N0 substrate → conversations → cost play → measured). The bullets below are the original F2 outcomes,
> now realised through that plan (the CompositeBackend bullet ↔ N0; in-chat compaction ↔ N2; chat search
> tools ↔ N3 native `store.asearch`; memory manager UI is later in the plan).
>
> **E0 ✅ SHIPPED (2026-06-28):** the Track-B CUAD retrieval instrument + objective span scorer + the
> frozen **FTS-only baseline** every later slice must beat (`docs/fork/evidence/retrieval-eval/`).
> Floor: within-doc hit@8 0.39 / MAP 0.30; **cross-doc (matter-wide) hit@8 0.04 / MAP 0.02 — FTS
> collapses at scale**.
>
> **E1 ✅ SHIPPED (2026-06-28):** the Track-A **agentic** baseline — masked judging packet + judge
> (`track_a_lib.py`; orchestrator-Claude primary, `deepseek-pro` gateway fallback; judge sees only the
> sanitised timeline + visible answer + rubric) + 4 scenarios + a free CI net + the live matrix
> (`test_track_a_{lib,fixtures,unit,eval}.py`). **Frozen baseline (N=10, DeepSeek, Claude-judged,
> `…/track-a/`): A1 grounding 8/10, A5 cross-thread recall 0/10 but honest-abstention 10/10, A7 no
> *autonomous* fan-out 0/10 (synthesises inline, judge-appropriate; subagents WERE wired & it delegates when
> coached per C7b — a strategy-selection finding, not a capability limit), A8 honest-absence 10/10.**
> Phase-E exit reached.
>
> **N0 ✅ SHIPPED (2026-06-28, ADR-F049 ACCEPTED):** the native langgraph `Store` (`AsyncPostgresStore`,
> filter-only) + deepagents `CompositeBackend` wired into every run — `/memories/{company,practice,user,
> matter}/` + `/conversation_history/` routed to `StoreBackend` namespaces keyed via a new
> `AgentRuntimeContext` (`rt.context`); company/practice read-only via a storage-level
> `ReadOnlyStoreBackend` backstop (subagent perms replace parent's). `store.py` mirrors `checkpointer.py`
> (both composition roots; library-managed tables, NO migration); `memory_backend.py` is the per-run
> backend factory; degrades to today's backend when the Store is down. **No migration, no new dependency.**
> The agent's builtin `write_file` now persists matter notes **across threads** (proven by
> `test_memory_backend.py` incl. an e2e write through `create_deep_agent`). **Honest gate
> (maintainer-ruled):** substrate proven by deterministic test + nothing regresses; **A5 recall stays a
> finding (~0) until N3** (N0 ships the substrate, not the recall behaviour). Next: **N1** (move the tier
> digests to `MemoryMiddleware`, replacing the hand-assembled prompt blocks).
>
> **N1 ✅ SHIPPED (2026-06-28, ADR-F049):** the four read-only DATA memory tiers (House Brief, Matter
> File, Matter Corrections, Matter Roster) moved off the static system prompt onto a fork
> `TierMemoryMiddleware` (`app/agents/tier_middleware.py`); `render_memory_tiers` (composition.py) is the
> single source of the fence constants/order/degradation and `system_prompt_for` stays the byte-identical
> equivalence oracle. **The original premise was falsified** — the Matter File can't move to the Store
> without a separate ADR'd slice (cockpit/transaction/guard/pin invariants), and deepagents' STOCK
> `MemoryMiddleware` injects `edit_file` self-learning guidance that conflicts with ADR-F042 — so SQL
> stays the source of truth and N1 used a thin **fork** middleware, not the stock one. One documented
> benign delta: tiers now render after `BASE_AGENT_PROMPT` + the area suffix. **No migration, no new
> dependency.** Gate met: full api suite **2857 passed / 38 skipped / 0 failed**, ruff + mypy clean,
> Track-A N=1 live smoke green, adversarial review 0 blockers/0 should-fixes. The **convergence** + the
> shared **Practice Knowledge** cross-matter learning tier are registered as the prize (**ADR-F050**
> proposed + `plans/PRACTICE-KNOWLEDGE-prize.md`). Next: **N2** (`SummarizationMiddleware` +
> `/conversation_history/` offload → within-chat recall post-compaction).

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

## Capability panel + in-matter Tabular review (ACTIVE — pulled forward 2026-06-30)

Outcome: in the cockpit, the lawyer SEES and CONTROLS what the practice-area Deep Agent has available —
a right-hand **capability panel** with **Playbooks / Skills / Tools** (and an MCP placeholder) — then
**Tabular review** lands as an in-matter agent **tool** in Commercial + Corporate, the grid UX augmented
by the maintainer's **[LQ-Grid](https://github.com/sarturko-maker/LQ-Grid)**. This pulls forward two
already-planned items and makes them concrete: F1's **RIGHT panel restructure** (Skills/Playbooks/Tools
sections, never built) and F3's **"playbooks + tabular review callable as agent tools … they become
unit-of-work panels"**; it also actions the Backlog **"Tabular review inside a matter"** roadmap decision
and **Playbooks-as-deliverables**.

**Decided design (maintainer, 2026-06-30):**
- **Two-layer scope** — the practice AREA curates the AVAILABLE capability set (admin/curated); the
  LAWYER toggles a subset on/off, **persisted per matter** (survives across that matter's conversations).
  "System proposes, user owns" applied to capabilities.
- **Playbooks, Skills, Tools are real now**; **MCP is a visible-but-disabled placeholder** to be wired
  into the (approval-gated) **MCP milestone** later. Playbooks reuse the EXISTING `playbooks`/
  `playbook_positions` DATA (the firm's preferred positions) — NOT the frozen legacy executor.
- Primitive builtins (read/write/edit/bash/task) are NEVER shown — only legal capabilities.

**Phase 1 — the capability-toggle panel. ✅ SHIPPED + MERGED PR #177 (`29d9d027`), 2026-06-30
(ADR-F054, migration 0081; maintainer-confirmed live).** A cockpit "Capabilities" tab listing the area's
Playbooks/Skills/Tools (+ disabled MCP placeholder) with per-matter on/off toggles that genuinely gate what
the agent gets: skills via the skill-wiring filter, tool GROUPS via the guard grant set (R6 fail-closes),
playbooks via a new read-only "Practice Playbook" tier on `TierMemoryMiddleware`. ONE pure
`app/agents/capabilities.py` inventory is the single source of truth (API + composition); two-layer scope
(area curates / lawyer toggles per matter); no-toggle default path byte-identical to pre-slice. Plan/ADR:
`docs/fork/plans/CAPABILITY-PANEL-slice.md`, `docs/adr/F054-per-matter-capability-toggles.md`. (Shipped as
a TAB; the co-visible resizable split is a noted follow-up. Endpoint is PATCH not PUT — the api CORS
allow-list has no PUT.)

**Phase 2 — Tabular review as an in-matter tool (Commercial + Corporate) + LQ-Grid.** Reuse the upstream
tabular SUBSTRATE (ColumnSpec, per-cell extraction, Citation-Engine ensemble, JSONB grid) — NOT the
frozen linear executor — exposed as a guarded agent tool the lawyer toggles on in the panel. Augment the
grid UX with **LQ-Grid** (React: source highlighting, document grouping, dual extraction); the
integration approach (port to Svelte / web-component wrap / rebuild-from-reference) is decided at Phase-2
planning (framework mismatch: LQ-Grid is React, our web is Svelte). Its own plan + ADR when it starts.
- **STARTED 2026-06-30** — plan `docs/fork/plans/TABULAR-REVIEW-agentic.md` (11 slices T1–T11), ADR-F055.
  Integration decided: **rebuild-from-reference in Svelte** (LQ-Grid patterns harvested, no code copied).
  User-facing noun **"grid"** + a dedicated **"Grids"** cockpit tab. **T1 SHIPPED** (the agentic grids tool
  — `start`/`record`/`finalize` through `guarded_dispatch`, migration 0082, live-verified end-to-end on
  DeepSeek). **T2 SHIPPED** (in-chat **grid preview card + Expand** overlay; **frontend-only** — refined from
  the planned `data-tabular` frame to **settled-step derivation** since the SSE replay re-emits only
  `data-step`, ADR-F055 T2 addendum; Cypress-screenshot-verified). **T3 SHIPPED** (discoverability
  `tabular-review` SKILL.md bound to Commercial via mig 0083; agent proactively **builds** a grid on a
  multi-doc compare intent, maps NL→columns, stays quiet on single-doc; live masked eval **3/3** across 2
  reps with the skill injected, ADR-F015). **T7 SHIPPED** (cockpit **"Grids" tab** — owner-scoped listing
  of the matter's agentic grids with derived titles + fill-mode, open/soft-delete; new read route, no
  migration; Cypress-verified). **T8 SHIPPED** (conversational grid-ops: `update_tabular_cells` edits a
  finalized grid in place — the "bash" loop; live-verified the agent selects it + corrects a cell;
  `combine_documents` → T8b, citation-integrity data-model). NEXT = **T5/T6** (live fill + stage takeover)
  then T4 (retrieval-fill), then
  T5/T6 (live fill + stage takeover) and T4/T8 (retrieval-fill + bash loop; sequenced low-risk-first).

**Deferred — resume after this milestone (paused 2026-06-30, honest record):**
- **F2 Slice P — PageIndex** (gateway-bound retrieval, eval-first; `plans/PAGEINDEX-SLICE-P.md`, ADR-F052
  to draft) — was the queued NEXT; paused.
- **Full hybrid+rerank @ scale calibration** (N=150 CUAD; needs a ≥16 GB box) — stays parked.
- **`cost_usd` exact per-run attribution** (routing-log `run_id`, cross-service) + a "typical run ≈ $X"
  pre-run hint (the O-2 follow-ups) — paused.
- **Per-turn conversation semantic granularity** (F2 Slice C2 follow-up, eval-gated) — stays parked.

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
  **(→ tabular pulled forward as Phase 2 of the "Capability panel + in-matter Tabular review"
  milestone, 2026-06-30; the capability panel itself is Phase 1.)**
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
  from its activity) → **PRIV-6 split (maintainer): PRIV-6a ✅ (PR #105)** (Article 30(1)(c) personal-data
  taxonomy — categories of data subjects + personal data; closes Article 30(1)) → **PRIV-6b ✅ (PR #108)**
  (privacy **programme dashboard** — read-only Overview tab over the register: totals, lawful-basis/controller-
  role/DPA-status breakdowns, special-category & restricted-transfer counts, "needs attention" gaps;
  `GET /ropa/programme-summary` + pure `ropa_summary.build_summary`; no migration) → **PRIV-6c ✅ (PR #109)**
  (data-flow / lineage view — interactive node-link graph auto-drawn from the System↔Activity↔Vendor↔Transfer
  relationships; `GET /ropa/data-flow` + pure `ropa_graph.build_graph`; rendered with `@xyflow/svelte` per
  **ADR-F022** (the fork's first deliberate new-dep exception, maintainer-authorised) but in our F013 style;
  no migration) → **PRIV-7 ✅ (PR #111)** (live **ROPA-population** validation: the maintainer's
  privacy-notice→ROPA onboarding test, run live on **DeepSeek-flash** against Zendesk's real notice via the
  scenario harness. Built a **fully-linked register (9/9 activities)** through the guarded write tools once two
  budget ceilings were lifted — proved the gap was budget, not model capability. Deliverables: reusable
  read-back/coverage scorer (`tests/agents/scenarios/ropa_eval.py`), the live scenario
  (`test_ropa_population_scenario.py`, provider-+notice-gated, self-skips in CI), the new **`ropa-population`
  skill** (link-as-you-go method; test-only bound — recommend shipping via a binding migration), and a
  **production runner fix**: `runner.py` now ties langgraph's graph `recursion_limit` to the run's `max_steps`
  (the default 25 was crashing any long/skilled run before `max_steps` fired). Findings:
  `docs/fork/evidence/priv-7/FINDINGS.md`) → **PRIV-8a ✅ (PR #112)** (ROPA **change verbs**: the agent can
  now *change* the register in plain language, not only append — 6 guarded tools `retire_*`×4 + `unlink_*`×2,
  **soft-retire** (`retired_at`, never delete → auditable), reads hide retired everywhere by default
  (`?include_retired=true` = audit), write verbs refuse retired targets; migration 0063; **ADR-F023**;
  `docs/fork/plans/PRIV-8-ropa-change-verbs.md`) → **PRIV-8b ✅ (PR #113)** (the LIVE mixpanel→hotjar proof on
  DeepSeek V4 — both skilled arms produced a *coherent* swap (Hotjar linked, Mixpanel unlinked + soft-retired,
  reported), the no-skill baseline left the register listing *both* → the new `ropa-maintenance` skill is
  load-bearing; + `seed_ropa_register` harness helper + `evaluate_swap` scorer; evidence
  `docs/fork/evidence/priv-8/`) → **PRIV-9a ✅ (PR #114)** (cockpit UX: chat + register **co-visible**
  (resizable, toggle fallback) + **run-lock** (chat collapses to a real-cancel Stop while the agent works) +
  **poll-while-running** live register refresh — committed change visible in ≈1.1 s; the group-chat
  "side-panel chatbox that updates the UI as the agent works"; evidence `docs/fork/evidence/priv-9a/`;
  `docs/fork/plans/PRIV-9-cockpit-live-register.md`) → **PRIV-9b** (changed-row **highlight** — the agent→register
  change-signal so the user sees *which* row changed, **ADR-F024**) → **PRIV-6d** (Legal-Entity / controller scope + per-controller
  Article 30 export — needs a migration)
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

## Authorization — areas of responsibility (ADR-F021, proposed)

The enterprise reality (maintainer, 2026-06-18): **users have areas of responsibility** — one user handles
Privacy, a colleague does not; several may share Privacy. A many-to-many **users ↔ practice-areas** model with
**roles within an area** that does not exist yet (authority today is the single boolean `is_admin`; the
`users.role` enum is assignable but its gate is mounted nowhere; no user↔area link exists). **ADR-F021** records
the target (one injected `can()`/`visible_filter()` decision seam + a fork-owned `user_practice_areas` table +
`is_admin` as the super-user) and — the load-bearing part now — a **design-readiness contract** so every module
is built flip-ready (reads through the seam, deny→404, durable NON-NULL `practice_area_id` scoping column on new
domain rows kept separate from provenance, agent writes through `guarded_dispatch` carrying user_id +
practice_area_id with the actor's area set resolved once at GuardContext build, owner-OR-area-member never
area-only). **Closes the PRIV-6a confused-deputy gap** (it is the symptom: the ROPA register is read by every
authenticated user). Grounded + designed via the `permissions-roadmap-design` workflow (28/32 code claims
verified). **Reference (clean-room, no code/identity copied):** the maintainer's private
`sarturko-maker/EU_AI_Act` repo ships a working analogue of this exact area-scope model —
`packages/profile/src/access.ts` (pure RBAC capability predicates) + a `DepartmentAssignment` M:N join
scoping a user to one or more departments + a server-side `authorize()` seam. `DEPT_SME ↔
DepartmentAssignment` ≈ our `user ↔ user_practice_areas`; consult it as prior art when implementing
Phase 1–2 (see Backlog: EU AI Act register module). Phased rollout (each its own slice, re-planned at the boundary):

- **Track 0 — ADR-F021 + this roadmap entry (no code; THIS slice).** Maintainer accepts before any enforcement
  flip. Settles the open questions (owner-retains-own-matter; ROPA backfill; `area_owner` scope; catalog
  visibility; retire `users.role`/`get_mutating_user`?; area-grain vs per-matter ACL).
- **Phase 1 — ship the decision seam, behavior-identical (no schema).** `app/authz/policy.py` with `can()` +
  `visible_filter()` returning today's results; refactor the scattered `_load_visible_*` helpers + the ropa
  read handlers to delegate; no-op-on-ship test. The one (desirable) one-way door.
- **Phase 2 — membership + per-matter sharing + invitations (schema + admin/grant surface; policy ignores it).**
  Migration **0063+**: `user_practice_areas` (area membership) **+ `matter_collaborators(project_id, user_id,
  role)`** (per-matter sharing — decision 6) + an auditable **invitation/grant** record (lifecycle
  invited→accepted/revoked, `granted_by` RESTRICT). ORM copies `TeamMember`'s shape into separate fork-owned
  tables. Grant/revoke + invite endpoints (admin, area_owner for their area, matter owner/collaborator for
  their matter; mirror `admin.update_user_role` + `teams.py` admin_router). Behavior unchanged until Phase 4.
- **Phase 3 — durable area attribution on ROPA rows + backfill (the hard prerequisite).** Non-null
  `practice_area_id` on `processing_activities` + `systems` (keep `source_project_id` as separate provenance);
  forward/backward migration + backfill (open question 2).
- **Phase 4 — flip enforcement per seam (each a one-line predicate, feature-flaggable, revertible):** matter
  creation; agent-run launch + worker re-validation; the guard R6-sibling per-call check; owned-resource reads
  (owner OR area-member); and **LAST** the register read-filter (`true()` → area-membership) — which closes
  PRIV-6a and supersedes ADR-F019's §Authz read-posture clause (single-tenant/schema untouched).
- **Phase 4b — the read flip extends to per-matter sharing**: matter reads = owner OR area-member OR
  matter-collaborator (decision 1 keeps owner unconditional).
- **Phase 5 — cross-area collaboration + new modules born flip-ready.** Cross-area **person** (invite an
  Employment colleague onto a Commercial matter as a matter-collaborator). Cross-area **agent** ("@ Deep Agent")
  — another area's Deep Agent as a **time-boxed, matter-scoped, default read-only GUEST** (honors ADR-F002
  one-matter-one-identity + the gateway/guard chokepoint; gated by the permission model) — **its own design
  slice + ADR** (grounding workflow `wf_815d3f81-70e` to fold). New modules (redlining, assessments) follow the
  readiness contract from birth — no retrofit.

## MCP capability — consume external MCP tool servers (approved 2026-06-21; own milestone)

**Why.** Practice-area Deep Agents are meant to pick **MCP servers** (CLAUDE.md vision); future tools (e.g.
case-law research) are external providers that **cannot be imported in-process**. We have **zero MCP wiring
today** (verified: nothing in `api/app`, `web/src`, `api/pyproject.toml`; the installed `deepagents==0.6.8`
bundles no MCP helpers). This is the capability that makes "the agent picks its own tools/MCPs" real.

**Decision (maintainer).** Build it as **its own milestone**, planned around a **sanction-sync of upstream's
MCP client** rather than a from-scratch rebuild. Upstream (Kevin-Tucuxi, post-our-baseline) shipped a
**gateway-brokered** MCP **client**: all MCP tool calls route through the Inference Gateway as the single
audited egress (ADR **0014** gateway-egress-boundary-for-tool-providers, **0015** governed-tool-calling-model),
per-user OAuth (Fernet at rest), tier-gating, audit counts/types-only, a human-confirm gate, an `/admin/mcp`
registry; first live tool = CourtListener case-law. **It already matches our gateway-only egress invariant** —
so reuse beats rebuild.

**Hard gate (ADR-F001).** Upstream is FROZEN. Pulling *any* upstream code needs the maintainer's **explicit
per-case approval** and a logged sync in `UPSTREAM.md`. Next step here is a **scoped sync proposal** (exactly
which files/ADRs, how they map onto the fork's gateway + `guarded_dispatch` + audit, what diverges) brought
back for approval — **not** a pull.

**Relation to Commercial.** Independent. Adeu (the redline tool) is integrated via its **SDK in-process**, not
MCP (COMM decision I; `adeu-pinning.md`) — a local, zero-network tool whose validated-write gate needs our
code interposed. The MCP track is for *external* tools and does not block C0–C7.

**Sketch (decompose when greenlit to start):** M0 scoped upstream-sync proposal + ADR (approval-gated) → M1
gateway MCP tool-provider adapter (egress + discovery) → M2 api MCP registry + `/admin/mcp` → M3 per-area MCP
grants (mirror the `composition.py` area-keyed grant; MCP tools pass `guarded_dispatch`) → M4 per-user OAuth
(Fernet at rest) → M5 first live external tool end-to-end on DeepSeek.

## In-app Word editor — Collabora / LibreOffice over WOPI (ADR-F047; 2026-06-25 → ✅ COMPLETE 2026-06-26)

**Why.** After the agent redlines a `.docx`, the lawyer should view / edit / comment / export it **inside the
tool**, then hand it back so the agent **resumes reading the markup** — the Harvey/Legora "review in-product"
UX, without licensing Word. Promoted from the Backlog "redline-viewing" item after a full research pass
(`docs/fork/research/libreoffice-editor.md`, 9 research + 4 verifier agents) + a throwaway **Spike 0 = GO**
(`docs/fork/evidence/libreoffice-spike0/`).

**Decision (ADR-F047).** **Collabora Online (CODE) — LibreOffice on LibreOfficeKit — over WOPI, `api` as the
WOPI host, reskinned via our own Svelte chrome.** The engine is **MPL-2.0, NOT AGPL** (the research corrected
the long-held AGPL assumption) — strictly lighter than the grandfathered PyMuPDF AGPL. WASM/ZetaOffice and
custom-LOK were rejected (per-row rationale in the research doc).

**Build / licence posture.** Dev + every integration slice run the **prebuilt `collabora/code` image** (the
doc/connection cap is gone in current CODE; "not for production" is a support/warranty framing, not a licence
prohibition; Collabora chrome is hidden via our UI + CSS config). The clean unbranded / supported **production**
posture — **self-build from MPL-2.0 source OR a Collabora subscription** — is a deferred productionisation
decision (Backlog), triggered at real deployment; engine behaviour is identical, so deferring blocks nothing.

**Slices (≤2–3 days, one PR each):**
- **S1 ✅ (2026-06-25)** — local **isolated** `collabora` service (no host port, MKNOD-only sandbox, WOPI
  allow-list = `api`, no gateway reachability) behind the same-origin web `/collabora/` proxy + a minimal
  framing CSP + the `NOTICES.md` row + ADR-F047. Engine reachable same-origin, isolated, licensed, decided.
  **No app code.** (S1 finding: coolwsd 400s on a prefixed path — nginx strips `/collabora/`; making coolwsd
  EMIT prefixed asset URLs for the iframe is an S4 task — proxy-prefix / `<base>` / dedicated origin.)
- **S2 ✅ (2026-06-25)** — the **WOPI host** in `api` (`app/api/wopi.py`, bare router, ADR-F047 addendum):
  `CheckFileInfo` / `GetFile` / the full **Lock family** + a file-scoped editor-session **token**
  (`create_wopi_token`, `typ="wopi"`) minted by `POST /files/{id}/editor-session`, all on the owner-scoped
  `_load_visible_file` seam (token failure → **401**; file not visible → **404**; no cross-file replay).
  Locks = the `editor_locks` table (migration **0074**) with a pure state machine. **Read-only viewer**
  (`UserCanWrite=false`) — no save path yet, no data-loss window. No model calls / no gateway reach.
- **S3 ✅ (2026-06-25)** — **PutFile save-back** (`POST /wopi/files/{id}/contents`, ADR-F047 addendum):
  session now **editable** (`UserCanWrite=true`/`SupportsUpdate=true`). Version model =
  **snapshot-then-mutate** (maintainer's call): the agent's untouched redline is copied to a new
  immutable `File` row (`(agent draft)`, provenance kept → C7a Documents tab) on the FIRST human save,
  then the live row mutates in place (keeping its WOPI id + the ADR-0005 `key==id` convention) and flips
  to `created_by_run_id=NULL`; later saves mutate only. Untrusted bytes gated by size cap (413) +
  `guard_ooxml` + `.docx` subtype (400); lock enforced (409 + `X-WOPI-Lock`); `X-COOL-WOPI-Timestamp`
  save-race → `409 {COOLStatusCode:1010}`; `files.updated_at` (migration **0075**) makes
  `LastModifiedTime` honest. Counts-only audit; no model calls / no gateway reach / no new dependency.
- **S4 ✅ (2026-06-25)** — the cockpit **Editor** panel (ADR-F047 addendum). Resolved the S1 asset-URL
  finding: host Collabora at its **native root paths** in nginx (`/browser/`, `/cool/`, `/hosting/`, no
  strip; admin-404 regex still wins) + `ssl.termination=false` for HTTP dev (→ `ws://`); the frontend
  re-homes the discovery `urlsrc` pathname onto `window.location.origin`. Maintainer-specified UX: when the
  agent **redlines** a doc (or the lawyer clicks *Edit* in Documents), the editor **slides in from the
  right**, the conversation stays on the left, and the practice-area **rail gracefully collapses** (shared
  `cockpit.editorOpen` signal); the conversation never remounts (live SSE). Launch = `editor-session` token
  +`/hosting/discovery` urlsrc → iframe + hidden-form POST of `access_token` (never in a URL). Reskin via
  WOPI `ui_defaults` (classic toolbar, no sidebar/ruler) + best-effort `Hide_Menubar`/save-pill postMessage.
  No backend change / no migration / no new dependency. **Live-verified** (headed Cypress, real Collabora):
  the agent redline renders with tracked changes + comments; edit→save round-trips through the S3 PutFile
  (`(agent draft)` snapshot + live doc mutated + `editor.file_saved` audit). Evidence
  `docs/fork/evidence/libreoffice-slice4/`. **Deferred (incremental):** charcoal toolbar theming
  (`css_variables`) + reliable menubar-hide.
- **S4b ✅ (2026-06-26)** — editor-panel **polish** (ADR-F047 Slice-4b addendum; frontend + compose only):
  the 4 maintainer-reported UX defects — editor pane → **2/3** (`flex-[2_1_0%]` + the load-bearing
  `<section> w-full`), Collabora popups suppressed (`--o:home_mode.enable`), and a **client-side iterative
  fit-to-width** (poll + ResizeObserver off the same-origin map; `nextFitAction` grows to a 92–99% band).
  Evidence `docs/fork/evidence/libreoffice-slice4b/`.
- **S5 ✅ (2026-06-26)** — **"Done — hand back to agent"** (ADR-F047 Slice-5 addendum). The lawyer clicks
  **Done — hand back** → the doc is saved → the editor closes and the conversation composer is **primed +
  focused** with an editable instruction naming the document; the lawyer sends it (the existing
  `createRun({prompt, thread_id})` path resumes the run on the same thread) and the agent re-reads their
  edits. **Resume is real** — the agent-run subsystem already continues a thread via the langgraph
  checkpointer (the "single-turn" blocker is the legacy *chat* endpoint, not agent runs). **"Zero new agent
  code" proved too optimistic** (maintainer-confirmed): C5a `extract_counterparty_position` frames markup as
  the *untrusted other side* — wrong for a *trusted supervising lawyer* — so this slice adds a thin
  **generic, area-agnostic** re-read tool **`review_edited_document`** (granted to every matter-bound run
  beside the matter-memory tools): it reuses the proven Adeu parse (`read_state_of_play`) in a TRUSTED frame
  and **filters out the agent's own still-pending redline** (author == `DEFAULT_AUTHOR`). The matter-docx
  loaders were factored from `commercial_tools` into the generic `tools.py` (DRY). **Track-changes
  prerequisite:** an Adeu redline carries tracked content but not the `<w:trackChanges/>` recording flag, so
  the editor would open with recording OFF and the lawyer's edits would be untracked — fixed deterministically
  by `ensure_track_changes_recording` (forces the flag in the redline output's `settings.xml`, surgical +
  idempotent). No migration / no new HTTP route / no new dependency. **Live-verified** (headed Cypress):
  evidence `docs/fork/evidence/libreoffice-slice5/`. **→ The editor milestone is COMPLETE** (the production
  licence posture remains the deferred Backlog decision below).

## SAAS — hosted product (ACTIVE — maintainer pivot 2026-07-02; ADR-F058)

Outcome: companies can be onboarded onto operator-hosted, EU-resident, dedicated LQ.AI stacks
(org → admin → users), updated continuously from `main`, hard against the public internet —
while self-hosting from GitHub keeps working. Plan of record: `docs/fork/plans/SAAS-HOSTING.md`
(recon + verified findings + the A/B architecture decision); charter: ADR-F058 (three delivery
modes; stack-per-tenant now; shared-schema Mode 3 recorded + trigger-gated). Working model:
lead model drafts/orchestrates/verifies; smaller models implement.

- **SAAS-0 ✓ done — charter + governance pack (doc-only).** ADR-F058 **accepted 2026-07-02**;
  NORTH-STAR addendum (invariant #4 survives — three delivery modes); this milestone entry;
  `plans/SAAS-COMMERCIAL-PACK.md` (MSA/ToS/SLA/AUP/DPA/IR/billing checklist for the
  lawyer-maintainer); `plans/SAAS-AIACT-SELF-ASSESSMENT.md` (the product classified through its
  own `app/aiact` engine). Product name DECIDED at acceptance: **"LQ.AI Oscar Edition"**
  (upstream's name is a group the maintainer belongs to — public DNS unblocked). Still open:
  PyMuPDF, Collabora posture, EU model menu, pricing.
- **SAAS-1 ✓ done — pipeline to a deployable artifact.** `release.yml` namespace → fork;
  NEW `images.yml` push-to-main `:sha-<12>`+`:main` builds (gha cache; all 3 services build
  unconditionally — deliberate simplicity over path filtering); NEW `docker-compose.prod.yml`
  (image refs, zero host ports, mem_limits everywhere, required-var secrets, no MinIO);
  `skills/` baked into the api image via repo-root build context + root `.dockerignore`
  (CI checkouts need `submodules: true` — skills/community is a gitlink); OOM mem_limits
  branch merged as PR #186; Dependabot + weekly Trivy (SARIF severity-limited); fork
  `SECURITY.md` + repo Private Vulnerability Reporting enabled.
- **SAAS-2 ✓ done — internet-exposure hardening pack** (PR #212, ADR-F059). Redis rate limits
  (per-IP+per-account, hand-rolled atomic Lua, no new dep, fail-open) on all auth endpoints +
  `/admin/bootstrap-status`; `/auth/refresh` HMAC index (migration 0084 — kills the O(n) global
  bcrypt-scan DoS); `deploy/caddy/Caddyfile` edge-deny of `/api/v1/internal/*` + `/api/v1/wopi/*`
  + `/metrics` (uniform 404) + security headers + access-token log scrub; trusted-proxy
  `FORWARDED_ALLOW_IPS` (prod); non-dev boot assertion on `jwt_secret`. WOPI TTL kept at 10h
  (no client renewal path — edge-deny + log-scrub are the fix); proof-key deferred. Tests:
  brute-force (per-IP + per-account), refresh-flood (zero-bcrypt), limiter-wiring drift guard,
  Caddyfile drift guard, boot assertion, log scrub.
- **SAAS-3a ✓ done — staging-ready substrate** (ADR-F060). Custom Caddy image (xcaddy +
  `caddy-dns/hetzner`, Caddyfile baked in, published by `images.yml`) + the `caddy` SERVICE in the
  prod compose (the only host-ports block, wildcard DNS-01, persisted cert volumes); `deploy.sh`
  (pull → dedicated migrate → up --wait → smoke, SHA-pinned) + `deploy-staging.yml` (SSH-push,
  `environment: staging`, fires after Images); encrypted backups (`backup.sh`: `pg_dump -Fc | age`
  asymmetric → object storage + dead-man) + `restore-drill.sh` (throwaway restore + row-count
  assert) — verified end-to-end vs MinIO + pgvector; `gen-secrets.sh`; `.env.prod.example`
  (placeholders-only, guard test + `!.env.prod.example` gitignore negation); `deploy/status/`
  (Uptime Kuma, separate stack); `deploy/dns/` (A/AAAA/CAA + SPF/DKIM/DMARC templates);
  `docs/fork/runbooks/staging-bringup.md`. All verifiable with no live box.
- **SAAS-rebrand ✓ done — "LQ.AI Oscar Edition" execution.** The name accepted in ADR-F058 applied
  to the 12 user-facing product-name surfaces (shell `<title>`, CockpitHeader wordmark lockup,
  DualBrandingFooter, 8 per-page titles, README H1 + fork-identity note), scoped by a 4-lens
  branding audit; surgical display-strings-only (identifiers/wire contracts/provenance untouched;
  NOTICES.md untouched by design). Deferred on record: Word add-in display-name + manifest
  tokenisation; README body rewrite; DevForkCallout repo-URL repoint (maintainer call). Plan:
  `plans/SAAS-REBRAND-oscar-edition.md`; decision record: ADR-F058 rebrand-execution addendum.
  Recommended before the SAAS-3b public proof — done ahead of it.
- **SAAS-3b — bring-up (maintainer-gated).** Provision domain / Hetzner node / DNS token /
  object-storage bucket + the `staging` Environment secrets → run `deploy.sh` for real → **Proof:**
  a real agent run end-to-end on the staging URL + a passed restore drill; then the SAAS-2 handoff
  hardening (pin `FORWARDED_ALLOW_IPS` to Caddy's IP, promote the report-only CSP, rotate the gateway
  key, lock Collabora egress). Thin PR: the runbook checkboxes ticked with evidence. (AIC-3+ module
  work is PARKED behind the SETUP ladder — maintainer redirect 2026-07-03.)
- **SETUP ladder (maintainer redirect 2026-07-03; plan of record
  `plans/SAAS-SETUP-onboarding-architecture.md`, DRAFT for maintainer edit).** Bring-up box = an
  IONOS VPS; 3-actor model + deployment→area→matter config hierarchy + operator wizard +
  admin-configurable practice areas. **SETUP-1 ✓ done** — multi-DNS edge (Option A, ADR-F060
  amendment): hetzner+ionos compiled in, parse-time `{$LQ_AI_DNS_PROVIDER}` selection,
  `LQ_AI_DNS_API_TOKEN` generalisation, runbook de-Hetzner'd. **SETUP-2 ✓ done** — operator
  tenant-setup wizard `scripts/setup-tenant.sh` (manifest/interactive; renders .env.prod 0600 +
  verbatim Anthropic-only gateway.yaml seed + dns-records + backup cron; secrets env/prompt-only,
  NEVER in the manifest or argv; charset fence — values land in a root-sourced env file; optional
  bucket create + deploy + admin handover) + FIRST_RUN_ADMIN_EMAIL/SMTP forwarded in prod compose.
  **SETUP-3a ✓ done** — user-lifecycle backend + operator fence (ADR-F061, mig 0085): one
  `user_auth_tokens` table (invite 7d + password_reset 1h, single-use, HMAC-at-rest per ADR-F059);
  admin invite/resend/revoke + accept-invite + password-reset (uniform-202 anti-enum, background
  SMTP send) + admin disable/enable (`users.disabled_at` enforced at login/get_current_user/refresh);
  new `operator` role + `OperatorUser` dep fencing the gateway-key surfaces (aliases/provider-keys/
  config/PATCH tier-policy/override-tier-floor) — org-admin keeps the rest; **escalation guard: no
  path mints an operator except bootstrap** (`FIRST_RUN_OPERATOR_EMAIL`). Mail transport generalised
  to `app/email.py` (notify_email delegates, never-raise preserved).
  **SETUP-3b ✓ done** — Users admin UI + onboarding pages + wizard handover (ADR-F061 addendum;
  plan `plans/SETUP-3b-users-admin-ui-onboarding.md`): `/lq-ai/admin/users` (generation-B; role
  change + disable/enable + invites with SMTP-off `accept_url` handover; operator rows visible/
  badged/locked, D6); unauth `/lq-ai/accept-invite` + `/lq-ai/reset-password` (dual-state) +
  login "Forgot your password?" + hosted-aware bootstrap hint (`bootstrap-status.hosted`, D8);
  emailed links carry the real `/lq-ai/*` paths (D1); fence gating in the web UI (`/admin/models`
  operator-only, `DevRoleManagementCard` deleted — audit in `evidence/setup-3b/fence-audit.md`);
  wizard: SMTP-on handover = POST `/auth/password-reset-request` (never scrapes/prints the
  password; SMTP-off keeps the labelled log-scrape fallback) + optional `OPERATOR_EMAIL` →
  `FIRST_RUN_OPERATOR_EMAIL` (D7).
  **SETUP-4a ✓ done** — tool-group registry (availability as DATA) + practice-area CRUD +
  deployment-wide (Level 0) capability toggles (ADR-F062, mig 0086; plan
  `plans/SETUP-4a-tool-group-registry.md`). `TOOL_GROUP_REGISTRY` (code) resolves a group NAME to its
  builder/ledger/spec; `practice_area_tool_groups` (seeded names-only from today's map) is the
  area↔group availability binding — the composition elif chain becomes a registry loop (row ∩ registry
  ∩ per-matter/Level-0 toggles; grants/`*_TOOL_NAMES`/guard UNTOUCHED). Availability is now data →
  admin-created areas can be granted domain tools (cross-area attach is a FEATURE; supersedes F054-D1
  for availability, grants stay code). `deployment_capability_toggles` (Level 0, sparse, no seed) only
  NARROWS through the one `build_area_inventory` chokepoint. Endpoints (all AdminUser, 404-not-403):
  POST/DELETE `/practice-areas` (delete refuses 409 while a live matter references it), POST/DELETE
  `/practice-areas/{key}/tool-groups`, GET/PATCH `/admin/capabilities`. Hard gate: parity golden
  (`tests/agents/test_registry_parity.py`) pins the registry loop reproduces the pre-refactor grants
  byte-identically (tools/order/ledger/tabular_enabled). No web UI (SETUP-4b). NEXT: SETUP-4b (Practice
  Areas + Capabilities admin surfaces) →
  SETUP-5 reconcile (F054 flip + D1 supersession) → **SETUP-6 — actor guides (maintainer,
  2026-07-04, ON HOLD until called): human-facing operating documentation, one guide per F061
  actor — Operator (provisioning/wizard, backups + restore drill, the fence, invite handover,
  ongoing ops; links the staging-bringup runbook) / Admin (claiming the workspace, Users admin,
  areas + Level-0 capabilities, House Brief, read-only transparency surfaces) / User (matters with
  the area agent, capabilities panel, matter memory, documents/redlines/grids, budget profiles).
  Suggested home `docs/guides/`; after 4b/5 so the described UI exists; the operator guide is
  separable and can be pulled forward for the weekend bring-up** → SETUP-3c (first-login onboarding
  checklist: House Brief → invite users → review area defaults — UX polish split out of 3b, can
  ride after the 4x/5 ladder).
- **SAAS-4 — user lifecycle + admin split — ABSORBED into SETUP-3a/b** (see the SETUP ladder above).
  Original scope: invitations/verification/reset/SMTP; forced first
  password change; WorkOS-style users/orgs/memberships modeling; platform-admin vs org-admin
  (customer admin never reaches gateway-key endpoints); anti-enumeration + rate limits inherited.
- **SAAS-5 — cookie auth.** HttpOnly+Secure+SameSite session cookies + CSRF; retires
  localStorage tokens.
- **SAAS-6 — EU routing + spend governance.** Tenant-tier provider fencing (MiniMax/DeepSeek out);
  EU default menu (decision closes here); per-tenant monthly LLM spend ceiling at the gateway
  (+80 % alert); legacy-chat-stream heartbeat; licensing actions (redis pin, MinIO→object storage
  for hosted, NOTICES rows, in-product source link).
- **SAAS-7A — control plane v1 (private repo).** `tenants.yaml` inventory; provision script
  (stack + DNS + secrets + per-tenant bucket/keys + seeded admin); deploy fan-out with the N-1
  skew gate. Proof: `provision acme` → working tenant at `acme.<domain>` <30 min on a fresh node.
- **SAAS-8A — tenant ops.** Per-tenant encrypted backup/restore drill; destroy-tenant
  (data-destruction clause); per-tenant usage/cost report feeding invoices; onboarding runbook
  (org-profile intake → first witnessed run — the empty-House-Brief degradation makes this
  non-optional).

## Backlog

(One line per idea surfaced out of scope; promote at milestone boundaries.)

- **Per-matter selectable embedding provider (ADR-F056, plan `EMBEDDING-PROVIDER-choice.md`; surfaced
  2026-07-01).** Local (private/$0/sensitive) vs inference (gateway→OpenAI now, Voyage `voyage-law-2` later),
  per-matter with a firm default; single ingest↔query resolver + per-chunk provenance + re-embed-on-change +
  coverage health. Fixes the silent drift/degrade/half-index class that caused the tabular thrash. **Confirmed:
  build AFTER tabular T4.** Immediate incident already fixed (aligned dev stack to `local`, re-embedded).

- **Full N=150 hybrid CUAD calibration on a non-memory-constrained host (surfaced 2026-06-29, F2 Slice C1).**
  Slice C1 calibrated the local-embedder hybrid at N=30 (apples-to-apples vs FTS@30; within-doc recall@5
  0.314→0.629, +100%) because the local embedder + the eval's query-volume crash a Postgres backend on this
  memory-constrained dev box at N≥60. Re-run the full 150-contract hybrid vs the frozen FTS@150 floor on a
  bigger host before production rollout — empirical confirmation only; no code gap (ADR-F015 finding).

- **Per-turn (sub-thread) conversation semantic granularity (surfaced 2026-06-29, F2 Slice C2).** C2 indexes
  the Store at thread/summary granularity — the N2 offload writes one summary key per thread, so semantic
  `asearch` ranks whole threads. A long thread that mentions a detail in passing dilutes that detail in the
  whole-summary embedding. Finer granularity (chunk the offloaded transcript into multiple Store keys, e.g.
  per-turn or per-section) would sharpen needle-in-haystack recall. Touches the N2 offload writer; own slice,
  gated on a measured recall gap (ADR-F015). No code gap today — thread-granular recall is proven live.

- ~~**Authorship / "who's on our team" identity model (surfaced 2026-06-26, maintainer, in editor S5).**~~
  ✅ **Slice 1 SHIPPED (2026-06-26, ADR-F048, migration `0076`):** a dedicated `matter_participants`
  roster (identity + alias match-set → `side` ∈ ours/counterparty/unknown + role, `trust` inferred/confirmed)
  the agent auto-populates (`record_matter_participant`/`list_matter_roster`, zero model calls) and the lawyer
  amends (`POST/PATCH/retire` + a cockpit **Participants** section, human-confirmed wins). `review_edited_document`
  now classifies each author via the roster (ours→incorporate, counterparty→negotiate, unknown→**ask** the user) —
  superseding the naive `DEFAULT_AUTHOR` filter. ✅ **Slice 2 SHIPPED (2026-06-26, ADR-F048 addendum, migration
  `0077`):** all four deferrals — roster-based author **grouping in the C5a negotiation render**
  (`_render_state_of_play`, additive labelling only — coverage gate unchanged; unplaced authors default to the
  counterparty on the counterparty's own doc); a structured **`get_document_metadata`** tool (email headers from
  `structured_content` + docx core-properties author; no new HTTP route); an **`'other'` third-party side** (its
  own "weigh, don't adopt" bucket); and **lazy auto-seed of the operator** as confirmed `'ours'` at run start
  (idempotent over active+retired so a human removal isn't undone). **Known limitation (ADR-F048 §Consequences):**
  author strings (now incl. email/docx metadata) are untrusted/forgeable — they inform candidacy but are not
  cryptographic identity (a trusted, e.g. WOPI-stamped, authorship channel is future work).
- **Search past chat within a matter (ALL areas, not just Commercial) — surfaced 2026-06-22 (maintainer,
  during C3 design).** Retrieval over a matter's prior conversations so the agent (and the lawyer) can find
  "what did we say about the indemnity last week" without re-reading every thread. Distinct from the matter
  wiki (C3): the wiki is the brief, curated standing summary; this is search over the raw chat history.
  Area-agnostic (every unit of work accumulates conversations). Its own slice + likely an ADR.

- **Cockpit chat UX polish (surfaced in the C9 live UAT, 2026-06-22; web-only, small).** (1) Render
  **GFM markdown in the assistant answer** — tables/lists render in the thinking stream but the user-facing
  final message shows raw markdown (tables don't render). (2) **Quieten tool calls by default** — smaller
  tool icons; hide raw params/JSON behind the expansion toggle; default view shows only the plain-language
  line of what the model is doing (transparency stays via expand). (3) ~~**Redline download affordance**~~
  ✅ **SHIPPED as C7a** (ADR-F046, 2026-06-24): a matter **Documents tab** + an **inline run-timeline
  download** surface the agent-produced `(redlined).docx` (and every matter file) over a new
  `GET /matters/{id}/files` + `File.created_by_run_id` provenance, reusing `GET /files/{id}/content`.
- **Surgical-gate friction + agent thrash (C9 UAT).** Flash retried `preview_redline` ~8× fixing D-gate
  violations one batch at a time (renumbering edits, <15-word rationales, anchor mismatches), then fell back
  to `rewrite_justified` whole-clause rewrites. Levers: pre-teach the gate rules in `surgical-redline`;
  have the gate return all violations at once; give up faster on persistent tool errors. Feeds C8/F041.

- **C8/C9 redline-craft follow-ups — ✅ LARGELY RESOLVED by the word-diff renderer (ADR-F045, 2026-06-24; see
  `docs/fork/evidence/c9/SUMMARY.md` v3, [[redline-worddiff-shipped]]).** The 2026-06-24 re-run confirmed the prior
  craft finding; root-causing it showed the residuals were a *renderer* limit (Adeu's wholesale prefix/suffix trim
  swallowed interiors), not only model craft. Re-rendering via Adeu's native word-diff fixed them: (a) the
  **grant-clause-narrowing** worked-example is **no longer needed** — the renderer keeps grant interiors bare
  regardless of how the model quotes the clause (SecureScan/DataBridge/Northwind grant clauses went surgical in v3);
  (b) the **overlap/duplication guard** is **no longer needed** — one diff per clause + Adeu's overlap detection
  eliminated the *seam* defects (`In no event In no event` etc.; deterministic scan shows zero in v3). **Remaining
  (optional, not blocking):** a **multi-rep × strong-judge eval** to put a confidence interval on the v3 6/7
  surgical-pass — the renderer's interior-bare property is already unit-test-proven, so this only tightens the
  *model-behaviour* estimate. (Step-budget tier still **deprioritised** — pro loops to cap_exceeded regardless.)

- **Redline-viewing direction — "the lawyer SEES the redlines" (surfaced 2026-06-24, maintainer; strategic).**
  Today the agent produces a tracked-changes `.docx` the user must download + open in Word. Competitors
  (Harvey, Legora) embed a **Word editor in-product** via a Microsoft licensing arrangement so redlines are
  reviewed/accepted in-app. We can't license Word, but want the same UX. Two complementary tracks to evaluate:
  - **(a) Adeu MCP Apps — interactive "show proposed redlines" mode.** Adeu supports **MCP Apps**, so instead
    of only emitting a `.docx` it can surface proposed redlines as an interactive review surface (see/accept/
    reject per edit). **Dependency:** the fork has **zero MCP wiring today** and uses Adeu **SDK in-process,
    not MCP** ([[mcp-capability-decision]], [[surgical-redline-craft-slice]]); MCP is its own approved milestone
    (ADRs 0014/0015, approval-gated). So this is **gated behind the MCP milestone** + an Adeu-MCP-Apps spike.
  - **(b) In-app Word-fidelity editor (LibreOffice-based) — ✅ PROMOTED to its own milestone (ADR-F047,
    2026-06-25): "In-app Word editor — Collabora / LibreOffice over WOPI" above; S1 shipped.** The research
    spike is DONE (`docs/fork/research/libreoffice-editor.md` + Spike 0 GO). **Correction:** Collabora Online is
    **MPL-2.0, NOT AGPL** — the old assumption recorded here was wrong (verified against the COOL `COPYING` +
    Collabora's terms). So the licence question is the build-or-subscribe **production** posture, not a copyleft
    problem; it is *lighter* than the PyMuPDF AGPL row, not heavier.
  Both relate to **C7** (redline-download UI) — **C7a shipped the download affordance** (download the
  `.docx`, open in Word); the (b) editor milestone is the bigger "review/accept in-app" evolution beyond it.

- **Collabora editor — production licence posture (deferred from ADR-F047, 2026-06-25).** Dev + integration run
  the prebuilt `collabora/code` image. Before any real deployment, decide + execute the clean posture:
  **self-build the unbranded image from MPL-2.0 source** (≈30 GB-peak build, run once on a throwaway/CI machine
  → private registry, ~1.5 GB at runtime; re-run per version bump) **OR a Collabora subscription**. Its own
  slice (+ a build script if self-building). Engine behaviour is identical, so this gates production, not
  internal use.

- **PyMuPDF AGPL cleanup (surfaced 2026-06-25, maintainer).** Replace/remove `pymupdf` (the *only* AGPL dep,
  grandfathered, server-side-only behind `PdfReader` — `NOTICES.md`, ADR-F029) with a permissive PDF parser. If
  done, the codebase carries **zero AGPL anywhere** (the self-built Collabora is MPL). Its own slice + ADR
  (COMM open question #1). Independent of the editor milestone.

- **ROPA onboarding flow + "ROPA-from-privacy-notice" end-to-end test — half (a) DELIVERED by PRIV-7
  (PR #111).** The live notice→ROPA validation ran on DeepSeek-flash against Zendesk's real notice and built a
  **fully-linked register (9/9 activities)** through the guarded write tools — proving the document-extraction
  half works (the gap was budget + the recursion ceiling, both now fixed; the `ropa-population` skill carries
  the method). **Remaining:** ship the skill via a binding migration; the **~50-question intake** half (b)
  (≈ PRIV-A2 / ADR-F020); and a guided bulk-extraction **UX**. See `docs/fork/evidence/priv-7/FINDINGS.md`.
  Original vision (for context): an onboarding flow where the operator
  (1) hands the Privacy agent a real company **privacy notice** and (2) answers a structured **~50-question
  intake**, and the agent **auto-populates ~80% of the ROPA** from the two. Maps onto the existing/planned
  stack in two halves: **(a) document-extraction → ROPA** — already possible with the PRIV-2…6c guarded,
  code-validated write tools (`propose_processing_activity`/`_system`/`_vendor`/`_transfer`,
  `add_data_*_categories`, `link_*`); the gap is **calibration + a guided bulk-extraction UX**, not new write
  plumbing. **(b) the ~50-question intake** ≈ the **conversational-link assessment track** (PRIV-A2,
  **ADR-F020**) — a structured questionnaire the agent runs, then files code-validated ROPA. **First-class
  TEST (do this first):** run it **live on DeepSeek via the scenario harness** (`api/tests/agents/scenarios/`,
  `harness.seed_matter(..., area_key="privacy")` + `build_document`), feeding a reputable company's PUBLIC
  privacy notice into a Privacy matter and checking the agent builds a coherent, valid ROPA — an honest
  end-to-end validation of PRIV-1…6c against a real document, whose payoff renders in the register + Overview
  dashboard + the new **Data flow** view. Capture an evidence report under `docs/fork/evidence/`; if it
  reveals a needed capability (a bulk-extract tool, the intake), that becomes its own sliced milestone + ADR.
  Providers are dev-only (MiniMax/DeepSeek; a client runs a Western model via the gateway —
  [[llm-is-injected-replaceable]]). Relates to [[oscar-privacy-modules-vision]] and the assessment track.

- **Find-or-create category deadlock under parallel tool calls (from PRIV-7, 2026-06-19 — real bug, HIGH).**
  `add_data_subject_categories` / `add_data_categories` find-or-create can hit a Postgres
  `DeadlockDetectedError` on the `lower(name)` unique index when deepagents executes a turn's tool calls
  concurrently and two overlapping category writes race. PRIV-6a's SAVEPOINT absorbs `IntegrityError` (lost
  race) but **not** a deadlock → the whole run fails. Fix = catch `DeadlockDetectedError` and retry the
  SAVEPOINT (bounded). Guarded write path → its own slice + security review. Evidence: PRIV-7
  `build-deepseek-skill-s150` pass 1.
- **ROPA quality gaps from the PRIV-7 privacy-lawyer audit (overall C+; real defects the structural scorer
  missed).** (a) **Invariant gap (code):** the write path enforces `special_category=true ⇒ art9_condition`
  but NOT the inverse — an activity can carry a special-flavoured data category (e.g. "Sensitive Personal
  Data") while `special_category=false`/no Art 9, and it passes as `integrity_ok=true` (a false-clean signal).
  Tighten the validation (flag/reject special-category-named data categories on non-special activities,
  or a controlled-vocabulary "is_special" flag). (b) **Transfers get dropped** under budget pressure — the
  most serious quality defect (Art 30(1)(e)/(f) absent despite an explicit transfer disclosure); the
  `ropa-population` skill should foreground transfers (or transfers get their own orchestrated step). (c)
  **Recipient-role calibration** (model tends to over-use `processor` where `separate_controller` is right for
  ad-tech / advisors). Evidence: `docs/fork/evidence/priv-7/FINDINGS.md` § Substantive quality audit.
- **Ship the `ropa-population` skill (from PRIV-7) — bind it to the Privacy area via a migration** (the 0056
  pattern; rebuild workers) so the live cockpit Privacy agent gets it, not just the harness. Validated
  test-only in PRIV-7 (the maintainer's "test-only first, ship once proven" — now proven, 9/9).
- **Register a deepagents harness profile for `deepseek` (from PRIV-7 — cheap).** deepagents logs "no profile
  matched … 'deepseek'; using defaults" every run; a tuned profile may improve loop/token budgeting.
- **"Populate records from a source" family (from PRIV-7's framing).** Notice→ROPA is the first; the same
  reusable scorer + skill pattern extends to populating/maintaining records from **files, interviews, client
  instructions, and analytics**, and to the **orchestrator/reader** subagent split (pro orchestrates, flash
  reads). Each its own slice.
- **ROPA private→shared information-flow gap (from the PRIV-6a ultracode audit, 2026-06-18 — medium) → now
  owned by the Authorization track (ADR-F021).** The deployment-global ROPA register (ADR-F019, shared-read)
  means a privileged/private matter's confidential narrative could be distilled by the Privacy agent into a
  register free-text field (purpose/description/details) and then read by ANY authenticated **enterprise** user.
  `project.privileged` is in the binding but gates only the inference tier, not ROPA writes. **This is the
  symptom of the missing areas-of-responsibility permissions layer, not a ROPA-local bug** — it is closed
  properly by **ADR-F021 Phase 3 + 4e** (durable area attribution on register rows, then flipping the register
  read-filter to area membership). The interim cheap mitigations (a generic-facts-only guardrail in the Privacy
  `profile_md` + `propose_*`/`add_*` docstrings; and/or gating privileged-matter writes) remain a maintainer
  option if the permissions flip is far out. Full write-up: `docs/fork/evidence/priv-6a/audit-report.md` #3.
- **Guard DB-error message scrubbing (defense-in-depth, from the PRIV-6a audit — low).** `guard.py` re-raises
  a tool's exception; the runner serialises `str(exc)` into `AgentRun.error` + the SSE frame, so a raw
  `DBAPIError`/`IntegrityError` would carry the failing SQL + bound params. PRIV-6a closed the only reachable
  path (the find-or-create savepoint); hardening the shared chokepoint to map `DBAPIError` → a constraint-
  name-only, value-free message (keeping the raw text in server logs) is belt-and-braces across all tools.
- ~~Project rename before public release (ADR-F001 obligation)~~ — DECIDED 2026-07-02 at
  ADR-F058 acceptance: "LQ.AI Oscar Edition" (upstream's name is a group the maintainer belongs to).
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
- ~~Redis pub/sub run-stream publisher (live token deltas across the api/worker boundary; F1-S1
  moved execution to arq, so live streams currently degrade to the 2s DB-tail — animation only).~~
  **DONE in PRIV-9b (ADR-F025):** `RedisStreamBroker` (worker, publish) + `RedisStreamBridge` (api,
  relays into the existing local broker) — the full live stream (reasoning ribbon, tool frames, the
  `data-ropa-change` highlight) now crosses worker→Redis→api→SSE; proven live on DeepSeek.
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
    in-matter agent capability, not a top-level tool. ~~Needs a roadmap decision.~~ **→ DECIDED
    2026-06-30: Phase 2 of the "Capability panel + in-matter Tabular review" milestone (Commercial +
    Corporate, as a guarded agent tool, grid UX augmented by LQ-Grid).**
  - **Per-user/per-area MCP connectors + OAuth handshake** — concrete reference for our stated MCP
    direction (aligns with upstream ADR 0014/0015 gateway tool-egress + the agentic-modules milestone).
  - **Document versioning + soft-delete**, **GDPR data export/erasure** (fits the Privacy area), and
    **collaboration: sharing + org multi-tenancy** (we are single-operator-voice today) — each a gap.
  - **Inline citation / case-law panels** as a first-class structured response element — a UX pattern
    for Citation-Engine output.
  - **CONTRAST, do NOT copy:** mike holds LLM keys per-user client-side; our gateway is the sole
    egress + key-holder ([[llm-is-injected-replaceable]]) — keep that boundary.
- **EU AI Act register module — BANKED (2026-06-19; reference-only prior art).** A second
  regulatory-register module for the agentic-modules substrate (ADR-F018), the near-twin of Module 1
  (Privacy/ROPA): a register of an enterprise's **AI systems** that a Deep Agent maintains, with system
  owners / SMEs invited to **chat to the agent via a link** to describe each system; a **deterministic
  rules engine — not the model — issues the verdict of record** (EU AI Act role + risk tier + obligations
  + article refs + deadlines), the LLM only *proposes* structured answers. This is exactly ADR-F018
  code-validated writes / "system proposes, user owns". The shape maps almost 1:1 onto Privacy: AI-system
  register ≈ processing-activity register; conversational-link intake ≈ **PRIV-A2 / ADR-F020**; per-area
  RBAC (DEPT_SME ↔ department) ≈ **ADR-F021** (user ↔ practice area). **Prior art = the maintainer's
  private repo `sarturko-maker/EU_AI_Act` (Next.js / Prisma).** **REFERENCE-ONLY, clean-room** (same
  posture as scira / willchen96-mike): take the *design + domain patterns*, re-author on our stack
  (FastAPI / SQLAlchemy / SvelteKit); copy **no** code, seed data, brand tokens, prompt copy, subsidiary
  list, docs, or git history. **HARD RULE — the employer's name / branding / corporate identity must
  appear NOWHERE in the fork**; clean-room re-implementation satisfies this *by construction* (the engine
  has no intrinsic employer dependency — "employer" is only the source repo's first seeded tenant, layered
  on top). Ports as *design*: the decision tree + named predicates + a signed verdict hash; the proposal
  envelope (value / confidence / state / evidenceQuote / citedRefs) + omit-don't-coerce + a **server-side
  presence gate** (the model can't self-certify into a classification); primary-source-only grounding with
  "every citedRef must resolve". Re-author (not port) as code: the Next.js/React/Prisma/zod/undici layer
  → our stack; and **improve** on the source's single stateless-HTTP intake turn → a real deepagents
  tool loop. Domain caveats to **re-validate, not copy**: the rules encode a *draft* Commission Art 6(3)
  guideline, do **not** model GPAI Chapter V, and straddle BASELINE vs the unpublished Digital Omnibus
  deadline set. **Promote → its own plan + ADR (~F022); it should RIDE ADR-F018 (module) + ADR-F021
  (permissions) + ADR-F020 (conversational intake), never precede them.** Assessment: this session's
  7-agent parallel read.
