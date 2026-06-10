# CLAUDE.md — LQ.AI Fork

Fork of [LegalQuants/lq-ai](https://github.com/LegalQuants/lq-ai) (Apache-2.0), baseline `f91149a` (post-v0.4.0). See `UPSTREAM.md`.

## The goal (why we forked)

Upstream organises the UX around tools (Skills, Playbooks, Tabular Review — 11 flat tabs). We organise it
around an in-house lawyer's **unit of work**, inside configurable **practice areas** (Commercial, Disputes,
M&A, Privacy, Employment…). Concretely:

- Each practice area is one **Deep Agent** (LangChain `deepagents`) that picks its own tools, skills,
  playbooks and MCP servers, and fans out subagents when useful. No fixed pipelines.
- Each practice area defines a configurable **unit of work** ("Matter" in Commercial, "Programme — GDPR"
  in Privacy) that loads the area's tools/skills/playbooks/MCPs and accumulates memory.
- **Memory accumulates at 4 levels**: company/client profile → practice area → user → unit of work.
  All four inject as context; the agent reads bulk material on demand.
- UX bar: effortless, like Claude Code. The user states intent; the agent works visibly
  (streamed tool calls, subagent fan-out, honest receipts).

Upstream's three "agentic" executors (playbooks, tabular, autonomous) are linear LangGraph pipelines —
Python walks the graph, the model fills JSON slots, no model-chosen tool call exists anywhere. We replace
the orchestration; we keep the substrate (gateway, brakes, audit, citations, skills format).

## State of the pivot (keep current — stale info here is worse than none)

- Nothing migrated yet. All upstream code is LEGACY: bugfix only — no new features, no refactors,
  unless the task IS the migration.
- ADR-F001..F004 are `accepted` — read them before structural work.

## Architecture rules

- IMPORTANT: new agent code uses `deepagents` (pinned exact version) on langgraph 1.x. Do not extend
  the legacy executors (`api/app/autonomous/`, `api/app/playbooks/executor.py`, `api/app/tabular/`).
- KEEP unchanged: the Inference Gateway as the only egress and only key-holder; the `guarded_tool_call`
  chokepoint pattern (R4 cost cap / R5 halt / R6 grants) for every agent action; the audit contract
  (counts/types/IDs, never raw values); the Citation Engine; the SKILL.md format.
- Every LLM call routes through the gateway. Never add a direct provider call.
- "System proposes, user owns" (ADR-0013 D4) holds for all memory writes at every level.
- Transparency is load-bearing: every prompt, skill, agent instruction and tool grant must be
  readable in the UI or the source.

## Code rules — dependency injection & security

- Inject dependencies; never reach for globals. FastAPI `Depends` at the API edge; constructor
  arguments everywhere else (DB session, gateway client, skill registry, memory backends, agent
  instances). Wire-up happens once in the lifespan/composition root — no import-time I/O, no new
  module-level singletons. Tests substitute fakes through the same seams; don't monkeypatch what
  you can inject. Upstream's `app.state` + dependencies pattern is the exemplar — match it.
- Provider keys exist only inside the gateway — never in `api/`, `web/`, logs, or error messages.
- Authz on every endpoint; cross-user access returns 404, never 403 (no existence leaks).
- SQL is parameterized via SQLAlchemy; string-built SQL never passes review.
- Validate all input at the boundary with Pydantic; reject, don't sanitize.
- Treat retrieved documents, KB chunks, and shared memory as untrusted model input (prompt
  injection) — this is why company- and practice-level memory are read-only to agents.
- Secrets never land in commits, fixtures, receipts, or audit rows (audit carries counts/types/IDs).
- New dependencies are SBOM entries and supply-chain surface — justify each one or don't add it.

## Known blockers (verified in code — sequence the pivot around these)

1. `api/pyproject.toml` pins `langgraph>=0.2.76,<0.3`; `langchain` is absent; no checkpointer or
   BaseStore is used anywhere. deepagents needs langgraph 1.x plus both. The upgrade is its own phase.
2. The gateway's Anthropic adapter is text-only — it never forwards `tools`
   (`gateway/app/providers/anthropic.py`, `_to_anthropic_request`);
   nothing in the codebase sets `tools` or executes a returned tool call. Tool calling through the
   gateway is prerequisite #1.
3. Chat sends single-turn requests — the model never sees prior turns (`api/app/api/chats.py:1370`).
4. The SSE protocol has only start/delta/complete/error frames (`web/src/lib/lq-ai/sse/parser.ts`).
   The Claude-Code-like UX needs tool-call/subagent/plan frame types end-to-end.
