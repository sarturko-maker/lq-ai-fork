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
- **S8 — matters without leaving the agent (maintainer directive, 2026-06-11).** "+ New matter"
  on the Agents tab reusing the SAME plumbing as the Matters tab: `NewMatterModal` +
  `POST /projects`, full form — the privileged ⇒ tier-floor invariant (PRD §3.11, enforced in
  `ProjectCreateRequest`) must ride along; never a name-only quick-create. Prereq refactor: the
  modal's hardcoded post-create `goto('/lq-ai/matters/{id}')` moves to the Matters page's
  `onCreated` callback (the caller owns navigation — invoked from the Agents tab it would yank the
  user out, defeating the directive). On create: bind the new matter, clear pending upload chips
  (the F0-S5 honesty invariant — chips belong to the matter they filed into), refresh the matter
  list. With create-in-place shipped, the free-floating "No matter — blank workspace" option is
  REMOVED (ADR-F002: free-floating agent chat is not offered — memory has nowhere to accumulate).
  Today's zero-matter first run is a hard dead end (no create affordance, attach disabled, no link
  out) — this is the worst live first-impression and is independent of S7.
- **S9 — eval gate (ADR-F004).** Tool-call and subagent uptake at N≥20 on MiniMax-M3 plus one
  second model family (masked judge, pre-flight variance gate); subagent dispatch as task-scoped
  procedures, not open-ended delegation.

## F1 — First practice area, end to end (ADR-F002)

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

## Backlog

(One line per idea surfaced out of scope; promote at milestone boundaries.)

- Project rename before public release (ADR-F001 obligation).
- Embedding provider strategy (KB + chat vector search currently lack one; MiniMax coding-plan key is
  chat-only — needs a dedicated embedding model, possibly local/Tier-1 for privileged matters).
- `<think>` block handling in MessageBubble for reasoning models (MiniMax-M3 emits them inline).
- Streaming anonymization rehydration end-to-end test (upstream defers the streaming response path).
- Per-phase / per-tool cost budgets inside a unit-of-work budget.
- Configurable ethics gates per practice area (upstream's ethics_review is a stub).
- Email-grade entry points: forward an email into a Matter; Word add-in revival.
- Revisit third-party memory (Zep/Graphiti temporal graph) only if native consolidation proves
  insufficient (ADR-F003 option 3).
- ~~Run artifact surface~~ — PROMOTED into F1 (audit 2026-06-11).
- Thread management: rename, delete (MUST call `adelete_thread` — checkpoint rows carry
  conversation content; security-review path), pagination past the 20-thread list cap (a cockpit
  grouping client-side from it under-reports older matters) — F1/F2.
- Searchable recent-first matter picker with privileged marker (replaces the flat name-only
  `<select>`; one of the S6 bare-select deferrals) — F1 design system.
- Global notification bell in the chrome (DE-324 deferral) — cockpit-adjacent.
- Declare the F3 retire list explicitly when the IA re-centres: saved-prompts, guided-dashboard
  components, FeaturedToolsRow, learn-as-global-tab.
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
