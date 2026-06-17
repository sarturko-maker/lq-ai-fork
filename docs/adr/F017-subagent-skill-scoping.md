# F017 — subagents: on-demand delegation + idiomatic per-subagent skill sources over a multi-source backend

- Status: accepted
- Date: 2026-06-17
- Deciders: maintainer (Arturs) — ruled in UX-B-4 after deepagents-docs/source research: *fit naturally
  within deepagents (it is maintained by LangChain — do what the framework intends); a deep agent does not
  always need subagents (read a single NDA and apply a skill directly; fan out for a complex multi-document
  RFQ); the goal is a Claude-Code-like agentic experience, for legal.*
- Extends: [[F010]] (per-area Deep Agent — config vocabulary, the gateway-bypass guard), [[F016]] (skills
  activation via the registry-backed backend), [[F015]] (scenario-based model qualification), [[F002]]
  (practice-areas-and-agent-home)
- Supersedes: none

## Context

Through UX-B-3 the cockpit Deep Agent runs the area's **bound skills** live via a read-only
`RegistrySkillBackend` exposing the area's subset at the source `/skills` (ADR-F016). Areas carry a
declarative `agent_config` whose `subagents` slot has been validated but **never populated**
(`agent_config={}` everywhere). UX-B-4 turns on the first live subagent. Two questions had to be settled, and
an initial sketch ("a subagent inherits the area's skill set") was **revised after reading the deepagents
0.6.8 docs + source**, which showed the framework already has a first-class, idiomatic answer:

1. **When does a subagent run?** deepagents exposes a `task` tool (`middleware/subagents.py`); the parent
   model decides to delegate. A declarative subagent only makes delegation **available** — it is not a
   pipeline stage. This matches the product goal: a single NDA is read and answered directly; a complex RFQ
   across dozens of documents is fanned out to subagents. Delegation is **on-demand**, model-chosen.
2. **How does a subagent get skills?** A custom subagent gets a `SkillsMiddleware` **only if it declares its
   own `skills`** (`graph.py:628-630`), over **source paths** — and *"custom subagents don't inherit parent
   skills; skill state is fully isolated in both directions"* (docs). Only the auto general-purpose subagent
   inherits the parent's `skills` (`graph.py:704-705`). The parent `backend` is shared as the **file-storage
   substrate** (`graph.py:621`), but skill **discovery is per-source, per-subagent**. Our config models a
   subagent's skills as **names**, so a stored `skills:["nda-review"]` would reach deepagents as
   `sources=["nda-review"]` → `ls("nda-review")` → `file_not_found` → a **silent zero-skills load**.

## Considered options

1. **Idiomatic per-subagent virtual sources (one multi-source backend).** Generalize `RegistrySkillBackend`
   to serve N virtual sources; the area agent points at `/skills`, each skill-bearing subagent points at its
   **own** source exposing its (⊆ area) subset. Mirrors deepagents' isolated-per-subagent design exactly.
2. **Subagent inherits the area set** (the initial sketch). Rewrite a subagent's skill names → the area
   source `/skills` so it sees the parent's full subset. Simplest, but uses custom subagents *against* their
   isolated-skills design (only the general-purpose subagent is meant to inherit) and gives the subagent a
   wider surface than it needs.
3. **Skill-less subagents.** Forbid subagent skills; a subagent inherits only the guarded matter tools.
   Tightest, but leaves the documented `skills` slot permanently dead and under-uses the framework.

## Decision outcome

**Option 1.** `RegistrySkillBackend` becomes **multi-source**: `sources: Mapping[source_path, Mapping[skill_
name, SKILL.md]]`. `ls`/`read`/`download` resolve by which source root a path sits under (the existing
exact-parts checks disambiguate nested roots, so `ls("/skills")` never reveals a subagent source). One shared
instance serves the area source **and** every subagent source — exactly deepagents' shared-backend model.

