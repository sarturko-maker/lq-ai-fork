# F008 — Conversation identity: `agent_threads` table + langgraph Postgres checkpointer

Status: accepted (2026-06-11, maintainer)
Date: 2026-06-11

## Context and problem statement

F0-S5 makes agent runs multi-turn: a follow-up message must continue the SAME agent state — prior
messages, tool results, todos, workspace files (ADR-F003's prerequisite; CLAUDE.md known blocker #3
for the legacy chat path, which stays LEGACY). Two coupled decisions:

1. **Where does conversation identity live in our schema?** Today each `agent_runs` row is an
   island; the UI shows a flat run list. A "conversation" = an ordered sequence of runs sharing
   agent state, bound to at most one Matter (ADR-F002: conversations bind to the unit of work).
2. **Where does durable loop state live?** deepagents compiles to a LangGraph graph; LangGraph
   persists per-thread state through a checkpointer keyed by `configurable.thread_id`.
   `langgraph-checkpoint-postgres` has been in `api/pyproject.toml` since F0-S1, unwired, for
   exactly this slice.

## Considered options

1. **`thread_id` column on `agent_runs`, no new entity.** Cheapest migration; conversation list =
   `GROUP BY thread_id` with awkward pagination; the title, Matter binding, and (later, ADR-F003)
   the rolling digest have no home — each would be denormalized onto runs and reconciled in code.
2. **Reuse the legacy `chats` table** (it already has `project_id`, `title`, `summary`). Entangles
   the new substrate with the single-turn path we are replacing (CLAUDE.md: never extend legacy
   executors/surfaces); `chats` rows carry message rows, not agent runs; deleting the legacy path
   later would orphan agent conversations.
3. **New `agent_threads` table; runs FK into it.** One row per conversation: identity, title,
   Matter binding, activity timestamp. The checkpointer thread key IS the table's id. ADR-F003's
   per-conversation summary/digest lands here later; ADR-F002's "conversations bind to (practice
   area, unit of work)" gets a real column to bind on.
4. **No checkpointer — replay prior runs' prompts/answers into the next run's input.** No new
   state store, but reconstructs lossy context (tool results and workspace files don't survive),
   and diverges from the deepagents/langgraph substrate we adopted in F0-S1 to stop hand-rolling.

## Decision outcome

Option 3 for identity + the Postgres checkpointer for state.

- **`agent_threads`** (migration 0050): `id`, `user_id` (FK users CASCADE), `project_id`
  (FK projects SET NULL), `title` (bounded first prompt for now; auto-titling is F1/F2),
  `created_at`, `last_run_at`. `agent_runs.thread_id` → FK `agent_threads` ON DELETE CASCADE,
  NOT NULL after backfilling one thread per existing run (legacy runs become one-run threads).
- **The thread owns the Matter binding.** A follow-up run inherits `thread.project_id`; the run
  row keeps its `project_id` column as the per-run snapshot the composition point already
  re-validates at execution time (F0-S4) — deleting a project SET-NULLs thread and runs alike.
- **One running run per thread**, enforced by a partial unique index
  (`agent_runs(thread_id) WHERE status = 'running'`) — the API maps the integrity error to 409.
- **Follow-ups only when the thread's latest run is `completed`.** An interrupted loop (timeout,
  step cap, failure) can leave the checkpoint mid-tool-call — dangling `tool_calls` with no tool
  results, which OpenAI-compatible providers reject on the next turn. Until the cancel/repair
  pathway lands (carry-over), the API answers 409 `thread_not_continuable`; the UI offers
  "New chat" instead. Likewise **409 `matter_archived`** when the thread's Matter has been
  archived since creation (F0-S5 review): accepting the follow-up would silently degrade the run
  to a blank workspace while the UI still presents the binding — the same execution-time-binding
  rule the new-thread path enforces with its 404.
- **Durable state: `AsyncPostgresSaver`** in the Postgres we already operate, constructed and
  opened at the composition root (lifespan, mirroring `app/db/session.py`'s process-global
  pattern), injected into the run composition through a provider seam; tests substitute
  `InMemorySaver` through the same seam. The checkpointer's tables are created by the library's
  own versioned `setup()` — they are deliberately NOT alembic-managed (the library migrates its
  own schema; alembic owns ours).
- The runner invokes the graph with `configurable.thread_id = agent_threads.id`; capabilities
  (tools, prompt, model envelope) are REBOUND per run from the thread's current binding —
  resume-on-existing with rebound capabilities, per ADR-F004's adopted oscar lesson.

## Consequences

- New API surface: `POST /agents/runs` accepts `thread_id` (404 unowned — no existence leak;
  409 not continuable / already running); `GET /agents/threads` (paginated, newest activity
  first) and `GET /agents/threads/{id}` (thread + runs + steps) drive the conversation UI.
- Checkpoint rows accumulate per turn and are invisible to alembic; thread deletion must call
  `adelete_thread` — no delete surface ships in S5, so a user-cascade delete orphans checkpoint
  rows until the F1 cleanup lands (Backlog line; same family as the arq/orphan-sweep carry-over).
- `cancelled` runs become meaningfully resumable only after a repair pathway exists; R5's
  advisory halt (agents/guard.py) is unchanged by this ADR.
- The legacy `chats` path is untouched; S6/S7 (ADR-F006) replace its UI shell and wire SSE onto
  the thread/run records this ADR creates.
