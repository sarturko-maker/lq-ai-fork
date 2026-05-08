# Repo-Opening Checklist

> **Purpose:** Operational sequence for taking the InHouse AI repository from private/staging to publicly open. Run through this checklist immediately before publishing; nothing here is hard, but the order matters and skipped steps are visible to the first wave of visitors.

This is a one-time checklist, expected to take 2–4 hours of focused work to complete (not counting the time to actually source the test corpus or stand up the Discord server, which run in parallel).

---

## Phase 1 — Pre-publish (before the repo is public)

### 1.1 File placement audit

The following files must be at the repository root, exactly named:

- [ ] `README.md` — the front-door doc.
- [ ] `LICENSE` — Apache License 2.0, with the project's copyright notice.
- [ ] `CONTRIBUTING.md` — engineering contribution guide.
- [ ] `CODE_OF_CONDUCT.md` — Contributor Covenant, project-customized.
- [ ] `SECURITY.md` — vulnerability disclosure policy.
- [ ] `.gitignore` — appropriate for the project's stack.

The following structure must exist under root:

- [ ] `docs/PRD.md` — the canonical PRD (v0.2).
- [ ] `docs/architecture.md` — architecture diagram and rationale.
- [ ] `docs/skill-authoring-guide.md` — operational skill-authoring conventions.
- [ ] `docs/quickstart.md` — the long-form quickstart.
- [ ] `docs/quickstart/sample-nda.md` — the demonstration NDA.
- [ ] `docs/compliance/README.md` — Compliance Alignment Pack index. (Component documents may be stub-status pending M1; document the stubbing in the README.)
- [ ] `docs/security/README.md` — security artifacts index. (Threat model, SBOM, etc., may be stub-status pending M1.)
- [ ] `docs/procurement/README.md` — procurement-readiness pack stub.
- [ ] `skills/CONTRIBUTING.md` — skill-specific contribution guide.
- [ ] `skills/<skill-name>/` — one folder per starter skill, each with `SKILL.md`, `reference/`, `examples/`, and (the new addition) `test-plan.md`.
- [ ] `docs/acceptance-testing-framework.md` — master testing framework. (Note: the per-skill test plans live alongside the skills in `skills/<skill-name>/test-plan.md` per Step 2's grounding choice; the framework document is the meta-document.)
- [ ] `.github/` — GitHub-specific configuration (templates, workflows). See section 1.4.

### 1.2 LICENSE verification

- [ ] The `LICENSE` file contains the unmodified Apache 2.0 license text (from <https://www.apache.org/licenses/LICENSE-2.0.txt>).
- [ ] A `NOTICE` file is present if the project incorporates code under licenses that require attribution beyond Apache 2.0 (e.g., MIT-licensed dependencies that require notice).
- [ ] The copyright line at the top of source files reads `Copyright LegalQuants and InHouse AI contributors. Licensed under the Apache License, Version 2.0.` (or equivalent project-standard form).
- [ ] PyMuPDF AGPL boundary is documented in `docs/PRD.md` Appendix B and in any source files that interact with PyMuPDF directly.

### 1.3 Cross-reference audit

The documentation cross-references each other in many places. Before publishing, verify:

- [ ] Every link in `README.md` resolves to an actual file or section.
- [ ] Every link in `docs/PRD.md` resolves (the PRD is heavily cross-referenced — section anchors, Appendix references, DE-### references).
- [ ] `docs/architecture.md` Mermaid diagram renders correctly on GitHub. **Test by opening the file on GitHub and visually verifying the diagram renders.** If it doesn't render, paste the Mermaid block into <https://mermaid.live> to debug syntax issues.
- [ ] Every `skills/<skill-name>/SKILL.md` is a valid agentskills.io artifact (frontmatter parses; required fields present).
- [ ] Every `skills/<skill-name>/test-plan.md` references the right skill and the right framework document.

A cheap way to validate: clone the repo as if a new visitor and click through the documentation in the order a new visitor would (README → quickstart → skill-authoring guide → PRD). Note any dead links or rendering issues.

### 1.4 GitHub-specific configuration

Create `.github/` with the following:

- [ ] **`ISSUE_TEMPLATE/bug-report.yml`** — structured form: what happened, expected behavior, reproduction, environment, version. Include "Have you searched existing issues?" checkbox.
- [ ] **`ISSUE_TEMPLATE/feature-request.yml`** — structured form: what use case, why it can't be met today, proposed approach, references to PRD §9 if applicable.
- [ ] **`ISSUE_TEMPLATE/skill-proposal.yml`** — structured form for proposing new skills: skill name and description, perspective branching if any, inputs, output format, target audience, has-the-DE-### entry. References `skills/CONTRIBUTING.md`.
- [ ] **`ISSUE_TEMPLATE/security-vulnerability.yml`** — short form that *redirects* to the security disclosure email. The template body says: "**Do not file security vulnerabilities as public GitHub issues.** Report to security@legalquants.com per `SECURITY.md`. This template exists only to redirect; close after reading."
- [ ] **`ISSUE_TEMPLATE/config.yml`** — disables blank-issue creation; surfaces the templates above.
- [ ] **`PULL_REQUEST_TEMPLATE.md`** — checklist: what does this PR do, what does it not do, tests added, docs updated, DCO sign-off, related issues. Include the skill-attestation paragraph for skill PRs that the contributor uncomments if applicable.
- [ ] **`CODEOWNERS`** — protects sensitive paths:
  ```
  # Maintainers review by default
  *                              @legalquants/maintainers

  # Security-sensitive paths require security review
  /SECURITY.md                   @legalquants/security
  /docs/security/                @legalquants/security
  /gateway/                      @legalquants/maintainers @legalquants/security

  # Compliance docs require review by counsel + maintainers
  /docs/compliance/              @legalquants/counsel @legalquants/maintainers

  # Skills containing legal substance require attorney review
  /skills/                       @legalquants/maintainers @legalquants/practicing-attorneys
  ```
- [ ] **`workflows/`** — at minimum `lint.yml` and `test.yml` for CI. Multi-arch container build, SBOM generation, Trivy/CodeQL scans land at M1 milestone but stub workflows can ship now.

### 1.5 Branch protection rules

On the `main` branch:

- [ ] **Require pull request before merging.** No direct commits to main.
- [ ] **Require approvals** — at least 1 from a maintainer; 2 for changes affecting multiple subsystems.
- [ ] **Require review from CODEOWNERS** — automatic.
- [ ] **Require status checks to pass before merging** — list the CI workflows that must succeed (lint, tests, container builds).
- [ ] **Require branches to be up to date before merging** — yes (forces rebases or merges of recent main into PR before merging).
- [ ] **Require signed commits** — recommended, especially given the DCO requirement.
- [ ] **Require linear history** — yes (enforces squash-merge or rebase-merge; no merge commits).
- [ ] **Include administrators** — yes (admins follow the same rules).
- [ ] **Allow force pushes** — no.
- [ ] **Allow deletions** — no.

### 1.6 Labels schema

Create a consistent label scheme. Suggested:

**Type labels:**
- `bug` (red)
- `enhancement` (light blue)
- `documentation` (gray)
- `skill-proposal` (purple)
- `skill-contribution` (purple, lighter)
- `question` (yellow)
- `security` (dark red — but security-vulns shouldn't be filed as issues anyway)

**Effort labels (mirror PRD DE-### conventions):**
- `effort: S` — days
- `effort: M` — weeks
- `effort: L` — months

**Priority labels:**
- `priority: P1` — should be addressed in v1.5+
- `priority: P2` — community-friendly any time
- `priority: P3` — nice-to-have

**Process labels:**
- `good first issue` (green) — calibrated for first-time contributors.
- `help wanted` (green) — particularly welcomes community contribution.
- `acceptance-test-fail` (orange) — surfaced by acceptance testing.
- `needs-attestation` (purple) — skill PR awaiting practicing-attorney attestation.
- `needs-review` (yellow) — PR ready for review.
- `blocked` (gray) — blocked on external dependency or decision.
- `duplicate` (light gray)
- `wontfix` (light gray) — closed after consideration.

**Subsystem labels (for routing):**
- `subsystem: gateway`
- `subsystem: skills`
- `subsystem: backend`
- `subsystem: web`
- `subsystem: word-addin`
- `subsystem: docs`
- `subsystem: compliance`

### 1.7 Security configuration

GitHub repository settings → Security:

- [ ] **GitHub Security Advisories** — enabled. Coordinated disclosure flows through this.
- [ ] **Dependabot alerts** — enabled.
- [ ] **Dependabot security updates** — enabled.
- [ ] **Secret scanning** — enabled.
- [ ] **Push protection** for secrets — enabled.
- [ ] **Code scanning** with CodeQL — enabled (run will appear when first CI workflow lands; that's fine).
- [ ] **Private vulnerability reporting** — enabled (gives security researchers a way to report through GitHub if they don't want to use the email channel).

### 1.8 Discussion configuration

GitHub repository settings → Discussions:

- [ ] **Enabled.**
- [ ] Categories created: `Announcements` (maintainer-only), `General`, `Help`, `Show and tell`, `Skill proposals`, `Roadmap discussion`.
- [ ] Welcome post drafted (see Phase 3).

### 1.9 Repository metadata

GitHub repository settings → General:

- [ ] **Description:** "Open-source AI for in-house legal teams. Bring your own keys, run it where you want, own your data."
- [ ] **Website:** legalquants.com (or whichever URL you want canonical).
- [ ] **Topics (tags):** `legal-tech`, `ai`, `legal-ai`, `in-house-counsel`, `contract-review`, `self-hosted`, `open-source`, `nda`, `dpa`, `gdpr`, `inference-gateway`. Topics drive discoverability — pick the ones that match how your audience searches.
- [ ] **Default branch:** `main`.
- [ ] **Wiki:** disabled (we use `docs/`).
- [ ] **Projects:** optional (enable if you plan to track work in GitHub Projects).
- [ ] **Sponsorships:** disabled for v1 (LegalQuants commercial services are how the project sustains, not GitHub sponsorships).

---

## Phase 2 — Pre-public dry run

### 2.1 Visit the repo as a logged-out user

- [ ] Open an incognito browser window.
- [ ] Navigate to the repo URL.
- [ ] Verify the README renders correctly.
- [ ] Click through the documentation as a new visitor would: README → quickstart → skill-authoring guide → PRD. Note any rendering issues.
- [ ] Open `docs/architecture.md` and verify the Mermaid diagram renders.
- [ ] Open one of the starter skill folders (e.g., `skills/nda-review/SKILL.md`) and verify it reads coherently.
- [ ] Try filing a test issue (you can delete it after) to verify the issue templates work as designed.

### 2.2 Have a friendly reviewer do the same

Before going public, send the staging URL to 2–3 people for a final review:

- [ ] **At least 1 in-house counsel** who can evaluate whether the README and quickstart land for the target audience.
- [ ] **At least 1 engineer** who can evaluate whether the contribution path is clear.
- [ ] **At least 1 procurement-or-security professional** who can evaluate whether §1.8 / Appendix E land.

Their feedback before public launch is much more valuable than after — public-facing typos and unclear sections are corrected easily before launch but become visible once published.

---

## Phase 3 — Day-one operational tasks (in order)

Run these in sequence on launch day.

### 3.1 Make the repo public

- [ ] GitHub repository settings → General → Danger Zone → Change repository visibility → Public.
- [ ] Verify README renders correctly publicly.

### 3.2 Open the initial issues

- [ ] Open the 12 curated initial issues (one issue per file). Use the corresponding labels (`good first issue`, `help wanted`, `skill-contribution`, etc.).
- [ ] Pin 3 of them as featured: 1 skill-contribution, 1 engineering, 1 documentation. Pin via the "..." menu on each issue.

### 3.3 Open the welcome discussion

In GitHub Discussions:

- [ ] Open a pinned post in `Announcements`: *"InHouse AI is now open source. What it is, what's shipped, and how to get involved."* — this is the same content as the LinkedIn announcement, adapted for an inside-baseball audience reading the GitHub Discussions tab. Cross-link to README, quickstart, PRD.
- [ ] Open a discussion in `Help` titled *"First-run gotchas: what tripped you up?"* — preempts and aggregates quickstart issues, makes the page friendlier.
- [ ] Open a discussion in `Roadmap discussion` titled *"M1 status and the M5+ direction — what's coming and how to weigh in"* — pulls people into the strategic conversation.

### 3.4 Discord setup

- [ ] Discord server is up with channels: `#announcements`, `#general`, `#help`, `#skill-authors`, `#contributors`, `#showcase`, `#meta`.
- [ ] Discord invite link is in the README (and in the LinkedIn post).
- [ ] First message in `#announcements`: same as the GitHub welcome post, calibrated for synchronous chat.

### 3.5 LinkedIn coordination

- [ ] LegalQuants official LinkedIn page publishes the announcement post.
- [ ] Kevin reposts to his personal feed with the personal note.
- [ ] Tag relevant people / companies thoughtfully — avoid mass tagging; tag people whose actual work the project relates to.
- [ ] Pin the post on the LegalQuants page.

### 3.6 Heads-up to friendly contributors

- [ ] Send direct outreach (not LinkedIn comments — direct DM or email) to 5–10 specific people whose engagement you'd value: practicing attorneys interested in legal-AI, engineers in the space, friendly customers/colleagues. Brief note: "we're publishing this today; if you find it interesting, here's the link."
- [ ] Don't spam. Quality of initial response matters more than volume.

---

## Phase 4 — First-week operational tasks

### 4.1 Response cadence

- [ ] **First-day issues and PRs:** respond within 4 hours during launch day. Sets the tone for engagement.
- [ ] **Week 1:** respond within 24 hours.
- [ ] **Steady state:** respond within 5 business days.

The first response doesn't have to resolve the issue — even a "thanks for filing this; we'll dig in by end of week" is meaningful. Silence in week 1 kills momentum.

### 4.2 First-week monitoring

- [ ] Watch GitHub stars and traffic (Insights → Traffic). Stars in week 1 mostly come from the LinkedIn audience; longer-tail traffic from search and inbound links is where the real growth is.
- [ ] Watch Discord for first questions. Answer with care.
- [ ] Watch for the first community-filed issue, the first PR, the first skill proposal. Each of these is a touch-point that warrants immediate response.

### 4.3 First-week communication

- [ ] **End of week 1:** post a brief follow-up on LinkedIn: "Week 1 in numbers — X stars, Y issues filed, Z PRs opened, here's what's most surprising." Continues the public engagement cycle.
- [ ] **End of week 1:** post a brief update in `Announcements` on GitHub Discussions: same content adapted for the GitHub audience.
- [ ] **End of week 1:** internal retrospective with maintainer team — what went well, what could be better, what to adjust for week 2.

---

## Common pitfalls

- **Publishing without testing the documentation links.** A README with broken links to the PRD reads as sloppy and undermines the substance. The cross-reference audit (§1.3) is the single highest-leverage prep step.
- **Going public on a Friday afternoon.** Tuesday or Wednesday morning gets the engagement window; Friday afternoon gets the weekend dead zone.
- **Over-tagging on LinkedIn.** Tagging 20 people in a launch post is annoying and ignored; tagging 3–5 specific people whose work this is genuinely relevant to is high-quality.
- **Treating issues as a backlog rather than a conversation.** The first 50 issues are conversations with potential contributors. Engage substantively; don't let them sit.
- **Letting the repo go quiet after launch.** Week 2 silence after a noisy launch reads as abandonment. Even brief weekly progress notes maintain momentum.
- **Conflating "open source" with "free labor."** Don't expect community contributions to substitute for maintainer work; treat community contributions as bonus while you continue executing M1. Premature dependence on community contribution kills projects.

---

## Notes for the maintainer team

The repo-opening checklist gets the project into the public square. What happens after is the long game:

- **The first 90 days set the tone.** If the first 90 days are responsive, substantive, and welcoming, the project has the conditions for community to grow. If the first 90 days are erratic or quiet, the project has uphill work to recover.
- **Skill contributions are the canonical artifact of value** (per [PRD §7.1](docs/PRD.md#71-project-philosophy)). The first community-contributed skill is a meaningful milestone — celebrate it visibly when it lands.
- **The procurement-defense story compounds with deployments.** Each operator who deploys InHouse AI and shares their experience (anonymously or otherwise) becomes part of the procurement-defense corpus for the next operator. The Compliance Alignment Pack and Pre-Empted Procurement Objections appendix are the substrate; real deployments are the validation.
- **Stay honest about what's shipped vs. what's planned.** The forward-looking M5+ roadmap is genuinely forward-looking; don't let marketing energy turn it into a delivery commitment. The "we're not promising this; we're naming it" framing in [§8.5](docs/PRD.md#m5m7--forward-looking-workflow-intelligence-community-driven-not-committed) is the right tone.

---

*Checklist maintained alongside the project. Updates land as launch lessons surface; substantive changes warrant maintainer-team review.*
