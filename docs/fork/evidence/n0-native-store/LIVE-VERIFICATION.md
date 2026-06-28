# N0 live verification (ADR-F049) — native langgraph Store + CompositeBackend

Dev stack, 2026-06-28, after rebuilding **api + arq-worker** on the N0 code (no migration; `docker image
prune -f` run). DeepSeek `deepseek-v4-flash` via the gateway. IDs/counts only — no secrets, no clause text.

## 1. Store inits on real boot (filter-only, library-managed tables)

- **api boot log:** `INFO:app.agents.store:agent memory store ready (AsyncPostgresStore, filter-only)`
- **dev DB tables:** `store`, `store_migrations` present; **`store_vectors` absent** (no IndexConfig → no
  pgvector at N0). `store_migrations` versions `0 1 2 3` (base only).
- *(The arq worker suppresses app-level INFO on stdout — the pre-existing "checkpointer ready" line is
  absent there too — so its store init is confirmed functionally by §2, which executes IN the worker.)*

## 2. End-to-end through the arq worker (the full live path)

A real run (`POST /api/v1/agents/runs`, matter = "Atlas Test", `max_steps=14`) asked the agent to
`write_file` `/memories/matter/n0_check.md` = `N0 LIVE OK` then `read_file` it back.

- **Run status:** `completed`.
- **Final answer:** *"The file `/memories/matter/n0_check.md` has been created and its exact contents are:
  `N0 LIVE OK` … Confirmed — the file reads back exactly as written."*
- **Store row written** (then deleted as a smoke artifact):
  `prefix = matter.0fdede7d-…` (namespace `("matter", project_id)`), `key = /n0_check.md`
  (the composite stripped the `/memories/matter/` route prefix), `content = N0 LIVE OK`.

This exercises the entire N0 wiring **in the worker process**: `init_agent_store` → `store_provider` →
`build_memory_backend` (real `CompositeBackend`) → `execute_agent_run(store=, context_schema=)` →
`astream_events(context=AgentRuntimeContext(...))` → `rt.context`-keyed StoreBackend namespace → the
builtin `write_file` routed to `store.aput`, then `read_file` round-tripped — with a real model.

## Gate status (maintainer-ruled honest gate)

- Substrate persists + isolates + read-only-tiers + skills-coexist: ✅ (deterministic
  `tests/agents/test_memory_backend.py`, incl. an e2e write through `create_deep_agent`) + ✅ live (above).
- Nothing regresses: ✅ full api suite **2851 passed / 38 skipped / 0 failed**; `tests/agents` 607.
- A5 cross-thread **recall rate**: a tracked finding (ADR-F015), expected ~0 until N3 — NOT gated at N0.
