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
- **S4 — multi-turn chat.** Send conversation history (replaces the single-turn request in
  `chats.py`); wire the Postgres checkpointer (first consumer of langgraph-checkpoint-postgres).
- **S5 — SSE v2.** Tool-call / subagent / plan / progress frame types end-to-end; upgrades the S3
  polled rail to live streaming.
- **S6 — eval gate (ADR-F004).** Tool-call and subagent uptake at N≥20 on MiniMax-M3 plus one
  second model family (masked judge, pre-flight variance gate); subagent dispatch as task-scoped
  procedures, not open-ended delegation.

## F1 — First practice area, end to end (ADR-F002)

Outcome: one configurable practice area (suggest: Commercial) with one Deep Agent and one unit-of-work
type ("Matter") usable for a real task (e.g. NDA review), with visible agent work in the UI.

- `practice_areas` schema + config/admin API (name, unit-of-work label, area profile, bound
  skills/playbooks/MCPs, default tier floor); `projects.practice_area_id` (nullable — legacy Matters
  unchanged); audit rows gain `practice_area_id`.
- Area config is declarative shape data (subject type, counterparty role enums, kind options,
  conditional extras, privileged defaults) consumed by one renderer — no per-area code branches;
  user-added areas can host units of work from day one (ADR-F004).
- Tool parameters classified A/B/C; matter/user/scope identifiers are B-class — runtime-injected,
  never LLM-visible (ADR-F004). Capability rail renders from settled state records, not the stream.
- **Agents tab = practice-area home**: area page with unit-of-work list, agent config, area memory,
  conversation surface. Conversations bind to (practice area, Matter) — no free-floating agent chat.
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
