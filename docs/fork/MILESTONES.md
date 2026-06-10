# Fork milestones

Outcome-based milestones, not calendar sprints. Each milestone breaks into vertical slices
(end-to-end, runnable, testable, ≤2–3 days, one PR each). Re-plan at milestone boundaries.
Status: DRAFT — pending maintainer review alongside ADR-F001.

## F0 — Agentic substrate (unblocks everything)

Outcome: a model can drive a real tool-calling loop through the gateway, in a multi-turn conversation.

- Lift the langgraph pin: langgraph 1.x + langchain + deepagents (pinned exact version); keep the three
  legacy executors compiling (frozen, bugfix only). Postgres checkpointer + BaseStore wired.
- First-class `tools` through the gateway: Anthropic adapter `tool_use`/`tool_result` translation;
  `tools`/`tool_choice` in the request schema; routing-log rows per loop step.
- Multi-turn chat: send conversation history (replaces the single-turn request in `chats.py`).
- SSE protocol v2: tool-call / subagent / plan / progress frame types, backend emitter → parser → UI.

## F1 — First practice area, end to end

Outcome: one configurable practice area (suggest: Commercial) with one Deep Agent and one unit-of-work
type ("Matter") usable for a real task (e.g. NDA review), with visible agent work in the UI.

- `practice_areas` schema + config API + admin UI (name, unit-of-work label, bound skills/playbooks/MCPs).
- Deep Agent per area via `create_deep_agent`: area system prompt, area-scoped skills, subagent fan-out,
  every tool dispatch through `guarded_tool_call` (R4/R5/R6 + audit preserved).
- Unit-of-work container: extend `projects` with practice_area FK + typed unit-of-work config.
- Extend `work_product_attributions` to multi-inference agent runs (fan-out-safe chain of custody).

## F2 — 4-level memory

Outcome: agent context assembled from company/client → practice area → user → unit of work; agents
propose, users curate, at every level.

- deepagents CompositeBackend: `/memories/{company,practice,user,matter}/` → StoreBackend namespaces
  keyed `(org_id, …)`; company + practice read-only to agents.
- Client/counterparty profiles (new entity — distinct from `organization_profile`).
- Wire kept user memory into prompts (today `load_kept_memory()` is uncalled).
- Memory curation UI per level; "system proposes, user owns" everywhere.

## F3 — Practice-area UX re-centre

Outcome: the IA is practice areas → units of work; tool tabs become in-context capabilities.

- Routing: `/lq-ai/areas/:area/...`; area-scoped dashboards; matter-first navigation.
- Playbooks + tabular review callable as agent tools inside a unit of work (unify the three substrates).
- MCP servers per practice area via `langchain-mcp-adapters` (scoped tool sets, not global).

## Backlog

(One line per idea surfaced out of scope; promote at milestone boundaries.)

- Project rename before public release (ADR-F001 obligation).
- Streaming anonymization rehydration end-to-end test (upstream defers the streaming response path).
- Per-phase / per-tool cost budgets inside a unit-of-work budget.
- Configurable ethics gates per practice area (upstream's ethics_review is a stub).
