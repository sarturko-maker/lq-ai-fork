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

- F0-S1 done: langgraph 1.x + `deepagents==0.6.8` substrate landed; first model-driven tool loop
  proven live through the gateway (MiniMax-M3). Upstream code remains LEGACY: bugfix only — no new
  features, no refactors, unless the task IS the migration.
- ADR-F001..F005 are `accepted` — read them before structural work. Current slice: see
  `docs/fork/HANDOFF.md`.

## Architecture rules

- IMPORTANT: new agent code uses `deepagents` (pinned exact version) on langgraph 1.x. Do not extend
  the legacy executors (`api/app/autonomous/`, `api/app/playbooks/executor.py`, `api/app/tabular/`).
- KEEP unchanged: the Inference Gateway as the only egress and only key-holder; the `guarded_tool_call`
  chokepoint pattern (R4 cost cap / R5 halt / R6 grants) for every agent action; the audit contract
  (counts/types/IDs, never raw values); the Citation Engine; the SKILL.md format.
- Every LLM call routes through the gateway. Never add a direct provider call.
- "System proposes, user owns" (ADR-0013 D4) holds for the company/practice (read-only to agents) and
  user/autonomous memory tiers. The **unit-of-work (matter/programme) tier is auto-write-then-correct**
  (ADR-F042): the agent maintains it automatically; the human owns it *after* the write (correct/undo/delete,
  human-pinned corrections win). Pinning is an authenticated human action, never an agent tool.
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

### Memory tiers (canonical names) — F2

