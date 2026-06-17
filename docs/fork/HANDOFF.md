# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (F2 + UX-A COMPLETE; UX-B milestone OPEN — UX-B-4 live subagent SHIPPED; pickup = UX-B-5 cockpit web)

- **UX-B-4 (PR #93) — SHIPPED. Live subagent (on-demand delegation), via the idiomatic deepagents
  per-subagent skill-source model (ADR-F017 accepted).** Commercial gained its first live subagent —
  `document-researcher` (migration **0057**, idempotent: writes only where `agent_config = '{}'`) — a GENERAL
  delegate the lead agent fans out to **on-demand** (the parent's deepagents `task` tool fires only when a
  matter warrants it: a single NDA is read directly; a complex multi-document RFQ is delegated). **Research
  first (maintainer steer):** re-read the deepagents docs/source before coding — they overturned the initial
  "subagent inherits the area set" sketch. deepagents shares the `backend` only as the file substrate, but
  **skill discovery is isolated per subagent**: a custom subagent gets a SkillsMiddleware only if it declares
  its own `skills` SOURCE PATHS (`graph.py:628-630`); *"custom subagents don't inherit parent skills."* So the
  idiomatic fix = give each subagent its OWN virtual source. **Generalised `RegistrySkillBackend` to
  multi-source** (`sources: {source_path: {name: SKILL.md}}`): the lead agent sees the area subset at
  `/skills`; each skill-bearing subagent sees only its (⊆ area) subset at `/skills/subagents/<name>`. The
  composition seam `build_area_skill_wiring` builds the one shared backend + rewrites each subagent's skill
  NAMES → its source path (⊆ area enforced: **rejected at PATCH**, dropped-not-fatal at render — the UX-B-3
  drift posture; registry None → skills stripped so no bogus source reaches deepagents). Subagent carries NO
  `model` (inherits gateway-bound parent, ADR-F010 guard re-asserts) and NO `tools` (inherits guarded matter
  tools). Removed the now-dead `build_area_skill_backend` (the wiring subsumes it). Harness gained
  **multi-document seeding** (`seed_multi_doc_matter`) + **delegation observations** on `Receipt`
  (`task_calls`/`delegated`/`ancestry` from `parent_step_id`). **Verify:** scripted suite **2158 passed / 10
  skipped** (0 errors; +10 vs UX-B-3's 2148 — multi-source backend + wiring + drift + the deterministic
  ancestry gate + 0057 migration tests; +1 self-skipping provider test) — the CI gate is
  `test_subagent_delegation_nests_steps_via_parent_step_id` (scripted `task` delegation → a `task` step with
  subagent steps **nested via `parent_step_id`**, F0-S7); ruff+mypy clean; dev stack migrated **0056→0057**
  (api+arq-worker+ingest-worker rebuilt together; Commercial shows `document-researcher`). **Live MiniMax-M3
  re-qualification (`docs/fork/evidence/ux-b-4/`, ADR-F015 — kept verbatim, NOT tuned green):** both RFQ
  scenarios `completed`; M3 correctly did NOT delegate the single fact (answered directly, cited), and ALSO did
  NOT delegate the 4-document review — it read all four docs itself and produced a structured comparison
  (`task_calls=0`). **The delegation plumbing is proven deterministically (CI); a tier-4 model just doesn't
  *elect* to fan out at this matter size** (4 short docs fit one context) — the honest finding; forcing it
  would be gaming. Fresh-context security+simplification pass: no secrets (migration is data-only, no creds;
  report carries observations only); no gateway bypass; backend stays read-only/allow-listed/no-host-FS; dead
  code removed. **Pickup: UX-B-5** (cockpit web — see Next slice).
- **UX-B-3 (PR #92) — SHIPPED. Skills activation (S9), via a read-only registry-backed virtual backend
  (ADR-F016 accepted).** Corrected the long-standing HANDOFF premise: **`SkillsMiddleware` adds no tools** —
  it `ls`/`download`s a deepagents *backend* and the model reads each `SKILL.md` via the **builtin
  `read_file`**; those builtins already exist on our agent over an empty `StateBackend` and are **not** wrapped
  by `guarded_dispatch` (the full-universe guard wrap is F1, out of scope). So activation = give the agent a
  **backend** carrying the area's skills + `skills=[sources]`, and the security boundary is **what the backend
  exposes**. **Maintainer-ruled architecture (ADR-F016):** one library, **no duplication** (areas reference
  skills by name), **subset per agent** (the whole library confuses the model), **relevant skills by default +
  user-extend**. Built **`app/agents/skill_backend.py`** (`RegistrySkillBackend`) — a read-only
  `BackendProtocol` adapter over a `SkillRegistry` snapshot serving ONLY the area's bound subset as a virtual
  `/skills/<name>/SKILL.md` tree (zero-copy; reaches no host FS / matter data / unbound skills; `read()`
  windows by offset/limit per the StateBackend contract; mutations refused; drift closes structurally — a
  bound name the registry forgot is absent). **Composition** (`composition.py`) gained a
  **`skill_registry_provider`** seam (default reads the worker/api `app.state.skill_registry` holder — the
  autonomous-executor precedent; runs execute in the arq worker which installs it at `on_startup`), loads the
  area's `practice_area_skills`, renders `render_area_agent(bound, known)`, builds the backend over the
  resolved subset, threads **`skills`+`backend`** → `execute_agent_run` → `build_deep_agent` →
  `create_deep_agent` (ADR-F010 subagent guard still runs; skills/backend carry no model → no gateway bypass).
  Dropped the `composition.py:151 bound_skill_names=[]` stub. **Migration `0056`** seeds focused default
  bindings per area (idempotent, insert-only-when-absent; symmetric downgrade removes only seeded pairs):
  Commercial 4 (msa-review-commercial-purchase/msa-review-saas/contract-qa/nda-review), Privacy 3
  (dpa-checklist-review/vendor-privacy-policy-first-pass/contract-qa), M&A 3 (nda-review/contract-qa/
  contract-snapshot), Disputes 2 (contract-qa/action-items-from-client-alert), Employment 3 (contract-qa/
  nda-review/action-items). **Drift gap closed:** `build_area_subagents(known_skill_names=…)` rejects a
  subagent referencing an unknown skill at PATCH time (best-effort — skips if no registry installed, never
  404s the PATCH). **Live skills-on re-qualification** (`docs/fork/evidence/ux-b-3/`, real MiniMax-M3): the
  **mechanism works** — the model reads the bound SKILL.md via the backend (5× `read_file` in one run);
  **focused** review still grounds+cites cleanly (`completed`), but a **broad** "structured risk review"
  over-explores to **`cap_exceeded` with no answer** — an honest calibration finding (the expanded surface
  amplifies M3's known multi-step inconsistency), **kept verbatim, not tuned away**. **Verify:** scripted suite
  **2148 passed / 9 skipped** (clean re-run, 0 errors; +18 vs UX-B-2's 2130 — backend/drift/composition/
  migration tests; the 9th skip = the new provider scenario test self-skipping without a key); migration verified on the conftest
  throwaway test DB; ruff+mypy clean; **dev stack migrated 0055→0056** (api+arq-worker+ingest-worker rebuilt
  together; all 5 areas show their bindings). The 22 `asyncpg` setup errors in the first full-suite run were
  **environmental** (I rebuilt the dev stack + ran the live harness on the same Postgres concurrently) — the
  errored clusters (auth/audit/admin/watches, untouched by this diff) re-ran **75/75 clean** in isolation; a
  clean re-run confirms the count. Fresh-context adversarial+security+simplification review: **SHIP-WITH-NITS**
  (1 should-fix — `read()` offset/limit windowing — FIXED in-slice + tested; 1 nit accepted). No secrets in
  code/migration/reports. **Pickup: UX-B-4** (live subagent — see Next slice).
- **UX-B-2 (PR #91) — SHIPPED. Sensible default practice areas, calibrated to the UX-B-1 baseline
  (ADR-F002/F004/F015).** Gave the four remaining standard areas — **Disputes / M&A / Privacy /
  Employment** — a real `profile_md` via the **idempotent migration `0055_default_area_profiles.py`** (the
  0054 pattern: write only where `profile_md IS NULL`, so re-running never clobbers an operator edit; sets
  the stored `configured` column true alongside, mirroring the admin PATCH — but the **derived
  `_is_configured` (non-empty profile) is the source of truth** the API list + the matter-creation gate
  read, so seeding the profile is what flips an area configured + matter-fileable). Profiles are
  **calibrated to the UX-B-1 MiniMax-M3 baseline**: each mirrors the 0054 Commercial shape (identity +
  domain precision) and leans explicitly on the disciplines that degrade honestly under a tier-4-weak model
  — **ground every claim in a tool result and cite it**, **say so plainly when the documents don't
  answer**, **ask one brief clarifying question before guessing** (M3's weakest shape), and **never fake a
  confirmation of an action it has no tool for**. **`default_tier_floor` stays NULL for all** (the 0054
  Commercial rationale: M3 is the only S9-qualified model at tier 4; any stronger floor makes the area fail
  `tier_below_minimum`, a floor of 4 is redundant — operators set one via PATCH once a stronger model
  qualifies). **`agent_config` stays `{}` — live subagents DEFERRED to UX-B-4** (the composition point
  renders area subagents *live* via `area_spec.subagents`; delegation is strictly harder than the
  multi-step chaining M3 is already inconsistent at, ADR-F015 forbids activating an unqualified capability,
  and the decomposition sequences subagents after skills — documented in the migration docstring + the
  evidence README; Privacy's forward-looking profile is prose only). **Harness generalised** (reused, not
  rebuilt): `harness.seed_commercial_matter` → area-agnostic **`seed_matter(factory, *, area_key, doc,
  matter_name)`** (the Commercial wrapper kept for UX-B-1); `scenarios.build_fixture_document` → reusable
  **`build_document(filename, sections)`**; `report.write_report` gained `area`/`milestone` params
  (defaults preserve UX-B-1). New **`area_fixtures.py`** (one synthetic doc + a 3-scenario set per area —
  grounded fetch / honest refusal / ambiguous→clarify, plus a no-tool case for Privacy) +
  **`test_default_area_scenarios.py`** (provider-marked, parametrised per area). **Scenario shapes were
  themselves calibrated** after a first live run: read is no longer forbidden on a fetch (M3's search→read→
  cite is *better* grounding) and the prompt-echo "both are done" was dropped from the false-confirmation
  guard (it matched inside the honest "I cannot confirm both are done"). **Verify:** migration ran clean on
  the conftest throwaway test DB (never the dev DB); scripted suite **2130 passed / 8 skipped** (was 2128:
  +2 new unit tests in `test_practice_areas.py` — derived-configured + 0055 idempotency; the 8 skipped =
  provider tests self-skipping with no key); ruff+mypy `app` clean. **Live per-area harness ran
  (out-of-CI, real MiniMax-M3):** all **12 scenarios `completed`** (no stranded/`cap_exceeded`); reports in
  `docs/fork/evidence/ux-b-2/{disputes,m-and-a,privacy,employment}/` + a README index. **Findings
  (observations, ADR-F015 — non-deterministic, the answer excerpt is authoritative):** M3 grounds + cites
  cleanly, **declines honestly** (issue/serve, sign+wire, terminate+email — states inability + governance
  reasons, never fakes it), and **clarifies** ambiguous referents for 3 of 4 areas (the calibrated profile
  sentence is visibly echoed). **Residual finding (calibration target, not a defect):** M3's tool-use
  *efficiency* varies — on some fetches it issues a redundant second `search_documents`+`read_document`
  before answering (correct + cited, but over the soft step bound); a "search once, precisely" profile note
  is a later-slice option. Reports + the two updated `test_practice_areas` assertions carry no
  key/secret/URL (re-scanned). **Pickup: UX-B-3** (skills activation / S9 — see Next slice).
- **UX-B-1 (PR #90) — SHIPPED. Scenario harness + Commercial baseline (ADR-F015). Test infra only — no
  `app/` change.** A reusable, provider-marked rig (`api/tests/agents/scenarios/`) that drives the REAL
  practice-area Deep Agent through the PRODUCTION composition point
  (`compose_and_execute_run`, injecting only the test-DB session factory + a null checkpointer — the model,
  gateway http client, and gateway URL/key all flow from settings exactly as in prod, so **no provider key
  is ever held or printed**) against the **live gateway / real MiniMax-M3**, then reads back the settled
  `AgentRun` + ordered `AgentRunStep` rows as honest **receipts** (tool selection, step count, model turns,
  final answer, latency) and emits a committed **behavior report**
  (`docs/fork/evidence/ux-b-1/behavior-report.{md,json}` — observations only: tool names/counts/pass-fail/
  bounded answer excerpts, never keys/secrets/raw payloads). Files: `scenarios.py` (the `Scenario` model +
  the 5 Commercial starter scenarios + a synthetic searchable MSA fixture, offsets satisfying the Citation
  Engine invariant + the pure `evaluate()`), `harness.py` (`seed_commercial_matter` → user + Commercial-bound
  matter + file→document→chunks; `run_scenario` → drive + receipt), `report.py` (JSON+MD emitter),
  `test_commercial_scenarios.py` (the `@pytest.mark.provider` + `LQ_AI_GATEWAY_KEY` skipif entry),
  `conftest.py` (`commit_factory`). **Per ADR-F015 it is NOT a model pass/fail gate** — a shape-miss is a
  recorded *finding* that calibrates UX-B-2; the test asserts only that the RIG ran (every scenario reached a
  terminal status + receipts + ≥1 live model turn). **Baseline findings (MiniMax-M3, runs vary — tier-4
  non-determinism is itself the observation):** single-tool fetch grounds + cites cleanly; no-tool-needed
  answers directly (respects "without consulting documents"); guard/refusal **honestly declines** delete/email
  (no such tool) with sound legal reasoning — never hallucinates a confirmation; **multi-step search→read is
  inconsistent** (M3 often answers from the search snippet alone when it already contains the clause — a
  calibration note, not a defect); **ambiguous→clarify is the real weakness** — M3 sometimes clarifies well
  but sometimes spins through repeated search/read (one run hit `cap_exceeded` at 16 steps, no answer). These
  CALIBRATE UX-B-2's default-area profiles + tier floors. **Verify:** scripted CI suite **2128 passed, 4
  skipped** (the 4 = provider tests self-skipping with no key — mine among them, so it never gates CI); ruff
  format+check clean; mypy `app` clean; harness runs locally against the live dev stack (87s → 70s; report
  committed); fresh-context adversarial+security review **SHIP** (0 blockers/should-fixes; 3 NITs — dead
  `applicable` field removed, model-resolution wording softened to observation-honest, a "reading the checks"
  heuristic caveat added to the report; the report carries no key/secret/PII). **Run it:** `DATABASE_URL=…
  LQ_AI_GATEWAY_KEY=… pytest -m provider tests/agents/scenarios/ -s` (containerized: `Dockerfile.dev` image,
  mount `api/`→`/app` + `skills/`→`/skills:ro` + the evidence dir, set `UX_B1_EVIDENCE_DIR`). **Pickup:
  UX-B-2** (default areas, calibrated to this baseline) — see Next slice.
- **UX-B-0 (PR #89) — SHIPPED. ADR-F015 ACCEPTED + UX-B decomposition. Docs only.** The maintainer revealed
  the long-range vision (agentic SaaS **modules** à la **Oscar Privacy**; see [[oscar-privacy-modules-vision]])
  and the near-term mandate that gates it: *Deep Agents must truly work, the cockpit must be perfect*. This
  is **UX-B** (ADR-F012's third leg; the delivery of roadmap "F3 — Practice-area IA re-centre" — named UX-B,
  not F3, to avoid the roadmap-label collision). **ADR-F015 accepted 2026-06-16** = *scenario-based model
  qualification is the gate*: a provider-marked live-MiniMax scenario harness emits a committed behavior
  report; nothing ships `configured`/`activated`/blessed until the report shows M3 handles it; area profiles
  + tier floors calibrated to observed behaviour. Scripted unit tests stay the CI gate; the harness runs
  out-of-CI. Maintainer's steers: start = harness + Commercial baseline; skills activation (S9) in scope (a
  later slice); plan reviewed first (this PR). Files: `docs/adr/F015-scenario-qualified-cockpit-deep-agent.md`,
  `docs/fork/plans/UX-B-deep-agents-truly-work-decomposition.md`. **Pickup: UX-B-1** (see Next slice).
- **F2-M9 (PR #88) — SHIPPED. Consistency sweep + verify — the F2 milestone closer. NO code change.**
  Static audit of every F2-touched surface (cockpit/rail/conversation/matters + all list/card surfaces +
  the M8 nav shells): **zero color `--lq-*`** survivors (the `--lq-radius*`/`--lq-space-*` + `lq-text-*`
  typography CLASSES are the deliberate R-TYPO carve-out, not a miss); **zero `{@html}` sinks** (the one
  grep hit is a *comment* in `CenteredEntry` saying "no `{@html}`"); **zero teal/hardcoded-hex rogue
  accents** — one-accent discipline holds (ink primaries + scarce `--brand`/`--ring`; the only colored
  accent left is the green TrustPill, a documented deferral). **Reachability (the ADR-F012 no-retire
  contract):** all 11 tab surfaces + trust + settings resolve under `(app)` and are reachable from the rail
  Tools group + header gear/ShieldCheck — nothing retired/hidden by the visual pass. **Cross-surface
  consistency (44-shot full matrix via `f2-baseline.cy.ts` 5/5, light+dark × wide+narrow):** the
  raised-card-pill active-nav idiom is identical across the rail + the M8 settings shell; status pills share
  the family (scarce-blue `running`/`indexing`, green `completed`); AA-dark legible, no light-in-dark panels.
  **Owned debt documented, NOT in scope** (the audit records it, M9 does not swallow it): the settings/admin
  child page **bodies** + Trust\*Card internals (still `--lq-*`/teal — R16/R19); `lq-text-*`/radius/space
  classes (R-TYPO); deferred TrustPill tones; the intentional auth-gated `_vl-lab`/`_ae-lab` scratch routes
  (kept by precedent — unadvertised, linked from nowhere). Suites: web check **0 err**; **vitest 851**
  (unchanged); cypress **5/5**. Evidence: `docs/fork/evidence/f2-m9/` (the full surface matrix). Review:
  **SHIP**, 0 blockers. web-only (no api/gateway). **F2 IS DONE.** **Pickup: a decision point — see Next slice.**
- **F2-M8 (PR #87) — SHIPPED. The settings / admin / trust nav shells calmed.** The three sub-nav
  shells under `(app)` were the last chrome still rendering the old **teal `--lq-accent`** active marker
  (`--lq-accent` = `#1f7a6b`, NOT the Vercel scarce blue — so these shells were visibly off-brand, not
  cosmetic-only). Migrated each: **`settings/+layout.svelte`** (vertical rail) — active = the live
  **AreaRail idiom** (raised `--card` pill + `--shadow-xs`, no accent colour), rest `--muted-foreground`,
  hover `--muted`; **`admin/+layout.svelte`** (horizontal tab strip) — keeps the underline idiom but
  **inks the active marker** (`--foreground` text + border, was teal), nav bg `--lq-surface`→`--background`,
  border `--lq-border`→`--border`; **`trust/+page.svelte`** — adopt **`<PageShell size="wide" pad="compact">`**
  (bespoke 1100px→`wide` 1024, the M7b snap), color `--lq-text-secondary`→`--muted-foreground`. Added a
  **`:focus-visible` ring** to both nav link sets (scarce blue, was absent). **Scope = the nav shells only**
  (the HANDOFF/plan rule): the settings/admin CHILD page **bodies** (account MFA button, audit-log table,
  word-addin/intake status pills — still teal/`--lq-*`) and the **Trust\*Card internals** are owned by
  **R16/R19 / their R-slices** — visible in the after-shots, documented, NOT a defect. Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 851** (unchanged — presentation-only,
  no new pure helper); **`f2-baseline.cy.ts` 5/5** headed/live (added a settings+admin+trust capture test,
  PHASE=after). Evidence: `docs/fork/evidence/f2-m8/` (settings + admin + trust, light+dark × wide+narrow —
  active markers inked not teal; dark renders honest charcoal). Fresh-context review: **SHIP**, 0
  blockers (every target token verified in both themes incl. `--shadow-xs`/`--background`; `.trust-stack`
  inner wrapper added so Svelte style-scoping applies — `class` on a child component's root would be a dead
  selector; testid forwarded via PageShell `{...rest}`; no `{@html}`; no stray/secret files). web-only.
  **Pickup: F2-M9** (consistency sweep + verify) — see Next slice.
- **F2-M7b (PR #86) — SHIPPED. The library card/wrapper surfaces calmed (the last `(app)` list pages
  on `--lq-*`).** Same M7a recipe applied to the three remaining library pages: **`knowledge`** (card grid +
  inline create form), **`learn`** (3-tile card grid), **`saved-prompts`** (thin `SavedPromptsPanel`
  wrapper). Each: **adopt `<PageShell pad="compact">`** (replacing the page's bespoke `<main>` wrapper — also
  drops a nested-`<main>` landmark, since `(app)/+layout.svelte` already supplies the page `<main>`); the
  bespoke widths **snapped onto the system reading widths** — knowledge 1100→`wide` (1024), learn 960 +
  saved-prompts 920→`default` (896); **migrate COLOR `--lq-*`→semantic** (text→`--foreground`/`--muted-foreground`,
  border→`--border`, card bg→`--card`, inset→`--muted`, accent button→`--primary`/`--primary-foreground` ink
  inverting, accent link/CTA→`--brand`, focus→`--ring`, error→`--destructive`+`--status-failed-wash`);
  **KB status pills → the `--status-*` tone family** (`indexed`→completed, `indexing`→the scarce-blue running
  tone, `failed`→failed, `empty`→muted — borderless, the M7a tabular-pill recipe); **F013 calm card idiom**
  (flat, border-led, hover washes to `--muted`, NO float shadow — dropped the old `box-shadow` hover, scarce
  blue reserved for focus). **Left for R-TYPO (documented, not a defect):** `--lq-radius*`/`--lq-space-*` +
  the `lq-text-*` typography CLASSES (no semantic equivalent, no light/dark variance — never re-introduced,
  just not double-touched). For saved-prompts, **only the page wrapper** is touched — `SavedPromptsPanel`
  itself keeps its own accents (its R-slice owns it). Suites: web check **0 err** (5 pre-existing a11y
  warnings, untouched files); **vitest 851** (unchanged — presentation-only, no new pure helper, like
  M2/M5/M7a); **`f2-baseline.cy.ts` 4/4** headed/live (added a knowledge+learn+saved-prompts capture test,
  PHASE=after). Evidence: `docs/fork/evidence/f2-m7b/` (knowledge + learn + saved-prompts, light+dark ×
  wide+narrow — dark renders honest charcoal, no light-in-dark; ink primaries, scarce-blue pills/links).
  Fresh-context review: **SHIP**, 0 blockers/should-fixes (every target token verified in both themes;
  markup balanced; testids forwarded via PageShell `{...rest}`; no dead selectors; no `{@html}`; the
  heavier `.lq-error` destructive border matches the M7a recipe). web-only — no api/gateway change.
  **Pickup: F2-M8** (calm settings/admin/trust shells) — see Next slice.
- **UX-A-5 (PR #85) — SHIPPED. The legacy `(tools)` shell + the header Tools dropdown RETIRED; UX-A
  COMPLETE.** Deleted `TopTabBar.svelte` (the legacy top-tab component) and the orphaned
  `(tools)/+layout.svelte` (the whole `(tools)` route group is gone). Moved the still-needed
  `visibleTabsFor` into `tabs.ts` (the tab vocabulary outlived the component; importers `(app)/+layout` +
  `CockpitHeader` repointed) and DROPPED the now-dead `tabStateClass` (the rail has its own styling).
  Retired the `CockpitHeader` Tools dropdown (it duplicated the rail Tools section — tools are reached
  ONLY from the rail now); **preserved trust** via a dedicated header ShieldCheck button → `/lq-ai/trust`
  (the dropdown was trust's only entry point; `AmbientTrustChrome` doesn't link). Dropped the unused `user`
  prop from `CockpitHeader`; added `data-testid="lq-cockpit-header"`. **No footer re-home needed**: the
  cockpit never carried `DualBrandingFooter` (it lives in the parent gate layout's auth-exempt branch +
  login only); the obligation ended F0-S6/ADR-F006. Swept stale comments (parent `+layout`, `tab-icons`,
  `autonomous/memory`) + cypress: **deleted** `wave-a-chrome.cy.ts` (100% legacy chrome) + the
  `vl2-cockpit` Tools-menu capture; **repointed** the rail-nav refs in `f1-s2-cockpit` (removed its
  obsolete "Tools menu" test — covered by the new spec), `wave-b-surfaces`, `wave-m1-final-surfaces`,
  `m4-autonomous` (its `.lq-tabbar` assertions had been dead since F2-M2) onto the rail Tools testids.
  Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 851** (−3 =
  removed `tabStateClass` tests; renamed `TopTabBar.test.ts`→`visible-tabs.test.ts`); **new
  `ux-a-5-retire-legacy-shell.cy.ts` 3/3** + **`f2-baseline.cy.ts` 3/3** + **`vl2-cockpit.cy.ts` 2/2**
  headed/live (no `nav[aria-label="Primary"]` / no header Tools dropdown on any surface; tools open from
  the rail into canvas; trust reachable from the header button). Evidence: `docs/fork/evidence/ux-a-5/`.
  Grep-clean: zero live `TopTabBar`/`(tools)`/`lq-tabbar`/Primary-nav refs remain. **KNOWN pre-existing
  legacy-spec debt (NOT in CI, NOT touched by UX-A-5, do NOT attribute to this slice):**
  `f1-s2-cockpit.cy.ts` test 1 (`lq-cockpit-new-matter-name` testid — matter-flow drift) + test 2 (asserts
  the dark canvas channel `>20` but VL0 set charcoal `#111`=rgb(17,17,17) — stale threshold);
  `wave-b-surfaces.cy.ts` `beforeEach` login flake. These are orthogonal test-debt for a later cleanup;
  UX-A-5 only removed their dead-chrome refs. Fresh-context review: **SHIP**, 0 blockers/should-fixes
  (reachability of every surface re-verified incl. the new header trust button; footer non-goal confirmed;
  `visibleTabsFor` move byte-identical; security clean). web-only — no api/gateway change. **ADR-F014
  closed** (status note appended). **Pickup: deferred F2 visual work** (see Next slice).
- **UX-A-4 (PR #84) — SHIPPED. The sub-nav surfaces re-hosted in the cockpit canvas (the last `(tools)`
  routes).** `git mv`'d `admin`, `autonomous`, `settings`, `trust` (incl. all children + `page-helpers` +
  `__tests__`) from `(tools)` into `(app)` — **27 pure renames, zero content change** — so they render in
  the cockpit canvas with the rail present. URLs unchanged (route groups URL-invisible); the
  `/lq-ai/+layout.svelte` auth/boot gate still wraps both groups. **Reachability preserved from cockpit
  chrome** (verified, no re-wiring needed): `admin` (admin-only) + `autonomous` (opt-in gated) appear in the
  rail Tools section + the header Tools dropdown; `settings` via the header gear (→ `settings/appearance`);
  `trust` via the header Tools-dropdown trust link. **Nested sub-nav chrome accepted** (per UX-A): three of
  the four carry their OWN sub-nav `+layout.svelte` (admin/autonomous = horizontal tab strip; settings =
  vertical rail) that now renders INSIDE the canvas beside the cockpit rail — functional, no DOM/id clash
  (distinct `aria-label`s). No `#lq-main`/`h-screen`/cross-boundary-import coupling (grep-verified; the
  route-group rename keeps directory depth identical so relative imports resolve unchanged); the 3
  `max-height: calc(100vh - 64px)` modal caps in autonomous are viewport-relative (pre-existing, fine
  nested). **Known cosmetic quirk (pre-existing, NOT fixed — mechanical scope):** `activeTabFor` keys the
  rail highlight off `admin`'s exact route `/lq-ai/admin/audit-log`, so the Admin tool highlights on
  audit-log but not on other admin sub-pages (models/word-addin/…) — predates this slice (the rail's had the
  admin tab since UX-A-2). **DELIBERATELY LEFT:** `(tools)/+layout.svelte` is now orphaned (zero child
  routes, unreachable) but kept in place — deleting it is coupled to re-homing the `DualBrandingFooter` it
  carries, which is a **UX-A-5** decision. Removed the `f2-baseline` legacy-chrome capture (no surface
  carries the legacy `TopTabBar` chrome any more — nothing left to capture). Suites: web check **0 err** (5
  pre-existing a11y warnings, untouched files); **vitest 854** (moved `__tests__` auto-discovered under
  `(app)`); **`ux-a-4-subnav-surfaces.cy.ts` 3/3** + **`f2-baseline.cy.ts` 3/3** headed/live (open admin
  from rail into canvas + rail-stays + active highlight + admin sub-nav paints; deep-link
  admin/models/settings/trust inside the shell; settings vertical sub-nav + trust in canvas). Evidence:
  `docs/fork/evidence/ux-a-4/`. Fresh-context review: **SHIP**, 0 blockers/should-fixes (1 stale-comment
  tidy applied). web-only — no api/gateway change. **Pickup: UX-A-5** (retire the orphaned
  `(tools)/+layout.svelte` + re-home `DualBrandingFooter` + decide on the header Tools dropdown + sweep).
- **UX-A-3 (PR #83) — SHIPPED. The conversation surfaces re-hosted in the cockpit canvas.** `git mv`'d
  `agents`, `chats`, `matters` (incl. `matters/[id]`) + `playbook-executions/[id]` (incl. its
  `page-helpers` + `__tests__`) from `(tools)` into `(app)` — **pure renames, zero content change** — so
  they render in the cockpit canvas with the rail present + the rail Tools active-highlight (generic via
  `activeTabFor`, no code change needed). URLs unchanged; the `/lq-ai/+layout.svelte` auth/boot gate still
  wraps both groups. **Scroll/height verified**: the list pages flow in the canvas `<main overflow-y-auto>`;
  `matters/[id]`'s `.matter-workspace{height:100%}` resolves against `main.h-full` → paneforge Pane (every
  ancestor has a definite height), same boundedness the old `(tools)` shell gave. **Nested `<main>` is
  pre-existing/unchanged** (the old `(tools)` shell also had a `<main>` around these pages' own `<main>`) —
  out of scope for a mechanical move. **Recorded call — the two-rail composition for `matters/[id]`**: the
  cockpit rail (app nav) and the matter's own `MatterRail` (within-matter nav: Chats/Files/Knowledge/Skills
  + metadata) now BOTH render, side by side. Kept deliberately for this slice (functional, no DOM/id clash,
  distinct selectors); it's visually dense at 1280px. A future slice (UX-B or a reconcile pass) may fold
  `MatterRail` into the cockpit rail or auto-collapse the cockpit rail on matter detail — NOT done here.
  Repointed the `f2-baseline` legacy-chrome capture `/chats`→`/trust` (chats is no longer legacy; trust
  migrates in UX-A-4). Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest
  854** (moved `__tests__` auto-discovered); **`ux-a-3-conversation-surfaces.cy.ts` 3/3** + **`f2-baseline.cy.ts`
  4/4** headed/live (open-from-rail-into-canvas + active highlight; deep-link agents/chats/matters inside the
  shell; `matters/[id]` two-rail composition). Evidence: `docs/fork/evidence/ux-a-3/`. Fresh-context review:
  **SHIP**, 0 blockers/should-fixes; 1 NIT (two-rail density, recorded/accepted). web-only — no api/gateway
  change. **Pickup: UX-A-4** (migrate the sub-nav surfaces `admin`/`autonomous`/`settings`/`trust` into
  `(app)`; each except trust has its own sub-nav `+layout.svelte` that now renders inside the canvas —
  nested chrome, accepted for UX-A; autonomous stays opt-in gated).
- **UX-A-2 (PR #82) — SHIPPED. Rail "Tools" section + the flat tool surfaces re-hosted in the cockpit
  canvas (the dead-end fix).** Added an expandable **Tools** group to `AreaRail` (open by default;
  `ChevronDownIcon` toggle; Lucide glyphs via the shared `tabIcon()` map; **active highlight** via
  `activeTabFor($page.url.pathname)` → `aria-current="page"`; the legacy executor group rests one step
  quieter, the M3 treatment). The layout (`(app)/+layout.svelte`) computes `toolTabs` (=
  `visibleTabsFor(user, {autonomousEnabled})` minus `home`, role/pref-gated identically to the header
  dropdown) + `activeTab` and passes `onSelectTool` (`drawerOpen=false; goto(tab.route)` — plain
  scroll-to-top nav). **`git mv`'d the six flat surfaces** `tabular`, `playbooks`, `saved-prompts`,
  `learn`, `knowledge`, `skills` (incl. `new`/`[id]`/`[id]/edit`/`easy` children + their `__tests__`)
  from `(tools)` into `(app)` — **pure renames, zero content change** — so they render in the cockpit
  canvas with the rail present (the way back is always the rail). URLs unchanged (route groups are
  URL-invisible); the parent `/lq-ai/+layout.svelte` auth/boot gate still wraps both groups. **Scroll
  parent resolved**: these pages use `PageShell` (flowing content, no `h-full`/`#lq-main` coupling — grep
  confirmed) so the cockpit canvas `<main overflow-y-auto>` provides the single scroll axis. `TopTabBar`
  still serves the not-yet-migrated surfaces (`agents`/`chats`/`matters`/`admin`/`autonomous`/`settings`/
  `trust`) — transitional; the header Tools dropdown also coexists until UX-A-5. Fixed 2 knowledge test
  import paths (`(tools)`→`(app)`); repointed the `f2-baseline` legacy-chrome capture `/skills`→`/chats`
  (skills is no longer legacy). Suites: web check **0 err** (5 pre-existing a11y warnings, untouched
  files); **vitest 854** (moved `__tests__` auto-discovered under `(app)`); **`ux-a-2-rail-tools.cy.ts`
  4/4** + **`f2-baseline.cy.ts` 4/4** headed/live (open-from-rail-into-canvas with rail-stays + active
  highlight; Tools collapse/expand; deep-link all 6 migrated surfaces inside the shell; deep-link a
  `[id]`-style child `tabular/new`). Evidence: `docs/fork/evidence/ux-a-2/`. Fresh-context review:
  **SHIP**, no blockers/should-fixes; 1 NIT (rail lists ALL tabs not just migrated — INTENDED per
  ADR-F014 "every surface reachable from the rail"; non-migrated ones transitionally leave the shell).
  web-only — no api/gateway change. **Pickup: UX-A-3** (migrate the conversation surfaces
  `agents`/`chats`/`matters` + `matters/[id]`/`playbook-executions/[id]` into `(app)`; reconcile
  `matters/[id]`'s own `MatterRail`/`ChatPanel` with the cockpit rail — record the call).
- **UX-A-1 (PR #80) — SHIPPED. The cockpit shell extracted into the `(app)` layout (pure refactor, no
  visual change).** Split `cockpit/Cockpit.svelte` into a shared SvelteKit SHELL
  (`routes/lq-ai/(app)/+layout.svelte`: `CockpitHeader` + the resizable rail/drawer/toggle + responsive
  state + the `nowMs` ticker + rail nav; the canvas renders `{@render children()}`) and a LANDING page
  (`(app)/+page.svelte`: the `areas/matters/matter/unfiled` view-switch; owns `projects` + `pendingDraft` +
  the matter/conversation handlers). Shared data (areas/activity/nowMs) flows rail↔canvas via
  **`CockpitShellState` Svelte context** in `cockpit/context.svelte.ts` — scoped **per-shell, NOT a module
  singleton** (so it can't leak one user's matters to the next session in the same tab). Deleted
  `routes/lq-ai/+page.svelte` (now served by `(app)/+page.svelte`, same URL — route groups are
  URL-invisible) + `cockpit/Cockpit.svelte`. **No tools moved, no visual change** — the landing is
  pixel-identical to VL2 (M1 bar). Suites: web check **0 err**; **`f2-baseline.cy.ts` 4/4** headed (cockpit
  + matters + conversation behave identically; `(tools)` surfaces untouched). Evidence:
  `docs/fork/evidence/ux-a-1/`. Fresh-context review: **SHIP** (one naming NIT fixed — `CockpitShellState`
  vs the helpers `CockpitState` URL type). web-only. The shell now persists across navigation, ready for
  UX-A-2 to render tool surfaces in its canvas.
- **UX-A (navigational convergence) — OPEN. ADR-F014 ACCEPTED (Approach B); UX-A-0 docs + UX-A-1 shell
  shipped.** Maintainer trigger after VL2: "open a tool and there's no clear way back to the cockpit;
  tools should live in an expandable rail section and render in the cockpit canvas." Make the cockpit the
  **single app shell** via a URL-invisible **route-group restructure**: extract the cockpit shell (header +
  resizable rail + an expandable **Tools** section + a canvas slot) out of `Cockpit.svelte` into a new
  `(app)/+layout.svelte`; the landing becomes `(app)/+page.svelte`; the `(tools)` routes + `trust` move into
  `(app)` to render in the canvas; the `(tools)` `TopTabBar` shell + the header Tools dropdown **retire** in
  UX-A-5 (maintainer confirmed). Deep-links survive (route groups are URL-invisible) and there are **no
  `load` functions** anywhere under `/lq-ai` (all client-side fetch), so no server logic migrates. NOT UX-B
  (tools stay tools, just re-hosted; capability convergence still rides the pivot). Plan: **ADR-F014** +
  **`docs/fork/plans/UX-A-navigational-convergence-decomposition.md`** (slices UX-A-0…5). **Pickup: UX-A-2 —
  add the expandable "Tools" section to the rail (Lucide icons via the shared `tabIcon()` map in
  `lib/lq-ai/tab-icons.ts` — already extracted; active highlight from `$page.url.pathname`; legacy group
  muted) + migrate the FLAT list surfaces** (tabular,
  playbooks, knowledge, skills, saved-prompts, learn incl. their `new`/`[id]`/`[id]/edit` children) **from
  `(tools)` into `(app)`** so they render in the cockpit canvas. Resolve the scroll-parent change (`#lq-main`
  → the cockpit canvas pane). `TopTabBar` still serves the not-yet-migrated surfaces (transitional). Then
  UX-A-3 (conversation surfaces: agents/chats/matters) → UX-A-4 (sub-nav: admin/autonomous/settings/trust)
  → UX-A-5 (retire TopTabBar + header Tools dropdown + sweep). Each: full ADR-F005 gate + deep-link checks +
  reversible.
- **F2-VL2 (PR #78, main `e5cf01b`) — MERGED. The flagship cockpit re-skin** (maintainer design-gate signed
  off).
  Re-skins `cockpit/` to the `direction-vercel` target using the VL1 primitives, **keeping the resizable
  PaneGroup + drawer mechanics** (maintainer chose "keep resizable pane, re-skin contents" over adopting
  the fixed-rail AppShell — so **AppShell stays a lab-only primitive**, not used in prod). Changes:
  **`CenteredEntry` → `Hero`** (first live `text-display` consumer) + a Vercel composer + SavedPrompts
  chips as calm text-links (dropped the AE `Suggestion` pills here); **`AreaGrid` → gap'd bordered
  `Card`s** (icon + name + `StatusDot` rollup of the area's latest matter status) + a new **"Recent
  matters" dot-status list** (all matters, newest-first — keeps unfiled/legacy reachable); **`AreaRail` →
  the Vercel `--sidebar`** (a "New matter" ink `Button` routing to the launcher, calm area rows with a
  bare per-area activity dot, the unfiled bucket, an identity-only account footer — account ACTIONS stay
  in the header). **StatusDot gained an `attention` tone** (systematic — `--status-attention` already
  exists; the stale/cap-reached belt); a new pure **`runDot()`** in `cockpit/helpers.ts` maps a settled
  run status → calm dot + label **through the canonical `statusBadge`** (incl. the stale belt) so the
  cockpit dots and the agents pills never disagree (ADR-F004). `areaActivityCounts` now also carries
  `lastStatus`. **IA UNCHANGED** (rail stays the practice-area navigator; areas reachable from the
  landing grid too) — no surface retired (F2 rule); **launcher not composer** (ADR-F002); **all rollups
  settled rows** (ADR-F004). **Resolved the VL1 `CardGrid` trailing-empty-cell**: with 5 seeded areas the
  hairline plane leaves a gray cell on non-full rows at most breakpoints, so the area grid uses **gap'd
  bordered cards** (clean at every count) — the hairline `CardGrid` stays for fixed-count sections. Suites:
  web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 854** (+4: `runDot` ×3 +
  `statusDotClass('attention')`); **`vl2-cockpit.cy.ts` 2/2** headed/live (landing light+dark × wide+narrow
  + the narrow rail drawer). Evidence: `docs/fork/evidence/f2-vl2/` (incl. `_target-vercel-{light,dark}.png`
  for side-by-side). Fresh-context review: **SHIP**, no blockers/should-fixes; one NIT (area-card `rd`
  computed-but-discarded) **FIXED in-slice**. web-only — no api/gateway change. **Pickup: present evidence,
  iterate values under the maintainer's eye, MERGE ONLY on explicit design sign-off.**

## State (F2 milestone — F2-VL1 shipped, F013 primitives live; AE-series CLOSED)

- **NEW MILESTONE — F2 (scira-style minimalist pass), governed by ADR-F012.** The maintainer wants the
  whole interface taken toward the calm, minimal aesthetic of [`scira`](https://github.com/zaidmukaddam/scira)
  (**AGPL → REFERENCE ONLY**: study look/IA, never fetch/copy code), AND a UX redesign (land in the
  cockpit → reach tools from there → deep-agents-per-area as the centre). **ADR-F012 splits the work by
  dependency:** **F2** = the *visual* pass (now, reversible, no irreversible IA move — all 11 tabs stay);
  **UX-A** = navigational convergence (own milestone after F2; cockpit becomes the single shell, legacy
  top-tab IA retired — unblocked frontend IA); **UX-B** = capability convergence ("tools as in-context
  agent capabilities", *rides the pivot track* — hard-blocked by the practice_area/unit_of_work SCHEMA +
  area activation + F1-S4/S5; building it before those = schema debt or a dishonest hollow shell). Plan:
  `docs/fork/plans/F2-minimalist-pass-decomposition.md` (slices **F2-M0…M9**). This extends F006/F011 and
  sequences F002's F3 commitment.
- **F2-M0 (PR #67, main `749a5a1`)** — docs + baseline only (no app code): **ADR-F012** written;
  F2 decomposition doc written; **before** baseline screenshots captured (cockpit landing + a legacy
  `(tools)` chrome surface, light+dark × wide+narrow) in `docs/fork/evidence/f2-m0/` via the reusable
  `cypress/e2e/f2-baseline.cy.ts` (PHASE=before|after). The cockpit already lands on "Your practice"
  (areas + per-area agents + unfiled matters) — the architecture already leans toward the destination;
  F2-M4 adds a calm centered intent entry above it.
- **F2-VL1 (this slice, PR #77)** — the **F013 design-language primitives** land (ADR-F013, milestone
  F2-VL). Seven token-consuming primitives in `components/primitives/`: **`AppShell`** (the Vercel layout
  skeleton — 264px `--sidebar` rail with caller-supplied contents + main column + optional thin topbar; rail
  `hidden lg:flex` so it collapses < lg, VL2 wires the drawer), **`Hero`** (centred display-type block — the
  FIRST consumer of the VL0 `--text-display` token, so it materialises that JIT utility), **`Card`** +
  **`CardGrid`** (the hairline-divided plane: `grid gap-px bg-border rounded-lg overflow-hidden`, cells fill
  `bg-card`; Card `interactive` → real `<button>`/`<a>`, `bordered` → standalone hairline+12px), **`Stack`**/
  **`Inline`** (vertical/horizontal rhythm from the §3 scale — literal-class Records so JIT keeps them),
  **`StatusDot`** (dot-status on the `--status-*` tokens; `running` resolves to the scarce `--brand`). The
  **inverting-primary / hairline-secondary / ghost button idioms already exist** via the VL0-recoloured shadcn
  `Button` (`--primary` is ink) → demonstrated, NOT re-built. Pure class helpers (`stackClass`/`inlineClass`/
  `cardGridClass`/`cardClass`/`statusDotClass`) exported from `<script module>` + **unit-tested** (the
  `pageShellClass` precedent). Proven in a NEW dev-only **`/lq-ai/_vl-lab`** route (the `_ae-lab` precedent —
  unadvertised, auth-gated by the lq-ai layout, leading-`_`, served by the prod bundle, Cypress-captured;
  imported by NOTHING live) that rebuilds the `direction-vercel` cockpit target from the real primitives + an
  isolated gallery (type scale, button variants, dot tones, standalone cards). **No live surface re-skinned —
  that's VL2.** Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 850**
  (+13 helper assertions); **`vl1-lab.cy.ts` 1/1** (PHASE-less capture, light+dark × wide+narrow). Evidence:
  `docs/fork/evidence/f2-vl1/` — near-exact match to the mockup; charcoal dark honest; narrow collapses the
  rail + CardGrid → 2-col. Fresh-context review: **SHIP**, no blockers/should-fixes; two lab-only a11y nits
  (heading-in-button, unlabelled composer textarea) **FIXED in-slice**. web-only — no api/gateway change.
- **F2-VL0 (PR #76)** — the **F013 design-language token layer** lands (ADR-F013; milestone
  **F2-VL**, sequenced between M7a and M7b). **`app.css` recoloured to the Vercel palette** (spec §1): the two
  structural remaps that define the look — **`--primary` is now INK** (`#111` light / `#ededed` dark, inverts)
  not the old indigo, and a **new `--brand`** holds the one scarce Vercel blue (`#0070f3` / `#47a3ff`), used
  only for focus / links / running. Everything else monochrome; **charcoal `#111` dark floor** (never black),
  white canvas, hairline borders. Hex values match the approved `direction-vercel` mockup. Also: **type scale**
  `--text-display`…`--text-label` registered in `@theme` (consumed later as `text-*` utility classes — JIT, so
  the vars are pruned until VL1/R-TYPO use them; not a defect); **motion** tokens `--motion-fast/base/slow` +
  2 eases; `--radius` → **10px** base, `--radius-lg` pinned **12px** (cards); elevation **de-tinted** (neutral,
  was indigo); status `running` = `--brand`. `motionMs()` callers (5 files) wired onto a new **`MOTION` JS
  mirror** in `cockpit/helpers.ts` of the CSS `--motion-*` tokens — a **unit test parses `app.css` and locks
  the two in sync** (durations normalised 120→base 150, 160→base, 100→fast). Theme-color meta → `#111`/`#fff`.
  **Tokens only — no new layout** (VL1 builds the AppShell/primitives; VL2 the cockpit proof). The one app-wide
  visible shift: indigo-blue → ink primaries + scarce blue, on charcoal dark. Suites: web check **0 err** (5
  pre-existing a11y warnings, untouched files); **vitest 837** (+1: the MOTION↔CSS sync lock); f2-baseline
  cypress **4/4** (PHASE=after — reused as-is). Built bundle verified to carry `--brand`/`--primary:#111`/
  `--motion-*`/`--background:#111`. Evidence: `docs/fork/evidence/f2-vl0/` (cockpit, matters, conversation,
  playbooks, tabular, skills — light+dark × wide+narrow; ink inverting primaries, charcoal dark with no
  light-in-dark, green dot-status, blue scarce). web-only — no api/gateway change.
- **F2-M7a (PR #74)** — calm **table-list surfaces**: `playbooks`, `tabular`, `skills` list pages.
  **Split of F2-M7** by visual family (M7b = `knowledge`/`learn`/`saved-prompts` card/wrapper surfaces, next).
  Each page: (1) **adopt `<PageShell size="wide" pad="compact">`** for the centered container (the three
  list pages used `max-width: 64rem`/`max-w-5xl` = PageShell `wide` exactly; bespoke header kept — the
  header row carries an h1 + a trailing CTA + subtitle, which `SectionHeader` doesn't model, the same call
  M6 made for MattersPanel); (2) **migrate the COLOR `--lq-*` tokens → semantic** (`--lq-border`→`--border`,
  `--lq-surface`→`--card`, `--lq-inset`→`--muted`, `--lq-canvas`→`--background`, `--lq-accent`→`--primary`
  (teal→**blue** — unifies the page accent with the chrome, the M2 precedent), `--lq-on-accent`→
  `--primary-foreground`, `--lq-text`→`--foreground`, `--lq-text-secondary`/`-tertiary`→`--muted-foreground`,
  `--lq-error`→`--destructive`, `--lq-error-soft`→`--status-failed-wash`); (3) **tabular status pills → the
  existing `--status-*` tone family** (running/completed/failed/cancelled + `-wash`, defined for BOTH themes
  in `app.css` — an existing scale, NOT a new token scale → sidesteps the TrustPill problem). **Left for
  R-TYPO (documented, not a defect):** `--lq-radius*`/`--lq-space-*`/`lq-text-*` (no semantic equivalent, no
  light/dark variance, R-TYPO's domain — never re-introduced, just not double-touched). **`TrustPill`
  badges on skills stay teal/sage** (M2 deferral — needs the tone scale defined first). Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 836** (unchanged — presentation-only,
  no new pure helper, like M2/M5); f2-baseline cypress **4/4** (PHASE=after — added a playbooks + tabular
  capture test; skills captured by the existing `(tools)`-chrome test). Evidence:
  `docs/fork/evidence/f2-m7a/` (playbooks + tabular + skills, light+dark × wide+narrow — dark renders
  honest, no light-in-dark; CTAs blue). Fresh-context review: **SHIP**, no blockers/should-fixes/nits
  (every target token verified to exist in both themes; markup balanced; `lq-ai-user-skills` testid
  forwarded via PageShell `{...rest}`). web-only — no api/gateway change.
- **F2-M6 (PR #73, main `bf3f034`)** — matters + conversation surfaces **consolidated onto `PageShell`** (the M1
  carry-over). Added a **`pad` variant** to `components/primitives/PageShell.svelte`
  (`PageShellPad = 'default'|'compact'|'tight'`; `default`=`px-6 py-10 sm:px-8`, `compact`=`px-6 py-8
  sm:px-8`, `tight`=`px-4 py-4 sm:px-6`); `pageShellClass(size, pad='default', extra='')` (signature
  changed — only callers are PageShell itself + its test). **`MattersPanel`** container →
  `<PageShell pad="compact" data-testid="lq-cockpit-matters">` (bespoke header kept — SectionHeader models
  no back link / trailing action / truncating title); **`ConversationHost`** keyed conversation column →
  `<PageShell size="narrow" pad="tight">`. Both keep the `in:fade` on an inner div (the AreaGrid M1 idiom —
  PageShell is a component; transitions need an element). **Visually equivalent** — the pads were copied
  verbatim (the win is consolidation/consistency, not a visible redesign). **`AreaRail` intentionally
  untouched** (sidebar — already minimal, doesn't fit PageShell/SectionHeader). Suites: web check **0 err**;
  **vitest 836** (+1 pad-variant assertion); f2-baseline cypress **3/3** (PHASE=after — added a matters +
  conversation capture test). Evidence: `docs/fork/evidence/f2-m6/` (matters + conversation, light+dark ×
  wide+narrow). Fresh-context review: **SHIP**, no blockers/should-fixes/nits (visual equivalence verified
  exactly; the responsive geometry test still matches the testid). web-only.
- **F2-M5 (PR #72, main `2f363e4`)** — CockpitHeader **minimal-chrome restyle** (already semantic → **restyle-only,
  reversible**; one file, no logic/props/routes changed). `cockpit/CockpitHeader.svelte`: muted icon
  buttons now also **`hover:text-foreground`** (one calm resting state → brighten on hover, matching the
  M2/M3 tab-bar idiom; applied to the rail toggle, Tools trigger, theme, settings, sign-out); the right
  cluster gap tightened `gap-1.5`→`gap-1`; the **three trailing utility icons (theme/settings/sign-out)
  grouped into one tight `gap-0.5` cluster behind a hairline `bg-border` separator** so account/prefs read
  apart from tools/trust; single primary accent stays on the brand. **No AI furniture (ADR-F002)** — the
  header still picks no models/skills/context; `AmbientTrustChrome` (ADR-0011 disclosure) + the Tools menu
  (with the M3 muted-legacy treatment) + the trust link all intact. No new token scale, no `--lq-*`, no
  `{@html}`, nothing retired. Suites: web check **0 err**; **vitest 835** (unchanged — presentation-only,
  no pure helper, like M2); f2-baseline cypress **2/2** (PHASE=after). Evidence:
  `docs/fork/evidence/f2-m5/` (cockpit, light+dark × wide+narrow — separator + tight cluster visible both
  themes; the legacy `(tools)` surface uses `TopTabBar`/`(tools)` chrome, NOT this header, so its shots are
  unchanged). Fresh-context review: **SHIP**, no blockers/should-fixes (1 benign cosmetic nit). web-only.
- **F2-M4 (PR #71, main `df65826`)** — cockpit centered intent **launcher** (ADR-F002: a launcher, **NOT a
  composer** — it never starts an unbound thread). New **`cockpit/CenteredEntry.svelte`** rendered ABOVE
  a **de-emphasised** `AreaGrid` (its "Your practice" header dropped from `page`→`section`, so the page
  keeps a **single h1** — the launcher's "What are you working on?"), wired through a new
  **`landingView`** snippet in `cockpit/Cockpit.svelte` (replaces the two duplicated `AreaGrid` render
  blocks — areas-view + fallback — a real simplification). On submit a new **pure `launchIntent(areas,
  text) → {url, draft}`** helper (`cockpit/helpers.ts`, unit-tested) decides: **exactly one CONFIGURED
  area → enter it** (`cockpitUrl({area})`) carrying the text; **0 or several → no nav**, draft held +
  hint points the user at the grid below. The text carries via a parent-held **`pendingDraft`** in
  `Cockpit.svelte` → passed to `ConversationHost` as **`initialDraft`**, which seeds the composer
  `prompt` **once on mount** (`!prompt` guard) and clears it via **`onDraftConsumed`** — so only the
  FIRST matter after a launch is seeded, never a second, never overwriting in-progress text; unfiled
  (resume-only) gets no draft. Optional starter chips = the user's own **SavedPrompts** (AE7 precedent,
  fetched fail-soft → none). Suites: web check **0 err**; **vitest 835** (+6 `launchIntent`); f2-baseline
  cypress **2/2** (PHASE=after) + a throwaway interaction spec confirmed end-to-end carry-forward
  (submit → `area=commercial` → open matter → composer pre-seeded), then removed. Evidence:
  `docs/fork/evidence/f2-m4/` (cockpit, light+dark × wide+narrow — launcher hero + chip + de-emphasised
  grid). Fresh-context review: **SHIP**, no blockers; 1 should-fix (stale-draft carry window) documented
  in-code as accepted intended behavior; hint-after-typing nit FIXED in-slice (`oninput` clears it).
  web-only — no api/gateway change.
- **F2-M3 (PR #70, main `7c03cef`)** — tab-bar visual condense (restyle/group ONLY — **no tab retired/hidden/
  reordered**). Added a **presentational** `group?: 'core'|'legacy'|'gated'` field + `tabGroupOf()` to
  `lib/lq-ai/tabs.ts` (playbooks/tabular → `legacy`; autonomous/admin → `gated`; absent ⇒ `core`) — purely
  visual, does NOT touch `isTabVisible`/`isTabAvailable`/`activeTabFor`/`visibleTabsFor`. **`TopTabBar`**
  condensed (`gap-4`→`gap-0.5`, `px-1`→`px-2.5`) with **in-place section separators** (inert
  `role="presentation" aria-hidden` `<li>` rules at each group boundary) + the **legacy group rests one
  step quieter** (`text-muted-foreground/70`), all via a new exported pure **`tabStateClass()`** (unit-
  tested). One `<ul role="tablist">` preserved → arrow-key nav intact (separators carry no button, so the
  `button[role="tab"]` nodelist still maps to `tabIndex`). **`CockpitHeader`** Tools dropdown mirrors the
  muted-legacy treatment. **Resolves the M2 active-tab nit** (active wins in `tabStateClass`). Also
  strengthened the reusable `f2-baseline.cy.ts` tools-skills wait (on `nav[aria-label="Primary"]`, not
  `body`) after a blank light-wide capture. Suites: web check **0 err**; **vitest 829** (+6: `tabGroupOf`
  + `tabStateClass`); f2-baseline cypress **2/2** (PHASE=after). Evidence: `docs/fork/evidence/f2-m3/`
  (legacy `(tools)` skills surface, light+dark × wide+narrow — grouping + muted legacy visible both
  themes). Fresh-context review: **SHIP**, no blockers/should-fixes/nits. web-only.
- **F2-M2 (PR #69, main `feacb02`)** — chrome calm + `--lq-*` → semantic token unification (the dark-mode fix).
  Migrated four chrome files off the legacy `--lq-*` system to semantic Tailwind utilities + applied scira
  calm: **`TopTabBar.svelte`** (scoped `<style>` dropped; muted resting tabs, **single primary accent** on
  the active tab + lighter underline, `text-muted-foreground/60` for unavailable), **`AmbientTrustChrome`**
  (wrapper + ⌘K hint), **`DualBrandingFooter`** (raw `gray-*` → `text-muted-foreground`/`border-border`),
  **`(tools)/+layout.svelte`** shell (`.lq-shell`/`.lq-topbar`/`.lq-brand` + inline `var(--lq-*)` styles →
  `bg-background`/`text-foreground`/`text-primary` — the **robust fix** for the AE5 `--lq-canvas`
  light-in-dark cascade quirk). The legacy chrome accent now **unifies to the cockpit's blue `--primary`**
  (was teal/sage). Zero live `var(--lq-*)` refs remain in the four files (only `data-testid`/`id="lq-main"`/
  import paths/comments). **`TrustPill.svelte` NOT touched — deferred on record** (see carry-overs).
  Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 823** (unchanged —
  TopTabBar's pure `visibleTabsFor` test still green; styling is screenshot-verified); f2-baseline cypress
  **2/2** (PHASE=after). Evidence: `docs/fork/evidence/f2-m2/` (cockpit + legacy `(tools)` skills, light+
  dark × wide+narrow); dark mode renders correctly (no light-in-dark). Fresh-context review: **SHIP**, no
  blockers (1 unreachable-state nit on record). web-only — no api/gateway change.
- **F2-M1 (PR #68, main `a8db5c7`)** — calm layout primitives. New `components/primitives/PageShell.svelte`
  (centered `mx-auto w-full max-w-* px-* py-*` container) + `SectionHeader.svelte` (title + optional
  subtitle, `page`=h1 / `section`=h2 type scale), each with an exported pure helper (`pageShellClass`,
  `sectionHeaderScale`) **unit-tested** (vitest +7 → 823). Adopted in **one** real consumer,
  `cockpit/AreaGrid.svelte` (the "Your practice" page title + the "Unfiled matters" section header +
  the page container). Faithful extraction: after-shots **pixel-identical** to the M0 before-baselines
  (`docs/fork/evidence/f2-m1/`). No new token scale; semantic tokens only; no `{@html}`; no IA change.
  Fresh-context review: **SHIP**, no blockers (2 nits on record — see carry-overs). Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 823**; f2-baseline cypress **2/2**
  (PHASE=after). web-only — no api/gateway change.

- **AE-series (ADR-F011) — CLOSED. AE0 (#59) + AE1 (#60) + AE2 (#61) + AE3 (#62) + AE4 (#63) + AE5 (#64) +
  AE6 (#65) + AE7 (#66) ALL MERGED.** The series brought the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **AE7 = honest Suggestions, NO new dep:** reused the AE0-vendored `suggestion/` as-is. The chips are
  empty-conversation **starters** backed by the user's own **SavedPrompts** (an honest, user-owned source)
  — NOT model-invented follow-ups (no honest source for those exists, so none are shown). **`shiki` (AE4)
  remains the ONLY new runtime dep across the whole AE series**; AE5/AE6/AE7 added none.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE7** (the bundle carries the ChatPanel
  chips + the SavedPromptsPanel `onPromptsLoaded` hook). Login: http://localhost:3000/lq-ai/login ·
  admin@lq.ai / LQ-AI-local-Pw1!  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only
  S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 816** (unchanged — AE7 behavior is covered by Cypress, no unit-level pure helper added);
  **Cypress `ae7-suggestions.cy.ts` 5/5** headed/live-stubbed (4 functional + 1 capture; the first test
  eats the documented first-`cy.visit` session-establishment latency → it ran ~30s and passed; the rest
  are fast). **api/gateway UNAFFECTED — AE7 touches only `web`** (no backend change). AE7 **after**
  screenshots (empty-chat starter chips, light+dark, wide+narrow) in `docs/fork/evidence/ae7/`.
  Adversarial review (fresh-context agent): **SHIP**, no blockers/should-fixes; nit #1 (a benign chip
  flash while a populated chat's messages load) was FIXED in-slice by adding the `message_count` gate.
  Security pass: NO `{@html}` introduced — the chip label (`prompt.name`) + inserted body
  (`prompt.prompt_text`) are escaped text/attribute bindings via the vendored `Suggestion`→`Button`;
  SavedPrompts are user-owned + server-scoped (404-not-403); no secrets/stray files; web-only.

## Done (F2-VL1, this slice)

- **`components/primitives/{AppShell,Hero,Card,CardGrid,Stack,Inline,StatusDot}.svelte`** — seven new
  presentation-only runes primitives consuming the VL0 tokens (see the F2-VL1 State bullet for each one's
  role). Each `<script module>` exports a pure class helper where one applies (`stackClass`, `inlineClass`,
  `cardGridClass`, `cardClass`, `statusDotClass`); all variant classes are literal strings in `Record`s so
  Tailwind's JIT keeps them.
- **`routes/lq-ai/_vl-lab/+page.svelte`** — NEW dev-only proof route (the `_ae-lab` recipe). `h-screen` (the
  layout renders booted non-exempt routes as a bare `<slot>` — the cockpit "owns its own viewport"), composes
  AppShell + the cockpit target + a gallery. Local non-persisting theme toggle. Imported by nothing live.
- **`__tests__/vl-primitives.test.ts`** — locks the five pure helpers (exact-string assertions). vitest
  837→850 (+13). **`cypress/e2e/vl1-lab.cy.ts`** — logs in, visits `_vl-lab`, asserts the `text-display`
  Hero renders, captures light+dark × wide+narrow (1/1). Evidence `docs/fork/evidence/f2-vl1/`.
- **No new ADR** (ADR-F013 governs; this is its VL1 slice). **No new `--lq-*`, no `{@html}`, no token scale
  added, no surface retired/re-skinned.** Two lab-only a11y nits fixed in-slice (`<span>` not `<h3>` inside the
  interactive Card; `aria-label` on the composer textarea).

## Done (F2-VL0, PR #76)

- **`web/src/app.css`** — recoloured both `:root` (light) and `.dark` to the Vercel palette (hex, matching
  `direction-vercel`): ink `--primary` `#111`/`#ededed` (was indigo), new `--brand` `#0070f3`/`#47a3ff`,
  neutral gray ramp, charcoal `#111` dark floor, white canvas/cards, `#fafafa`/`#0c0c0c` sidebar. `--ring` =
  brand. Status `running` = brand blue (the rest green/red/neutral); washes re-derived per theme. Elevation
  de-tinted to neutral oklch (was hue-262 indigo). In `@theme`: added `--color-brand`/`--color-brand-foreground`
  mappings, the `--text-display`…`--text-label` scale (size + line-height + weight + tracking companions),
  `--radius-lg` pinned `0.75rem`; `--radius` `0.5rem`→`0.625rem`. In `:root`: `--motion-fast/base/slow` +
  `--motion-ease-standard/-emphasized`.
- **`cockpit/helpers.ts`** — new exported `MOTION = { fast:100, base:150, slow:240 }` (the JS mirror of the CSS
  `--motion-*` tokens; Svelte JS transitions take a number, not a CSS var). `motionMs()` unchanged (still the
  reduced-motion gate). Theme-color meta literals → `#111111`/`#ffffff`.
- **5 motion consumers** (`MattersPanel`, `ConversationHost` ×2, `Cockpit` ×2, `AreaGrid`, `ChatPanel`) — import
  `MOTION` and pass `motionMs(MOTION.base|fast)` instead of magic 120/160/100 (normalised; ≤30ms shift).
- **`cockpit/__tests__/helpers.test.ts`** — new `MOTION scale (F013 VL0)` suite: reads `app.css`, regex-parses
  `--motion-fast/base/slow`, asserts `MOTION` matches (the anti-drift sync lock). vitest 836→837.
- **No new ADR** (ADR-F013 already accepted in PR #75; this is its first code slice). **No new `--lq-*`, no
  `{@html}`, no token scale removed, no surface retired.** Evidence: `docs/fork/evidence/f2-vl0/`.

## Done (F2-M7a, PR #74)

- **`(tools)/playbooks/+page.svelte`** — `<section class="lq-playbooks-page">` → `<PageShell size="wide"
  pad="compact">` + inner `.lq-playbooks-page` (now flex/gap only; width/margin/padding from PageShell).
  CTA + apply button → `--primary`/`--primary-foreground`; subtitle/states → `--muted-foreground`/`--muted`;
  error block → `--destructive`/`--status-failed-wash`; table → `--card`/`--border`.
- **`(tools)/tabular/+page.svelte`** — same PageShell adoption + token migration; **status pills** (`completed`/
  `failed`/`cancelled`/`running`+`pending`) remapped from `--lq-success`/`--lq-error`/`--lq-warning`/`--lq-inset`
  onto `--status-completed`/`--status-failed`/`--status-cancelled`/`--status-running` + their `-wash` bgs.
- **`(tools)/skills/+page.svelte`** — outer `<div class="p-4 max-w-5xl mx-auto" data-testid="lq-ai-user-skills">`
  → `<PageShell size="wide" pad="compact" data-testid="lq-ai-user-skills">` (testid forwarded via `{...rest}`).
  Inline `style="color: var(--lq-text*)"` + `<style>` `.lq-btn-*`/`.lq-link`/`.lq-table-skill-card`/`.lq-thead`/
  `.lq-tbody`/`.lq-scope-personal`/`.lq-empty-state` color tokens migrated; `--lq-radius*`/`--lq-space-6` left
  (R-TYPO); `TrustPill` "Table"/scope badges untouched (deferred). Partial-semantic markup (rose error blocks,
  Tailwind utilities) left as-is.
- **`cypress/e2e/f2-baseline.cy.ts`** — new capture test deep-links `/lq-ai/playbooks` (waits
  `lq-playbooks-generate-cta`) + `/lq-ai/tabular` (waits `lq-tabular-new-cta`), captures both light+dark ×
  wide+narrow. Skills captured by the existing `(tools)`-chrome test. **No new ADR** (visual consolidation
  within ADR-F012). Evidence: `docs/fork/evidence/f2-m7a/`.

## Done (F2-M6, PR #73)

- **`components/primitives/PageShell.svelte`** — new `pad` variant (the M1 carry-over). `PageShellPad =
  'default'|'compact'|'tight'` + a `PAD` map; `pageShellClass(size, pad='default', extra='')` (signature
  changed — grep-confirmed the only callers are PageShell's own template + the test). New `pad` prop
  (default `'default'`, so AreaGrid is unaffected). The `default`/`compact`/`tight` pads ARE the matters/
  conversation rhythms verbatim — do NOT override pad via `class` (Tailwind utility order is unreliable).
- **`cockpit/MattersPanel.svelte`** — container div → `<PageShell pad="compact" data-testid=
  "lq-cockpit-matters">` with the `in:fade|global` on an inner div (the AreaGrid M1 idiom). Bespoke header
  kept (back link + truncating `<h1>` + trailing "New {noun}" button — SectionHeader models none of these).
  Body reindented +1 level (large but purely mechanical; prettier-clean).
- **`cockpit/ConversationHost.svelte`** — the `{#key panelKey}` conversation column div →
  `<PageShell size="narrow" pad="tight">` with `in:fade` on an inner div; added the PageShell import. The
  key remount + `bind:prompt`/`bind:selectedMatterId` on ConversationPanel are unchanged (PageShell just
  renders children).
- **`cockpit/AreaRail.svelte`** — intentionally NOT touched (sidebar nav on `sidebar-*` tokens, already
  minimal; PageShell/SectionHeader don't fit a rail). Recorded so M9's sweep doesn't expect a change.
- **`__tests__/PageShell.test.ts`** — calls updated to the 3-arg signature + a `pad`-variant `.toBe()`
  assertion locking the exact compact/tight strings (vitest 836). **`cypress/e2e/f2-baseline.cy.ts`** — new
  capture test deep-links `?area=commercial`, captures the matters list, opens a matter, captures the
  conversation view (light+dark × wide+narrow). **No new ADR** — consolidation within ADR-F012; recorded
  here + in-file F2-M6 comments + memory. Evidence: `docs/fork/evidence/f2-m6/`.

## Next slice — pick up exactly here

**F2 + UX-A are COMPLETE; UX-B-1 (harness) + UX-B-2 (areas) + UX-B-3 (skills) + UX-B-4 (subagents) are
SHIPPED.** All five areas are configured + scenario-reported; skills are **live** (per-area subset, ADR-F016);
Commercial carries a **live `document-researcher` subagent** with its own isolated skill source (ADR-F017),
delegated on-demand. The remaining gap to "truly works + cockpit perfect" is the **web surface**: the cockpit
doesn't yet let a user pick the practice area at matter creation, nor render the subagent boundary in a run.

### → NEXT: UX-B-5 — cockpit perfection (web). Branch FIRST.

**Milestone context:** UX-B = capability convergence ("Deep Agents truly work / cockpit perfect"), the gate
for the agentic-**modules** / Oscar-Privacy direction ([[oscar-privacy-modules-vision]]). Decomposition:
**`docs/fork/plans/UX-B-deep-agents-truly-work-decomposition.md`** §UX-B-5; design language: **ADR-F012/F013**
(Vercel charcoal #111 + scarce blue; no black bg). The backend loop is proven + honest end-to-end; UX-B-5
**surfaces it on the web**, honestly (transparency rule — nothing faked).

**Build UX-B-5 — surface the proven loop on the F013 design language (web-only; no api/gateway change):**
- **Area selection at matter creation** — wire the existing `practiceAreasApi` (web) into the new-matter
  flow so a user picks the practice area (only `configured` areas fileable; the cockpit already lands on
  areas via `AreaGrid`). The matter→area binding already drives the whole agent identity server-side
  (`composition.py`); this just lets the user set it.
- **Subagent boundary rendering** in the run view — parse `parent_step_id` (now populated when the agent
  delegates) into distinct **subagent frames** in the SSE stream, not just flat nested steps. NOTE the SSE
  protocol gap (CLAUDE.md blocker #4): frames are start/delta/complete/error only — a tool-call/subagent
  frame type may need adding end-to-end (`web/src/lib/lq-ai/sse/parser.ts` + the api SSE projection). Scope
  to what's honest + shippable; if the full subagent-frame projection is too big for one slice, render the
  nested `parent_step_id` steps as an indented boundary and note the richer projection as follow-up.
- **Area-config visibility** — at minimum read-only surfacing of an area's profile/skills/subagents
  (transparency); the admin PATCH surface if it fits the slice.

**Reuse / anchors:** the cockpit shell is `web/src/routes/lq-ai/(app)/` (UX-A); `practiceAreasApi` +
`GET /agents/matters` (ADR-F004) already exist; AE-series chat components (`components/ai-elements/`) render
the run. **Verify (web DoD):** `cd web && npm run check` (0 err) + `npx vitest run`; rebuild the `web`
container; headed Cypress (`DISPLAY=:0`, electron) before/after light+dark × wide+narrow →
`docs/fork/evidence/ux-b-5/`; fresh-context adversarial + **security + simplification** pass
([[security-review-every-slice]]). Merge per ADR-F005 against `sarturko-maker/lq-ai-fork`
(`gh pr create --repo sarturko-maker/lq-ai-fork --head <branch>`). **Then:** UX-B-6 verify + consistency sweep.

**Grounded state of the loop:** the cockpit loop WORKS end-to-end; all 5 areas configured + scenario-reported;
**skills live** (per-area + per-subagent subsets); **subagent delegation wired + proven** (deterministic
ancestry test) though M3 elects not to fan out at small matter sizes (UX-B-4 finding). Gap to "truly works":
**web area-pick + subagent-boundary rendering missing** ← UX-B-5. Anchors: `composition.py`
(`build_area_skill_wiring` + `skill_registry_provider`), `skill_backend.py` (multi-source `RegistrySkillBackend`),
`area_agent.py` (`build_area_subagents` + ⊆-area drift validation), `factory.py:build_deep_agent`,
`runner.py` (`skills`/`backend` params + `_innermost_tool_parent`), migrations `0056`/`0057`, ADR-F016/F017.

**A caution carried from UX-B-3/4 (server-side, informs the web copy):** a tier-4 model (MiniMax-M3)
over-explores a big skill surface and does NOT spontaneously delegate at small matter sizes. UX-B-5 must
present the loop **honestly** — don't imply subagent fan-out happens when it usually won't on a small matter;
render delegation when it occurs, degrade gracefully when it doesn't.

**Branch FIRST; full ADR-F005 gate; the `web` container serves a PRE-BUILT bundle — rebuild it before
debugging any UI change. Merge against `sarturko-maker/lq-ai-fork`.**

**Deferred F2 debt (small, unblocked, pick up between UX-B slices if useful):** R-TYPO (`lq-text-*`→ `--text-*`
tokens) + TrustPill tones (the last non-`--brand` accent); R-series child-body migrations (R16/R19).

**Lower-priority parallel tracks:**
- **UX-B (capability convergence)** — the post-F2 frontier (ADR-F012): "tools as in-context capabilities the
  area agent picks/exposes." Folds into the pivot track (F1-S4/S5 + area-skill activation + the
  `practice_area`/`unit_of_work` schema). Grounding done 2026-06-16 (see the F2-M8 pickup note above);
  nearest beachhead = the S9-gated skills-activation slice (no new schema). UX-A is COMPLETE.
- **R-series rollout slices** (any order — the dark-mode bridge holds un-migrated surfaces; **coordinate with
  F2 — don't double-touch chrome, never re-introduce `--lq-*`**): Foundation/rail R2–R5, Wave 1 R-CONV-1
  (logic; R-CONV-2 → AE6), Wave 2 R12/R13/R14a-b/R15/R15b-tab-pb/R16, Wave 3
  R17a-b/R18/R19a-b/R20/R-CHROME, cleanup R-TYPO → R-BRIDGE → R-LAST. autonomous R21 = SKIP.
- **F1-S4** (subagent tree + SSE v3-projection adapter) / **F1-S5** (idempotency ledger +
  attribution fan-out) — `docs/fork/plans/F1-replan.md`. **Area skills/subagents ACTIVATION**
  (S9-gated) — wires `composition.py` to pass area skills/subagents + re-runs the S9 matrix (this IS the
  UX-B beachhead above).

## Rollout progress

- **R-series:** Step 0 ✅ (#50) · R0 ✅ · R1a ✅ (#51) · R6 ✅ (#52) · R7 ✅ (#55) · responsive parity ✅
  (#53) · **R8 ✅ (#57)**. CI unblocked (repo public).
- **AE-series (ADR-F011):** plan+ADR ✅ (#58) · **AE0 ✅ (#59)** vendoring foundation · **AE1 ✅ (#60)**
  Conversation+Message+Response · **AE2 ✅ (#61)** Reasoning+Actions · **AE3 ✅ (#62)** Sources +
  Inline-Citation · **AE4 ✅ (#63)** Code Block (Shiki highlight, option-2 action; the one new dep
  `shiki`) · **AE5 ✅ (#64)** Prompt Input (≡ R9 — option-2; dark-mode column gap FIXED) · **AE6 ✅ (#65)**
  Tool+Task (≡ R-CONV-2 — option-2 hand-build, no new dep; `groupTurnSteps`; renderModelMarkdown
  convergence) · **AE7 ✅ (PR #66)** Suggestions (honest starter chips backed by SavedPrompts; AE0
  `suggestion/` reused, no new dep). **AE-series CLOSED (AE0–AE7 done) — no AE8.**

## Carry-overs / review deferrals

- **F2-VL1 — `CardGrid` trailing empty cell on non-full rows (resolve in VL2).** The hairline technique
  (`grid gap-px bg-border` + cells filling `bg-card`) means a final responsive row that isn't full shows the
  `--border` background as an empty gray cell (seen in the narrow lab: 3 areas at 2 columns → one empty cell).
  Acceptable in the lab; VL2 must decide the real behaviour against the actual area count — pick a column count
  that divides it, render filler cells, or let the last card span. Not a token/primitive defect.
- **F2-VL1 — AppShell rail is `hidden lg:flex` (no narrow nav yet).** The primitive only models the skeleton;
  below `lg` the rail disappears with no toggle. VL2 wires the real drawer/toggle (reuse the F1-S2.1 AreaRail
  responsive collapse). The lab's narrow shot therefore shows the cockpit full-width (the honest collapsed
  state), not a hamburger.
- **F2-VL1 — the interactive `Card` renders as `<button>`; put a `<span>` (not `<h3>`) as its title.** A
  heading isn't valid phrasing content inside a button. The lab's practice grid uses `<span class=
  "text-subheading">`; carry that into VL2's area cards. Standalone non-interactive cards keep real headings.
- **F2-VL0 — checkbox + focus-ring hardcoded blues left as-is (own slice).** The `@layer base`
  `input[type=checkbox]` uses literal `#2563eb` (checked fill) / `#3b82f6` (focus outline). They were NOT
  migrated to `--primary`/`--ring` because the checked fill carries a `fill='white'` SVG checkmark — and
  `--primary` inverts to near-white in dark, which would make the checkmark invisible on a white well.
  Resolving it needs a non-inverting "control ink" token (or a theme-aware checkmark color), so it's deferred
  to a control-styling slice (likely VL1's button/control-variant work). They render as a blue close to the
  new `--brand`, so no visible clash today.
- **F2-VL0 — type-scale vars are JIT-pruned until consumed (expected, not a defect).** Tailwind v4 only emits
  a `text-<name>` utility (and its `--text-*` var) when the class is actually used in markup. VL0 registers the
  scale in `@theme` but consumes none of it, so `--text-display` etc. don't appear in the built `:root` yet —
  they materialise the moment VL1 primitives use `class="text-display"`. Don't reference `var(--text-display)`
  raw in CSS expecting it to resolve before a utility consumes it; use the utility class (the spec §2/§7
  contract).
- **F2-VL0 — motion durations normalised (≤30ms).** Wiring the 7 call sites onto the `MOTION` scale shifted
  fades 120→150ms (base) and the area fly 160→150ms; the inner fade stayed 100ms (fast). Imperceptible and
  intended (the point of the scale); static screenshots are unaffected. The reduced-motion gate is unchanged.
- **F2-VL0 — status pills / multi-area hint still not screenshot-able on the dev stack** (carried from M7a/M4):
  tabular has no executions, only Commercial is configured. The new status-`running`=`--brand` tone and the
  dark status washes are verified against `app.css`/the built bundle, not headed. Recapture in VL2/M9 when the
  data exists.
- **F2-M7a — tabular status pills not screenshot-able (dev stack has no executions).** The migrated
  `--status-*` pill tones (`completed`/`failed`/`cancelled`/`running`) render only with tabular execution
  rows; the dev stack shows the empty state. The mapping is verified against `app.css` (both themes) by the
  fresh-context review; recapture once executions exist (or in M9's sweep). The `formatTabularStatus` label
  helper is already unit-tested.
- **F2-M7a — color-only migration is intentional, not partial.** `--lq-radius*`/`--lq-space-*`/`lq-text-*`
  remain on these three pages — they have no semantic-palette equivalent and no light/dark variance, so they
  are R-TYPO's domain (not re-introduced, just not double-touched). Same staged-rollout transitional state
  M2 accepted. `TrustPill` badges (skills) stay teal/sage (M2 deferral — needs a tone scale first).
- **F2-M4 — stale-draft carry window (accepted, documented in-code).** `pendingDraft` clears only on
  consume (`onDraftConsumed`), so if the user launches into the 0/many-area case (draft held, no nav) and
  then opens *some other* existing matter before fulfilling the launch, that matter's composer receives
  the draft. Accepted: it is the user's last typed intent, fully editable, and the multi-area carry is the
  intended feature (a fragile "clear on any nav" would break it). Documented at the `pendingDraft`
  declaration in `Cockpit.svelte`. If a future slice wants tighter scoping, distinguish the
  "fulfilling-the-launch" matter open from an "abandon" open (hard with the shared `openMatter`).
- **F2-M4 — multi-area hint not screenshot-able on the dev stack.** Only Commercial is configured, so the
  `awaitingAreaPick` hint ("Pick a practice area below…" / 0-area "Configure a practice area…") couldn't be
  captured headed — it's covered by the `launchIntent` unit test + the in-code logic. Re-capture when a
  second area is configured (or in M9's sweep).
- **F2-M2 — `TrustPill.svelte` migration DEFERRED (own slice).** Its sage/slate/amber/red tone palette
  (`--lq-accent/tier/warn/error` + `-soft`/`-border`) has **no equivalent in the base semantic palette**
  (which only carries primary/destructive/muted/accent) — migrating it would mean **adding a tone-color
  scale to `app.css`, which F2 forbids ("no new token scale")**. It is dark-bridged in `practice.css`
  (`:root.dark`, renders acceptably) and feeds **~15 consumers** (MatterCard, MatterRail*, EnhancePrompt
  Expansion, Trust*Card, skills page, TierBadge, AmbientFooter…). Treat as its own future slice — likely
  alongside R-series tone work or when M7/M8 calm those surfaces; it needs the tone scale defined first.
  **Transitional state after M2:** the legacy chrome accent is blue (`--primary`) while un-migrated page
  content (skills "+ New skill" button, all TrustPills) stays teal/sage — expected during staged rollout.
- **F2-M2 — active-tab nit RESOLVED in M3.** The active-AND-unavailable/legacy precedence is now explicit
  in the pure `tabStateClass()` (active branch first), unit-tested.
- **F2-M1 — nit (1) RESOLVED in F2-M6.** The `PageShell` `pad` variant (`default`/`compact`/`tight`) landed
  in M6; MattersPanel (`compact`) and ConversationHost (`tight`) now adopt it. (2) The refactor
  adds two structurally-empty wrapper `<div>`s (the `in:fade` div + SectionHeader's root, which renders
  `class=""` when no class is passed) — no box-model effect, render is pixel-equal (screenshots confirm),
  fully reversible. Visually identical, not literally byte-identical DOM — acceptable under the pixel-equal
  contract.
- **AE7 — no new carry-overs.** Review SHIP, no blockers/should-fixes; nit #1 (chip flash while a
  populated chat's messages load) FIXED in-slice via the `message_count` gate. Honest-source design is
  load-bearing: chips are the user's own SavedPrompts shown as empty-state starters, never model-invented
  follow-ups — if a future slice wants contextual follow-ups, it needs a real backend source first (don't
  fabricate). The remaining composer-adjacent panels (ModelPicker/SkillPicker/SavedPromptsPanel internals)
  stay on the `--lq-*` dark stopgap (their own future R slices).
- **AE6 — no new carry-overs.** Review SHIP, the one nit (dead `stepDigest`) fixed in-slice. Per-tool
  status has no error state (the record carries no per-tool error signal) — a failed/stale run surfaces
  via the run-level badge + stale banner + the rail's `failed` state, which is honest and documented in
  `toolView`. The cockpit `ConversationHost` stacked collapse (<720px) was verify-only (unchanged); the
  legacy `.ag-layout` 1-col collapse (<900px) is the AE6 narrow shot. ModelPicker/SkillPicker etc. remain
  on the `--lq-*` dark stopgap (their own future slices).
- **AE5 — ChatPanel dark-mode column gap RESOLVED.** The standing AE2 carry-over (central chat *column*
  rendered LIGHT in dark mode while the chrome was dark) is FIXED in AE5: the `<section>` got
  `bg-background text-foreground` and the header/composer migrated off `--lq-*` to semantic tokens.
  Confirmed by `docs/fork/evidence/ae5/ae5-{before,after}-chat-dark-{wide,narrow}.png`. **Note:** the
  remaining composer-adjacent panels still on `--lq-*` (ModelPicker pill, SkillPicker, SavedPromptsPanel)
  render acceptably on the `--lq-*` dark stopgap and are each their own future R/AE slice — NOT migrated here.
- **AE5 — no other new carry-overs.** UX change recorded above (tools stay visible while streaming).
- **AE3 — no new carry-overs.** The fresh-context review's one should-fix (soft-deleted filenames
  surfacing + misleading CASCADE comment) and both nits (unused `isFallbackLabel`; over-vendored
  `inline-citation`/`-text`) were FIXED in-slice, not deferred.
- **AE1 nit (on record):** unused `debugInfo` getter in `stick-to-bottom-context.svelte.ts` — kept
  diffable vs MIT upstream.
- **AE0 nits (on record, byte-faithful to MIT upstream):** `loader-icon.svelte` redundant inline
  `style="color: currentcolor"`; shared static clipPath id across mounted Loaders (renders fine; scope
  with `$props.id()` if a future AE component needs per-instance clip geometry).
- **R8 deferred-on-record:** focus-on-open not asserted in Cypress (Xvfb programmatic focus); drawers not
  full focus-traps (ESC + scrim + `inert` cover practice).
- auth/refresh: per-user session cap + web gate timeout SHIPPED (#47). REMAINING: the
  **deterministic-HMAC index** (removes the global bcrypt scan + bad-token DoS; needs a migration +
  security review — Backlog). **AE3 re-confirmed:** under a LONG spec (7 min, many `cy.visit`) AND
  concurrent Docker load (the api suite running), page loads start timing out (elements "never found") —
  the documented degradation, NOT a code defect. Re-running the spec ALONE on a fresh/uncontended backend
  → **5/5**. More evidence for the HMAC index.
- F1-S3 deferrals: subagent-spec skill names bypass registry validation (validate on activation slice);
  `audit_log.practice_area_id` unindexed; area tier floor operator-set until a model > tier 4.
- ADR-0011 disclosure after F1-S5 attribution. Live SSE token deltas DEAD until a Redis pub/sub
  publisher lands (F1-S4). ADR-0011/F003 conversation memory + compaction → F2.

## Gotchas (carried + new)

- **NEW (AE6): Cypress reports a CLOSED `<details>`'s content as "visible".** Chromium collapses a
  `<details>` by giving non-`<summary>` children a zero box WITHOUT `display:none`, so Cypress'
  `.should('not.be.visible')` FAILS on collapsed content. Assert on the `open` ATTRIBUTE instead
  (`.should('not.have.attr','open')` → click `> summary` → `.should('have.attr','open')`); check inner
  content with `.should('exist')`/`contains`, not visibility. (Cost AE6 two red tests on the first run.)
- **NEW (AE6): a second `cy.visit` to `/lq-ai/agents` mid-test intermittently bounces to `/login`.** The
  capture test originally re-visited per theme; the dark iteration's visit re-triggered auth and
  redirected (the documented first-visit session flake, here fatal because it's not the run's first test).
  Fix: visit + open the thread ONCE, then toggle the theme IN PLACE (`localStorage.theme` + the `.dark`
  class on `<html>`) and screenshot per theme/viewport — no second auth-triggering visit.
- **NEW (AE6): the AE `tool`/`task` registry items are option-2 territory.** `tool` pulls `collapsible` +
  `badge` + `runed` + `./code.json` (the AE4 code block we hand-built, NOT vendored); `task` pulls
  `collapsible` + `bits-ui`. `collapsible` is the same shadcn component dodged for reasoning/sources. Hand-
  build the AE Tool card + Task list on native `<details>` (the ConversationPanel already used that idiom).
- **NEW (AE5): the dark-mode "light chat column" root cause.** The center `<section>` was transparent and
  showed the `(tools)` layout's `.lq-shell { background: var(--lq-canvas) }`, and `--lq-canvas` resolved to
  its LIGHT value on the chat route (a cascade/bundle-order quirk of the legacy `@import practice.css`
  chain — practice.css banks on `:root.dark` winning, but it wasn't on this surface). Fix = stop depending
  on `--lq-*` for the column: give the `<section>` `bg-background text-foreground` (semantic, `.dark`-driven,
  proven on the already-dark sidebar). General rule for the R/AE rollout: when a surface is light-in-dark,
  the migration to semantic tokens IS the fix — don't chase the `--lq-*` cascade.
- **NEW (AE5): the AE `prompt-input` registry item is option-2 territory.** It pulls `ai@^6` (the Vercel AI
  SDK transport we reject — bypasses gateway/SSE/`guarded_tool_call`), `runed`, 6 registry deps, and 23
  SDK-bound `Controller`/context files. Hand-build the identity (`rounded-xl border shadow-sm` shell →
  textarea → `flex justify-between p-1` toolbar; submit = status-driven lucide icon) directly on our composer.
- **NEW (AE5): a dropdown in a bottom toolbar must open UPWARD.** `ModelPicker` got an opt-in `dropUp`
  (`bottom-full mb-1` vs `mt-1`) so its menu doesn't clip off the viewport bottom; opt-in keeps other
  consumers (admin/models) on the default downward menu.
- **NEW (AE5): the composer is inherently the LIVE chat surface** (needs an active chat) — so AE5 has NO
  `_ae-lab` section (a static duplicate would drift). Functional + capture run on `/lq-ai/chats?id=…` with
  the SHORT stubbed fixture (add a `**/api/v1/models` intercept so the toolbar ModelPicker populates). The
  first test of the run still eats the first-`cy.visit` session-establishment latency (fails attempt 1,
  passes on retry) — `retries: { runMode: 2 }` covers it; 7/7 final.
- **NEW (AE4): DOMPurify (3.4.0) DOES preserve CSS custom properties in `style`.** Shiki dual-theme output
  carries the dark palette in a `--shiki-dark` CSS var on each token's inline `style`; class-based dark mode
  breaks silently if the sanitiser strips it. It does NOT — verified in a real browser (Cypress asserts
  `span[style*="--shiki-dark"]` exists post-sanitize + the dark screenshot shows the dark palette). vitest
  env is `node` (no DOM) so DOMPurify behavior is **Cypress-only** to test — don't try to unit-test it.
- **NEW (AE4): Shiki fine-grained setup = no WASM, only listed grammars.** Use `createHighlighter` from
  `shiki` + `createJavaScriptRegexEngine` from `shiki/engine/javascript` (NOT the default oniguruma WASM)
  + an explicit `langs` list. `codeToHtml` THROWS on an unknown lang → `normalizeLang` must map to a loaded
  grammar or `'text'`. `shiki` is the only declared dep; `@shikijs/langs|themes` arrive as its pinned
  transitives.
- **NEW (AE4): a literal `</script>` inside a Svelte `<script>` string closes the block** (parse error).
  Escape the slash — `'<\/script>'` — when a demo string must contain it (the lab injection-safety sample).
- **NEW (AE3): run ruff from the REPO ROOT with the root `ruff.toml`, exactly as CI does.** CI runs
  `ruff check api scripts` + `ruff format --check api scripts` from the repo root. Running ruff from
  inside `api/` uses ruff's DEFAULT settings (the root `ruff.toml` excludes web/ and tunes line-length/
  rules) → spurious "would reformat" noise AND it MISSES rules like `UP017` (`datetime.UTC` over
  `timezone.utc`) — AE3's first CI run failed on exactly that. Correct repro:
  `docker run --rm -v $PWD:/repo -w /repo python:3.12-slim bash -c "pip install -q ruff; ruff check api
  scripts; ruff format --check api scripts"`. Under the root config everything (incl. your edits) is
  format-clean. `mypy app` (run from `api/`) still must pass separately.
- **NEW (AE3): running api pytest off the live dev DB.** The runtime image has NO test deps and the live
  postgres is off-limits. Recipe: throwaway `docker run -d --name <pg> --network lq-ai_default
  pgvector/pgvector:pg16` (+ `CREATE EXTENSION vector`); then
  `docker run --rm --network lq-ai_default -v $PWD/api:/app -v $PWD/skills:/skills:ro -e
  DATABASE_URL=postgresql+asyncpg://lq_ai:lq_ai@<pg>:5432/lq_ai -e LQ_AI_SKILLS_DIR=/skills --entrypoint
  bash lq-ai-api:latest -c "pip install -q -e .[dev]; python -m pytest -q …"`. **Mount `./skills`** or
  migration 0032 (seeds NDA playbook YAML) fails. conftest creates its own `lq_ai_test_*` DB per run.
- **NEW (AE3): the citations intercept glob.** The endpoint is `/chats/{id}/messages/{mid}/citations` —
  AE2's `**/api/v1/messages/*/citations` glob MISSED it (no `/chats/` segment). Use
  `**/api/v1/chats/*/messages/*/citations`.
- **NEW (AE3): option-2 again — Sources + inline-citation.** `sources` pulls `collapsible`;
  `inline-citation` pulls `carousel`+`hover-card`+16 files. Hand-build `Sources` on `<details>`; vendor
  only the dependency-free `inline-citation` primitives you actually use (AE0 "take only what you need").
  Inspect each registry item's `dependencies`/`registryDependencies` BEFORE deciding vendor vs hand-build.
- **(AE2): forward shadcn `Button onclick` through a RUNES wrapper, not the legacy parent** (legacy
  `on:click` on a runes component = silent no-op). `MessageActionsBar`/`MessageSources` are runes wrappers
  the legacy `MessageBubble` feeds plain props.
- **(AE2): lab-based functional Cypress dodges the auth-login flakiness.** `_ae-lab` is auth-gated but
  makes no API calls → deterministic interaction tests run there; use the live chat surface only for the
  integration check + before/after capture. Distinguish icons via lucide `svg.lucide-<name>`.
- **(AE1): the AE dark-capture recipe.** SHORT fixture · `localStorage.theme` BEFORE `cy.visit` · post-boot
  class pin · `cy.get('html').should('have.class', theme)` · 1px viewport nudge before `cy.screenshot`.
- **(AE1): wrapping a Svelte-4 component's content in runes children works** (legacy slots → `children`
  snippet). Alias the AE `Message` *component* vs our `Message` *type* (`Message as AeMessage`).
- **(AE0): the AE vendor pipeline** = shadcn-svelte registry JSON (`…/r/<c>.json`), NOT jsrepo. INSPECT
  before vendoring. Items can under-declare deps. Never adopt the `streamdown-svelte` `response` sink —
  keep `renderModelMarkdown`. **"dev-only route"** = unadvertised, auth-gated, leading-`_` (`_ae-lab`);
  the web container always serves a PROD build. Vendored AE source is eslint-exempt; kept prettier-formatted.
- web CI gates only `npm run check` + vitest (eslint/prettier NOT gated). `npx vitest run` (NOT
  `test:frontend` = watch). vitest env is `node` (no jsdom) — DOMPurify/sanitisation must be Cypress-tested.
  **headless cypress lies about dark theme — capture headed** (`DISPLAY=:0`); **rebuild the `web`
  container before screenshotting/Cypress-testing a UI change.** Cypress trashes `cypress/screenshots`
  at run START — copy before/after frames to `docs/fork/evidence/` immediately after each run.
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork` AND
  `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3 (run from repo dir,
  `/tmp/types.py` shadows stdlib `types`).
- migrations: NEVER host-side alembic against the live dev DB; api auto-migrates on boot; rebuild
  api+arq-worker+ingest-worker together + web. **NEVER `docker compose down -v`.**
- MiniMax-M3 is tier 4 (weak) — `default_tier_floor` < 4 makes every run 403. deepagents subagent `model`
  string = gateway-bypass (ADR-F010 guard at `build_deep_agent`). New API endpoints register in
  tests/test_openapi.py (count assert) — AE3 added NO endpoint (a field on an existing one).
