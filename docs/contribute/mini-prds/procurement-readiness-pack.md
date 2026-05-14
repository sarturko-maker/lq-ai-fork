# Mini-PRD: Procurement-Readiness Pack

> **Status:** Open for contribution
> **Effort:** M
> **Contributor profile:** In-house counsel, procurement analyst, or OSS contributor with enterprise-security-review experience. No coding required.
> **Mentor:** Maintainer (Kevin Keller, via PR review)

## What this is

The Procurement-Readiness Pack is a set of pre-filled enterprise procurement-questionnaire responses an operator's procurement team can take into their internal security review on day one. Concretely: a SIG Lite response document, a CAIQ Lite response document, and a cover letter explaining why LQ.AI is an unusual procurement (self-hosted open source, not SaaS) so the procurement reviewer reads the questionnaire responses in the right frame.

The stub at [`docs/procurement/README.md`](../../procurement/README.md) already documents the structure and the `[OPERATOR-CONFIGURABLE]` marker pattern. The work is producing the actual questionnaire content using the existing substance in PRD Appendix E (17 pre-empted procurement objections) and the Compliance Alignment Pack stubs.

## Why it matters

Procurement reviews are the single largest adoption-friction barrier for any enterprise tool. The standard intake process — SIG Lite from Shared Assessments, CAIQ from the Cloud Security Alliance, or a custom enterprise questionnaire — assumes the vendor is a SaaS provider and asks questions structured around that assumption ("which AWS region is the data in?", "what is your data residency policy?"). The answer for a self-hosted open-source product is often "the operator chooses," which is correct but lands as a non-answer in the procurement team's spreadsheet.

The Pack closes that gap by pre-filling the substantive answers, marking the operator-configurable items consistently, and giving the procurement team a cover letter that explains the deployment posture. A second in-house counsel can take the Pack into their procurement team and answer the standard intake questions without re-keying the responses from PRD prose. That is the structural advantage: every claim in the response cites into the repository, so the procurement team's security reviewer can verify each answer against the actual code, configuration, or documentation rather than trusting a vendor's spreadsheet.

A closed-source vendor cannot offer this same artifact in the same shape. Their SIG response answers a question about their SaaS environment; the operator's security team has no way to confirm the answers against the actual implementation. Here, every answer cites into source the operator can read.

## What we'd ship

Three new files under [`docs/procurement/`](../../procurement/):

```
docs/procurement/
├── README.md                # exists; status table updates to reflect the new files
├── sig-lite.md              # NEW — pre-filled SIG Lite responses
├── caiq.md                  # NEW — pre-filled CAIQ Lite responses
└── cover-letter.md          # NEW — sample cover letter for the procurement team
```

**`sig-lite.md`** — every SIG Lite question gets a response in the existing format documented in `docs/procurement/README.md` (Question / Project response / Operator-configurable items / References). SIG Lite has ~100 questions across domains: Risk Management, Security Policy, Organizational Security, Asset Management, Human Resources, Physical Security, Operations Management, Access Control, Application Security, Incident Management, Business Continuity, Compliance, End-User Device Security, Network Security, Privacy, Threat Management, Server Security, Cloud Hosting, IoT Security. Many questions are operator-configurable for a self-hosted deployment; mark those with `[OPERATOR-CONFIGURABLE]` and a one-line description of what the operator should fill in.

**`caiq.md`** — every CAIQ Lite question (~250 questions across the CSA Cloud Controls Matrix v4 domains) gets the same treatment. CAIQ is more cloud-native than SIG Lite; many questions resolve to "the operator deploys this themselves; here is the recommended configuration in `docker-compose.yml` / Helm chart."

**`cover-letter.md`** — a 1-2 page template the operator can adapt. Covers: what LQ.AI is and is not (self-hosted software, not SaaS); how to read the attached questionnaire responses (the `[OPERATOR-CONFIGURABLE]` marker convention); where to find the underlying artifacts (PRD §1.8, the Compliance Alignment Pack stubs, the threat model, the SBOM, the source); how the procurement team's security reviewer can independently verify each answer.

## How we'd know it's done

- [ ] `docs/procurement/sig-lite.md` exists and covers every SIG Lite question in the current published version (track the version in the document front-matter).
- [ ] `docs/procurement/caiq.md` exists and covers every CAIQ Lite question in the current published CCM version.
- [ ] `docs/procurement/cover-letter.md` exists and is adaptable by a non-maintainer in under 30 minutes.
- [ ] Every response either (a) cites into the repository (PRD section, code module, doc) or (b) is marked `[OPERATOR-CONFIGURABLE]` with a description of what the operator fills in.
- [ ] No response invents project capability that does not exist. Items deferred (the Citation Engine M2, the Anonymization Layer M2, etc.) are answered honestly: "structurally addressed by [design choice]; full mitigation is M2 per [PRD §X]." The `[OPERATOR-CONFIGURABLE]` marker is not used as a fig leaf for unshipped capability.
- [ ] `docs/procurement/README.md` is updated to remove the "TBD" markers for the three new files.
- [ ] A second in-house counsel (not the contributor) reads the Pack and can answer at least 80% of the standard intake questions for a hypothetical deployment without writing new prose.

