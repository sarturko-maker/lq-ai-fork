# UX-B-4 — live subagent scenario. Plan.

Milestone **UX-B** (Deep Agents truly work / cockpit perfect), gate **ADR-F015**. Decomposition:
`UX-B-deep-agents-truly-work-decomposition.md` §UX-B-4. Builds on UX-B-3 (skills live via the
registry-backed backend, ADR-F016). MiniMax-M3 is the DI model (tier-4-weak).

## What "exercise a live subagent" is

The whole subagent pipe already exists and is guarded: `composition.py:247` passes `area_spec.subagents`
**live** → `execute_agent_run` → `build_deep_agent`/`create_deep_agent`; the ADR-F010 model-bearing-subagent
guard fires at the seam; `build_area_subagents` validates each declarative spec. What's missing is (a) **any
area actually carrying a subagent** (`agent_config={}` everywhere — deliberately, through UX-B-3), and (b) a
**resolution of the skill name↔source-path mismatch** so a skill-bearing subagent doesn't silently break.

When the parent delegates, deepagents' **`task`** tool (StructuredTool `name="task"`,
`middleware/subagents.py:590`) runs the subagent on the SAME gateway-bound model instance (no `model` key →
no gateway bypass). The runner already records the nesting: `runner.py:_innermost_tool_parent` (F0-S7) sets
each subagent step's **`parent_step_id`** to the enclosing `task` step's settled row id. So the qualification
signal is: a `task` tool_call step exists, and ≥1 later step nests under it via `parent_step_id`.

## Delegation is on-demand, not a pipeline (the Claude-Code-for-legal goal)

A declarative subagent only makes delegation **available** — the parent model invokes `task` **when the work
warrants it**, exactly as Claude Code fans out. A Commercial agent handed a single NDA should just read it
(and apply an NDA skill/playbook) and answer **directly — no subagent**; handed a complex RFQ with dozens of
documents it should **spawn subagents** to investigate in parallel and keep the main thread focused. So the
honest qualification is not "force one delegation" but "delegates *only* when the matter is genuinely
complex." That shapes two things: the subagent is framed as a **general document-researcher** (its
`description` tells the parent *when* to delegate — many documents / several independent questions), and the
harness runs **two** scenarios against a **multi-document** matter: a simple ask (expect a direct answer, NO
`task`) and a broad multi-document ask (expect ≥1 `task` delegation nesting via `parent_step_id`). Both
outcomes are honest findings (ADR-F015); neither is tuned green.

## The mismatch + the maintainer's ruling (2026-06-17, research-revised) — idiomatic per-subagent sources

deepagents shares the parent `backend` with every subagent as the **file-storage substrate**
(`graph.py:621 backend=backend`), but **skill discovery is per-subagent and isolated**: a custom subagent
gets a SkillsMiddleware **only if it declares its own `skills`**, over its own sources
(`graph.py:628-630: SkillsMiddleware(backend=backend, sources=subagent_skills)`); only the auto
general-purpose subagent inherits the parent's `skills` (`graph.py:704-705`). The docs are explicit: *"Custom
subagents don't inherit parent skills … skill state is fully isolated in both directions,"* and per-subagent
source paths are *"the idiomatic way to give different subagents different skill subsets."* A `skills` value is
a list of **source paths** — each a *parent-of-skill-dirs* (`ls(source)` → each subdir a skill); a source
pointed AT a skill dir yields zero skills. Our config stores subagent `skills` as **names**
(`area_agent.py:_ALLOWED_SUBAGENT_KEYS`), so a stored `skills:["nda-review"]` would reach deepagents as
`sources=["nda-review"]` → `ls("nda-review")` → `file_not_found` → **silent zero-skills load**. That is the
bug; the fix is to give each subagent a real virtual source over our backend.

**Maintainer ruling (research-revised, chosen over "skill-less" and the earlier "inherit area set"):** adopt
the **idiomatic per-subagent source** model. The area (main agent) keeps its source `/skills`; each
skill-bearing subagent gets its **own** virtual source exposing **its** (⊆ area) subset, isolated exactly as
deepagents intends. This fits the framework's grain (it's the documented pattern, not extra machinery), honors
ADR-F016's "subset per agent" **down to the subagent**, and keeps each subagent's surface **tighter** than the
area's (good for M3's over-exploration). It supersedes the prior "inherit the area set" sketch.

## Decision (ADR-F017) — one multi-source `RegistrySkillBackend`; each agent points at its own source