The composition seam builds the wiring (`build_area_skill_wiring`): the area source `/skills` (the bound
subset, unchanged from UX-B-3) plus, for each skill-bearing subagent, a source `"/skills/subagents/<name>"`
exposing that subagent's resolved subset; it rewrites each subagent spec's `skills` (names) → `[its source
path]`, or drops the key when nothing resolves, and passes the main agent `skills=[/skills]` + the one
backend. Subagent skill names are validated **⊆ the area's bound set** — rejected at PATCH (config time),
dropped-not-fatal at render (the UX-B-3 drift posture, so a removed skill never breaks a run).

Delegation stays **on-demand**: the seeded `document-researcher` subagent's `description` tells the parent
*when* to delegate (many documents / several independent questions), and the parent's `task` tool fires only
when it judges the matter complex enough. The default cockpit experience is unchanged for simple matters.

This satisfies every rule the maintainer set:

- **Fits deepagents' grain** — per-subagent source paths with isolated skill state is the framework's
  *documented* mechanism, not a fork-specific shim; the backend is the documented `BackendProtocol` extension
  point; one shared backend serves all sources as deepagents expects.
- **Subset per agent, down to the subagent** (extends ADR-F016) — a subagent sees only its own source's
  skills in its prompt; it never sees the catalogue, and its surface is **tighter** than the area's (good for
  the M3 over-exploration finding, UX-B-3).
- **One library, no duplication, zero-copy** — every source is an allow-list view over the resident
  `SkillRegistry`; nothing is copied per area or per subagent, nothing persists into a checkpoint.
- **No gateway bypass** — subagents omit `model` (inherit the gateway-bound parent instance); the ADR-F010
  guard re-asserts it at the `build_deep_agent` seam. The seeded spec is `model`-free.
- **Least privilege over the unguarded builtins** (ADR-F016 carries over) — every source is read-only, serves
  only allow-listed names, reaches no host FS and no matter data.

### Backend is shared: a note on read-access vs discovery

deepagents shares the one backend across parent + subagents, so the builtin `read_file` could in principle
fetch any source path the backend serves. **Discovery** is isolated (a subagent's prompt lists only its own
source's skills), which is what prevents the "too many skills confuse the model" failure. **Read-access** is
not partitioned by agent — but every source is read-only and contains only skills the **area already bound**,
so the worst a prompt-injected subagent does through a guessed path is read an area-bound skill (the same
bound already accepted for the parent, ADR-F016). Partitioning read-access per agent is not a deepagents
capability and is not pursued.

### Forward path (noted, NOT built here)

The multi-source backend is the general mechanism for **playbooks** and **MCPs** too (ADR-F016 forward path):
each becomes another source/adapter the area or a subagent references by name. The **redlining MCP** rides the
MCP-plumbing slice (gateway-mediated, credentials never in `api/`). Per-subagent **tool** subsets (`tools`
stays omitted → inherit the guarded matter tools) and parallel multi-subagent fan-out for very large matters
are later refinements; the `task` tool already supports them.

## Consequences

- **Good:** subagents land the idiomatic way; per-subagent skill isolation with a tight surface; one source
  of truth; no duplication; the latent silent-zero-skills bug is structurally impossible (a subagent gets a
  real source or no `skills` key); the pattern generalizes to playbooks/MCPs.
- **Cost / risk:** `RegistrySkillBackend` grows from single- to multi-source (still one isolated module beside
  `factory.py`, the "absorb deepagents churn" seam). Delegation adds tool surface to a tier-4-weak model that
  UX-B-3 already showed over-explores — re-qualified via the UX-B-4 scenario report (ADR-F015); a no-delegate
  or no-converge run is a recorded finding, not a blocker, and the deterministic ancestry test proves the
  mechanism regardless.
- **Security:** skill content stays curated-but-untrusted (prompt injection) and read-only; company/practice
  memory remains read-only to agents; no secrets in `agent_config`, the backend, reports, or audit
  (counts/types/IDs only).
