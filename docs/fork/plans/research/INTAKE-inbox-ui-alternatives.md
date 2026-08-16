# INTAKE research round 2 — inbox-UI alternatives, production practice, and why LangChain stepped back (2026-08-16)

> Commissioned after the maintainer asked: "how about we look for UI alternatives to Agent
> Inbox? what do people use to monitor agents? why has LangGraph disconnected it?"
> Three Sonnet research lines. §1 and §3 are verbatim agent reports; §2 is the lead's
> distillation of two raw evidence dumps (GitHub archaeology + official/community statements)
> whose full text lives in the session transcript. Feeds `INTAKE-INBOX-plan.md` § Ruling 2.

---

# §1 — HITL approval-UI landscape vs `agent-inbox` (verbatim agent report)

Frame: Svelte 5 SPA, FastAPI + langgraph 1.x + deepagents 0.6.8 in-process, self-host-first
(data residency), existing SSE + deepagents `HumanInTheLoopMiddleware` schema
(`HITLRequest{action_requests,review_configs}` in / `{"decisions":[{type:
approve|edit|reject|respond}]}` out), existing Slack/Teams bridges.

## Baseline: langchain-ai/agent-inbox
Next.js/React, MIT, ~1,071 stars, since 2024-11-04 ([repo](https://github.com/langchain-ai/agent-inbox)). Native schema is the *legacy* `HumanInterrupt`/`HumanResponse` shape ([types.ts](https://github.com/langchain-ai/agent-inbox/blob/main/src/components/agent-inbox/types.ts)). PR #91 (2026-01-22) added an **inbound-only, partial** shim for the newer middleware format — it reads only `action_requests[0]` (drops the rest) and has no mapping for `allow_ignore` ([PR #91](https://github.com/langchain-ai/agent-inbox/pull/91)). The **outbound resume path was never updated**: it still POSTs the legacy `HumanResponse[]` array, not a `{"decisions":[...]}` envelope, and the vocabularies don't line up (accept≠approve, no `respond` equivalent) ([hook](https://github.com/langchain-ai/agent-inbox/blob/main/src/components/agent-inbox/hooks/use-interrupted-actions.tsx), [middleware docs](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)). Commit history shows ~7 months of pure dependency bumps, zero feature work since Jan 2026 ([commits](https://github.com/langchain-ai/agent-inbox/commits/main)); no auth story (open issue #84 since 2025-10-06, unanswered) ([issue #84](https://github.com/langchain-ai/agent-inbox/issues/84)). Not archived; LangGraph Studio has not absorbed this capability ([Studio docs](https://docs.langchain.com/langgraph-platform/langgraph-studio)).

## 1. langchain-ai/agent-chat-ui
Next.js/React 19 chat app for any LangGraph server ([README](https://github.com/langchain-ai/agent-chat-ui/blob/main/README.md)). MIT ([LICENSE](https://github.com/langchain-ai/agent-chat-ui/blob/main/LICENSE)).
- **Schema:** supports **only** the newer `HITLRequest{action_requests,review_configs}`/decisions shape — legacy support was *removed* 2025-11-14 (PR #194) ([PR #194](https://github.com/langchain-ai/agent-chat-ui/pull/194)). Only 3 of 4 decision types are wired (`approve|reject|edit`; no `respond`) ([utils.ts](https://github.com/langchain-ai/agent-chat-ui/blob/main/src/components/thread/agent-inbox/utils.ts)). Anything not matching the exact shape falls to a **read-only** JSON dump with no resume — open bugs report non-matching interrupts, including **deep-agents interrupts**, causing the graph to restart from START instead of resuming ([#262](https://github.com/langchain-ai/agent-chat-ui/issues/262), [#269](https://github.com/langchain-ai/agent-chat-ui/issues/269)).
- **Embeddability:** standalone app only — `private:true`, no npm registry entry ([package.json](https://github.com/langchain-ai/agent-chat-ui/blob/main/package.json)).
- **Backend contract:** requires the LangGraph Platform/Server REST+SSE API via `useStream`; an in-process backend would need to fake that whole surface ([Stream.tsx](https://github.com/langchain-ai/agent-chat-ui/blob/main/src/providers/Stream.tsx)).
- **Maintenance:** pushed 2026-08-12, but zero releases/tags, ships unversioned off `main`, 7/10 recent commits are Dependabot ([commits](https://github.com/langchain-ai/agent-chat-ui/commits/main)).
- **Verdict:** exact schema match on paper, but React-only, app-not-library, and requires a server API we don't run — usable only as a logic reference, not runnable code.

## 2. CopilotKit + the AG-UI protocol
CopilotKit: MIT, self-hostable "Copilot Runtime" + React frontend stack; "CoAgents" is its LangGraph integration (Generative UI + HITL checkpoints + shared state) ([CoAgents](https://docs.copilotkit.ai/coagents), [self-host](https://docs.copilotkit.ai/guides/self-hosting)). HITL hooks: `useHumanInTheLoop` (agent-initiated) and `useInterrupt` (graph-enforced, unsupported on CopilotKit's own built-in agent) ([HITL docs](https://docs.copilotkit.ai/agent-spec/human-in-the-loop)). Very active (36.8k★, releases days apart) ([API](https://api.github.com/repos/CopilotKit/CopilotKit)).
**AG-UI** is CopilotKit's protocol, "born from CopilotKit's initial partnership with LangGraph and CrewAI" ([intro](https://docs.ag-ui.com/introduction)) — still CopilotKit-hosted governance; no evidence of a neutral-foundation move as MCP made to the Linux Foundation ([MCP/LF](https://github.blog/open-source/maintainers/mcp-joins-the-linux-foundation-what-this-means-for-developers-building-the-next-era-of-ai-tools-and-agents/)). Its `EventType` enum has no dedicated interrupt event, but `RunFinishedEvent.outcome` carries a typed `Interrupt{id,reason,message,tool_call_id,response_schema,expires_at,metadata}`, resumed via a `resume[]` array on the next run ([events.py](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/python/ag_ui/core/events.py)). **Critically, the core packages are framework-agnostic**: `@ag-ui/core` depends on nothing but `zod`; the Python `ag-ui-protocol` package depends on nothing but `pydantic` — docs explicitly frame any consumer (web app, terminal, Slack/Teams) as a valid "client" ([clients](https://docs.ag-ui.com/quickstart/clients), [npm](https://www.npmjs.com/package/@ag-ui/core), [PyPI](https://pypi.org/project/ag-ui-protocol/)). Official adopters include LangGraph, MS Agent Framework, Google ADK, AWS Strands, Mastra, CrewAI, LlamaIndex, Anthropic's Claude Managed Agents, Bedrock AgentCore ([integrations](https://docs.ag-ui.com/integrations)). MIT, 15.3k★, releases every 1-3 days ([API](https://api.github.com/repos/ag-ui-protocol/ag-ui)).
**Verdict:** CopilotKit's own UI is React-locked, but the AG-UI *protocol* is a real, self-hostable, Svelte-reachable wire format with a native interrupt/resume envelope — the most standards-credible non-React option, at the cost of a schema-translation layer and zero ready UI.

## 3. assistant-ui
TS/React library, MIT, YC-backed ([LICENSE](https://github.com/assistant-ui/assistant-ui/blob/main/LICENSE)). `@assistant-ui/react-langgraph` treats interrupts as first-class state (auto-reconciled across thread switches) but requires a LangGraph Cloud API server ([interrupts docs](https://www.assistant-ui.com/docs/runtimes/langgraph/interrupts)). No pre-built approval widget — you author one via `resume()`/`addResult()`/`respondToApproval()` render props; a copy-paste "elements" gallery includes an Approval Card, Permission Grant, Confirm Dialog, Reviewable Diff ([tool-ui](https://www.assistant-ui.com/docs/tools/tool-ui), [elements](https://www.assistant-ui.com/elements)). **Confirmed no Svelte/Vue/Angular binding exists** — every shipped runtime is React-family (web, React Native, React Ink) ([packages](https://www.assistant-ui.com/packages)). 11.7k★, active daily ([API](https://api.github.com/repos/assistant-ui/assistant-ui)).
**Verdict:** React-only, unusable as code in a Svelte app; valuable purely as a component-taxonomy reference.

## 4. HumanLayer
The original approvals-as-API SDK is dead: its own README says "pretty much all deprecated," redirecting to a different product ([README](https://raw.githubusercontent.com/humanlayer/humanlayer/main/README.md)); PyPI's last release was 0.7.9 on 2025-06-03, 14+ months stale ([PyPI](https://pypi.org/project/humanlayer/)). The company pivoted to **CodeLayer**, a coding-agent orchestration IDE (multi-agent Claude Code/Codex session management) — a different product category, not yet open source per its own FAQ, priced $0/$100 per user per month/Enterprise-with-on-prem ([humanlayer.com](https://humanlayer.com)). `12-factor-agents` is a popular methodology repo (25.3k★) with a HITL discussion (Factor 7) but **no shipped UI code**, unpushed since 2025-09-21 ([repo](https://github.com/humanlayer/12-factor-agents)).
**Verdict:** no currently-maintained generic approvals product exists here today — exclude.

## 5. gotoHuman
Hosted SaaS review inbox; core app is closed, client SDKs (Python/JS/MCP) are MIT ([Python SDK](https://github.com/gotohuman/gotohuman-python-sdk)). Contract: `POST https://api.gotohuman.com/requestReview` with `formId`/`fields`/`assignTo`; decision returned only via webhook ([docs](https://docs.gotohuman.com/send-requests)). No self-host at any tier; four SaaS plans, $0–$950/month ([pricing](https://www.gotohuman.com/pricing)). Actively released as recently as June 2026 ([PyPI JSON](https://pypi.org/pypi/gotohuman/json)).
**Verdict:** clean contract, but third-party-hosted approval data is close to disqualifying for our data-residency bar.

## 6. Portia AI
**Appears defunct/rebranded as of this research.** `portialabs.ai` now 301s to `rezonant.app`, an unrelated product-management tool; the `portiaAI` GitHub org has been renamed to Rezonant; `github.com/portiaAI/portia-sdk-python` and its PyPI project both return genuine 404/Not-Found. Its well-designed `Clarification` primitive (6 typed subclasses: Input/Action/MultipleChoice/ValueConfirmation/UserVerification/Custom) never shipped a UI — resolution was always developer-wired via a `ClarificationHandler`, with only a CLI reference implementation (per a cached third-party doc mirror, since official docs are also dead) ([DeepWiki mirror](https://deepwiki.com/portiaAI/portia-sdk-python/5-clarification-system)). Last known-good release 0.9.0, 2025-10-28 ([libraries.io](https://libraries.io/pypi/portia-sdk-python)).
**Verdict:** do not adopt — the project is gone.

## 7. Permit.io
Authorization-as-a-service; its "Access Request MCP"/"Elements" HITL feature is real, but **the actual approval UI is a closed-source iframe served from Permit's own cloud** (`embed.permit.io`, configured at `app.permit.io`) — not an embeddable component, and "React Elements" are still listed as "coming soon" ([Elements docs](https://docs.permit.io/embeddable-uis/element/operation-approval), [elements page](https://www.permit.io/elements)). The only feature-named OSS repo, `permit-mcp`, has 3 stars and hasn't been pushed since 2025-05-05 ([repo](https://github.com/permitio/permit-mcp)). The self-hostable PDP keeps a live sync channel to Permit's cloud unless on the Enterprise on-prem tier, and no self-host path was found for the approval UI itself ([PDP docs](https://docs.permit.io/concepts/pdp/overview), [pricing](https://www.permit.io/pricing)).
**Verdict:** third-party-hosted UI in the approval path — exclude on data-residency grounds.

## 8. Inngest / AgentKit
`step.waitForEvent()` pauses a function; any system resumes it with a plain HTTP POST to the Event API ([waitForEvent](https://www.inngest.com/docs/reference/typescript/functions/step-wait-for-event), [events](https://www.inngest.com/docs/events)). **No inbox UI exists anywhere in the product** — this is a backend primitive only ([AgentKit HITL](https://agentkit.inngest.com/advanced-patterns/human-in-the-loop)). The self-hostable server is **SSPL-licensed** (source-available, not OSI-approved); AgentKit itself is Apache-2.0 but quiet since 2026-04-29 versus core Inngest's daily activity ([LICENSE](https://raw.githubusercontent.com/inngest/inngest/main/LICENSE.md), [API](https://api.github.com/repos/inngest/agent-kit)).
**Verdict:** adopting it means running a second durable-execution runtime to reproduce pause/resume semantics LangGraph's own checkpointer + `interrupt()` already give us, with still zero UI. Exclude.

## 9. Svelte ecosystem
`@ai-sdk/svelte` is genuinely Svelte-5-native (runes, `svelte:^5.31.0` peer dep) and released in lockstep with the React package, but its only interrupt-like primitive, `addToolOutput`, is a single-tool-call confirm gate, not a resumable-graph concept — and its HITL cookbook is React/Next.js-only ([npm](https://registry.npmjs.org/@ai-sdk/svelte/latest), [cookbook](https://ai-sdk.dev/v5/cookbook/next/human-in-the-loop)). shadcn-svelte has no official AI/HITL component set; community ports (an `ai-elements` port, `shadcn-svelte-extras`) are generic chat UI with **zero interrupt concept** ([shadcn-svelte.com](https://shadcn-svelte.com), [shadcn-svelte-extras](https://github.com/ieedan/shadcn-svelte-extras)). A LangGraph-Server Svelte frontend exists (`synergyai-nl/svelte-langgraph`, 13★) but a repo-wide search found zero occurrences of "interrupt" in its code ([repo](https://github.com/synergyai-nl/svelte-langgraph)). **Best-evidenced path found:** `@langchain/langgraph-sdk`'s `./stream` export — 2,557 lines, zero React imports, with first-class typed `Interrupt`/`Command`-resume modeling (namespacing for multiple pending interrupts, response normalization) and a **pluggable transport** that doesn't require the LangGraph Server REST API ([langgraphjs `libs/sdk/src/stream/`](https://github.com/langchain-ai/langgraphjs)). MIT, 2.46M weekly downloads ([npm](https://registry.npmjs.org/@langchain/langgraph-sdk/latest)). No official `./svelte` binding ships, despite an optional `svelte` peer-dep entry.
**Verdict:** nothing production-ready and Svelte-native exists off the shelf; the `langgraph-sdk` stream controller is the strongest *engine* to wrap, not a drop-in UI.

## 10. Other notable OSS found
- **Microsoft Magentic-UI / MagenticLite** — AutoGen-based human-centered web agent with inline "action guards" approval UX; MIT, 10.1k★, active ([repo](https://github.com/microsoft/Magentic-UI)). No formal JSON approval schema found; UX is inline-in-session, not a cross-run inbox.
- **Mastra** — TS agent framework with native workflow suspend/resume and a dev Playground for resuming; Apache-2.0 core (`ee/` proprietary), 27.2k★, very active ([HITL docs](https://mastra.ai/docs/workflows/human-in-the-loop), [LICENSE](https://github.com/mastra-ai/mastra/blob/main/LICENSE.md)). Framework primitive + local dev tool, not a distributable inbox.
- **Hermes WebUI** — MIT, 17.4k★, very new and active, but its "approval card" is a single-session tool-consent prompt tightly coupled to one backend (Hermes Agent) — weakest architectural match to an "inbox" despite the biggest star count here ([repo](https://github.com/nesquena/hermes-webui)).
- **Compozy** — self-hosted Go "OS for AI agents" with approvals as a first-class object; MIT, 2.6k★, but its own README flags the current line as beta with recent breaking-version churn ([repo](https://github.com/compozy/compozy)).
- Checked and excluded for insufficient adoption/staleness/no-UI: CrewAI (Enterprise-only or CopilotKit-dependent, [docs](https://docs.crewai.com/en/enterprise/guides/human-in-the-loop)), LlamaIndex's HITL demo (74★, stale since 2024, [repo](https://github.com/run-llama/human_in_the_loop_workflow_demo)), Temporal (patterns, no UI, [blog](https://temporal.io/blog/human-in-the-loop-approvals)), Open WebUI (feature requested, not shipped, [issue](https://github.com/open-webui/open-webui/issues/26073)), and a Laravel/AGPLv3 project (`escapeboy/agent-fleet-o`) whose framing is the closest literal match to "inbox" but sits at 59 stars, below this report's credibility bar.

## (a) Ranked shortlist — most credible adoption candidates for us

**1. `@langchain/langgraph-sdk`'s framework-agnostic stream controller, wrapped in Svelte 5 runes.** Integration surface: moderate — write a custom `Transport` against our existing FastAPI SSE endpoint (pluggable, not hard-wired to LangGraph Server), then a thin reactive wrapper. Schema translation: **near-zero** — its `Interrupt`/`Command`-resume model descends from the same LangGraph primitives our deepagents middleware already speaks. Stack mismatch: low — plain TypeScript, zero React dependency at this layer. Real cost is UI-only: we'd still hand-build every component.

**2. AG-UI protocol, adopted at the wire level only (ignore CopilotKit's React runtime).** Integration surface: moderate-high — implement a backend translation layer from our middleware's `HITLRequest`/`decisions` into AG-UI's `Interrupt`/`resume[]` envelope, plus a Svelte client against `@ag-ui/core`'s zod-typed events. Schema translation: real work — two distinct vocabularies. Stack mismatch: low at the protocol layer, but adopting AG-UI only pays off if we want interop with the wider agent ecosystem beyond our own Slack/Teams bridges — a bigger structural bet than this task calls for.

**3. `agent-chat-ui`, mined as a logic reference only — never run its code.** Integration surface: none (port the decision-building logic from `use-interrupted-actions.tsx`, don't embed the app). Schema translation: zero — it's the only project that speaks our *exact* native schema. Stack mismatch: total — 100% rewrite to Svelte, independently implement the missing `respond` decision type, and don't trust its interrupt-matching verbatim given open bugs specifically about deep-agents interrupts failing to resume.

## (b) Does anything beat a native Svelte inbox?
No. Every option above still requires hand-writing 100% of the Svelte UI, and the two most "standards-credible" options each cost us something we don't need: agent-chat-ui demands the LangGraph Platform/Server API surface we deliberately don't run, and AG-UI demands a schema-translation layer to buy cross-framework interop we have no current use for. Given we already have the exact native schema, a working SSE substrate, and Slack/Teams bridges, the net-new surface for a native inbox is small — two endpoints (list pending interrupts, post decisions) plus a handful of Svelte components (list, action-request card, decision controls, an edit/diff view, a generic-JSON fallback) — with **zero new dependencies, zero license review, zero schema translation**. The one genuinely useful output of this research is a **component taxonomy to steal**: assistant-ui's Approval Card / Permission Grant / Reviewable Diff split, and agent-chat-ui's decision-type-driven conditional rendering — copied as design patterns, not code.

## (c) Could not verify
- Whether HumanLayer's public `hld`/`hlyr`/`humanlayer-wui` code is the actual current CodeLayer app source or coexisting legacy in the same repo.
- Exact month `portia-sdk-python` and its PyPI project were taken down (bounded to Oct 2025–May 2026 by release/launch dates); Portia's SDK license text (MIT reported only by secondary sources); whether its (also-dead) cloud dashboard ever exposed a resolve-clarification UI.
- Whether Permit.io's Enterprise on-prem tier extends to self-hosting the Elements approval UI itself, or only the PDP.
- Whether AG-UI has any foundation-governance move in progress beyond the CopilotKit-run working group (only a negative finding was obtained).
- Compozy's and FleetQ's precise approval JSON schemas (docs 404'd / not published).
- assistant-ui issue #1899's resolution text (approve/reject not reaching a Python backend; closed, but resolution unconfirmed).

---

# §2 — Why LangChain stepped back from the OSS Agent Inbox (lead's distillation of two raw evidence dumps)

Evidence gathered by two sub-agents (GitHub archaeology via `gh api`; official/community
statements sweep). **No explicit deprecation statement exists anywhere** — every finding is
circumstantial but the direction is consistent.

## Timeline

| Date | Event | Source |
|---|---|---|
| 2025-01-14 | Harrison Chase blog "Introducing ambient agents" launches Agent Inbox — "modeled after some combination of an email inbox and a customer support ticketing system" | langchain.com/blog/introducing-ambient-agents |
| 2025-03-10 | agent-chat-ui PR #41 embeds agent-inbox as a component inside it (lineage of the later successor surface) | agent-chat-ui#41 |
| 2025-04-22/23 | Last dense feature burst on agent-inbox (bracesproul + starmorph); last substantive bugfix 2025-05-03 | repo commits |
| 2025-08-09 | `deep-agents-ui` created — official companion UI for the new deepagents framework, ships a real `ToolApprovalInterrupt.tsx` | github.com/langchain-ai/deep-agents-ui |
| ~May 2025 | Chase in Sequoia interview: "I use the agent inbox all the time… a pretty cool… glimpse of what's next" — calls it a **prototype**; still endorsing | inferencebysequoia.substack.com (date has a conflicting 2026 republish stamp on sequoiacap.com — unresolved) |
| 2025-05-03 → 2025-12-31 | **8-month total commit gap** (zero commits of any kind) | repo commits |
| 2025-09-15/17 | langchain PR #32962 (new `HumanInTheLoopMiddleware`) carries the TODO "work w/ applied AI team to ensure compat w/ agent inbox long term" — PR closed unmerged ("too breaking"); the merged fast-follow #32996 **drops the compat TODO** | github.com/langchain-ai/langchain/pull/32962, /32996 |
| 2025-10-06 | Issue #84: "We are planning to use it for production. Do you have any plans to add support for authentication?" — **zero replies in 10+ months** | agent-inbox#84 |
| 2025-10-22 | LangChain/LangGraph **1.0 GA**: `HumanInTheLoopMiddleware` becomes first-class with the new decision schema (approve/edit/reject/respond) | langchain.com/blog/langchain-langgraph-1dot0 |
| 2025-11-14 | agent-chat-ui migrates its embedded interrupt UI to the NEW `HITLRequest` schema and **removes legacy support** (PR #194) | agent-chat-ui#194 |
| 2025-12-02/04 | LangSmith Agent Builder public beta — no "inbox" language yet | langchain.com blog |
| 2026-01-12 | Community PR #90 (full backend `AgentInboxMiddleware` bridge) — **zero maintainer engagement ever**, still open | agent-inbox#90 |
| 2026-01-22 | PR #91 self-merged: `normalizeInterrupt()` frontend shim for the new schema — **inbound-only and partial** (`action_requests[0]` only, no `allow_ignore` map; resume path still posts legacy `HumanResponse[]`), undocumented in README | agent-inbox#91 |
| 2026-02-25 | `agent-inbox-langgraph-example` archived; same day `open-agent-platform` archived **with explicit successor statement: "We recommend using Agent Builder on LangSmith instead"** — the only explicit "use the paid thing" statement found, on a sibling repo | both repos' archive banners |
| 2026-03-19 | **LangSmith Fleet launch** — ships a commercial feature literally named "Agent Inbox": "review, approve, or reject actions… from one central place." No reference to the OSS repo; no "v2" language | langchain.com/blog/introducing-langsmith-fleet, langchain.com/langsmith/fleet |
| 2026-03-31 | Last human code change on agent-inbox: reactive fix for an assistant-ui dependency major bump (AI-assisted maintenance commit) | commit cce59a8 |
| 2026-06-28 | **`deep-agents-ui` archived** ~10 months after creation — the official deepagents companion UI, `ToolApprovalInterrupt.tsx` and all | repo banner |
| 2026-07-27 | `executive-ai-assistant` (the flagship ambient-email reference) archived | repo banner |
| 2026-08 | Dependabot-only; toolchain major upgrades explicitly deferred "before a dedicated migration effort occurs" (PR #174); the current official HITL docs **never mention agent-inbox**; deepagents docs name **no UI** for `interrupt_on` | repo, docs.langchain.com |

## Best-supported explanation, ranked by evidence strength
(Final ordering per the synthesizer agent, which independently re-verified every load-bearing
claim via direct GitHub API/doc fetches — the evidence below is double-verified.)

1. **Schema fork + abandoned follow-through** (strongest — direct evidence): HITL investment
   moved into `langchain` core middleware at 1.0 GA (2025-10-22); the one written
   compatibility commitment ("ensure compat w/ agent inbox long term", Sept 2025) died with
   its unmerged PR; the community's backend bridge (PR #90) has zero maintainer engagement in
   7+ months; the merged shim (PR #91) is half-functional and undocumented; the production
   auth question (#84) is 10 months unanswered. Reads as plain deprioritization — nobody is
   assigned to the repo.
2. **Commercial consolidation into LangSmith** (strong on the product side; *causation*
   inferred): the inbox concept re-emerged, name and all, as a **paid, metered** LangSmith
   Fleet feature (2026-03-19); the sibling `open-agent-platform` repo was archived with an
   explicit "use Agent Builder on LangSmith instead" — the pattern demonstrated once, the
   causal link to agent-inbox never stated.
3. **Companion-app lifecycle** (moderate — comparative): LangChain treats single-purpose
   companion UIs as disposable — `agent-inbox-langgraph-example`, `llmanager`,
   `executive-ai-assistant`, `open-agent-platform`, and even **`deep-agents-ui`** (the
   official deepagents UI with a real `ToolApprovalInterrupt.tsx`, archived 2026-06-28 after
   ~10 months) — while consolidating interrupt rendering into whichever chat UI is currently
   blessed (`agent-chat-ui`).

Nobody at LangChain has said any of this out loud; issue #84's silence is the loudest signal.

## LangChain's current officially-documented path (verified against live docs)

There is **no named replacement app**. The docs teach three routes: (a) **build your own
approval card** — `docs.langchain.com/oss/python/langchain/frontend/human-in-the-loop` gives
full `useStream()` examples for React/Vue/**Svelte**/Angular covering all four decisions
including `respond`, and names no app; (b) **Agent Chat UI** as the general `create_agent`
frontend (`docs.langchain.com/oss/python/langchain/ui` names only it) — though it never
implemented `respond`; (c) **pay for LangSmith Fleet's Inbox**. LangSmith annotation queues
are post-hoc labeling, not approval gating; Studio's interrupt support is static breakpoints,
which the docs themselves say are "not recommended for human-in-the-loop workflows." I.e. the
vendor's own free-tier answer for our situation IS "build the approval UI yourself" — in
Svelte if you like.

---

# §3 — What teams actually use to monitor agents in production (verbatim agent report)

[Two senses deliberately separated.]

## Sense 1 — HITL approval surfaces (human approves before the action executes)

### The hard numbers

- **LangChain's annual practitioner survey** (fielded Nov 18–Dec 2, 2025; n=1,340; published 2026 across [langchain.com/stateofaiagents](https://www.langchain.com/stateofaiagents) and [langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)): *"most teams allow either read-only tool permissions or require human approval for more significant actions, such as writing or deleting"*; *"very few respondents allow their agent to read, write, and delete freely."* Enterprises with 2,000+ employees skew hardest toward read-only; companies under 100 employees lean on tracing/observability over restrictive gates. The same report lineage puts observability adoption at 89% vs. eval adoption at 52%, and production adoption at 57%.
- **Zapier's own commissioned survey**, 500+ enterprise leaders: *"human-in-the-loop remains the most common approach (38%) to AI agent management heading into 2026,"* defined as "building approval gates directly into AI workflows." [zapier.com/blog/ai-agents-survey](https://zapier.com/blog/ai-agents-survey/)
- **Anthropic Economic Index** (Jan 2026): "augmented" (human-in-the-loop-ish) conversation share rose to 52%, "automated" fell to 45% in Nov 2025 data; 77% of enterprise **API** usage is automation-flavored; task success drops from 60% (sub-hour tasks) to 45% (5+ hour tasks). Adjacent evidence, not a direct approval-rate stat. [anthropic.com/research/anthropic-economic-index-january-2026-report](https://www.anthropic.com/research/anthropic-economic-index-january-2026-report)
- A widely-repeated "Gartner says 85% of enterprises will require human oversight of AI-generated external comms by 2026" **could not be traced to any Gartner document** — unverified.

### Named production patterns, by channel

**(a) Slack button approvals — the best-evidenced pattern.** Salesforce + AWS built a Kubernetes self-remediation agent where "safe remediation actions" go through Slack-based HITL approval, with a *multi-layer* approval chain for sensitive operations — ~150 engineer-hours/month saved ([ZenML LLMOps database](https://www.zenml.io/llmops-database/ai-powered-self-remediation-loop-for-large-scale-kubernetes-operations)). **HumanLayer** popularized the pattern (`@hl.require_approval()` → Slack/email) but by mid-2026 repositioned to a coding-agent SDLC product — a signal the standalone approval-inbox-as-a-service wedge didn't become the company's main business, even as the pattern remains widely cited.
**(b) Email-reply approvals** — well-documented as a *pattern* (thread approval through `Message-ID`/`In-Reply-To`), but how-to guides only; no named company at scale. Weakest-evidenced channel.
**(c) Custom dashboards / internal-tool builders.** Retool ships HITL pause tasks as a first-class primitive ("auditable, permissionable," role-gated) ([retool.com blog](https://retool.com/blog/how-agents-in-retool-solves-hard-parts-of-agent-development)) — vendor description, no independent customer-metric case study found.
**(d) Existing ticketing (Jira/ServiceNow/Zendesk).** Supported integration pattern; thinnest named-company evidence of the six.
**(e) Purpose-built inbox UIs.** LangChain's OSS Agent Inbox (outside LangSmith); **gotoHuman** (SaaS, PayFacto named customer).
**(f) IDE/terminal-level.** Claude Code's permission system (deny→ask→allow rules, per-tool-call) — the clearest *synchronous, local* approval example; all others are async/remote.

### By risk level
Outbound comms and infra/ops remediation dominate the documented Slack/inbox examples. Payments/finance more often uses **configurable autonomy boundaries** (Ramp's "autonomy slider": LLM judgment + deterministic dollar/vendor/category rules) rather than per-action approval. Code deploy overwhelmingly reuses the **existing PR review process** (Cognition/Devin: standard human review before merge, plus tooling to make review cheaper). No comparably well-evidenced named example found for legal-specific approval gates.

## Sense 2 — observability/monitoring platforms

| Tool | License / self-host | Maintenance signal | What it's for |
|---|---|---|---|
| **LangSmith** | Proprietary. Cloud, hybrid, or Enterprise self-host (paid) | Active, LangChain-backed | Tracing + evals + annotation queues |
| **Langfuse** | OSS MIT core; open-core EE add-ons | Very active — ~20.5k★ | The standard self-host OSS choice |
| **Arize Phoenix** | Elastic License 2.0 (free self-host); evals/client/otel sub-packages Apache-2.0 | Active, ~10.7k★, OTel-native | Tracing + strong RAG eval |
| **Helicone** | Apache-2.0, self-hostable | **Maintenance mode** — acquired by Mintlify 2026-03-03; fixes only | Proxy gateway + cost/latency |
| **W&B Weave** | SDK Apache-2.0; platform closed | Active (CoreWeave acquisition 2025) | Tracing/eval on W&B console |
| **Braintrust** | Proprietary | Active | Traces → eval/regression cases |
| **AgentOps** | SDK MIT; web app Elastic 2.0 | Active, YC-backed | Session replay/debugging |
| **OTel GenAI conventions** | Apache-2.0, CNCF | "Development" stability (pre-1.0); own repo since v1.42.0 (2026-06-12) | The emerging neutral substrate |

### Do any of these ship an approval/HITL inbox?

**No — checked directly.** LangSmith annotation queues attach feedback to runs *after* they ran ([docs](https://docs.langchain.com/langsmith/annotation-queues)); Langfuse annotation queues are "a manual evaluation method… for domain experts to add scores and comments to traces," and Langfuse's own docs say verbatim that *"if you need approval workflows beyond the built-in annotation queues... you can connect that custom tooling to Langfuse"* ([docs](https://langfuse.com/docs/evaluation/evaluation-methods/annotation-queues)). No pre-execution/blocking approval feature ships in any of the seven platforms. The gate lives one layer down: in the agent framework (`interrupt()`) or bespoke application code.

## Verdict

**Observability** is commoditizing around a few OSS/source-available options with OTel GenAI becoming (not yet arrived as) the neutral substrate. **Approval** shows no platform convergence: it is overwhelmingly custom code. The best-evidenced dominant pattern is **Slack-button approval wired directly into agent code**, supported by the Salesforce/AWS case study, Slack's own developer docs ("any action with real-world output… should require explicit human confirmation"), and both surveys landing in the same 38–~50% zone for approval-gated write/delete actions. Evidence strength for the headline: moderate-to-good. Evidence for finer claims (which channel wins per risk tier): weak. Purpose-built inbox products are real but show no more traction than "engineer wires a Slack webhook into the tool-call layer."

## Could-not-verify (production practice)

- Exact relationship between langchain.com's two survey report pages (same n=1,340 survey, unclear edition boundary; 51% vs 57% production-adoption figures unreconciled).
- The "Gartner 85%" claim — likely content-farm fabrication.
- Secondary "2026 statistics" listicle numbers (78% HITL for Tier-2+, 88% pilots fail, 31% ISO 42001) — untraceable to primary studies; excluded.
- No metrics-bearing case study for email-reply approval, ticketing-routed approval, or a payments/legal-specific deployment.
- HumanLayer/gotoHuman customer logos genuine but no usage-metric case studies.
