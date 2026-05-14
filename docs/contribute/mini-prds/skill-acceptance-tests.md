# Mini-PRD: Acceptance Tests for the Built-in Skills

> **Status:** Open for contribution
> **Effort:** M per skill (roughly half a day of focused attorney time per skill; 10 skills total tracked as separable PRs)
> **Contributor profile:** Practicing attorney with subject-matter expertise in the skill's area. Can be a different attorney per skill. No coding required.
> **Mentor:** Maintainer (Kevin Keller, via PR review) + paired domain-expert reviewer

## What this is

Every built-in skill in `skills/` ships with a `test-plan.md` describing the scenarios the skill should handle and the expected calibration of its output. The plans are drafted; what is missing is the **acceptance pass** — running the skill on real (anonymized) documents matching each scenario, recording the actual outputs, and certifying that the outputs meet the structural expectations the test plan describes.

This contribution operationalizes the acceptance pass for each of the ten built-in skills: an `acceptance/` directory per skill containing anonymized input documents, expected-output structural notes, and a `results.md` summarizing the skill's behavior on each input across at least two inference models. The acceptance criteria are **structural** — issue count, severity distribution, section presence, citation resolution — not stylistic. Style varies with model and seed; structure does not.

Each of the ten skills is a separable PR. A contributor takes one skill, works through the test plan, and ships the acceptance pack. Or a contributor takes a few related skills (e.g., all three contract-review skills) and ships them together. The 10-skill total is a tracking effort, not a single PR.

## Why it matters

