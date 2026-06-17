# UX-B — capability convergence: Deep Agents truly work / cockpit perfection (decomposition)

**UX-B** is the third leg of the ADR-F012 split (F2 visual ✓ / UX-A navigational ✓ / **UX-B capability**).
It is the concrete delivery of the roadmap milestone **"F3 — Practice-area IA re-centre"**
(`docs/fork/MILESTONES.md`: *"the IA is practice areas → units of work; tool tabs become in-context
capabilities"*) and the prerequisite for the modules / Oscar-Privacy direction (see
[[oscar-privacy-modules-vision]]). Governed by **ADR-F015** (scenario-based model qualification as the
gate). Builds on F1-S3 (per-area Deep Agent, [[f1-s3-practice-area-deep-agent-shipped]]) and the complete
F2 visual pass + UX-A shell.

> Naming note: the design track previously overloaded "F2" (minimalist pass, ADR-F012) against the roadmap's
> "F2 — Memory". To avoid compounding that, this milestone uses the **UX-B** label from ADR-F012's own
> vocabulary (UX-A shipped as UX-A-1…5) rather than a colliding "F3". The ADR keeps the monotonic number
> **F015**.

## Goal

Make the practice-area Deep Agents **genuinely work** through a real model, and make the cockpit **honest +
perfect** about what they do. "Done" = a user lands in a configured practice area, states intent in a
matter, and the area's agent visibly works (picks tools, optionally fans out to subagents, cites/streams),
backed by **observed** MiniMax-M3 behaviour — not assumption. All five default areas are configured +
scenario-tested; skills are live; subagents are exercised; the cockpit surfaces the loop faithfully.

## Non-goals (this milestone)

- The modules / Oscar-Privacy product surface itself (data-discovery / ROPA tooling) — UX-B is the substrate
  it will sit on, not the module.
