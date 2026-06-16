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

- **UX-B-1 — Scenario harness + Commercial baseline.** Build the reusable rig: scenario fixtures (intent +
  expected-shape: which tool(s), step bound, must/should-not, refusal expectation) → drive the **real** agent
  against the live gateway → capture receipts (tool selection, step count, final-answer check, guard/refusal,
  latency) → emit a structured **behavior report**. Run it against **Commercial** (the one configured area)
  with a starter set: single-tool fetch, multi-step `search → read → answer`, no-tool-needed, ambiguous →
  clarify, and a guard/refusal case. Commit the baseline report. Output = the harness + an honest map of how
  MiniMax-M3 behaves in the cockpit loop. Production code change limited to test infra (+ minimal
  observability hooks if needed). **Verify:** scripted suite still green (CI); harness runs locally against
  the dev stack; report committed. **(The agreed start.)**

- **UX-B-2 — Sensible default practice areas, calibrated to UX-B-1.** Author `profile_md` +
  `default_tier_floor` + `agent_config` (subagents) for **Disputes / M&A / Privacy / Employment** via an
  **idempotent migration** (the `0054` pattern — write only when `profile_md IS NULL`, never overwrite
  operator edits; rebuild `api` + `arq-worker` + `ingest-worker` together, verify on a throwaway pgvector
  container first per the dev-env hard rules). Profiles + tier floors **calibrated to the UX-B-1 baseline**
  (degrade honestly where M3 is weak). Extend the harness with per-area scenarios; commit per-area behavior
  reports. Cockpit then shows all five areas configured. **Privacy gets a forward-looking profile** (it is
  the future Oscar-Privacy module's home). **Verify:** migration on throwaway container; per-area harness
  reports; cockpit screenshot showing 5 configured areas.

- **UX-B-3 — Skills activation (S9). The big, security-sensitive slice.** Drop the `composition.py:151`
  `bound_skill_names=[]` stub; attach `SkillsMiddleware`; thread the DB-bound skill names through. **Re-
  qualify the harness** with skills on (expanded tool surface → harder selection) and commit the
  re-qualification report. **Deeper security pass:** skill-bound tool dispatch routes through
  `guarded_tool_call` (R4 cost cap / R5 halt / R6 grants preserved); skill content curated/read-only;
  validate subagent-referenced skill names against the registry at config time (close the drift gap). ADR
  note if the harness profile change is architecturally load-bearing. **Verify:** scripted suite green;
  skills-on harness report; security pass on record.

- **UX-B-4 — Live subagent scenario.** Configure an area with a real subagent spec (e.g. a research subagent
  that narrows to document search), run a matter under it through the harness, and prove the subagent
  executes, calls tools, and returns to the parent. Assert subagent steps carry `parent_step_id`. Commit the
  subagent behavior report. **Verify:** harness report shows delegation; scripted assertion on
  `parent_step_id` ancestry.

- **UX-B-5 — Cockpit perfection (web).** Surface the now-proven loop honestly, on the F013 design language:
  **area selection at matter creation** (wire the existing `practiceAreasApi` into the new-matter flow);
  **subagent boundary rendering** in the run view (parse `parent_step_id` → distinct subagent frames in the
  SSE stream, not just nested steps); and area-config **visibility** (at minimum read-only; admin PATCH
  surface if it fits the slice). **Verify:** `npm run check` + vitest; rebuild the web container; headed
  Cypress before/after (light+dark × wide+narrow) → `docs/fork/evidence/ux-b-5/`.

- **UX-B-6 — Verify + consistency sweep (if warranted).** Cross-slice: all 5 areas configured + scenario-
  reported; skills on + re-qualified; subagents exercised; cockpit honest. Final HANDOFF + a milestone
  behavior-report index. (May fold into UX-B-5 if thin.)

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
