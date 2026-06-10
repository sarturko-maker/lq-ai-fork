# F003 — Conversation memory: matter-level chat history with compaction, digests, and search

Status: proposed
Date: 2026-06-10

## Context and problem statement

Upstream chat sends single-turn requests — the model never sees prior turns — and each chat is an
island: no summarisation, no cross-chat recall, nothing accumulates at the Matter. The fork needs:
multi-turn conversations that survive growing long; chat history that accumulates **at the unit-of-work
(Matter) level**; past conversations the agent can search when relevant; and a "new chat" button that
is cheap to press without losing continuity. The user must never re-explain the matter to the agent.

## Considered options

1. **One ever-growing thread per Matter.** Rejected: unbounded context, stale 400-message scrolls,
   and compaction pressure concentrated in a single thread.
2. **Raw-history stuffing** — load all matter chats into context each turn. Rejected: token cost,
   context overflow, and recency drowning relevance.
3. **Third-party memory service** (Mem0, Zep/Graphiti, Letta). Rejected for now: each adds a service
   or graph DB to operate and an SBOM surface; they target cross-session fact memory, which our
   4-level memory design already covers with LangGraph's native Store. Revisit only if native
   consolidation proves insufficient (Zep's temporal graph is the strongest candidate then).
4. **Three-layer native design** on the LangChain/deepagents stack we already adopt in F0.

## Decision outcome

Option 4 — three distinct layers, because they have different costs and failure modes:

1. **Within a chat — compaction.** LangChain's `SummarizationMiddleware` (ships in the deepagents
   middleware stack) summarises older turns in place when context nears the limit, keeping recent
   turns verbatim; `SummarizationToolMiddleware` additionally lets the agent compact itself mid-task.
   Summarisation runs on the `budget` model alias.
2. **Across chats in a Matter — rolling digests, not raw history.** Each chat carries an
   incrementally-updated summary (`chats.summary`); a background consolidation job (arq, on chat
   idle) maintains the Matter digest — discussed / decided / open — under the matter memory level
   (`/memories/matter/<id>/`). The digest is what loads into agent context by default, and powers the
   "Where were we?" card shown on Matter open (done / in motion / waiting on you).
3. **Verbatim recall on demand — agent tools, not context stuffing.** `search_chats(matter, query)`
   (Postgres FTS + pgvector hybrid, same machinery as KB retrieval) and `read_chat(chat_id, range)`
   give exact wording when precision matters. Both are tools dispatched through `guarded_tool_call`.
   The same tools serve recall of compacted-away history within the current chat.

Supporting rules:

- **New chat is cheap and encouraged**; continuity lives in matter memory, not thread length. Chats
  are auto-titled and auto-filed (ADR-F002).
- **Privilege and tier floors extend to the chat index.** Chat transcripts inherit the Matter's
  privilege flag and `minimum_inference_tier`; embedding privileged chat content through a cloud
  embedding provider is data leaving the deployment, so the tier-floor gate covers the embedding path
  and the search index, not just inference. FTS-only mode is the fallback when no tier-compliant
  embedding provider exists.
- **Digests are derived data, not memory.** They are mechanical, regenerable summaries and bypass
  curation; the "system proposes, user owns" discipline (ADR-0013 D4) continues to govern *memory*
  (preferences, facts, precedents). Memory proposals surface gently — "I'll remember you prefer X —
  keep / undo" inline, plus a weekly batch review instead of per-item interruptions.

## Consequences

- Schema: `chats.summary` (+ summary watermark), matter digest storage, chat-chunk embedding table;
  a consolidation arq job; two new agent tools registered through the chokepoint.
- Depends on F0 (multi-turn chat, deepagents middleware). Vector chat-search additionally needs an
  embedding provider; FTS works without one.
- Compaction and digest calls add background inference cost — they run on the cheap alias and are
  metered per Matter through the existing cost-tracking seam (R4).
- The single-turn blocker (CLAUDE.md §Known blockers #3) is closed by this design's prerequisite work.
