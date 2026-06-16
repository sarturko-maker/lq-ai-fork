# F016 — skills activation: a read-only registry-backed virtual backend exposing each area's bound subset

- Status: accepted
- Date: 2026-06-16
- Deciders: maintainer (Arturs) — ruled the architecture in UX-B-3: *one skill library, no duplication
  (a skill added once to LQ.AI is available everywhere and pulled into the relevant agent by name); relevant
  skills land in each area agent by default; users are free to add more; an agent exposed to ALL skills gets
  confused — so each area sees only its subset; skills, playbooks and MCPs are the three capability kinds
  (MCP plumbing, incl. a redlining MCP, comes later).*
- Extends: [[F010]] (per-area Deep Agent — config vocabulary, the gateway-bypass guard), [[F015]]
  (scenario-based model qualification — this slice re-qualifies with skills on), [[F002]]
  (practice-areas-and-agent-home)
- Supersedes: none

## Context

Through UX-B-2 the cockpit Deep Agent ran on a clean **matter-tool** surface (`search_documents` +
`read_document`, both wrapped by the `guarded_dispatch` chokepoint). The next capability is **skills** — the
SKILL.md library (`skills/`, loaded once per process into the in-memory `SkillRegistry`; the
`practice_area_skills` m2m binds skills to areas by name; config-landed since F1-S3 but never live). The
HANDOFF framed activation as "attach `SkillsMiddleware` so bound skills become tools." Reading deepagents
0.6.8 corrected that premise:

- `SkillsMiddleware` adds **no tools**. It `ls`/`download`s a *backend* to discover skills, injects each
  skill's name/description/path into the system prompt (progressive disclosure), and the model reads a
  skill's full instructions on demand via the **builtin `read_file`** tool — which also goes through the
  backend. Our agent already carries the deepagents builtin filesystem tools (`ls`/`read_file`/`glob`/
  `grep`/`write_file`/`edit_file`/`execute`/`task`/`write_todos`) over an empty in-memory `StateBackend()`
  (deepagents default).
- Those builtins are **not** wrapped by `guarded_dispatch` — only the two matter tools are. Extending the
  guard to the full tool universe (+ R4 budgets) is F1's "universe-wrap" (`runner.py` comment), not this
  slice.

So "activate skills" = give the agent a **backend** carrying the area's skills + pass `skills=[sources]`;
the security posture comes from **what that backend exposes to the unguarded builtins**, not from the guard.
A second fact forces a design choice: a `SkillsMiddleware` *source* is a **parent directory** that exposes
**every** skill subdir beneath it — but our binding is **per-skill-name**, and the maintainer's rule is that
an agent must see only its area's subset (the whole library confuses the model).

## Considered options

1. **Registry-backed virtual backend exposing only the bound subset.** A read-only `BackendProtocol` adapter
   over a `SkillRegistry` snapshot + an allow-list of names, serving a virtual `/skills/<name>/SKILL.md` tree.
2. **Per-run seeded `StateBackend`.** deepagents' documented happy path: seed the agent's invoke state with
   the bound skills' SKILL.md text. Reuses deepagents' own backend; but copies skill bodies into **every
   thread checkpoint** (runtime duplication) and threads skill content through the runner's invoke payload.
3. **`FilesystemBackend` rooted at `/skills` + list only bound skills in the prompt.** Least code, real
   curated read-only disk — but the unguarded `read_file` can reach **any** skill under `/skills` (the whole
   built-in library + the community submodule), not the bound subset: the confusion the maintainer warned
   against, plus a wider prompt-injection surface.

## Decision outcome

**Option 1 — `app/agents/skill_backend.py: RegistrySkillBackend`.** Built per run by
`build_area_skill_backend(registry, names)` from the area's `practice_area_skills` names, filtered to the
registry's current set. The composition point (`composition.py`) loads the bound names, renders the area
agent with `bound_skill_names` + `known_skill_names`, builds the backend over the resolved subset, and
threads `skills=[SKILLS_ROOT]` + `backend=` through `execute_agent_run` → `build_deep_agent` →
`create_deep_agent`. When an area binds no resolvable skill, both are omitted and the qualified default graph
(no `SkillsMiddleware`, deepagents' default `StateBackend`) is unchanged.

This is the only option that satisfies every rule the maintainer set:

- **One library, no duplication** — areas reference by name; the backend reads the resident registry. Nothing
  is copied per area, and nothing is persisted into checkpoints (vs option 2).
- **Subset per agent** — the backend exposes only the allow-listed names; the agent never sees the catalogue
  (vs option 3).
- **Least privilege over the unguarded builtins** — `RegistrySkillBackend` is **read-only** (mutations return
  a read-only/permission error), serves **only** the bound names (every other path is `file_not_found`),
  reaches **no host filesystem and no matter data**. So even though `read_file`/`ls` are not yet guarded, the
  worst a prompt-injected model can do through them is read a skill the area already bound. Wrapping the
  builtins in `guarded_dispatch` + R4 stays the F1 universe-wrap, explicitly out of scope here.
- **Drift closes structurally** — a bound name the registry forgot is absent from the backend; it cannot
  surface to the model. The main agent already filtered at render; this slice also validates
  **subagent-referenced** skill names against the registry at **config (PATCH) time**
  (`build_area_subagents(known_skill_names=…)`), so a dangling reference is rejected, never stored.
- **Efficiency** — zero-copy per run (the registry is already in memory; the backend just filters + rebuilds
  SKILL.md text from the record's verbatim frontmatter + body).

Relevant skills are bound **by default** per area (migration `0056`, idempotent, focused — a few skills that
match the area's unit of work, not the catalogue) and users **extend** via the existing admin attach
endpoint. The model still **chooses** which bound skill to apply (progressive disclosure).

The registry snapshot reaches the worker (where runs execute) via a new `skill_registry_provider` injection
seam defaulting to the `app.state.skill_registry` holder — the same holder the arq `on_startup` installs and
the autonomous executor reads; tests inject a fake.

### Forward path (noted, NOT built here)

Skills, **playbooks**, and **MCPs** are the three capability kinds. The `agent_config` already carries
validated, credential-free **by-reference** slots for `playbooks` and `mcp_servers` (F010). They consume the
same "one registry, reference by name, expose the area's subset" shape this ADR establishes: a future slice
adds a playbook/MCP backend or tool adapter the same way. The **redlining MCP** the maintainer wants rides
that MCP-plumbing slice — gateway-mediated, credentials never in `api/` (NORTH-STAR inv 3). Live **subagents**
(which can carry skills) remain UX-B-4.

## Consequences

- **Good:** skills go live with the tightest blast radius available before the F1 guard universe-wrap; one
  source of truth; no per-area or per-run duplication; drift impossible to store or serve; the pattern
  generalizes to playbooks + MCPs.
- **Cost / risk:** `RegistrySkillBackend` implements a slice of the pre-1.0 deepagents `BackendProtocol`
  (`ls`/`read`/`download_files` + read-only mutation stubs) — churn surface, isolated to one module beside
  `factory.py` (the "absorb deepagents churn here" seam). `grep`/`glob` over skills are unsupported
  (progressive disclosure uses `read_file` by path). The expanded tool surface makes MiniMax's tool selection
  harder — re-qualified via the UX-B-3 scenario report (ADR-F015); a shape-miss calibrates, not blocks.
- **Security:** skill content is curated **but untrusted** model input (prompt injection) — it stays
  read-only and registry-sourced; company/practice memory remains read-only to agents. No secrets in the
  backend, reports, or audit (counts/types/IDs only).