Generalize `RegistrySkillBackend` from a single name-map to **multiple virtual sources**:
`sources: Mapping[source_path, Mapping[skill_name, SKILL.md]]`. `ls`/`read`/`download` resolve by which source
a path belongs to (exact-parts match per source root → inherent longest-prefix disambiguation). One shared
instance serves the area source **and** every subagent source — exactly deepagents' shared-backend model. The
composition seam builds the wiring: the area source `/skills` (the bound subset, as in UX-B-3) plus, per
skill-bearing subagent, a source `"/skills/subagents/<name>"` exposing that subagent's resolved subset; it
rewrites each subagent spec's `skills` (names) → `[its source path]` (or drops the key when nothing resolves),
and passes the main agent `skills=[SKILLS_ROOT]` + the one backend. Subagent skill names are validated
**⊆ the area's bound set** (rejected at PATCH; dropped-not-fatal at render, the UX-B-3 drift posture). Sources
nest under `/skills/subagents/<name>` but `ls("/skills")` is fully virtual and returns ONLY the area names — no
leakage. ADR-F017 is load-bearing (sets the subagent skill-scoping contract + the multi-source backend) →
drafted this slice, accepted by the maintainer.

## Goals / non-goals

**Goals:** one area (Commercial) carries a real, narrow declarative subagent; a skill-bearing subagent maps
correctly to the area backend (no silent-zero); the subagent runs live and the run nests via `parent_step_id`;
a **deterministic** scripted test asserts the ancestry (CI gate); a **live** MiniMax-M3 behavior report is
committed (`docs/fork/evidence/ux-b-4/`); ADR-F017.

**Non-goals (noted forward):** per-subagent skill *narrowing* / multi-root backend (ADR-F017 forward path);
per-subagent tool subsets (`tools` stays omitted → inherit the guarded matter tools); playbooks + MCP
plumbing (the by-reference slots stay validated-but-unconsumed); subagents in the other four areas; any web
work (UX-B-5); extending `guarded_dispatch` to the builtin filesystem tools (F1).

## Files

- **`app/agents/skill_backend.py`** — generalize `RegistrySkillBackend` to **multi-source**
  (`sources: Mapping[str, Mapping[str, str]]`); `ls`/`read`/`download` resolve per source root (the existing
  exact-parts checks already disambiguate nested roots). Add `subagent_source_path(name)` (the
  `/skills/subagents/<name>` convention) + `build_area_skill_wiring(registry, *, area_skill_names, subagents)`
  → a `SkillWiring(backend, main_sources, subagents)` dataclass: resolves the area subset + each subagent's
  ⊆-area subset, builds the one backend, and returns the subagent specs **rewritten** to point at their source
  paths. `build_area_skill_backend` (UX-B-3, single-source) kept as the area-only convenience wrapper.
- **`app/agents/area_agent.py`** — `render_area_agent` filters each subagent's declared `skills` to the
  resolved area set (drop-not-fatal, area is source of truth, the UX-B-3 drift posture); message cites
  ADR-F017. `build_area_subagents` keeps the PATCH-time ⊆-registry check; the PATCH path additionally rejects a
  subagent skill ∉ the area's bound set (config-time honesty).
- **`app/agents/composition.py`** — replace the area-only `build_area_skill_backend` call with
  `build_area_skill_wiring(...)`; pass `wiring.main_sources` + `wiring.backend` + `wiring.subagents` to
  `execute_agent_run`. One comment at the seam citing ADR-F017. No new I/O.
