# Capability sources — a bird's-eye view

**Status:** map / discovery (2026-07-06). Written at the maintainer's request during the STORE-3
walk: *"Before we do anything, we need a bird's-eye view of existing structure. LQ.AI upstream has
functionality where people can create skills and playbooks and upload knowledge. Now it should be
possible to give those created skills, playbooks and knowledge to the agents in a controlled manner."*

This is **not a plan** — it is the ground truth of what exists, what reaches a Deep Agent today, and
where the gap is. Code is canonical; every claim carries a `file:line`. Directions at the end are
candidates for the maintainer to choose between, not committed work.

---

## The one-sentence finding

There are **two parallel universes** in the codebase, and they barely touch:

1. **The Deep Agent capability pipeline** (fork, live) — Store → Library → Area binding →
   composition → guarded tool loop. Its sources are the *shipped* filesystem catalog and the
   tool-group registry.
2. **The legacy authoring surfaces** (inherited from upstream) — create/fork a skill, build a
   playbook, upload a knowledge base. These still work in the UI and write real DB rows, but **almost
   none of what they produce can reach a fork Deep Agent.** They feed the frozen legacy executors.

The maintainer's item 4 is precisely the request to **merge universe 2 into universe 1**: let
org-authored skills, playbooks, and knowledge flow through the *same* adopt → bind → compose pipeline
the Store already uses — in a controlled, transparent, injection-safe way.

A naming trap sits on top of this (item 3): the thing STORE-1/2 named **"Library"**
(`org_library_entries`) is **the adopted subset of the shipped Store** — it is *not* a home for
org-authored content. So "the Library points to the Store and nothing else can be done" is exactly
right by construction today. F065 D7 anticipated this and left "a future `org` tier" as the seam
(`docs/adr/F065-org-library-adoption-model.md:72-74, 83`).

---

## Universe 1 — what a Deep Agent can carry today

The live pipeline (all fork code):

```
 shipped catalog            org adoption                 area binding              run composition
 ───────────────            ────────────                 ────────────              ───────────────
 filesystem skills/  ─┐
 tool-group registry ─┼──▶  org_library_entries  ──▶  practice_area_skills   ──▶  build_area_inventory
 shipped playbooks   ─┘     (kind∈{skill,           practice_area_tool_groups     (registry ∩ Library
 (5, DB-seeded)             playbook,tool})         practice_area_playbooks         ∩ toggles)  ─┐
                                                                                                  │
                                                                                                  ▼
                                                             area_agent  ◀──  system prompt + tool set
                                                             + guarded_dispatch tool loop (R4/R5/R6)
```

The sources that can actually reach the agent:

| Source | Where it lives | How it reaches the agent | Binding |
|---|---|---|---|
| **Default tools** | `TOOL_GROUP_REGISTRY` (`capabilities.py:116+`) | tool group → `build_deep_agent_tools` (`capabilities.py:309+`); grants stay code (ADR-F062) | `practice_area_tool_groups` ∩ Library ∩ per-matter toggle |
| **Skills** | **filesystem** `skills/` (66 SKILL.md incl. `skills/community/`) loaded into `app.state.skill_registry` (`registry.py:9-10` — filesystem, atomic swap) | injected as the area's skill list; agent reads a SKILL.md via built-in `read_file` (`composition.py:640,812`) | `practice_area_skills` **∩ `registry.names()`** ∩ Library (`capabilities.py:11-12,596-597`) |
| **Playbook *positions*** | 5 DB-seeded playbooks (`playbooks`/`playbook_positions`, migs 0032/0033; `skills/playbooks/{nda,nda-unilateral,msa-saas,msa-commercial-purchase,dpa-gdpr}`) | the **"Practice Playbook" memory tier** — read-only injected *text* of the company's preferred positions (`composition.py:309-355`, `playbook_context.render_practice_playbook`). The agent **reads** positions; it does **not execute** a playbook | `practice_area_playbooks` (0 bound on a fresh org) |
| **Matter files** | documents uploaded *to the matter* | `search_documents` / `read_document` / `get_document_metadata` → `matter_hybrid_search`/rerank (`tools.py:122-174,228`) | implicit (the run's matter) |
| **Memory tiers** | House Brief (`organization_profile`), Matter File/Corrections/Roster | `TierMemoryMiddleware` injects read-only (ADR-F049) | company/matter scoped |

**Key mechanical fact (the crux of item 3/4):** the agent's skill list comes from the **filesystem
registry only**. `build_area_inventory` drift-filters bound skills against `registry.names()`
(`capabilities.py:11-12,596`), and the registry is loaded from the `skills/` directory
(`registry.py:9-10`). So a skill that exists only as a DB row is invisible to the agent even if bound.

---

## Universe 2 — the authoring surfaces (and where they dead-end)

These are real, working, shipped UI + API. What they produce is the problem.

### Skills — you can author one; the agent can't see it

- **Surfaces:** `/lq-ai/skills/new`, `/lq-ai/skills/[id]/edit`, `POST /skills/{name}/fork`
  (`skills.py:752`), full CRUD on `/user-skills` (`user_skills.py:48,442,591,785`), the
  `skill-creator` skill itself. Rows land in the **`user_skills`** table (`models/user_skill.py:47`).
- **The dead-end:** the runtime registry is filesystem-only. `user_skills` is merged **only** into the
  `GET /skills?scope=all` *listing* (user shadow over built-in, `skills.py:226+`) — a display concern.
  **No agent-runtime code reads `user_skills`** (only `skills/schema.py`, the shared frontmatter
  parser, references the model). → **An admin-authored skill never reaches a Deep Agent today.**
- Fresh-org count: `user_skills = 0`.

### Playbooks — you can build one; only its *positions* could ever inject, and only if bound

- **Surfaces:** `/lq-ai/playbooks`, the `/lq-ai/playbooks/easy` builder, full CRUD
  (`playbooks.py:183,260,378`), `playbooks`/`playbook_positions`/`easy_playbook_generations` tables
  (`models/playbook.py:38,102,241`, `created_by` FK — user-authored).
- **The dead-end:** the legacy **playbook executor is frozen** (CLAUDE.md). The fork's only playbook
  touchpoint is the read-only **Practice Playbook tier**, which reuses the *same* `playbook_positions`
  data as injected text (`playbook_context.py:3,59`). So a *bound* user-built playbook's positions
  *could* surface as text — but there is **no adopt/bind flow that puts a user-created playbook into
  the Store/Library**, and nothing runs a playbook as a pipeline for a Deep Agent. In the Store today,
  playbooks show `source=None` and none are recommended/seed-bound (`practice_area_playbooks = 0`).

### Knowledge — you can upload collections; the agent only reads matter files

- **Surfaces:** `/lq-ai/knowledge` ("Curated collections of documents your matters can search
  alongside the prompt. Upload PDFs…", `knowledge/+page.svelte:157`), `knowledge_bases.py` upload
  endpoints (`:238,447,719`), models `knowledge_base`/`document`/`project_knowledge_base` (the last is
  an M2M attach of a KB to a project/matter, `models/project_knowledge_base.py:21-38`).
- **The dead-end:** the Deep Agent's document tools are **matter-file-scoped** — `_search` →
  `matter_hybrid_search` over the matter's own files (`tools.py:228+`). `knowledge_bases` is consumed
  only by **legacy `autonomous/`** (`watch_trigger.py`, `guard.py`). **No Deep Agent tool searches an
  org-level or project-attached knowledge base**, and nothing binds knowledge to a practice
  area/agent. *(Unverified nuance: whether attaching a KB to a matter via `project_knowledge_bases`
  makes those docs visible to `search_documents` — the retriever path I traced is matter-files only;
  worth a 20-minute confirm before any knowledge-binding design.)*
- Fresh-org count: `knowledge_bases = 0`.

---

## The gap, stated plainly (maps to the four STORE-3 findings)

| # | Maintainer finding | Ground truth | Nature |
|---|---|---|---|
| 1 | No org-profile screen; agents need to know who they act for | House Brief backend is complete (`organization_profile.py`, admin `PUT`) but has **no web UI** — this is **ONBOARD gap G2**, already logged. Empty profile ⇒ every agent runs with blank company identity | build a small admin page (no backend) |
| 2 | Split Store skills by category; pull from `github.com/LegalQuants/lq-skills` | `lq_ai.tags` already exist on every SKILL.md (categories are latent in the data). `lq-skills` is public, Apache-2.0, 50 skills, 17+ jurisdictions, same SKILL.md format | (a) group Store by tag = small; (b) remote sync = own milestone (maintainer: not priority) |
| 3 | Library dead-ends to the Store; admin should create skills + playbooks | The named "Library" is *by construction* the adopted subset of the Store (F065). Org authoring exists (Universe 2) but is **orphaned from Deep Agents** | the core architectural gap |
| 4 | Give org-authored skills/playbooks/knowledge to agents, controlled | Requires **merging Universe 2 into Universe 1**. F065 D7 deferred exactly this (ratified §7 no-v1): org-authored skills are a **prompt-injection surface needing its own harness + ADR**. The `org` namespace tier is already reserved (`F065:72-74`) | ADR-gated; the biggest piece |

---

## Candidate directions (for the maintainer to choose — not yet planned)

Ordered smallest-blast-radius first. Each is a separable slice; the maintainer picks scope + order.

- **A. House Brief admin page** (finding 1 / G2). Small, zero-backend. Unblocks the "agents know who
  they act for" problem immediately and independently of everything else. *Strong candidate to do
  first* — it's the cheapest high-value fix and needs no ADR.
- **B. Store categories** (finding 2a). Group the Store page by `lq_ai.tags`. Small, display-only,
  no schema change. The data is already there.
- **C. Org-authored skills → agent** (finding 3/4, skills half). The load-bearing change: make the
  runtime skill set **filesystem ∪ org-authored DB rows**, so an adopted org skill flows through
  `org_library_entries` (new `source='org'`) → binding → composition. **Reopens F065 D7** →
  needs the injection harness + an ADR (org content is untrusted model input per CLAUDE.md; today
  company/practice memory is read-only-to-agents *because* of injection risk). This is where the real
  design work is.
- **D. Org-authored playbooks → agent** (finding 4, playbooks half). Decide what "give a playbook to
  an agent" *means* for a Deep Agent (inject positions as the Practice Playbook tier? expose a
  run-this-playbook tool?) — the legacy executor stays frozen either way. Depends on C's adoption
  plumbing.
- **E. Knowledge → agent** (finding 4, knowledge half). Needs both a **binding** (attach a KB/
  collection to a practice area or matter) *and* a **deep-agent org-KB search tool** — neither exists.
  Confirm the `project_knowledge_bases` retriever question first. Largest surface; likely its own
  milestone with its own retrieval-eval gate (the F2 retrieval doctrine applies).
- **F. Remote `lq-skills` sync** (finding 2b). Maintainer flagged **not priority**. Own milestone;
  supply-chain + provenance concern (adopting external skills = adopting an injection surface at
  scale); belongs after C proves the org-authored path is safe.

**Cross-cutting constraint on C/D/E:** every one of these lets *non-shipped, org-controlled content*
reach an agent prompt. CLAUDE.md treats retrieved/shared content as untrusted (prompt injection); the
curated read-only tiers exist for this reason. So the unifying ADR must answer: *who may author*
(admin only? role-gated?), *what's the approval step* (F065's "agent proposes / human approves"
posture, or admin-authors-directly?), *what harness* validates an org SKILL.md before it can inject,
and *how provenance/transparency* is shown (the Store's `source` badge already has a slot: add `org`).

---

## What NOT to conclude from this map

- The authoring UIs are **not broken** — they work and write valid rows. They're just wired to the
  frozen legacy executors, not the fork's Deep Agents.
- STORE-1/2 are **not wrong** — they correctly built the shipped-catalog adoption pipeline. Universe 2
  was always out of their ratified scope (F065 D7). This map is the input to deciding the *next*
  milestone, which is the org-authored half F065 deliberately left a seam for.

## Cross-references

- `docs/adr/F065-org-library-adoption-model.md` — the Store/Library/Binding model; **D7** reserves the
  `org` tier and defers org-authored content.
- `docs/fork/plans/STORE-org-library.md` — the decided Store model.
- `docs/fork/plans/ONBOARD-admin-experience.md` — G2 (House Brief UI), G4 (Store/Library fusion),
  G5 (skill viewer unlinked); the STORE-3 walk findings append there.
- `CLAUDE.md` — untrusted-input doctrine, read-only curated tiers, transparency rule (the guardrails
  any org-authored path must satisfy).
