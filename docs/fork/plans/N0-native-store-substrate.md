# Plan — F2 Slice N0: wire the native langgraph `Store` + deepagents `CompositeBackend` (accepts ADR-F049)

**Status:** DRAFT for maintainer review/edit (CLAUDE.md § Iteration — explore → written plan → human edits → implement).
**Branch:** `fork/n0-native-store-substrate`. **ADR:** F049 (flips `proposed → accepted` in this slice).
**Deps:** none new. **Migration:** none (langgraph-owned tables via `store.setup()`). **New product code path:** the memory substrate (no new HTTP route).

## Context

E0 + E1 froze the eval instrument (Track-B CUAD floor + Track-A agentic baseline); Phase-E is exited. N0 is the
**first substrate slice**: get the agent onto the native langgraph `Store` + deepagents `CompositeBackend`/
`StoreBackend` memory tier instead of the hand-assembled prompt-injection path. ADR-F049 is accepted here.

Everything below was **verified against our exact pins this session** (deepagents 0.6.8, langgraph 1.2.6,
langgraph-checkpoint-postgres **3.1.0**) by in-container introspection + a driven write/read round-trip — not from
docs (deepagents ships breaking changes on minors; this is the re-verify-at-each-boundary gate).

## Goal / Non-goals

**Goal.** A run's deep agent is built with `store=AsyncPostgresStore` + a per-run `CompositeBackend` that routes
`/memories/{company,practice,user,matter}/` (+ `/conversation_history/`) to `StoreBackend` namespaces keyed via
`rt.context`, with **company/practice read-only at the storage layer**. The agent's builtin `write_file`/`read_file`/
`ls`/`edit_file` now persist to a matter-scoped, **thread-independent** Store — proven by a deterministic test.
Nothing that exists today regresses (skills still resolve; matter tools/wiki/roster unchanged).

**Non-goals (explicit — later slices).**
- **No semantic index** (filter-only; `store.setup()` runs without an `IndexConfig`, so no pgvector column). Slice C.
- **No `MemoryMiddleware` tier-digest injection** — the hand-assembled prompt blocks (`composition.py`) stay. **N1.**
- **No `SummarizationMiddleware` / conversation offload** — the `/conversation_history/` route is *installed but
  unwritten* at N0; what fills it is **N2**.
- **No `search_matter_conversations` tool / no semantic recall** — **N3.**
- **No doctrine change** telling the agent to jot cross-thread notes to `/memories/matter/` — that belongs with N1's
  memory injection. N0 ships the *substrate*, not new agent *behaviour*.
- **No reconciliation** between the new `/memories/matter/` Store surface and the lawyer-owned SQL matter wiki
  (`project.context_md`, ADR-F042). They are deliberately separate at N0 (the Store is agent scratch/working memory;
  the wiki stays the human-owned tier). N1 decides how/whether they converge.

## ⚠ Gate re-framing (the one finding that changes the slice's DoD — please confirm)

The HANDOFF said the N0 gate is *"A5 must light up (cross-thread recall 0/10 → rises)."* **Investigation
(2026-06-28) shows that over-promises and the slice's own docs disagree with each other:** the eval-first plan says
A5 is "frozen expected-fail **until N2/N3**" (line 54), the fixture docstring says "until N0/N3" (line 171), and the
N0 gate says "A5 **substrate** lights up" (line 74) — the word *substrate* is load-bearing and was dropped in the
HANDOFF restatement.

**Why A5's *rate* cannot rise at N0 (structural, not tuning):** A5 plants a deliberately **non-matter** aside
("working from our Manchester office today — nothing to file") in thread 1 and asks for it in thread 2. The only way
thread 2 could recall it at N0 is if the thread-1 agent *spontaneously* `write_file('/memories/matter/…')`'d a casual
aside — and **nothing** (prompt, doctrine, middleware) tells it to; the one cross-run memory doctrine
(`update_matter_memory`) explicitly says *"not … this turn's chat"* and is in the fixture's `fixture_invalid_if_fired`
guard. Automatic conversation persistence is **N2** (`SummarizationMiddleware` → `/conversation_history/`); recall via
search is **N3**.

**Proposed honest N0 gate (recommended):**
> The `/memories/matter/` Store route **persists a written note across threads of the same matter** — proven by a
> **deterministic integration test** (write to `/memories/matter/<k>` under a thread-1 runtime context, read it back
> under a *fresh thread-2 context of the same matter*; a *different* matter sees nothing — namespace isolation).
> **Company/practice routes reject agent writes** (read-only, test-proven). **Nothing green regresses** — full api
> suite green; **skills still resolve**; the live Track-A matrix holds (A1 ≈8/10, A7 inline, A8 10/10, A5
> honest-abstention 10/10). **A5's cross-thread *recall rate* is tracked as a finding (ADR-F015), NOT gated — it is
> expected to stay ~0/10 until N3.**