## Where to start

1. Read [`docs/procurement/README.md`](../../procurement/README.md) in full — it documents the format and the marker convention.
2. Read [PRD Appendix E](../../PRD.md#appendix-e--pre-empted-procurement-objections) (17 pre-empted procurement objections). The substantive answers to the highest-traffic questionnaire categories are already written there in prose; the work is restructuring them into row-by-row questionnaire responses.
3. Read [PRD §1.8 Security Posture](../../PRD.md#18-security-posture) for the underlying posture.
4. Read [`docs/security/threat-model.md`](../../security/threat-model.md) for the STRIDE coverage that backs many security-domain answers.
5. Read [`docs/compliance/README.md`](../../compliance/README.md) for the framework-mapping context.
6. Obtain the current SIG Lite and CAIQ Lite questionnaire templates from Shared Assessments (https://sharedassessments.org/sig/) and the Cloud Security Alliance (https://cloudsecurityalliance.org/research/cloud-controls-matrix/) respectively. Both are published with redistribution constraints; the contribution authors LQ.AI's responses to the questions, not the questionnaires themselves.

## Scope cuts (what's out of scope for this PR)

- The Compliance Alignment Pack documents themselves (`soc2-alignment.md`, `iso27001-alignment.md`, etc.) are tracked separately in [`docs/compliance/`](../../compliance/) and are not authored here. The SIG/CAIQ responses can cite "see SOC 2 alignment doc when published" for control-mapping answers that the alignment docs will eventually carry.
- Custom enterprise security questionnaires (e.g., a specific Fortune-500 buyer's internal template) are out of scope; SIG Lite and CAIQ Lite are the two industry-standard formats and that is what the Pack covers.
- A procurement-team-facing one-pager on the "two axes" framing is a launch-communications artifact, not a procurement-readiness artifact; it is not part of this PR.
- The Acceptable Use Policy / Statement of Operational Controls template (`aup-soc-template.md`) listed as "Future" in `docs/procurement/README.md` remains future; this PR ships the three questionnaire artifacts.

## How this strengthens the project

The Pack is the artifact a procurement reviewer asks for first, and the artifact a closed-source competitor cannot match in shape. Their SIG response answers a question about their managed environment; the operator's security team cannot independently verify each answer. The Pack's answers cite into the repository, so the operator's security reviewer can confirm "access controls operate effectively" by reading `api/app/api/auth.py` rather than trusting an attestation. The verification path does not terminate in a paid intermediary.

The substantive payoff: every operator who adopts LQ.AI does this work once for their own procurement team. The Pack saves the next operator from re-deriving the answers. Procurement-cycle time, not feature parity, is the throttle on enterprise adoption for self-hosted open-source legal AI; the Pack moves the throttle.

## References

- [PRD §1.8 Security Posture](../../PRD.md#18-security-posture)
- [PRD Appendix E — Pre-Empted Procurement Objections](../../PRD.md#appendix-e--pre-empted-procurement-objections)
- [PRD §9 — DE-086 Procurement-Readiness Pack](../../PRD.md#de-086--procurement-readiness-pack)
- [`docs/procurement/README.md`](../../procurement/README.md) — stub documenting the format
- [`docs/compliance/README.md`](../../compliance/README.md) — Compliance Alignment Pack scope
- [`docs/security/threat-model.md`](../../security/threat-model.md) — STRIDE coverage
- Shared Assessments SIG: https://sharedassessments.org/sig/
- Cloud Security Alliance CCM / CAIQ: https://cloudsecurityalliance.org/research/cloud-controls-matrix/
- Related: [Mini-PRD: OWASP LLM Top 10 mapping](owasp-llm-top10-mapping.md), [Mini-PRD: NIST AI RMF 1.0 Profile](nist-ai-rmf-profile.md)

## Definition of "merged"

The PR is merged when (a) the acceptance criteria checklist is fully checked off, (b) the maintainer has reviewed the substance for accuracy against the underlying PRD and code citations, and (c) a practicing attorney (in-house counsel or procurement-experienced legal-ops practitioner) has reviewed the Pack and provided an attestation in the PR description that the responses are substantively accurate and would not mislead a procurement reviewer relying on them. The attestation follows the format documented in [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md#3-attest) — the same attestation pattern applies because the procurement responses are work product the in-house counsel community will rely on.