- **`alembic/versions/0057_commercial_subagent.py` (NEW)** — idempotent: set Commercial's `agent_config` to a
  one-subagent spec **only where `agent_config` is empty/`{}`/NULL** (never clobber an operator edit; the 0055
  pattern). Symmetric downgrade resets it to `{}` only if it still equals the seeded value. The subagent is a
  **general document-researcher** (the delegate the parent fans out to for complex, multi-document matters —
  NOT a mandatory step):
  - `name`: `document-researcher`
  - `description`: signals *when to delegate* — "Investigate a specific question across the matter's
    documents and report findings with citations. Delegate to this researcher when the matter has many
    documents or several independent questions, so investigations run in parallel and the main thread stays
    focused. For a single short document, read it directly instead."
  - `system_prompt`: narrow — investigate the one question you're handed across the matter's documents
    (`search_documents`/`read_document`), quote findings with document name + page, report back to the
    parent; ground every claim, say so plainly when the documents don't answer; do NOT write the final
    client-facing answer.
  - `skills`: `["contract-qa", "nda-review"]` (⊆ Commercial's 4 bound skills → its OWN isolated source under
    ADR-F017, tighter than the area's 4). Tight surface per the UX-B-3 caution.
  - NO `model`, NO `tools` (inherit gateway-bound parent + guarded matter tools).
- **`tests/agents/test_skill_backend.py`** — unit: `subagent_skill_sources` returns `[SKILLS_ROOT]` with a
  backend + names, `None` with no backend, `None` with no names.
- **`tests/agents/test_area_agent.py`** — unit: render rejects a subagent skill outside the area's bound set;
  accepts a subset; existing drift tests stay green.
- **`tests/agents/test_agent_composition.py`** — **deterministic ancestry test** (the CI gate): a scripted
  model emits a `task` delegation then answers; assert the settled `AgentRunStep` rows contain a `task`
  tool_call and ≥1 step whose `parent_step_id` is that task step (delegation nested). Assert the subagent
  spec's `skills` was rewritten to `[SKILLS_ROOT]` (composition translation) when a registry/backend is
  present.
- **`tests/agents/scenarios/harness.py`** — extend `Receipt` with delegation observations: `task_calls`
  (count of `name=="task"` tool steps), `delegated` (≥1 step with non-null `parent_step_id`), and a small
  `ancestry` summary (parent task step seq → child step seqs). Read `parent_step_id` from the already-loaded
  step rows (no new query). `to_dict` carries them (observations only — counts/seqs, never raw values). Add a
  **multi-document** seed helper (`seed_matter` extended, or a thin wrapper) so a matter can carry several
  documents — a single-doc matter gives the agent no reason to fan out.
- **`tests/agents/scenarios/area_fixtures.py`** — add a small **multi-document Commercial RFQ** fixture
  (several short docs: e.g. an RFQ cover, two vendor responses, terms) + **two** scenarios: (a) *simple* —
  a focused single-question ask whose best path is a direct grounded answer (**expect NO `task`**); (b)
  *complex* — a broad "review the RFQ across all the documents and flag the key risks" ask whose best path is
  to **delegate** per-document/-question investigation (**expect ≥1 `task`** + nested `parent_step_id`).
- **`tests/agents/scenarios/test_subagent_scenarios.py` (NEW)** — provider-marked (skips without
  `LQ_AI_GATEWAY_KEY`); loads the real registry from `/skills`, seeds the multi-doc Commercial matter, runs
  BOTH scenarios via `run_scenario(..., skill_registry=registry)`, writes the report to
  `docs/fork/evidence/ux-b-4/commercial/` (milestone `UX-B-4`), env override `UX_B4_EVIDENCE_DIR`. Per
  ADR-F015 the rig asserts only that it ran + recorded receipts; delegate/no-delegate are findings.
- **`docs/adr/F017-subagent-skill-mapping.md` (NEW)** — the mismatch, the three options, the chosen
  inherit-area-set mapping + the honesty (⊆-area) guard, the forward path (per-subagent narrowing / multi-root),
  the ADR-F010/F015/F016 links.
- **`docs/fork/evidence/ux-b-4/` (NEW)** — README + committed behavior report.
- **`docs/fork/HANDOFF.md`** — top entry + Next slice → UX-B-5.
- **`docs/fork/plans/UX-B-deep-agents-truly-work-decomposition.md`** — mark UX-B-4 shipped.

## Security pass (folded into the adversarial review)

- **No gateway bypass:** the subagent omits `model` (inherits the gateway-bound parent instance); the
  ADR-F010 guard at `build_deep_agent` re-asserts it. The migration's spec is `model`-free; assert it in the
  0057 test.
- **No credential storage:** `agent_config` carries only name/description/system_prompt/skills (NORTH-STAR
  inv 3); the `_FORBIDDEN_REF_KEYS` guard already covers the by-reference slots. Re-scan the migration.
- **Backend boundary unchanged (ADR-F016):** the subagent uses the SAME read-only `RegistrySkillBackend` over
  the area's bound subset — no host FS, no matter data, no unbound skills; the translation only points the
  subagent at the existing root. Skill content stays curated-but-untrusted (prompt injection) and read-only.
- **No secrets in the report/fixtures/migration:** counts/types/seqs + bounded answer excerpts only (re-scan).

## Verification

Containerized api suite (`lq-ai-api-dev` image, mount `api/`→`/app` + `skills/`→`/skills:ro`, `--network host`,
`--user`, `HOME=/tmp`, `cache_dir=/tmp/pytest_cache`) — counts quoted; ruff format+check + mypy `app` clean.
Migration on the conftest throwaway test DB only (never the dev DB / host `alembic upgrade`). Dev stack:
migrate 0056→0057 (rebuild api+arq-worker+ingest-worker together; never `down -v`). Live subagent harness
report committed (`LQ_AI_GATEWAY_URL=http://localhost:8001` under `--network host`). The deterministic
ancestry test runs in CI; the live scenario self-skips without a key. Fresh-context adversarial + security +
simplification review. Merge per ADR-F005 against `sarturko-maker/lq-ai-fork`.

**Expectation (ADR-F015, NOT a gate):** UX-B-3 showed M3 over-explores a skill-heavy surface to
`cap_exceeded`. Delegation is *harder* than chaining. A no-converge / no-delegation live run is an **honest
qualification finding** kept verbatim, not tuned green; the deterministic test proves the mechanism regardless.