Plus a **3-line doc alignment**: make the "until" boundary consistent across `RETRIEVAL-MEMORY-eval-first.md:54`,
`track_a_fixtures.py:171`, `HANDOFF.md` (→ "substrate at N0; recall rises at N3").

*If you'd rather N0 also chase A5's rate (add a doctrine nudge + tighten the leak-guard), say so — but that blurs N0
into N1/N3 and I'd advise against it.*

## Decisions (forced by the code; flag any you'd change)

1. **No `org_id` exists (single-tenant; CLAUDE.md blocker #5).** The ADR's `(org_id, …)` namespace can't bind.
   Substitute the **existing isolation key**: namespaces are
   - company → `("company",)` (operator-global singleton, read-only)
   - practice → `("practice", practice_area_id)` (read-only; route installed only when an area is bound)
   - user → `("user", user_id)` (writable)
   - matter → `("matter", project_id)` (writable; route installed only when a matter is bound)
   - conversation → `("conversation", thread_id)` (installed when a matter/thread is bound; unwritten until N2)

   `project_id`/`user_id`/`thread_id` are UUIDs (pass the `^[A-Za-z0-9\-_.@+:~]+$` component validator). Cross-user
   isolation holds because a run can only ever resolve **its own** owner-checked `project_id`
   (`composition.py` loads the project `WHERE Project.owner_id == run.user_id`), so no run can name another user's namespace.
2. **Read-only company/practice via a storage-level wrapper, not just permissions.** Subagent `permissions`
   *replace* the parent's (verified), so a `FilesystemPermission(deny)` rule would not survive into a subagent. The
   durable backstop is a thin **`ReadOnlyStoreBackend`** wrapper (delegates reads; returns a read-only *error string*
   — never raises — on write/edit/upload, mirroring `RegistrySkillBackend`'s no-raise discipline). This is exactly
   the "storage-level read-only wrapper as backstop" ADR-F049 prescribed.
3. **`context_schema` is mandatory.** Add a small frozen dataclass `AgentRuntimeContext(owner_id, project_id,
   practice_area_id, thread_id)`; pass `context_schema=AgentRuntimeContext` to `create_deep_agent` **and**
   `context=AgentRuntimeContext(...)` at the `astream_events` invoke. Without both, `rt.context` is empty and every
   namespace callable breaks — this is the single most load-bearing wiring detail.
4. **The Store mirrors the checkpointer exactly** (`app/agents/checkpointer.py` is the template): a new
   `app/agents/store.py` with module-global `_store`/`_store_pool`, `init_agent_store()`/`close_agent_store()`/
   `get_agent_store()`, its **own autocommit psycopg pool** (autocommit is mandatory — base migration uses
   `CREATE INDEX CONCURRENTLY`), `await store.setup()` once at init, **degrade-not-crash** on failure. Reuse
   `checkpointer._psycopg_dsn`. Library-owned tables, **not alembic** (no migration; no alembic collision — proven).
5. **Init in BOTH composition roots.** Runs execute in the **arq worker**, not the api. Wire `init_agent_store()` in
   `main.py` lifespan (`:103`, close `:127`) **and** `arq_setup.py` on_startup (`:187`, close `:239`) — symmetric with
   the checkpointer. Missing the worker = the Store is `None` exactly where runs need it.
6. **Compose the skills backend INTO the CompositeBackend, don't replace it** (the #1 regression risk). Per-run:
   `CompositeBackend(default=wiring.backend or StateBackend(), routes={...memory routes...})`. `/skills` (and
   `/skills/subagents/<name>`) fall through to `default` = the existing `RegistrySkillBackend`, so skill reads are
   untouched; scratch-write behaviour is unchanged from today. Pass `store=get_agent_store()` to `create_deep_agent`
   too (deepagents requires `store=` when a backend uses the store).
7. **Degraded-mode parity.** If the Store is `None` (init failed) or no relevant id is bound, install only the routes
   that resolve; a plain chat with no matter/area gets `{company, user}` (and `default`); the agent still runs (the
   memory tier is additive — nothing reads it yet outside the agent's own filesystem tools).

## Files

**NEW**
- `api/app/agents/store.py` — the `AsyncPostgresStore` DI module (mirrors `checkpointer.py`).
- `api/app/agents/memory_backend.py` — `AgentRuntimeContext` dataclass, the namespace callables, `ReadOnlyStoreBackend`
  wrapper, and `build_memory_backend(*, skills_backend, store, binding/ids) -> BackendProtocol` (the per-run
  CompositeBackend factory). *(Name TBD — could fold into `composition.py`; a new module keeps it testable + small.)*
- `api/tests/agents/test_agent_store.py` — store init/setup idempotency + the cross-thread/cross-matter/read-only
  integration test (the **real N0 gate**, CI-runnable via `InMemoryStore` for logic + a test-DB for `setup()`).
- `api/tests/agents/test_memory_backend.py` — namespace-callable shapes, route map per binding (matter/area
  present/absent), `ReadOnlyStoreBackend` rejects writes, **skills still resolve through the composite**.

**EDIT (additive)**
- `api/app/main.py` (+`init_agent_store`/`close_agent_store` in lifespan + closer tuple).
- `api/app/workers/arq_setup.py` (+ the same in worker on_startup/on_shutdown).
- `api/app/agents/composition.py` — build the `CompositeBackend` + the `AgentRuntimeContext` payload from the binding;
  thread `store=` + `context=` into the `execute_agent_run` call (`:568-590`); add a `store_provider` default param
  mirroring `checkpointer_provider` (`:283`) so tests inject `InMemoryStore` through the same seam.
- `api/app/agents/runner.py` — `execute_agent_run` accepts `store=` + a `context` payload; put `store` (+
  `context_schema`) into `agent_kwargs` (`:596-606`) and `context=` into `stream_kwargs` (`:317-331`).
- `api/app/agents/factory.py` — `build_deep_agent` forwards `store=` + `context_schema=` (already `**kwargs`-friendly;
  confirm `context_schema` passes through to `create_deep_agent`).
- `docs/adr/F049-…md` (`proposed → accepted`), `RETRIEVAL-MEMORY-eval-first.md` (N0 ✅ + the "until N3" fix),
  `track_a_fixtures.py:171` (docstring "until" fix), `HANDOFF.md`, `MILESTONES.md`, memory.

## Verification / DoD (ADR-F005 gate)

1. **CI (free, no live model):** `test_agent_store` + `test_memory_backend` green in the dev image — the cross-thread
   persistence + cross-matter isolation + read-only-company/practice + skills-still-resolve assertions. **Full api
   suite green, counts quoted; ruff (repo-root) + mypy `app` clean.** E0/E1 tests still green.
2. **Live on the dev stack:** rebuild api + arq together; a real DeepSeek run on the Atlas matter completes; confirm
   `store`/`store_migrations` tables created (introspect), a run's `write_file('/memories/matter/…')` persists +
   reads back in a second thread of the matter; **re-run the Track-A matrix** — A1/A7/A8/A5-abstention hold, A5
   recall recorded as a finding (expected ~0). Evidence in the PR.
3. **Fresh-context adversarial review (ultracode dims × verify) incl. the mandatory security + simplification pass.**
   Primary risks: (a) **cross-user/cross-matter leak** via a mis-keyed namespace — assert isolation in code + test;
   (b) **agent writing to read-only company/practice** — the storage wrapper is the backstop, test it incl. a
   subagent path; (c) skills-resolution regression; (d) no secrets/raw values in audit/logs (the Store holds agent
   working notes — never logged; namespaces are IDs only). Blockers/should-fixes fixed or deferred on record.
4. **HANDOFF + MILESTONES + plan + ADR-F049 status + memory updated.** Merge under the ADR-F005 gate
   (`gh pr … --repo sarturko-maker/lq-ai-fork`).

## Recommended order
`store.py` (+ both init sites, prove tables created) → `memory_backend.py` (`AgentRuntimeContext` + namespaces +
`ReadOnlyStoreBackend` + `build_memory_backend`) → `test_memory_backend` + `test_agent_store` green (the gate) →
thread `store=`/`context=`/`context_schema=` through composition/runner/factory → full suite + ruff + mypy →
live dev-stack run + Track-A re-run → docs/ADR/HANDOFF/memory → adversarial review → PR + merge.

## Maintainer rulings (2026-06-28, AskUserQuestion)
- **Gate = honest substrate gate** (recommended option chosen): deterministic integration test + nothing-regresses +
  skills-resolve; A5 recall is a tracked **finding** (ADR-F015), expected ~0 until N3; align the 3 inconsistent docs.
- **`/conversation_history/` route = install-but-unwritten** at N0 (keyed by `thread_id`); N2 adds the middleware
  that fills it.
- **`memory_backend.py` = new module** (agent's call: small + testable).
