# Plan + outcome — COMM C8/C9 redline-eval RE-RUN (honest craft numbers, skill loaded)

Branch `fork/c8c9-redline-eval-rerun` · governing ADR-F041 (craft = prompt-quality tuned by eval, not a runtime
gate) · **no migration, no new deps, no production code change.**

## Why

C8/C9's craft findings were produced with `skills/surgical-redline/SKILL.md` **silently absent** from the
registry (frontmatter `": "` bug, fixed in C3a + guarded by `test_every_real_skill_loads_no_silent_drops`). The
findings were **confounded** — the skill that teaches the surgical technique was never in context. This slice
re-runs both evals with the skill **loaded** and replaces the confounded conclusion with honest numbers.

Maintainer decisions (locked): **both harnesses** (C8 auto-rate + C9 Claude-judged) · **flash + conditional pro**
on the flash failures.

## What was done

1. **Premise gate (deterministic):** `surgical-redline` loads (19/19 skills, no silent drops) and is bound to
   Commercial — `test_every_real_skill_loads_no_silent_drops` + `test_commercial_surgical_redline_skill_and_doctrine`
   green; registry probe positive. The harnesses inject the real registry, so the skill is present in every run.
   Corroborated behaviourally: every run calls the on-demand `read_file` skill tool, and redlines reproduce the
   skill's worked examples (ADR-F016 progressive disclosure — the body is read on demand, not auto-injected).
2. **Archived the confounded v1** (`c8/eval-v1-skill-absent/`, `c9/v1-skill-absent/`) + bannered both READMEs.
   Nothing erased.
3. **Live re-runs (DeepSeek, dev image, skill loaded):** C8 eval (2 docs × 3 reps, flash); C9 manual (7
   instruments, flash); C9 pro on the 4 flash non-surgical instruments.
4. **Claude-judged (Opus 4.8) the C9 artifacts** with a sharp/sceptical panel + adversarial refuter on the
   mutualisation cases; **re-judged the archived v1 with the identical panel** to remove judge drift (it
   reproduced v1's 5/7 → no drift).

## Outcome (full detail in `docs/fork/evidence/c9/SUMMARY.md`)

**The confound is removed and the original finding largely HOLDS — confirmed, not overturned.**

- **Confirmed:** pervasive mutualisation is a real, persistent weakness (Aegis NDA still rip-and-replaces §9/§3
  across flash + pro); complexity is not the predictor (Helios/Orion STRONG·surgical both runs); a stronger model
  does NOT fix craft and is **less robust** (pro: 2/4 no-redline, NDA cap_exceeded).
- **Corrected (real effects of loading the skill):** robustness 6/7→7/7 redlined (Meridian no-redline→STRONG·
  surgical), boilerplate-bare 5/7→6/7, and the taught indemnity/cap moves are observably applied.
- **Surgical-pass count** (same panel): v1 5/7, v2 3/7 — **noise, not a regression** (n=1; the flips are
  borderline calls on dense single-party grant clauses). Deterministic signals + direct text inspection are the
  reliable evidence.
- **Residual** (ranked): dense grant/data-licence clauses struck wholesale (no skill worked-example for them);
  editor *seam* defects (duplicated inserted text from overlapping anchors); NDA mutualisation unreliable;
  pro robustness collapse.

**Decision (rules A/B/C): NO production change this slice.** The re-run substantially confirms the prior finding;
**n=1 cannot verify a craft change**, so shipping a skill/prompt tweak would be unverifiable ("if you can't
verify it, don't ship it"). The clearest defect (editor seam duplication) is a substrate fix, not a skill tweak.
All fixes are deferred to dedicated slices that pair each with a verification (see Backlog in MILESTONES):
grant-clause worked-example + **multi-rep × strong-judge eval**; overlap/duplication guard in the redline tools;
multi-rep mutualisation eval. Step-budget tier deprioritised (pro loops regardless of budget).

## Verification / DoD

- Premise gate green (quoted above). **Live verification IS the deliverable** — evidence committed under
  `docs/fork/evidence/{c8,c9}` (eval-report, flash/pro artifacts, verdicts, SUMMARY). No production code touched →
  CI trivially green; skill-loader guard re-run green. Fresh-context adversarial review of the evidence honesty
  (v1 labelled confounded not erased; contamination caught + corrected via manifest ground-truth; no
  secrets/PII — all instruments synthetic). HANDOFF + memory updated. Merge per ADR-F005.