Skills are the canonical artifact of value in this project ([PRD §1.3 Transparency as a Founding Principle](../../PRD.md#13-transparency-as-a-founding-principle)). When the project produces a wrong answer, the answer to "why" is almost always in a `SKILL.md` somewhere. The skill-authoring guide and the contribution path in [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md) document **how to write a skill correctly**; the acceptance pass demonstrates that the shipped skill actually works on real documents.

That demonstration is the operator's first verification path. A general counsel evaluating LQ.AI for in-house deployment opens the NDA Review skill, reads the SKILL.md, and asks: "would this produce a substantively correct review on the documents my team actually handles?" Without acceptance results, the answer is "trust the maintainer." With acceptance results, the answer is "read the acceptance directory — here are 5 anonymized NDAs the skill was tested against, here are the structural assertions about each output, here is the summary of where the skill performed well and where it produced findings the reviewing attorney disagreed with." The operator's evaluator forms their own judgment from the data.

A closed-source vendor's equivalent claim about NDA-review quality is unverifiable from the outside: the prompts are not visible, the test corpus is not published, the reviewing-attorney process is not documented. The acceptance directory is the verifiable counterpart — operator's evaluator reads the inputs, the outputs, and the reviewing attorney's substantive notes, and forms their own judgment. It is also a forcing function: where the skill produces unsatisfactory output, the contributor opens a follow-up issue and the skill gets revised. Acceptance results are not a one-time signoff; they are a living quality artifact tied to a specific skill version.

## What we'd ship

Per skill, a new `acceptance/` directory with the following structure:

```
skills/<skill-name>/
├── SKILL.md
├── reference/
├── examples/
├── test-plan.md
└── acceptance/                          # NEW
    ├── README.md                        # how to read this directory; reviewer's name + attestation
    ├── inputs/
    │   ├── 01-mutual-nda-baseline.pdf   # anonymized
    │   ├── 02-unilateral-discloser.pdf
    │   ├── 03-unilateral-recipient.pdf
    │   ├── 04-unusual-structure.pdf
    │   └── 05-routine-vendor.pdf
    ├── expected/                        # structural expectations per input
    │   ├── 01-mutual-nda-baseline.md
    │   ├── 02-...
    │   └── ...
    ├── outputs/                         # actual outputs from the test runs
    │   ├── 01-mutual-nda-baseline-claude-X.md
    │   ├── 01-mutual-nda-baseline-gpt-Y.md
    │   └── ...
    └── results.md                       # summary: structural pass/fail per input × model, reviewer notes
```

**`README.md`** (per acceptance directory) — names the reviewing attorney, the date of the acceptance pass, the skill version tested (matches `lq_ai.version` in `SKILL.md`), the inference models used, and a brief attestation that the reviewer believes the results substantively reflect how the skill would perform on real documents in real practice. The attestation format follows the convention in [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md#3-attest).

**`inputs/`** — anonymized real-document inputs, one per scenario in the skill's `test-plan.md`. Anonymization removes party names, identifying details, and any client-specific information. Documents can be sourced from prior matters, from the operator's own document corpus, or from public sources (SEC EDGAR exhibits, public template repositories, regulator-published templates) where appropriate to the skill.

**`expected/`** — one markdown file per input describing the **structural** expectations: section presence, severity distribution, issue-count range, citations expected, expected calibration phrases ("recommend executing as-drafted" vs. "negotiate before signing"). Structural, not exact-text — the actual wording varies with model.

**`outputs/`** — the actual skill outputs captured during the acceptance pass. One file per `<input> × <model>` combination. At minimum, two models per input (one cloud, one local-or-cloud-second-option) so the contributor and reviewer see the skill's behavior across the inference matrix.

**`results.md`** — the headline document. Per input: structural pass/fail per model (matched the expected structure? identified the expected categories of issues? produced citations that resolve?); the reviewing attorney's substantive notes on the output (calibration too aggressive? too lenient? missed an issue? invented an issue?); follow-up issues filed against the skill where applicable. The summary table at the top makes the pass/fail visible at a glance.

The 10 skills, in the order suggested for acceptance work (ordered by how much the skill leans on calibration vs. mechanical extraction):

1. `nda-review` (calibration-heavy; perspective-branched)
2. `msa-review-saas` (calibration-heavy)
3. `msa-review-commercial-purchase` (calibration-heavy)
4. `dpa-checklist-review` (regime-heavy)
5. `contract-qa` (extraction-heavy; KB-coupled)
6. `vendor-privacy-policy-first-pass` (calibration-heavy)
7. `action-items-from-client-alert` (extraction-heavy)
8. `comms-improver` (transformation; calibration about tone)
9. `enhance-prompt` (meta-skill; transforms user input)
10. `skill-creator` (meta-skill; produces other skills)

The 10 skills are tracked as 10 separable PRs. One PR per skill keeps the review surface tractable and lets multiple attorneys contribute in parallel.

## How we'd know it's done

For each skill PR:

- [ ] `skills/<skill>/acceptance/` directory exists with the structure documented above.
- [ ] At least 3 anonymized inputs (5 preferred) covering the scenarios in the skill's `test-plan.md`.
- [ ] One `expected/<input>.md` per input describing structural expectations.
- [ ] One `outputs/<input>-<model>.md` per `<input> × <model>` combination, for at least 2 distinct models.
- [ ] `results.md` summarizes per-input structural pass/fail and includes the reviewing attorney's substantive notes.
- [ ] `README.md` carries the reviewing attorney's name, the skill version tested, the date, and the attestation.
- [ ] Where the skill produced unsatisfactory output on a specific input, a follow-up GitHub issue is filed against the skill (or the skill version is bumped in a same-PR follow-up commit).
- [ ] Anonymization is verified — no party names, no identifying details, no client-confidential information in any input or output file.
- [ ] The skill's `SKILL.md` is updated to reference the acceptance directory (a one-line "Acceptance results: `acceptance/results.md`" near the top of the skill).

Across all 10 skills (tracking criteria, not single-PR criteria):

- [ ] All 10 built-in skills have populated `acceptance/` directories.
- [ ] The top-level [`README.md`](../../../README.md) and [`skills/`](../../../skills/) overview link the acceptance directories as "verifiable evidence of skill quality."
- [ ] Per-skill follow-up issues are tracked against a "Acceptance feedback" GitHub Project or label.

## Where to start

1. Pick a skill. The contribution decisions for one skill drive the conventions for the rest, so pick the one closest to your practice area first.
2. Read the skill's existing artifacts: `skills/<skill>/SKILL.md`, `skills/<skill>/test-plan.md`, `skills/<skill>/reference/`, `skills/<skill>/examples/`. The `test-plan.md` is the authoritative source for which scenarios the skill should be tested against.
3. As a canonical reference: read [`skills/nda-review/test-plan.md`](../../../skills/nda-review/test-plan.md). It is the most detailed test plan and demonstrates the structural-expectation conventions the acceptance pass should match against.
4. Read [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md) — particularly the attestation conventions in §3 and the conservative-posture norms in §2.
5. Read [`docs/skill-authoring-guide.md`](../../skill-authoring-guide.md) — relevant to identifying what counts as "structural" vs. "stylistic" output variation.
6. Source 3-5 anonymized documents matching the test-plan scenarios. Anonymize carefully; redact party names, addresses, financial terms specific to the matter, and any other client-identifying detail. The substantive structure of the document is what the skill operates on.
7. Run the skill on each input. If you do not have an LQ.AI deployment, the maintainer can run the skill on your inputs and return the outputs (open the issue first). Capture the output verbatim in `outputs/<input>-<model>.md`.
8. For each output, write the structural assessment in `results.md`: did the output match the structural expectation in `expected/<input>.md`? What did the reviewing attorney note about the output's substance? What follow-ups are needed?
9. Pair with the maintainer (or another practicing attorney in the skill's domain) on the rubric. The rubric is the agreement on what "structural pass" means; getting it right for one skill makes the next nine easier.
10. Submit the PR with the attestation in the description per [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md#3-attest).

## Scope cuts (what's out of scope for this PR)

- The automated eval harness (running the acceptance pass in CI with multi-judge grading) is a separate, larger deliverable. The acceptance pass here is by-hand structural assessment by a reviewing attorney; the eval harness comes later and consumes the same `inputs/` + `expected/` directories.
- Inter-rater agreement metrics (multiple attorneys grading the same output) are a future deliverable, not in scope for the first acceptance pass.
- Cross-skill comparison (which skill outperforms which on overlapping document types) is out of scope.
- Public skill-quality leaderboards (per-release scoring) are a separate effort.
- The acceptance pass does not test for adversarial robustness (prompt-injection, jailbreak); those are separate test categories with separate corpora.
- Skill improvements that surface from the acceptance pass are tracked as follow-up issues, not as same-PR fixes. The acceptance PR ships what the skill does today; substantive improvements ship as their own versioned PRs.

## How this strengthens the project

The acceptance directories are the project's first **operator-verifiable** skill-quality artifact. A general counsel evaluating LQ.AI reads the acceptance directory for the skills they would actually deploy and forms their own judgment about whether the skill meets their bar — the same way they would evaluate a junior associate's work product before relying on it. That verification path is impossible against a closed-source vendor: their skill's prompts are not visible, their test corpora are not published, their attorney-review process is not documented.

The acceptance pass also operationalizes the project's core claim that **skills are work product, not black-box prompts**. The acceptance directory makes that claim concrete: here is the skill, here are the inputs, here is the output, here is the reviewing attorney's assessment. The chain of custody is visible end to end.

## References

- [PRD §3.4 Skill Library and Skill Creator](../../PRD.md#34-skill-library-and-skill-creator)
- [PRD §1.3 Transparency as a Founding Principle](../../PRD.md#13-transparency-as-a-founding-principle) — skills are the canonical artifact of value
- [PRD §9 — DE-050 Skill quality bar / community review process](../../PRD.md#9-deferred-enhancements-and-identified-future-work)
- [PRD §9 — DE-051 Acceptance testing for the 10 starter skills](../../PRD.md#9-deferred-enhancements-and-identified-future-work)
- [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md) — attestation conventions
- [`docs/skill-authoring-guide.md`](../../skill-authoring-guide.md) — skill-authoring conventions
- [`skills/nda-review/test-plan.md`](../../../skills/nda-review/test-plan.md) — canonical test-plan example
- The 10 skills: [`skills/nda-review/`](../../../skills/nda-review/), [`skills/msa-review-saas/`](../../../skills/msa-review-saas/), [`skills/msa-review-commercial-purchase/`](../../../skills/msa-review-commercial-purchase/), [`skills/dpa-checklist-review/`](../../../skills/dpa-checklist-review/), [`skills/contract-qa/`](../../../skills/contract-qa/), [`skills/comms-improver/`](../../../skills/comms-improver/), [`skills/action-items-from-client-alert/`](../../../skills/action-items-from-client-alert/), [`skills/vendor-privacy-policy-first-pass/`](../../../skills/vendor-privacy-policy-first-pass/), [`skills/enhance-prompt/`](../../../skills/enhance-prompt/), [`skills/skill-creator/`](../../../skills/skill-creator/)

## Definition of "merged"

A per-skill acceptance PR is merged when (a) the acceptance criteria checklist for that skill is fully checked off, (b) the maintainer has reviewed the directory structure and verified anonymization, and (c) the practicing-attorney attestation per [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md#3-attest) is in the PR description. Because the acceptance results carry substantive legal-quality judgment, the attestation is required — even though no skill substance is being modified, the reviewing attorney is certifying that the results would not mislead a downstream attorney evaluating whether the skill is fit for their practice.
