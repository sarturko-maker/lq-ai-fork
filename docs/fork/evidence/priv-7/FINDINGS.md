# PRIV-7 — findings: ROPA population from a real privacy notice (Zendesk)

**Date:** 2026-06-19 · **Source:** Zendesk UK privacy notice (public; testing-only, held transiently, not
committed) · **Models:** `deepseek` → `deepseek-v4-flash`, `deepseek-pro` → `deepseek-v4-pro` (gateway-routed;
DeepSeek not yet ADR-F015 scenario-qualified — these are its first data points). Reports kept verbatim.

## Headline verdict

**Flash + the `ropa-population` skill + an adequate step budget builds a fully-linked Article 30 register —
9/9 activities linked across all four axes (systems, recipients, data-subject categories, data categories).**
The earlier "it only reaches ~50%" result was **not a model-capability limit** — it was two budget ceilings:
(1) langgraph's default `recursion_limit=25` crashing skilled runs mid-build, and (2) too small a `max_steps`.
With both lifted, **flash** hits the maintainer's ~80% aspiration **structurally** (100% linkage on the
activities it recorded). **Structural completeness ≠ legal quality, though** — an independent privacy-lawyer
audit grades the substance **C+** (a usable first-draft skeleton with real defects; see § Substantive quality
audit below). The two are different claims and this report keeps them separate.

## What this slice surfaced and fixed in-flight: the recursion ceiling

The first skill runs failed with `GraphRecursionError: Recursion limit of 25` — langgraph's default graph
superstep cap, which is **far below** our real brakes (`max_steps`, the 300 s wall clock, the R4/R5/R6
guards) and was never set anywhere. With skills on, a run burns supersteps on skill machinery (ls /
read_file the SKILL.md) and a long tool loop, blowing 25 before `max_steps` ever fired — **crashing and
losing the work**. This caps *all* substantial production agent work, not just this test. **Fixed** in
`runner.py`: the graph `recursion_limit` is now tied to the run's own `max_steps`
(`max(50, max_steps * 4)`) so the intended cap governs; unit-tested; runner + stream suites green. After the
fix, every run terminated cleanly (`cap_exceeded`/`completed`), no crashes.

## The controlled build comparison (naive prompts; the skill carries the method)

Prompts held constant (a realistic "build our ROPA" ask, 2 passes); the only variables are the skill, the
model and the step budget. "Fully linked" = an activity with ≥1 system, ≥1 recipient, ≥1 data-subject
category and ≥1 data category.

| Config | max_steps | Activities | Systems | Vendors | Transfers | **Fully linked** | Read of behaviour |
|---|---|---|---|---|---|---|---|
| flash, **no skill** | 60 | 8 | 0 | 0 | 0 | **0/8** | breadth-first: tags all categories, links nothing |
| flash, **+ skill** | 60 | 8 | 3 | 3 | 2 | **1/8** | skill flips it depth-first (link-as-you-go) but budget completes ~1 |
| **pro**, + skill | 60 | 3 | 3 | 3 | 0 | **2/3 (67%)** | deepest per activity, fewest activities (pro is deliberate) |
| flash, + skill | **150** | 9 | 6 | 8 | 0 | **9/9 (100%)** | budget lifted → every activity fully linked |

(Plus the Phase-A naive baselines, kept: `deepseek-oneshot` stalled at entities only; `deepseek-staged`
[4 rigid stages] got entities + categories + 10 transfers but 0 links — the rigid final "links" stage ran
out before reaching the link tools.)

## What each lever does

