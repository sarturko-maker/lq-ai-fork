# Mini-PRD: OpenSSF Scorecard + Best Practices Badge (Passing Tier)

> **Status:** Open for contribution
> **Effort:** S
> **Contributor profile:** Junior-to-mid engineer with GitHub Actions familiarity. Comfortable editing CI workflows and reading the OpenSSF Scorecard / Best Practices Badge criteria. ~half a day plus the badge-self-attestation walkthrough.
> **Mentor:** Maintainer (Kevin Keller, via PR review)

## What this is

Three deliverables that together publish independently-verifiable engineering-discipline signals in the README:

1. An OpenSSF Scorecard CI workflow that runs the `scorecard-action` weekly and on pushes to main, with results published to OpenSSF and a badge in the README.
2. A `SECURITY-INSIGHTS.yml` at the repository root describing the project's security posture in the OSSF-standard format.
3. An OpenSSF Best Practices Badge (Passing tier) self-attestation, with the criteria walkthrough captured in a `BEST_PRACTICES_CRITERIA.md` document and the badge rendered in the README.

The work is small in volume: ~80 lines of new YAML + markdown, plus the self-attestation walk through the Best Practices Badge criteria on https://www.bestpractices.dev/. The work's value is structural: a reviewer with no context on the project can confirm 18 objective security-and-practice signals in 30 seconds by reading the Scorecard badge, and a procurement reviewer can verify that the Best Practices Badge criteria (objective, listed publicly) are met without taking the project's word for anything.

## Why it matters

