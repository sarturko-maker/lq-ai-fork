# C9 — redline craft, CORRECTED re-run (v2: surgical-redline skill LOADED)

**Why this exists.** The original C8/C9 craft evidence (now archived under `v1-skill-absent/` and
`../c8/eval-v1-skill-absent/`) was produced with the `surgical-redline` SKILL.md **silently absent from the
registry** — an unquoted `": "` in its `description:` frontmatter made `yaml.safe_load` parse it as a mapping,
so the loader skipped it (found in C3a, fixed + guarded by `test_every_real_skill_loads_no_silent_drops`). The
v1 craft findings were therefore **confounded**: the skill that teaches the exact surgical technique was never
in context. This is the corrected re-run with the skill **loaded** (premise proven: registry + Commercial
binding green; corroborated behaviourally — every run calls the on-demand `read_file` skill tool, and the
produced redlines reproduce the skill's worked examples nearly verbatim, e.g. Meridian §7).

**Judge:** Claude (Opus 4.8), a deliberately sharp/sceptical panel (`surgical=false` if **any** material clause
is struck-and-retyped wholesale), with an **adversarial refuter** pass on the mutualisation cases. To make the
v1↔v2 comparison fair, the archived v1 reconstructions were **re-judged with the identical panel** (it
reproduced v1's original 5/7 → no judge drift). One run per (instrument, model) — **n=1**.

## Headline: the confound is removed, and the original finding largely HOLDS

Loading the skill did **not** overturn the v1 conclusions — it **confirms** them, with two genuine corrections.

**Confirmed (unchanged by removing the confound):**
1. **Pervasive mutualisation is a real, persistent craft weakness.** The Aegis NDA still gets wholesale
   strike-and-retype on the §9 indemnity verb phrase and the §3 exclusions clause — in v1 flash, v2 flash, **and**
   v2 pro. Loading the skill did not fix it.
2. **Complexity is not the craft predictor.** Helios and Orion (the dense, multi-limb instruments) are
   STRONG·surgical in both v1 and v2 — every LEAVE-ALONE trap (indemnity procedure, SLA mechanics, existing
   carve-outs) respected.
3. **A stronger model does NOT fix craft — and is *less* robust.** Pro (deepseek-v4-pro) on the four flash
   non-surgical instruments produced **no redline on 2/4** (DataBridge, Northwind); the **NDA looped to
   `cap_exceeded`** (it applied a redline but never finished — still not-surgical); only SecureScan completed
   cleanly (also not-surgical). **0/4 surgical.** This reproduces v1's model-vs-method result.

**Corrected (genuine effects of loading the skill):**
4. **Robustness improved (deterministic): 6/7 → 7/7 redlined; boilerplate-bare 5/7 → 6/7.** The standout:
   **Meridian SOW went from no-redline (v1) → STRONG·surgical (v2)**, including a textbook §7 indemnity
   mutualisation.
5. **The skill's taught moves are observably applied.** Surgical indemnity mutualisation (defined-term swap,
   `shall indemnify, defend and hold harmless` left bare) and the cap swap+carve-out appear across SecureScan §8,
   DataBridge §7, Meridian §7, Orion §6/§7 — near-verbatim the skill's worked examples. The skill body is read
   and used.

**Net:** the skill lifts *robustness* and the *specific clauses it teaches*, but the overall surgical-pass rate
did **not** rise at n=1 (see matrix). The residual ceiling on these single-run instruments is
**reliability/editor-bound**, not skill-absence-bound — so the v1 finding, by luck, was substantially right.

## Result matrix (identical sharp panel; flash v1 vs flash v2 vs pro v2)

| tier | instrument | v1 flash (skill absent) | **v2 flash (skill loaded)** | v2 pro (control) |
|---|---|---|---|---|
| moderate | SecureScan MSA | STRONG·surgical | ADEQUATE·not-surgical | ADEQUATE·not-surgical |
| moderate | DataBridge licence | STRONG·surgical | **STRONG**·not-surgical | — no redline |
| moderate | Aegis NDA | ADEQUATE·not-surgical | ADEQUATE·not-surgical | ADEQUATE·not-surgical *(refuted from STRONG; cap_exceeded)* |
| moderate | Northwind DPA | ADEQUATE·surgical | ADEQUATE·not-surgical *(garbled seams)* | — failed, no redline |
| moderate | Meridian SOW | **NONE — no redline** | **STRONG·surgical** | _(not run; flash already surgical)_ |
| **complex** | **Helios master agreement** | STRONG·surgical | **STRONG·surgical** | _(not run)_ |
| **complex** | **Orion dev + licence** | STRONG·surgical | **STRONG·surgical** | _(not run)_ |
| | **surgical-pass** | **5 / 7** | **3 / 7** | **0 / 4** |
| | **redlined (robustness)** | 6 / 7 | **7 / 7** | 2 / 4 |
| | **boilerplate-bare (deterministic)** | 5 / 7 | **6 / 7** | 0 / 2 redlined |

> ⚠ **Read the 5/7 → 3/7 as noise, not a regression.** Single run per instrument; the flips
> (SecureScan/DataBridge/Northwind) are on **borderline** calls about dense single-party *grant* clauses
> (data/content licences) being struck wholesale — which the same panel scored "defensible" on the v1 artifacts
> and "not-surgical" on the (different) v2 artifacts. Two stochastic runs + a borderline boolean ≠ a measurable
> craft change. The **deterministic** signals (robustness, bare) and **direct text inspection** are the reliable
> evidence; the surgical-pass *count* is qualitative at n=1.

## The residual weaknesses (ranked, with the precise failure mode)

1. **Dense single-party GRANT clauses** (IP assignment, data/content licence, exclusion lists) are
   struck-and-retyped wholesale rather than narrowing the toxic limb (SecureScan §5/§6, DataBridge §5, Aegis §3).
   *Borderline* — a bare grant limb has no boilerplate verb phrase to preserve, so it is partly defensible; but
   the surgical move (strike only `perpetual, irrevocable, worldwide` + the over-broad purpose tail, keep the
   grant skeleton bare) is teachable. **The skill has indemnity + cap worked-examples but no grant-clause one.**
2. **Editor *seam* defects** — duplicated inserted text in the accepted output: `In no event In no event`
   (SecureScan §9), `the Personal Data the Personal Data` / `Sub-processors any Sub-processor` (Northwind §3/§4),
   a duplicated termination sentence (Meridian §9). Caused by the model emitting **overlapping/adjacent edit
   anchors** that the editor applies on top of each other. This is an **apply-time quality bug**, not a craft
   strategy issue — and the most clearly *fixable* defect (a deterministic overlap/duplication guard in
   `preview_redline`/`apply_redline`).
3. **NDA pervasive mutualisation** — the indemnity-swap move the skill teaches does **not** reliably transfer to
   the NDA §9 (rip-and-replace persists across flash, pro). A reliability gap, not a capability gap (the same
   move lands on Meridian §7).
4. **Pro robustness collapse** — pro loops to `cap_exceeded` (NDA) or gives up with no redline (DataBridge,
   Northwind). More step budget is unlikely to help (it loops re-deriving anchors), so a "redline step-budget
   tier" is **not** an obvious fix.

## Follow-ups (each needs its own slice — and, crucially, a way to VERIFY it)

The key methodological lesson: **n=1 per instrument cannot verify a craft change.** Shipping a skill/prompt tweak
here would be unverifiable ("if you can't verify it, don't ship it"), so this slice ships the **measurement
only** and defers the fixes, each paired with a proper test:

- **Grant-clause-narrowing worked-example** in `skills/surgical-redline/SKILL.md` (strike only the toxic
  adjectives/purpose tail; keep the grant verb bare) — verified by a **multi-rep × strong-judge eval** (the
  only instrument that can measure a craft-rate change; C8's 3-rep auto-rate uses the weak self-judge, C9 is n=1).
- **Overlap/duplication guard** in the redline tools (reject or merge edits whose anchors overlap, and dedupe an
  insertion that already exists) — a deterministic, unit-testable substrate fix for the seam defects (#2 above).
- **Multi-rep mutualisation eval** (e.g. the NDA × N reps, Claude-judged) to turn "the NDA mutualisation is
  unreliable" from an n=1 observation into a rate.
- The **redline step-budget tier** is **deprioritised** — pro's looping suggests more steps won't help.

## C8 auto-rate companion (weak self-judge — secondary signal)

The C8 3-rep eval (`../c8/eval/eval-report.json`, SecureScan + DataBridge × 3, DeepSeek self-judge) moved
**2/6 (v1) → 0/6 (v2)** surgical-pass — but this is the **weak self-judge** with an all-or-nothing `surgical`
boolean: its own v2 verdicts read ADEQUATE/STRONG on substance with one or two wholesale clauses tripping the
boolean (e.g. "*Elsewhere, changes are surgical… standard boilerplate left intact*"). Deterministic
boilerplate-bare held at **4 of 5 redlined runs, both v1 and v2** (unchanged). C8 is consistent with the C9 picture — mostly-surgical with isolated
wholesale clauses — and is **not** read as a craft regression (it is the reason C9's strong judge exists).

## Methodology notes (honesty)

- **Same-panel re-judge of v1** removes judge drift from the v1↔v2 comparison (it reproduced v1's original 5/7).
- **Adversarial refuter** on the mutualisation cases caught over-credit: it refuted the Aegis-pro STRONG·surgical
  claim (the §3 exclusions strike is gratuitous — the struck text reappears verbatim as new limb (a)).
- **Contamination caught + corrected:** when an instrument produced *no* redline (so no `reconstruction.txt`),
  the judge harness searched and read a *different run's* file, yielding a verdict for the wrong artifact. Those
  cells (v1 Meridian, pro DataBridge/Northwind) are **discarded** here in favour of the manifest ground-truth
  (no-redline). Trustworthy verdict = one backed by a real `reconstruction.txt` on disk.
- **n=1** per (instrument, model): treat verdicts as strong-judged data points, not a rate.