- **The skill is validated.** It is the *only* thing that produced any links / systems / vendors on flash
  (no-skill control: 0 of each). It changes strategy from shallow breadth (tag everything, link nothing —
  whatever survives truncation) to **complete depth** (finish each activity's whole record before the next).
  Under a tight budget that means fewer complete records; under an adequate budget it means a **fully-linked**
  register (9/9).
- **Budget was the real ceiling.** A complete activity is ~6–8 tool calls; ~10 activities ≈ 60–80 calls,
  which simply did not fit a 60-step run. At 150 steps (2 passes) flash+skill reached 9/9. The wall clock
  (300 s, ~1 s/step) is the next limit; ~250–280 steps fit before it.
- **Pro goes deepest per activity** (67% linked at the same 60-step budget vs flash's 12%) but records
  fewer activities — more reasoning per step. Untested at high budget; expected to scale similarly.

## Coverage vs. the maintainer's "~80%"

**Achieved on flash** (9/9 fully-linked activities) once the recursion fix + budget were in place — through
the guarded, code-validated tools, so every row is valid by construction and the special-category⇔Art 9
invariant held throughout. The notice's ~10 purpose-table activities, recipient taxonomy, systems and
categories all landed. The remaining honest gap in the 9/9 run: **0 transfers** (the budget went to
activities/systems/vendors/categories/links across the two passes; transfers were deprioritised). A third
pass, a transfers-specific nudge, or more budget would close it.

## Bugs / limitations flagged (recommend focused follow-ups — NOT fixed here)

1. **Deadlock in the category find-or-create under parallel tool calls (real bug).** The high-budget run's
   pass 1 `failed` with a Postgres `DeadlockDetectedError` on `INSERT INTO data_categories`: deepagents
   executes a turn's tool calls **concurrently**, and two overlapping `add_data_categories` calls raced on
   the `lower(name)` unique index. PRIV-6a's SAVEPOINT absorbs `IntegrityError` (lost-race re-select) but
   **not** a deadlock, so the whole run failed (pass 2 recovered the register). Fix = catch
   `DeadlockDetectedError` and retry the SAVEPOINT (small, but it's the guarded write path → its own slice +
   security review). **This is the most important follow-up.**
2. **deepagents has no tuned profile for `deepseek`** → default loop/token settings (logged every run).
   Registering a profile may improve budgeting/looping — cheap follow-up.
3. **0 transfers in the best run** — a budget-priority artifact, not a capability gap (the staged baseline
   recorded 10 transfers). The onboarding flow should make transfers their own step or nudge.

## Recommendations

- **Ship the `ropa-population` skill** (bind to Privacy via a migration — it is validated). Test-only binding
  proved its value this slice per the maintainer's choice.
- **Raise the build-time step budget** for ROPA-population work (now safe — the recursion ceiling no longer
  pre-empts it). The eventual onboarding flow should orchestrate one fat run (or a few), not many tiny ones.
- **Fix the find-or-create deadlock** (follow-up #1) before this runs at scale / with parallel tool calls.
- **DeepSeek-flash is a credible scenario candidate** on this evidence (a fully-linked, valid register from a
  real notice). The formal ADR-F015 qualification call is the maintainer's.
- The **orchestrator/reader split** (pro orchestrates, flash reads) remains a strong future direction but is
  no longer required to hit the target — flash alone clears it with the skill + budget.

## Substantive quality audit (independent privacy-lawyer panel) — overall **C+**

The coverage scorer measures **structure** (did it link?), not **legal substance**. A 5-lens adversarial
audit of the 9/9 register against the real notice (grades: lawful-basis B, decomposition B, special-category
B, recipients/retention/**transfers D**, grounding B) gives the honest picture: **a usable first-draft
skeleton, NOT a sign-off-ready ROPA.**

**Genuine strengths.** DEI special-category handling is correct and non-trivial (inferred the Art 9 dimension
the notice never states, flagged `special_category` + `explicit_consent` Art 9(2)(a), paired to the Art 6
consent limb). Lawful bases are conservative in the *right* direction (Marketing → consent, correctly
resisting the notice's own legitimate-interests hedge — PECR-aware). Faithful 1:1 decomposition of the §3
purpose table with no hallucinated activity, and correctly respecting the notice's controller-only scope (it
did NOT invent a support-ticketing activity, which is Zendesk's processor role). No data/vendor confabulation;
honest restatement of vague retention rather than inventing fake periods.

**Serious issues a privacy lawyer would red-pen.**
1. **Zero transfers (Art 30(1)(e)/(f) absent) — most serious.** The notice itemises the full Art 46 stack
   (SCCs, UK Addendum, BCRs, adequacy, 3 named DPF entities, ~28 affiliate jurisdictions); the register
   recorded **0**. Root cause is the budget/deadlock (pass 1 deadlocked, pass 2 hit the step cap before
   transfers) — but the deliverable reads as "no international transfers exist," which would mislead.
2. **Special-category data on a contract-based activity with no Art 9 condition.** "Service delivery" carries
   the `Sensitive Personal Data` category yet is `special_category=false` / `art9_condition=null` /
   `lawful_basis=contract` — internally incoherent (contract is not an Art 9 gateway; likely spillover that
   belongs only on DEI). **The write-path invariant only checks `special_category=true ⇒ art9 present`, NOT
   the inverse**, so this passed as `integrity_ok=true` — a **false-clean signal**. (→ backlog: tighten the
   invariant / flag special-flavoured category names on non-special activities.)
3. **Recipient-role misclassifications.** "Cookie & Tracking Companies" tagged `processor` (should be
   `separate_controller` — §10 CPRA lists them as sold/shared ad-tech parties); "Professional Advisors"
   tagged `processor` (independent controllers per EDPB 07/2020). These invent Art 28 obligations and hide
   controller-to-controller disclosures.
4. **Questionable:** Legal/security collapsed to sole `legal_obligation` (notice gave 3 bases; LI is more
   defensible); webinar → `contract` (a stretch); "Job Applicants" inferred though the notice never names
   them as a subject; retentions are non-committal restatements, not concrete Art 30(1)(f) limits (CCTV
   especially should be quantified).

**Bottom line:** trust the activity/basis/special-category scaffolding as a *starting point* a privacy officer
can refine (it genuinely saves time on the §3 substance), but **rebuild transfers from scratch, re-derive
every recipient role, resolve the Service-delivery Art 9 contradiction, and replace boilerplate retention with
concrete periods.** Shipped as-is and trusted, it would understate the controller's transfer obligations. The
two failure modes that would mislead an unwary reader — `transfers:0` and the `integrity_ok=true` masking the
Art 9 contradiction — are the ones to fix first. (Full panel + synthesis: workflow `wf_ff1eeb6d-b22`.)

## Caveats

- Live runs are non-deterministic; each row above is one observation. The 9/9 result is one run.
- All runs used isolated throwaway test DBs (dropped after the session); the dev register was never touched.
- "Fully linked" is a coarse 4-axis heuristic; the produced registers in each `behavior-report.md` are the
  authoritative record.