The Scorecard score is a measurable engineering-discipline signal that no closed-source vendor can match in shape. The Scorecard tool (https://github.com/ossf/scorecard) computes 18 checks against the public repository: branch protection, signed releases, dependency-update automation, fuzzing presence, pinned dependencies, vulnerability response timing, and so on. The output is a 0-10 score with per-check breakdowns. Anyone can run the tool against any public repository; the badge in the README displays the continuously-updated score and links to the per-check details on `securityscorecards.dev`.

The Best Practices Badge (Passing tier) requires a set of objective criteria — a public source repository, a documented bug reporting process, documented changes between versions, an explicit license, a maintained security policy, and others. The criteria are listed publicly at https://www.bestpractices.dev/en/criteria; the self-attestation walks the contributor through each criterion, asking for a citation into the repository that demonstrates the criterion is met. The Passing tier is the table-stakes signal; Silver and Gold require additional engineering practices and are tracked as follow-on work.

Both signals are independently verifiable. A procurement reviewer who has never opened the LQ.AI source tree can confirm "this project meets the OpenSSF Best Practices Passing criteria" by clicking the badge — they do not need to take the maintainer's word for anything. That structural property — engineering rigor that is verifiable, not asserted — is what distinguishes a serious project from a marketing claim. Closed-source vendors cannot earn these badges because the criteria presuppose source visibility; the asymmetry is unanswerable.

## What we'd ship

Four files (three new, one edited):

```
.github/workflows/
└── scorecard.yml             # NEW — runs scorecard-action weekly + on push to main

# repository root
SECURITY-INSIGHTS.yml         # NEW — OSSF SECURITY-INSIGHTS spec, v1.0+

docs/security/
└── best-practices-criteria.md  # NEW — walkthrough of each Passing criterion with citations

README.md                     # EDITED — add two badges + a one-paragraph "Engineering posture" section
```

**`.github/workflows/scorecard.yml`** — based on the OSSF-published example workflow at https://github.com/ossf/scorecard-action#installation. Runs on `schedule: weekly` and `push` to the default branch. Publishes results to OSSF (or stores them as a CI artifact). The badge URL the action emits is the one that lands in the README.

**`SECURITY-INSIGHTS.yml`** — follows the OSSF SECURITY-INSIGHTS specification (https://github.com/ossf/security-insights-spec). Fields populated: header, project lifecycle, contribution-policy, dependencies, documentation, distribution-points, security-artifacts (links to `SECURITY.md`, the threat model, the encrypted-keys doc), vulnerability-reporting (the `security@legalquants.com` email from `SECURITY.md`). The file is the standard format for projects publishing structured security metadata.

**`docs/security/best-practices-criteria.md`** — per-criterion walkthrough. For each Passing criterion: state the criterion in one sentence; cite the repository artifact that satisfies it (a path, a file, a section). Example for the "project_homepage" criterion: cite `README.md` and the project description in `package.json`. Example for the "bug_reporting_process" criterion: cite `SECURITY.md` and `CONTRIBUTING.md`. The walkthrough is the artifact a Best Practices Badge reviewer would assemble themselves; shipping it explicitly means the self-attestation form filling is fast and the reviewer can verify each citation.

**`README.md` edit** — add the Scorecard badge (auto-generated by scorecard-action) and the Best Practices badge (provided by the OpenSSF Best Practices project) near the top of the README, and a short "Engineering posture" section near the bottom (under "About this project" or equivalent) that points to the badges as the at-a-glance signal and to `docs/security/best-practices-criteria.md` for the underlying walkthrough.

## How we'd know it's done

- [ ] `.github/workflows/scorecard.yml` exists, runs cleanly on PRs, produces a Scorecard result, and uploads it as the action documents.
- [ ] The Scorecard score on the default branch is at least 7.0 (the documented M1 target). If below 7.0 at first run, the contributor documents the specific failing checks in `best-practices-criteria.md` with a gap-closure plan.
- [ ] `SECURITY-INSIGHTS.yml` exists at the repository root, validates against the OSSF spec, and accurately reflects the current security posture.
- [ ] `docs/security/best-practices-criteria.md` exists and walks every Passing-tier criterion with a citation into the repository that demonstrates the criterion is met.
- [ ] The OpenSSF Best Practices Badge Passing tier is awarded on https://www.bestpractices.dev/ (the contributor walks through the self-attestation form). The badge link from the awarded project page is committed to the README.
- [ ] The README displays both badges (Scorecard and Best Practices) near the top of the file.
- [ ] The README's "Engineering posture" section explains what the badges mean and links to `docs/security/best-practices-criteria.md`.
- [ ] No false-positive Scorecard checks: each "low score" on a check is either fixed (branch protection enabled, signed releases configured, etc.) or documented as a deliberate deferral in `best-practices-criteria.md`.

## Where to start

1. Read the OSSF Scorecard documentation at https://github.com/ossf/scorecard and the GitHub Action setup guide at https://github.com/ossf/scorecard-action. The README of `scorecard-action` includes a copy-pasteable workflow template.
2. Read the OpenSSF Best Practices Badge criteria at https://www.bestpractices.dev/en/criteria/0 (Passing tier specifically). The criteria are short and concrete.
3. Read the existing CI workflow at [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) — the new `scorecard.yml` follows similar conventions (the workflow header comments, the trigger patterns). The CI workflow's header (lines 1-20) documents the convention used in this repository.
4. Read [`SECURITY.md`](../../../SECURITY.md) — the security policy underpins several Best Practices criteria and the SECURITY-INSIGHTS file.
5. Read [`docs/security/threat-model.md`](../../security/threat-model.md), [`docs/security/cryptography.md`](../../security/cryptography.md), and [`docs/security/encrypted-keys.md`](../../security/encrypted-keys.md) — these are linked from SECURITY-INSIGHTS as security artifacts.
6. Read the existing [`README.md`](../../../README.md) — note the badge conventions already in use (if any) and the document structure for the new "Engineering posture" section.
7. For Scorecard configuration examples in similar Python+TypeScript projects, browse public projects that publish a Scorecard score >= 7.0 — the OSSF maintains a list at https://securityscorecards.dev/. Pick one with a similar project shape (FastAPI + frontend) and read its `scorecard.yml`.
8. Run the Scorecard tool locally against the repository before opening the PR: `gh repo clone legalquants/lq-ai && cd lq-ai && docker run -e GITHUB_AUTH_TOKEN=$GH_TOKEN gcr.io/openssf/scorecard:stable --repo=github.com/legalquants/lq-ai`. The output tells you which checks pass and which need work.

## Scope cuts (what's out of scope for this PR)

- The Best Practices Badge **Silver** and **Gold** tiers are tracked as follow-on work and are not in scope. Silver requires signed commits enforced on main and a few additional practices; Gold requires multi-factor authentication for committers, public reproducible builds, and other criteria. Both are documented separately in the engineering-discipline roadmap.
- Closing specific Scorecard check failures that require deeper engineering work (e.g., adding fuzzing for additional surfaces, configuring SBOM publication if not yet shipped, adding a dependency-update bot if not present) are tracked as separate issues — they are not blocking the badge-publication PR.
- Configuring branch protection on `main` via the GitHub UI is a maintainer-permission action and lives outside this PR. The PR documents the recommended branch-protection settings in `best-practices-criteria.md`; a maintainer applies the settings.
- The Scorecard score floor target ("≥7.0 at M1, ≥8.5 at M2") is documented in the new file but the actual roadmap commitment to those numbers is a separate PRD update.

## How this strengthens the project

The badges are the project's at-a-glance verifiable engineering-discipline signal. A reviewer comparing legal-AI products opens the README and sees two badges that resolve to public, independently-verifiable assessment pages. The same reviewer comparing a closed-source competitor sees marketing copy. The asymmetry is structural: the Scorecard and Best Practices Badge criteria presuppose source visibility, so a closed-source product cannot earn the same badges at any price.

Internally, the badge criteria are a forcing function: each failing check is a backlog item the project agrees to either close or document the rationale for. Targeting Passing at M1, Silver at M2, and Gold at M4 makes the engineering-discipline trajectory concrete and trackable.

## References

- OpenSSF Scorecard: https://github.com/ossf/scorecard
- OpenSSF Scorecard GitHub Action: https://github.com/ossf/scorecard-action
- OpenSSF Best Practices Badge: https://www.bestpractices.dev/
- Best Practices Passing tier criteria: https://www.bestpractices.dev/en/criteria/0
- OpenSSF SECURITY-INSIGHTS spec: https://github.com/ossf/security-insights-spec
- [PRD §1.8 Security Posture](../../PRD.md#18-security-posture)
- [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) — existing CI workflow conventions
- [`SECURITY.md`](../../../SECURITY.md) — security policy
- [`docs/security/threat-model.md`](../../security/threat-model.md)
- [`docs/security/encrypted-keys.md`](../../security/encrypted-keys.md)
- Related: [Mini-PRD: Air-gap install verification CI test](air-gap-install-verification.md)

## Definition of "merged"

The PR is merged when (a) the acceptance criteria checklist is fully checked off, (b) the maintainer has confirmed the Scorecard score on the default branch is at the target floor (or has agreed to the documented gap-closure plan for any failing checks), and (c) the Best Practices Badge Passing tier is awarded on bestpractices.dev with the badge URL committed to the README. Practicing-attorney attestation is not required for this engineering-discipline contribution.
