# F002 — Practice areas as backend entities; the Agents tab as practice-area home

Status: proposed
Date: 2026-06-10

## Context and problem statement

The fork organises work around practice areas and units of work (ADR-F001), but today `practice_area`
and `unit_of_work` appear nowhere in the schema; Matters are generic `projects` rows; and the UI is 11
flat tool tabs. We need an incremental path that ships a real practice-area experience without
rewriting the whole IA first. The maintainer's direction: a new **Agents** tab, split by practice
area, where agents use the existing skills, tools, and Matters.

A second requirement shapes the UX: the target user is a non-AI-native in-house lawyer. They must not
assemble context (model pickers, skill pickers, attach-this-attach-that), but they must always be able
to **see** what the agent is doing — invisible magic erodes trust as fast as visible complexity erodes
adoption. This is the transparency principle (PRD §1.3) applied to agent activity.

## Considered options

1. **Frontend-only grouping** — practice area as a UI filter over existing entities. Rejected: memory
   scoping, agent config, audit slicing, and tool grants have nothing to hang off; it would all be
   rebuilt later.
2. **Full IA rewrite first** — re-route everything under `/lq-ai/areas/:id/...` before shipping any
   agent. Rejected: months of refactoring before any user-visible agent value; high regression risk.
3. **Agents tab as practice-area home, backed by first-class backend entities**, promoted to the
   top-level IA later (milestone F3).

## Decision outcome

Option 3, with these load-bearing rules:

- **Practice areas are backend entities from day one**: a `practice_areas` table (name, unit-of-work
  label e.g. "Matter"/"Programme", area profile markdown, bound skills/playbooks/MCP servers, default
  tier floor) plus a config API and admin surface. Matters (`projects`) gain a nullable
  `practice_area_id`; existing Matters keep working unchanged.
- **Conversations bind to (practice area, unit of work).** You talk to the Commercial agent *about* a
  specific Matter; the agent loads that Matter's files, KBs, context, and digest. Free-floating agent
  chat with no unit of work is not offered — it gives memory nowhere to accumulate.
- **The agent's tool universe comes from area config**, and every tool dispatch goes through the
  existing `guarded_tool_call` chokepoint (R4/R5/R6 + audit). The agent picks among what the area
  grants; the user picks nothing.
- **The Agents tab is the area's home, not a chat gadget**: each area page holds its unit-of-work
  list, its agent configuration, its area memory, and the conversation surface.

### The visible-work UX (the "glass cockpit")

- **No AI furniture**: no model picker, no skill picker, no attach-context controls — one message box
  on the unit-of-work page. Skills/playbooks/MCP tools are capabilities the agent selects.
- **Capability rail**: a side panel listing the area's available skills, playbooks, and tools — dim
  when idle, **lit when loaded into context, animated while in use**. Each entry click-throughs to the
  existing inspection surfaces (SKILL.md view, playbook view), preserving "every artifact is readable."
- **Live activity feed**: streamed agent steps (tool calls, subagent fan-out, plan updates) rendered
  in the rail/drawer — requires the SSE v2 frame types from milestone F0.
- **Decision inbox**: when the agent needs input or approval, it surfaces as a card (home + area
  page), implemented on LangGraph interrupts — not a question buried in chat scroll.
- **Trust chrome stays quiet but present**: tier badge, citations inline, receipts drawer for
  retrospective "what exactly happened" (existing machinery).
- **Auto-titling and auto-filing**: chats are named automatically and filed to the inferred Matter,
  with a one-tap confirmation when the inference is uncertain.
- **Deliverables are artifacts, not chat text**: drafts/redlines land as versioned files on the
  Matter (M4 artifact pattern), one click to Word.

## Consequences

- New migrations (`practice_areas`, `projects.practice_area_id`, area↔skill/playbook/MCP bindings) and
  a config/admin API; audit rows gain `practice_area_id` for per-area slicing.
- F1 ships this inside one new tab with zero disruption to existing tabs; F3 promotes area pages to
  the top-level IA and demotes tool tabs to in-context capabilities.
- Risk: the tab ossifies as a 12th tool surface. Mitigations are the rules above — real backend
  entity, conversation binding, area-scoped tool grants — plus the explicit F3 commitment.
- The capability rail and activity feed depend on F0 (gateway tool-calling + SSE v2); until then the
  rail can show only available/loaded states, not live use.
