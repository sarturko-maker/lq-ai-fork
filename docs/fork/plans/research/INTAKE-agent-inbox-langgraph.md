# INTAKE research 1/4 — Agent Inbox & LangGraph HITL (Sonnet sub-agent, 2026-08-16)

> Commissioned for the INTAKE milestone plan (`docs/fork/plans/INTAKE-INBOX-plan.md`, task #536).
> Web research against primary sources; verbatim from the research agent, unedited.

## 1. Agent Inbox: what it is, stack, config, maintenance

**github.com/langchain-ai/agent-inbox** — "An inbox UX for interacting with human-in-the-loop agents." Next.js + TypeScript + Tailwind, Yarn, MIT license ([repo](https://github.com/langchain-ai/agent-inbox), [README](https://github.com/langchain-ai/agent-inbox/blob/main/README.md)). Confirmed via GitHub API: `archived: false`, created 2024-11-04, last push 2026-08-12, 1071 stars, 26 open issues. The three most recent commits (Aug 5/10/12, 2026) are all dependency bumps/chores, not features.

**Config, entirely client-side:** a LangSmith API key entered in a Settings dialog, plus one "inbox" per LangGraph deployment: **Deployment URL** (required), **Assistant/Graph ID** (required), optional Name. The README states these values "are stored in your browser's local storage, and are only used to connect & authenticate requests to the LangGraph deployment" ([README](https://github.com/langchain-ai/agent-inbox/blob/main/README.md)). `src/lib/client.ts` confirms it's a thin wrapper over `@langchain/langgraph-sdk`'s `Client`, sending the key as an `x-api-key` header on every browser→deployment request — no backend proxy, no server-side secret storage. Hosted instance at `dev.agentinbox.ai`. A "Open in Studio" button links out to LangSmith Studio, showing coupling to the LangSmith product family.

**Backend surface required (confirmed by reading the actual hooks, not docs):**
- `client.threads.search({offset, limit, status, metadata})` → `POST /threads/search` — list interrupted threads ([use-inboxes.tsx](https://github.com/langchain-ai/agent-inbox/blob/main/src/components/agent-inbox/hooks/use-inboxes.tsx))
- `client.threads.getState(thread_id)` → `GET /threads/{thread_id}/state` — fetch pending interrupt value(s) ([ThreadContext.tsx](https://github.com/langchain-ai/agent-inbox/blob/main/src/components/agent-inbox/contexts/ThreadContext.tsx))
- `client.runs.create(threadId, graphId, {command:{resume: response}})` → `POST /threads/{thread_id}/runs` — resume (non-streaming)
- `client.runs.stream(threadId, graphId, {command:{resume: response}, streamMode:"events"})` → `POST /threads/{thread_id}/runs/stream` — resume (streaming)
- `client.threads.updateState(threadId, {values: null, asNode: END})` → `POST /threads/{thread_id}/state` — used for "ignore"/"mark resolved"

`POST /threads/search`'s own docs cite exactly this use case ("filtered by thread state values... build highly specific UIs — such as agent inboxes") ([forum result](https://forum.langchain.com/t/langgraph-server-api-threads-search-return-total-number-of-threads/962)). LangChain also publishes an open, evolving **Agent Protocol** spec for this Runs/Threads/Store surface, explicitly noting "LangGraph Platform implements a superset of this protocol" ([agent-protocol](https://github.com/langchain-ai/agent-protocol)) — i.e. the real surface is somewhat wider than the minimal spec.

## 2. The interrupt schema — canonical definitions

Verbatim from `langgraph-prebuilt` (`langgraph/prebuilt/interrupt.py`, package v1.1.0, released 2026-05-12 — [pypi](https://pypi.org/project/langgraph-prebuilt/)):

```python
class HumanInterruptConfig(TypedDict):
    allow_ignore: bool
    allow_respond: bool
    allow_edit: bool
    allow_accept: bool

class ActionRequest(TypedDict):
    action: str
    args: dict

class HumanInterrupt(TypedDict):
    action_request: ActionRequest
    config: HumanInterruptConfig
    description: str | None

class HumanResponse(TypedDict):
    type: Literal["accept", "ignore", "response", "edit"]
    args: None | str | ActionRequest
```

**All three (`HumanInterruptConfig`, `ActionRequest`, `HumanInterrupt`) carry a `@deprecated` decorator**: *"has been moved to `langchain.agents.interrupt`. Please update your import to `from langchain.agents.interrupt import ...`"* — this is a **LangGraph-v1.0-era relocation**, same field names, new module. `HumanResponse` in the same file is not decorated (asymmetry noted, unexplained — see Could-not-verify).

Agent Inbox's own TypeScript copy (`src/components/agent-inbox/types.ts`) matches field-for-field:

```typescript
export interface HumanInterrupt {
  action_request: ActionRequest;
  config: HumanInterruptConfig;
  description?: string;
}
export type HumanResponse = {
  type: "accept" | "ignore" | "response" | "edit";
  args: null | string | ActionRequest;
};
export type HumanResponseWithEdits = HumanResponse &
  ({ acceptAllowed?: false; editsMade?: never } | { acceptAllowed?: true; editsMade?: boolean });
```

**Resume semantics** (confirmed against both reference agents, §4): `accept` → execute tool with original args; `edit` → execute with `args` from the edited `ActionRequest`; `response` → free text fed back as a message so the model loop continues *without* executing the tool; `ignore` → **not a LangGraph builtin** — an application convention. Both reference repos implement it as: synthesize an "Ignore" tool/assistant message, then `Command(goto=END)`, ending the run.

**Multiple pending interrupts:** the Agent-Inbox generation does **not** batch. Reference graphs call `interrupt([request])[0]` inside a `for tool_call in tool_calls:` loop — one `interrupt()` call per tool call. Because a resumed node re-executes from the top and replays already-answered `interrupt()` calls from an index-ordered cache, this yields several sequential single-interrupt pause/resume rounds rather than one multi-interrupt payload. Agent Inbox's own README states it "will always respond with a list of `HumanResponse` objects, although at this time only a single object will be returned" — consistent with this one-at-a-time pattern.

## 3. `interrupt()` on langgraph 1.x, self-hosted in-process

Requires a **checkpointer** (durable in prod) + a stable `thread_id` in `config.configurable` ([Interrupts docs](https://docs.langchain.com/oss/python/langgraph/interrupts)). Plain `.invoke()` still surfaces pauses via `result["__interrupt__"]`; the newer `stream_events(..., version="v3")` surface exposes `stream.interrupts` as a tuple of `Interrupt(value=..., id=...)`.

`Command(resume=...)` has two forms: **scalar** (`Command(resume=<value>)`, index-matched within a node) and **map** (`Command(resume={interrupt_id: value, ...})`, for genuinely parallel interrupts, keyed by each `Interrupt.id`).

**Open bug relevant to multi-interrupt resume**: [langgraph#6626](https://github.com/langchain-ai/langgraph/issues/6626) — parallel `interrupt()` calls inside the same `ToolNode`/namespace can generate **identical IDs** because the ID is `xxh3_128_hexdigest(ns.encode())`, hashing only the checkpoint namespace, not a per-call index; the resume-map dict then collapses multiple entries into one and only one of several parallel tool calls can be resumed. Status: **open, unresolved**, no maintainer fix merged as of this research. This affects true concurrent interrupts specifically — the sequential for-loop pattern used by the reference agents (§2) is not concurrent and is not documented as affected.

Static `interrupt_before`/`interrupt_after` still exist but current docs explicitly discourage them for HITL: *"Static interrupts are not recommended for human-in-the-loop workflows. Use the `interrupt()` function instead."* Node code before an `interrupt()` call re-runs on every resume — an idempotency requirement.

## 4. Reference email-agent implementations

**agents-from-scratch** ([repo](https://github.com/langchain-ai/agents-from-scratch)) — active, not archived, pushed 2026-08-11, 2064 stars. `RouterSchema.classification: Literal["ignore","respond","notify"]` via structured output. `write_email` and `schedule_meeting` are interrupt-wrapped with all four flags `True`; a synthetic `"Question"` action has only `allow_ignore`/`allow_respond` `True`. `notify` calls `interrupt()` with a no-tool, description-only `HumanInterrupt` (`allow_accept`/`allow_edit` `False`). Memory: LangGraph Store namespaces `("email_assistant","triage_preferences")`, `("email_assistant","cal_preferences")`, `("email_assistant","response_preferences")`; every human edit/ignore/response triggers `update_memory(store, namespace, messages)`, an LLM call with structured output (`UserPreferences`) that rewrites a `"user_preferences"` doc at that namespace.

**executive-ai-assistant** ([repo](https://github.com/langchain-ai/executive-ai-assistant)) — **archived and read-only as of 2026-07-27** (confirmed via GitHub API, `archived: true`), 2207 stars, 41 commits total. `RespondTo.response: Literal["no","email","notify","question"]`. `send_message`/`notify` interrupts allow only ignore+respond; `send_email_draft`/`send_cal_invite` allow all four. `notify()` builds `ActionRequest(action="Notify", args={})`. Preferences live in a static `eaia/main/config.yaml`, not a Store — no Store/memory code found in `graph.py`.

## Endpoints Agent Inbox requires of its backend

`POST /threads/search` (status+metadata filter) · `GET /threads/{id}/state` · `POST /threads/{id}/runs` · `POST /threads/{id}/runs/stream` · `POST /threads/{id}/state` (updateState, for ignore/resolve). Five endpoints, all part of the LangGraph Platform "Threads/Runs" REST surface, which the Agent Protocol spec describes as still evolving.

## Feasibility verdicts

**(a) Point OSS Agent Inbox at a custom FastAPI shim:** *Narrow-but-workable for the transport, broken for the payload.* The five endpoints are small and stable enough to shim (assuming a Postgres checkpointer backs `GET/POST state`). But Agent Inbox only parses the **legacy** `HumanInterrupt`/`HumanResponse` shape — it cannot render or resume the `HITLRequest`/`Decision` shape that `deepagents.interrupt_on` actually emits (see §5) without the still-unmerged [PR #90](https://github.com/langchain-ai/agent-inbox/pull/90). You'd have to bypass deepagents' own HITL middleware and hand-roll legacy `interrupt()` calls to be compatible.

**(b) Run OSS Agent Inbox against a local `langgraph dev` server:** *Works as documented, wrong topology.* [agent-inbox-langgraph-example](https://github.com/langchain-ai/agent-inbox-langgraph-example) shows this exactly (no LangSmith key needed against `http://127.0.0.1:2024`) — but it requires the separate `langgraph dev`/CLI server process and its own persistence, not an in-process embed inside an existing FastAPI app; and that example repo is itself archived (2026-02-25).

**(c) Rebuild the inbox surface natively in Svelte:** *Recommended.* You already control both the emitting side (choose any interrupt payload shape — legacy, new `HITLRequest`/decisions, or fully custom) and the consuming UI, and already have interrupt-based HITL plumbing and an extensible SSE protocol. This avoids both the schema mismatch in (a) and the deployment-topology mismatch in (b); only the interrupt *schema* (§2, or the newer one in §5) is worth adopting, not the app.

## Maintenance-state assessment

`agent-inbox`: not archived, pushed within days of this research, but recent history is dependency-bump-only, 26 open issues, and its own bridge to the current LangChain HITL middleware ([PR #90](https://github.com/langchain-ai/agent-inbox/pull/90), opened 2026-01-12) has sat open **over seven months**. Its companion getting-started example repo is archived. Its closest sibling reference app, `agent-chat-ui`, is far more active (3064 stars, 88 open issues, same-week commits — [API check](https://github.com/langchain-ai/agent-chat-ui)) and is chat-first rather than inbox-first. Read together: agent-inbox reads as **maintenance mode**, not the team's current investment for HITL UX — LangChain's newest HITL docs ([frontend guide](https://docs.langchain.com/oss/python/langchain/frontend/human-in-the-loop)) teach building your own approval-card UI against `useStream()`, and cite neither Agent Inbox nor Agent Chat UI as the reference.

## 5. Newest developments (2025–2026): a schema fork

`langgraph.prebuilt.interrupt` → deprecated, moved to `langchain.agents.interrupt` (same field names). Separately, **`create_agent`'s `HumanInTheLoopMiddleware`** (`langchain.agents.middleware`) is the new first-class HITL surface: `interrupt_on: dict[str, bool | InterruptOnConfig]`, `InterruptOnConfig = {"allowed_decisions": ["approve","edit","reject","respond"], "description": str|callable, "when": callable}` (`when` needs `langchain>=1.3.3`). Internally it builds **one** `HITLRequest` TypedDict (`{"action_requests":[...], "review_configs":[...]}`), calls `interrupt()` **once per turn** for *all* tool calls needing approval, and reads back `decisions = interrupt(...)["decisions"]` — a list of `{"type": "approve"|"edit"|"reject"|"respond", ...}`. These types live in `langchain.agents.middleware.types`/`human_in_the_loop.py`, **not** imported from the legacy module — a parallel, wire-incompatible schema, decision names included (`approve`/`reject` vs. old `accept`/`ignore`).

**deepagents wraps this exact middleware**: `create_deep_agent(..., interrupt_on={...})` requires a checkpointer, subagents may override `interrupt_on` per-agent, and `FilesystemPermission(operations=[...], paths=[...], mode="interrupt")` — **gated at `deepagents>=0.6.8`, your pinned version** — merges into the same `decisions` flow ([deepagents HITL docs](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)). Batching sidesteps the #6626 identical-ID bug for this path specifically, since it is one `interrupt()` call, not several parallel ones.

No standalone "LangSmith-hosted inbox" product was found; LangSmith Deployment markets HITL approvals as a managed-runtime feature, and Studio can inspect/resume interrupts in its trace UI, but neither is a distinct inbox SKU beyond the OSS app + `dev.agentinbox.ai`.

## Email-assistant graph pattern, distilled

1. Inbound email → normalized `email_input` (id, thread, from/to, body) as graph input.
2. **Triage node**: structured-output LLM call against a small `Literal` schema, prompted with static background + triage rules + the email.
3. Route on classification: ignore → end/mark-read (no human); notify → `interrupt()` with a no-tool, description-only request (respond/ignore only); respond → enter the response agent.
4. **Response agent**: tool-calling LLM loop with domain tools (draft/send email, schedule/send calendar invite, ask-human "Question").
5. Before any sensitive tool executes, `interrupt()` with the proposed action + a per-tool `HumanInterruptConfig`.
6. Human: accept / edit / free-text response / ignore.
7. accept/edit → tool executes; loop continues or ends.
8. response/question → text appended as a message, LLM loop continues (redraft) instead of executing.
9. Every edit/ignore/response feeds a memory-update LLM call that rewrites a per-category preferences doc in a Store namespace (agents-from-scratch) or a static config file (EAIA).
10. Thread ends; checkpointer + Store carry state and preferences into the next run.

## Could not verify

- Whether pre-1.x LangGraph used a different (non-colliding) interrupt-ID scheme than the one implicated in #6626 — no changelog entry found either way.
- The exact current `HumanResponse` definition at the new `langchain.agents.interrupt` location — only inferred to exist from the deprecation message text; direct fetch 404'd on guessed paths.
- Whether merging PR #90 would make Agent Inbox support **both** schemas or replace one — only its description was reviewed, not the diff.
- Whether `dev.agentinbox.ai` is a pure client-side SPA with zero server-side data pass-through — inferred from source (browser→deployment direct calls) but no explicit privacy statement located.
- Any pricing/ToS gate on the hosted Agent Inbox instance or on LangSmith API keys for non-local use.
- Whether the sequential per-tool-call `interrupt()` loop pattern (§2/§4) is formally guaranteed collision-free, or just incidentally unaffected by #6626 by virtue of being non-concurrent.