- The `practice_area` / `unit_of_work` **memory schema** beyond what already exists (areas + matters are
  enough for UX-B; the 4-level memory accumulation is the roadmap's "F2 — Memory" milestone).
- Multi-provider support — MiniMax-M3 stays the injected model; the harness is *built* model-agnostic but we
  qualify only M3 now.

## The gate (ADR-F015)

Two complementary suites:
- **Scripted-model unit tests** (`test_agent_composition.py` etc.) — deterministic, free, **gate CI**.
- **Scenario harness** — provider-marked (`@pytest.mark.provider`), live gateway + real MiniMax, **gates
  "production-real" claims**, runs out-of-CI (manual/nightly), emits a **behavior report** committed to
  `docs/fork/evidence/ux-b-*/`. Nothing ships `configured`/`activated`/blessed until the report shows M3
  handles it; profiles + tier floors are calibrated to the report.

## Slices (each = one PR, ≤2–3 days, full four-discipline DoD + a security + simplification pass)

- **UX-B-0 — ADR-F015 + this decomposition (THIS PR).** Docs only. Maintainer edits + accepts before UX-B-1.

- **UX-B-1 — Scenario harness + Commercial baseline. ✅ SHIPPED (PR #90).** Build the reusable rig: scenario fixtures (intent +
  expected-shape: which tool(s), step bound, must/should-not, refusal expectation) → drive the **real** agent
  against the live gateway → capture receipts (tool selection, step count, final-answer check, guard/refusal,
  latency) → emit a structured **behavior report**. Run it against **Commercial** (the one configured area)
  with a starter set: single-tool fetch, multi-step `search → read → answer`, no-tool-needed, ambiguous →
  clarify, and a guard/refusal case. Commit the baseline report. Output = the harness + an honest map of how
  MiniMax-M3 behaves in the cockpit loop. Production code change limited to test infra (+ minimal
  observability hooks if needed). **Verify:** scripted suite still green (CI); harness runs locally against
  the dev stack; report committed. **(The agreed start.)**

- **UX-B-2 — Sensible default practice areas, calibrated to UX-B-1. ✅ SHIPPED (PR #91).** Authored
  `profile_md` for **Disputes / M&A / Privacy / Employment** via the **idempotent migration `0055`** (the
  `0054` pattern — write only when `profile_md IS NULL`, never overwrite operator edits). Profiles
  **calibrated to the UX-B-1 baseline**: every one leans on the disciplines that degrade honestly under a
  tier-4-weak model — ground-and-cite, say-so-when-absent, **ask one clarifying question before guessing**,
  and never fake a confirmation. `default_tier_floor` stays NULL (the 0054 Commercial rationale: M3 is
  tier 4, a stronger floor makes the area unusable). **`agent_config` stays `{}` — live subagents are
  DEFERRED to UX-B-4** (the composition point renders subagents live; delegation is harder than the
  multi-step chaining M3 is inconsistent at, and ADR-F015 forbids activating an unqualified capability —
  the sequencing rationale below already puts subagents after skills). Extended the harness to be
  area-agnostic (`seed_matter`, per-area fixtures + scenario sets) and committed per-area behavior reports
  (`docs/fork/evidence/ux-b-2/`). **Privacy got a forward-looking profile** (the future Oscar-Privacy
  module's home). **Verify:** migration on throwaway test DB (conftest) — scripted suite **2130 passed/8
  skipped**, ruff+mypy clean; live per-area harness ran (all 12 scenarios `completed`); cockpit shows 5
  configured areas. **Pickup: UX-B-3.**

- **UX-B-3 — Skills activation (S9). ✅ SHIPPED (PR #92, ADR-F016).** Corrected the HANDOFF premise:
  `SkillsMiddleware` adds **no tools** — it `ls`/`download`s a *backend* and the model reads each `SKILL.md`
  via the builtin `read_file`; so activation = give the agent a **backend** + `skills=[sources]`, and the
  security posture is **what the backend exposes** (the builtins aren't guarded — the F1 universe-wrap is
  out of scope). Maintainer-ruled architecture (**ADR-F016**): one library, no duplication (reference by
  name), **subset per agent** (the whole library confuses the model). Built `app/agents/skill_backend.py`
  (`RegistrySkillBackend`) — a read-only `BackendProtocol` adapter over a `SkillRegistry` snapshot serving
  ONLY the area's bound subset (`/skills/<name>/SKILL.md`); zero-copy, reaches no host FS / matter data,
  drift closes structurally. Composition gained a `skill_registry_provider` seam (worker reads
  `app.state.skill_registry`), loads `practice_area_skills`, renders with bound/known, builds the backend,
  threads `skills`+`backend` → `execute_agent_run` → `build_deep_agent`. Dropped the `composition.py:151`
  stub. Migration **0056** seeds focused default bindings per area (idempotent). Drift gap closed:
  `build_area_subagents(known_skill_names=…)` rejects unknown subagent skill names at PATCH time. **Re-
  qualified live** (`docs/fork/evidence/ux-b-3/`): focused review grounds+cites with skills on (clean); a
  **broad** "structured risk review" makes M3 read the skill 5× and over-explore to `cap_exceeded` — an
  honest calibration finding (the expanded surface amplifies M3's known multi-step inconsistency), NOT tuned
  away. **Verify:** scripted suite green (provider tests self-skip); migration on the throwaway test DB;
  dev stack 0055→0056 (5 areas bound). **Pickup: UX-B-4.**

- **UX-B-4 — Live subagent scenario. ✅ SHIPPED (PR #93, ADR-F017).** Commercial gained a live
  `document-researcher` subagent (migration 0057) — an **on-demand** delegate (the parent's `task` tool fires
  only when a matter warrants it; a single NDA is read directly, a complex multi-document RFQ is fanned out).
  Resolved the deepagents name↔source-path mismatch the **idiomatic** way (re-read the docs first): each
  subagent gets its OWN virtual skill source over a generalised **multi-source `RegistrySkillBackend`** —
  deepagents' isolated per-subagent skill model — rather than inheriting the area set (the initial sketch,
  revised after research). The composition wiring (`build_area_skill_wiring`) rewrites a subagent's skill
  NAMES → its source path (⊆ area; rejected at PATCH, dropped-not-fatal at render). Harness gained multi-doc
  seeding + delegation observations (`task_calls`/`delegated`/`parent_step_id` ancestry). **Verify:** scripted
  suite **2158 passed / 10 skipped** (incl. the deterministic ancestry CI gate
  `test_subagent_delegation_nests_steps_via_parent_step_id` — a `task` step with subagent steps nested via
  `parent_step_id`); ruff+mypy clean; dev stack migrated 0056→0057. **Live finding (ADR-F015, kept verbatim):**
  both RFQ scenarios `completed`; M3 correctly did NOT delegate the single fact, and ALSO did not delegate the
  4-document review (read all four itself, `task_calls=0`) — the plumbing is proven (deterministic test) but a
  tier-4 model doesn't *elect* to fan out at this matter size; not tuned green
  (`docs/fork/evidence/ux-b-4/`). **Pickup: UX-B-5.**

- **UX-B-5 — Cockpit perfection (web). ✅ SHIPPED (PR #94).** Surfaced the now-proven loop honestly on the
  F013 design language, **web-only** (every datum already on the wire — no api/gateway change). **(1) Area
  selection at matter creation:** `NewMatterDialog` gained an explicit practice-area **picker** (configured
  areas only, ADR-F002; defaults to the contextual area; noun/title follow the chosen area's `unit_label`),
  threaded from the cockpit context's `configuredAreas` into `MattersPanel` + `ConversationHost` — the
  matter→area binding that drives the server-side agent identity (`composition.py`) is now explicit + visible
  at creation. **(2) Subagent boundary rendering:** a pure `groupTurnTree` folds a `task` tool-call + its
  `parent_step_id`-nested children + the task result into one labelled **"Delegated to `<subagent_type>`"**
  boundary block (subagent type parsed from the call's args digest); honest by construction — renders only
  when delegation occurred, degrades to flat rows otherwise (the common tier-4 case). The flat-rendering
  path was factored into a `StepRow.svelte` child (the parent uses legacy `<slot>`, so a `{#snippet}` there
  is illegal) — a net code reduction, no DOM/testid change (ae6 regression 7/7). The SSE protocol gap
  (blocker #4) was **not** needed: `parent_step_id` already rides every `data-step`, so the boundary renders
  live + on replay with no protocol change — a richer subagent frame type stays follow-up (decision held).
  **(3) Area-config visibility:** a read-only `AreaConfigDisclosure` in the matters-panel header surfaces the
  area's profile (sanitised), bound skills, and subagents (name + description + each one's ⊆-area skill
  subset) — the transparency rule. Admin PATCH editor **deferred** (own slice — needs a web PATCH client +
  validation mirroring). **Verify:** `npm run check` **0 err** (5 pre-existing a11y warnings); **vitest 861**
  (+10: `groupTurnTree`/`subagentTypeOf`/`areaSubagents`); web container rebuilt; headed Cypress
  `ux-b-5-cockpit.cy.ts` **2/2** + ae6 regression **7/7** (light+dark × wide+narrow) →
  `docs/fork/evidence/ux-b-5/` (area-config + area-pick LIVE Commercial; delegation boundary STUBBED — M3
  doesn't elect to fan out at small matter sizes, UX-B-4, so the unit test is the gate). **Pickup: UX-B-6.**

- **UX-B-6 — Verify + consistency sweep. ✅ SHIPPED (PR #TBD).** The UX-B closer (its own small slice —
  UX-B-5 stayed focused, so this did not fold in). Re-verified every cross-slice claim against the **live dev
  DB (read-only)**: all 5 areas `configured` + profiled; tier floors NULL; skills bound per area (0056 —
  Commercial 4 / Disputes 2 / M&A 3 / Privacy 3 / Employment 3); Commercial's `document-researcher` subagent
  present with skills ⊆ its bound set (0057, ADR-F017 subset holds in stored data); cockpit honest (UX-B-5).
  No drift between docs and the running stack. Wrote the **milestone behavior-report index**
  (`docs/fork/evidence/UX-B-MILESTONE-INDEX.md`) tying UX-B-1…5 together — the honest map of what M3 does
  (grounds+cites, declines honestly, clarifies, answers general directly) and does not do reliably
  (multi-step efficiency varies; a broad ask over a large skill surface can `cap_exceeded`; doesn't elect to
  delegate at small matter sizes). The open calibration question (does a tier-4 model fan out on a genuinely
  large matter?) recorded as **backlog** in `MILESTONES.md`, not built. Docs-only. **UX-B is COMPLETE — the
  agentic-modules / Oscar-Privacy direction is unblocked as its own milestone.**

## Sequencing rationale

Harness **first** (UX-B-1) so UX-B-2/3/4 calibrate to observed reality. Default areas (UX-B-2) before skills
(UX-B-3) because skills expand the tool surface — we want a clean matter-tool baseline before we make
selection harder. Subagents (UX-B-4) after skills since subagent specs can carry skills. Web (UX-B-5) last —
it surfaces a loop that is by then proven, not aspirational.

## Risks / mitigations

- **Live provider cost / non-determinism** — small scenario sets; manual/nightly runs, never CI; the
  committed report is the artifact (ADR-F015).
- **MiniMax tier-4-weak may fail scenarios** — that is the *point*: the report tells us where to set tier
  floors, simplify profiles, or add guardrails. A failing scenario is a finding, not a blocker.
- **Skills re-qualification may regress the harness** — UX-B-3 is gated on its report; if selection degrades,
  the slice fixes profiles/guardrails or narrows the skill set before shipping.
- **Dev-stack safety** — migrations verified on a throwaway pgvector container first; never host-side
  `alembic upgrade` on the live dev DB; never `docker compose down -v`; rebuild workers together (CLAUDE.md
  dev-env hard rules).

## Verification (per slice)

Four-discipline DoD: build/`check`/tests shown; fresh-context adversarial + **security + simplification**
pass ([[security-review-every-slice]]); the relevant evidence (scripted suite green for CI + the scenario
behavior report / UI screenshots for production-real claims); HANDOFF updated. Merge per ADR-F005 against
`sarturko-maker/lq-ai-fork` (`gh pr create --repo sarturko-maker/lq-ai-fork --head <branch>`).
