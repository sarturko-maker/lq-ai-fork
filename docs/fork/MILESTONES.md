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
- **S6 — the shell shed (ADR-F006, pending acceptance).** Extract the lq-ai code (zero
  husk-imports, audited) into a standalone lean SvelteKit app; kill the OpenWebUI husk, its Python
  backend container, and the §4 branding obligation. Includes the per-file provenance pass over
  lq-ai `.svelte` components and the `app.html` theme-script rewrite. Verification: screenshot
  diff + the f0-s3 Cypress spec green on the new shell.
- **S7 — SSE v2: stream like Claude Code (ADR-F006 wire spec).** Emit the AI SDK UI Message Stream
  v1 from FastAPI (hand-rolled emitter; `data-*` parts for subagent/interrupt/plan/receipt carrying
  settled step-row ids — ADR-F004 intact). Reasoning deltas as a collapsed-by-default thinking
  ribbon with shimmer status (the cross-product convention); tool/plan frames live; upgrades the S3
  polled rail.
- **S8 — eval gate (ADR-F004).** Tool-call and subagent uptake at N≥20 on MiniMax-M3 plus one
  second model family (masked judge, pre-flight variance gate); subagent dispatch as task-scoped
  procedures, not open-ended delegation.

## F1 — First practice area, end to end (ADR-F002)

Outcome: one configurable practice area (suggest: Commercial) with one Deep Agent and one unit-of-work
type ("Matter") usable for a real task (e.g. NDA review), with visible agent work in the UI.

- **Design system build-out (ADR-F006)** alongside the area home: shadcn-svelte + bits-ui +
  paneforge + Tailwind v4; semantic intent tokens (the Harvey pattern), light+dark, denser
  work-tool spacing; bespoke agent components (reasoning ribbon, plan/task/tool cards, subagent
  tree) with AI Elements / deep-agents-ui as semantic references. Benchmark bar: Harvey/Legora
  workspaces, Claude.ai thinking UX.

- `practice_areas` schema + config/admin API (name, unit-of-work label, area profile, bound
  skills/playbooks/MCPs, default tier floor); `projects.practice_area_id` (nullable — legacy Matters
  unchanged); audit rows gain `practice_area_id`.
- Area config is declarative shape data (subject type, counterparty role enums, kind options,
  conditional extras, privileged defaults) consumed by one renderer — no per-area code branches;
  user-added areas can host units of work from day one (ADR-F004).
- Tool parameters classified A/B/C; matter/user/scope identifiers are B-class — runtime-injected,
  never LLM-visible (ADR-F004). Capability rail renders from settled state records, not the stream.
- **Agents tab = practice-area home** (maintainer layout, 2026-06-10): **LEFT panel = practice
  areas** — click an area to create a Matter or pick an existing one (S3's auto-landing in
  Commercial was flagged); CENTER = the conversation. Conversations bind to (practice area,
  Matter) — no free-floating agent chat.
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
- Auto-titling + auto-filing of chats to the inferred Matter (one-tap confirm when uncertain).
- Extend `work_product_attributions` to multi-inference agent runs (fan-out-safe chain of custody).

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
- Playbooks + tabular review callable as agent tools inside a unit of work (unify the three substrates).
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
- Run artifact surface: expose the deepagents workspace files a run produced (S3 deferral).
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
- `docs/api/backend-openapi.yaml` is stale for the agents surface (runs since S2, threads since
  S5) — regenerate or annotate when the surface settles (S7's SSE v2 reshapes it anyway).