5. No client/counterparty entity exists; `organization_profile` is the operator's own voice and is
   injected only when skills are attached (plain chats get zero company context). `practice_area` /
   `unit_of_work` appear nowhere in the schema.
6. `work_product_attributions` assumes one inference per message — breaks under agent fan-out.
7. Kept autonomous memory is write-only today: `load_kept_memory()` has no callers outside its module.

## Memory model (target)

| Level | Today | Fork |
|---|---|---|
| Company / client | `organization_profile` singleton (operator voice only) | + client/counterparty profiles |
| Practice area | — nothing | new: owns agent config, skills, playbooks, MCPs, area memory |
| User | `autonomous_memory` (write-only) | wired into prompts |
| Unit of work | `projects.context_md` | typed per practice area; accumulates from runs |

Implementation: one deepagents `CompositeBackend` — `/memories/{company,practice,user,matter}/` routed to
StoreBackend namespaces keyed `(org_id, …)`; company and practice levels read-only to agents (curated).

## Rules of the game

### Decisions (ADRs)
- Upstream ADRs keep their `0001+` numbers (including any cherry-picked updates); fork ADRs use the
  parallel **F-series** (`docs/adr/F001-title.md`, F002, …) so the two spaces never collide while
  upstream keeps minting numbers. Format: MADR-minimal (Context, Considered Options — 2–4 real ones,
  Decision Outcome, Consequences). Status: proposed / accepted / superseded-by-FNNN. Immutable once
  accepted — supersede, never rewrite.
- Write one when a decision is hard to reverse, crosses module boundaries, diverges from upstream, or
  would surprise a future reader. Draft it in the same PR as the change; the human accepts.
- Check `docs/adr/` before structural changes. Never silently contradict an accepted ADR — supersede it.
- Reference ADR numbers in commit messages and in a one-line comment at the code seam they govern.

### Iteration (no sprints)
- Work from `docs/fork/MILESTONES.md`: outcome-based milestones broken into vertical slices —
  end-to-end, runnable, testable, ≤2–3 days, one PR each. Never slice horizontally.
- Multi-file change: explore → written plan (goals, non-goals, files, linked ADRs, verification) →
  human edits the plan → implement. Diffs describable in one sentence skip the plan.
- Re-plan at milestone boundaries, not on a calendar. Out-of-scope ideas: one line in
  `docs/fork/MILESTONES.md` § Backlog — don't expand the task.

### Definition of done
- Build + lint + typecheck + tests pass and the output is SHOWN, not asserted. New behavior has tests.
- Fresh-context review of the diff against the plan (correctness gaps only).
- ADR drafted if the slice made an architectural call. If you can't verify it, don't ship it.
- When the agent repeats a mistake, the retro action is editing this file (and keeping it short).

### Fork discipline
- Hard fork, upstream FROZEN (ADR-F001): no merges, no cherry-picks, nothing from upstream — and no
  proposals/PRs to upstream — without the maintainer's explicit per-case approval. Upstream is not
  ours; we track it for awareness only. If approval is ever given, log the sync in `UPSTREAM.md`.
- Keep the Apache-2.0 `LICENSE` and `NOTICES.md` intact; extend, never edit upstream entries. The
  OpenWebUI license in `web/LICENSE` (branding clause §4 for >50 users) and the PyMuPDF AGPL
  server-side-only boundary are obligations, not suggestions.

## Commands
- Stack: `docker compose up -d` (8 services; api auto-migrates on boot)
- API tests: `cd api && pytest` · Gateway tests: `cd gateway && pytest` (mypy `--strict` there)
- Lint: `ruff format && ruff check` — run both; CI gates them separately
- Web: `cd web && npm run check && npm run test:frontend`

## Dev-environment hard rules (violations corrupt the dev stack)
- NEVER run host-side `alembic upgrade` against the live dev DB — verify on a throwaway pgvector
  container; apply by rebuilding the workers.
- When a migration lands, rebuild `api` + `arq-worker` + `ingest-worker` together.
- NEVER `docker compose down -v` (wipes volumes). Rebuild single services instead.
- The `web` container serves a pre-built bundle — rebuild it before debugging a UI change.

## Where to look (read on demand — do not preload)
- Fork charter / divergence policy: `docs/adr/F001-fork-charter.md` · sync log: `UPSTREAM.md`
- Milestones and backlog: `docs/fork/MILESTONES.md`
- Upstream's shipped-vs-deferred catalog: `docs/HONEST-STATE.md` — code is canonical over all docs
- Architecture: `docs/architecture.md` · DB schema: `docs/db-schema.md` · ADR index: `docs/adr/`
- deepagents: https://docs.langchain.com/oss/python/deepagents/overview