These are the agreed names for every memory tier. **Convention: when discussing memory with the
maintainer, always refer to a tier by its canonical name followed by a one-sentence plain-language
description** (e.g. *"Practice Knowledge — the firm's approved, anonymised house know-how shared across
the practice group"*).

| Name | Level | One-sentence description | Source of truth |
|---|---|---|---|
| **House Brief** | Firm | who the firm is and who it acts for; same for everyone, read-only to the agent. | `organization_profile` |
| **Practice Playbook** | Practice area | the area's job description (doctrine, skills, helper roster, min model), human-curated, read-only to the agent. | `practice_areas` + bound skills |
| **Practice Knowledge** ⭐ | Practice area | approved, anonymised house know-how built up across matters; agent proposes, human approves, shared with the practice group. | *future* — Store-backed + a safety harness (`docs/fork/plans/PRACTICE-KNOWLEDGE-prize.md`); NOT built |
| **Lawyer Preferences** | User | one lawyer's private notes on how they like to work; never shared. | `autonomous_memory` (write-only today) |
| **Matter File** | Matter | the running one-pager of a deal; agent keeps current, lawyer corrects/undoes. | `projects.context_md` (ADR-F042) |
| **Matter Corrections** | Matter | lawyer-pinned authoritative facts; human-only writes; pins win. | `matter_memory_entries` (ADR-F042) |
| **Matter Facts** | Matter | structured, time-stamped record of what's true and when; agent-maintained. | `matter_memory_entries` (ADR-F042/F043) |
| **Matter Roster** | Matter | who's who + sides; agent infers, lawyer confirms. | `matter_participants` (ADR-F048) |
| **Conversation Memory** | Conversation | what's been said in this chat + a running summary so long chats keep the thread. | checkpointer + Store `/conversation_history/` |

The four read-only DATA tiers (House Brief, Matter File, Matter Corrections, Matter Roster) are injected
into the system prompt by `TierMemoryMiddleware` (F2 N1, ADR-F049), not baked into the static prompt;
SQL stays their source of truth. The Store/`MatterMemoryEntry` split is deliberate (N1 did NOT converge
the Matter File onto the Store — that is its own future ADR'd slice).

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

### Session handoff (context-compaction discipline)
- Sessions compact near 50% context. `docs/fork/HANDOFF.md` is the live pickup document:
  overwritten at the END of every slice (and before any planned compaction), committed with the
  slice's PR. Sections: State (branch / PR / stack), Done, Next slice, Pick up exactly here, Gotchas.
- A fresh or compacted session reads HANDOFF.md FIRST, then this file, then the ADRs it names.
- A slice is not finished until HANDOFF.md says where the next one starts.

### Definition of done
- Build + lint + typecheck + tests pass and the output is SHOWN, not asserted. New behavior has tests.
- Fresh-context review of the diff against the plan (correctness gaps only).
- **Security + simplification pass on EVERY slice — no exceptions, even "unrelated"/design/doc work.**
  Folded into the slice's adversarial review: pause and check for leaked secrets/credentials, authz
  holes, injection, unsafe sinks, and anything that shouldn't be in the diff (e.g. a stray `.env*`
  backup); and for dead code / duplication to delete. This is universal now, not just for
  gateway/auth/audit/crypto paths. (Added 2026-06-14 after a `.env.bak-f0-s4` backup — which the
  `.gitignore` didn't match — shipped the live MiniMax/JWT/gateway/Postgres secrets to the public repo.)
- ADR drafted if the slice made an architectural call. If you can't verify it, don't ship it.
- When the agent repeats a mistake, the retro action is editing this file (and keeping it short).

### Merge policy (agent-merged — ADR-F005)
- This project is fully agentically coded; the maintainer does not review code. The agent
  squash-merges a PR when the FULL gate passes: (1) CI green; (2) containerized suites for every
  touched service with counts quoted in the PR; (3) fresh-context adversarial review of the diff,
  which ALWAYS includes a security pass (leaked secrets/credentials, authz, injection, unsafe sinks,
  stray files that shouldn't ship) + a simplification pass — blockers/should-fixes fixed or explicitly
  deferred on record; (4) live verification on the dev stack when behavior changes (provider tests /
  UI screenshot), evidence in the PR; (5) HANDOFF.md updated. Security-sensitive paths (gateway, auth,
  audit, crypto, anonymization) get an additional, deeper security-focused review pass.

### Fork discipline
- Hard fork, upstream FROZEN (ADR-F001): no merges, no cherry-picks, nothing from upstream — and no
  proposals/PRs to upstream — without the maintainer's explicit per-case approval. Upstream is not
  ours; we track it for awareness only. If approval is ever given, log the sync in `UPSTREAM.md`.
- Keep the Apache-2.0 `LICENSE` and `NOTICES.md` intact; extend, never edit upstream entries. The
  PyMuPDF AGPL server-side-only boundary is an obligation, not a suggestion. The OpenWebUI §4
  branding obligation ended in F0-S6 (husk removed, ADR-F006); builds from pre-S6 commits remain
  bound — see NOTICES.md § Web client provenance.
- The checkout carries an `upstream` remote, so a bare `gh pr create` can target the FROZEN
  upstream (nearly happened once). `gh repo set-default sarturko-maker/lq-ai-fork` is set; still
  pass `--repo sarturko-maker/lq-ai-fork` explicitly on every `gh pr`/`gh issue` call.

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
- After ANY `docker compose build` / `up --build`, run `docker image prune -f` (dangling only).
  Each rebuild orphans the prior ~6 GB image as a dangling `<none>` layer; on the Crostini/btrfs
  driver these pile up and filled the disk (2026-06: 65 GB reclaimable, disk hit 100%). Prune
  dangling at the source — do NOT `prune -a` (keeps tagged stack images) and do NOT touch the build
  cache or volumes. `scripts/docker-prune.sh` is the fuller manual sweep (dangling + stopped
  containers + leftover `lq_ai_test_*` DBs). No cron — this is rebuild-time discipline.

## Where to look (read on demand — do not preload)
- **Current state + where to pick up: `docs/fork/HANDOFF.md` — read first in every session**
- Fork charter / divergence policy: `docs/adr/F001-fork-charter.md` · sync log: `UPSTREAM.md`
- North star (resident agents, forward deployment — check structural slices against its
  keep-possible invariants): `docs/fork/NORTH-STAR.md`
- Milestones and backlog: `docs/fork/MILESTONES.md`
- Upstream's shipped-vs-deferred catalog: `docs/HONEST-STATE.md` — code is canonical over all docs
- Architecture: `docs/architecture.md` · DB schema: `docs/db-schema.md` · ADR index: `docs/adr/`
- deepagents: https://docs.langchain.com/oss/python/deepagents/overview
