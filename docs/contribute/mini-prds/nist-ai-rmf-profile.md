# Mini-PRD: NIST AI RMF 1.0 Profile Mapping

> **Status:** Open for contribution
> **Effort:** M
> **Contributor profile:** AI-governance, compliance, or risk-management professional with NIST AI RMF (AI 100-1) and the Generative AI Profile (AI 600-1) familiarity. Can pair with the maintainer for code-citation accuracy. ~one to two focused weeks.
> **Mentor:** Maintainer (Kevin Keller, via PR review), with code-citation accuracy support

## What this is

A new document at `docs/compliance/nist-ai-rmf-profile.md` that maps LQ.AI's design, architecture, and operational practices to the NIST AI Risk Management Framework 1.0 (AI 100-1) and the Generative AI Profile (AI 600-1). Each AI RMF subcategory (across the four functions: Govern, Map, Measure, Manage) gets a substantive response: applicability to LQ.AI, the project's design choice or operational practice that addresses it, the operator's responsibility, and any gap with a deferral path.

The Generative AI Profile (AI 600-1) layers AI-system-specific risk categories on top of the framework: data and data preprocessing, model and model preprocessing, confabulation, intellectual property, and others. The mapping document covers both the base framework subcategories and the Generative AI Profile additions.

## Why it matters

The NIST AI RMF is the U.S. federal-aligned framework for AI risk governance. For federal procurement, federal-adjacent enterprise procurement (defense contractors, federally-regulated industries, state-government agencies), and any organization with an AI-governance program structured around NIST, this is the document the operator's AI-governance or compliance team will look for first. Its absence is treated as a signal the vendor has not engaged with AI-specific governance — a signal the project's posture is otherwise designed to invalidate.

The Generative AI Profile is recent (NIST AI 600-1, published July 2024) and the framework most explicitly designed for LLM-touching products. Procurement teams in regulated industries are increasingly asking for Generative AI Profile alignment specifically. Publishing a substantive mapping at M1 closes that procurement objection structurally rather than reactively.

The mapping is also the kind of document that distinguishes a serious AI-governance posture from marketing. Each subcategory gets a real response with a citation into source or operational guidance; where a subcategory is gap (e.g., published eval scores against held-out test sets, which depends on the eval-harness work that is not yet shipped), the gap is named directly with a deferral path. An operator's AI-governance reviewer reads the mapping and can produce a list of substantive follow-up questions — which is the right outcome. A "this is marketing copy" rejection is the wrong outcome and is what happens when the mapping is absent or aspirational.

The asymmetry with closed-source vendors holds here too: their AI RMF mapping, if it exists, asserts the alignment without showing the implementation. Here, every alignment claim cites into the repository.

## What we'd ship

One new file:

```
docs/compliance/
└── nist-ai-rmf-profile.md     # NEW — full Profile mapping
```

Document structure mirrors the framework's organization:

```
# NIST AI RMF 1.0 Profile — LQ.AI Alignment

## Scope and limits
What this document is and is not. The Profile maps LQ.AI's design to the
framework's subcategories; it is not a certification, and certification of a
specific operator's AI-governance program is the operator's responsibility.

## How to read this document
Each subcategory gets four fields:
  - Applicability to LQ.AI
  - Project response (design choice or operational practice with citation)
  - Operator responsibility
  - Gap (if any; with deferral path)

## GOVERN
[GOVERN-1.1 through GOVERN-6.2 subcategories]

## MAP
[MAP-1.1 through MAP-5.2 subcategories]

## MEASURE
[MEASURE-1.1 through MEASURE-4.3 subcategories]

## MANAGE
[MANAGE-1.1 through MANAGE-4.3 subcategories]

## Generative AI Profile (NIST AI 600-1) additions
Covers the Generative-AI-specific risk categories:
  - GAI-1: CBRN information or capabilities
  - GAI-2: Confabulation
  - GAI-3: Dangerous, violent, or hateful content
  - GAI-4: Data privacy
  - GAI-5: Environmental impacts
  - GAI-6: Harmful bias or homogenization
  - GAI-7: Human-AI configuration
  - GAI-8: Information integrity
  - GAI-9: Information security
  - GAI-10: Intellectual property
  - GAI-11: Obscene, degrading, or abusive content
  - GAI-12: Value chain and component integration

## Out of scope
Subcategories that are fully the operator's responsibility (organizational
governance, internal compliance program design, etc.) with a brief note
explaining the boundary.
```

Per-subcategory content lives in four paragraphs:

1. **Applicability to LQ.AI.** Specific. Some subcategories apply directly to the project's design; others apply only to the operator's deployment; a few are not applicable (e.g., subcategories about training data only apply to projects that train their own models).
2. **Project response.** The design choice or operational practice that addresses the subcategory, with a citation. For GOVERN subcategories about documentation: cite the PRD, the security docs, the threat model. For MAP subcategories about risk identification: cite the threat model's STRIDE coverage at [`docs/security/threat-model.md`](../../security/threat-model.md). For MEASURE subcategories about quality measurement: cite the per-skill test plans (`skills/<skill>/test-plan.md`) and name the eval-harness deferral honestly.
3. **Operator responsibility.** Items the operator must do in their deployment to fully address the subcategory (governance structure, internal AI-policy documentation, training of users on the system, etc.). For an OSS self-hosted product, many subcategories carry significant operator responsibility; the mapping makes that explicit.
4. **Gap.** Where the project's response is incomplete, name the gap directly. The Anonymization Layer is M2 (cite [PRD §4.7](../../PRD.md#47-anonymization-layer-m2)); the eval harness with held-out test sets and inter-rater agreement is deferred; published prompt-injection detection rates depend on the eval harness. Honest disclosure of partial alignment is the deliverable.

## How we'd know it's done

- [ ] `docs/compliance/nist-ai-rmf-profile.md` exists and covers all subcategories in AI 100-1 (Govern, Map, Measure, Manage).
- [ ] All Generative AI Profile (AI 600-1) risk categories are addressed with substantive responses, not boilerplate.
- [ ] Every "Project response" claim cites into the repository (PRD section, code module, doc) or into a specific operational practice documented in the project.
- [ ] Subcategories that depend on capability not yet shipped (eval harness, published prompt-injection rates, the Anonymization Layer enforcement path) are named as gaps with citations to the deferral path. The document does not claim the capability is shipped.
- [ ] Subcategories that are fully operator-responsibility (organizational governance, internal AI-policy training, etc.) are marked explicitly rather than left ambiguous.
- [ ] The document is referenced from [`docs/compliance/README.md`](../../compliance/README.md) (status table updated) and linked from the main [`README.md`](../../../README.md) under the engineering-posture or compliance section.
- [ ] An AI-governance professional who has not contributed to LQ.AI can read the document and produce concrete follow-up questions rather than "this is marketing copy."
- [ ] The mapping's "How to read this document" section distinguishes structural alignment (in source) from operator-configured alignment (defaults the operator tunes) from operator-only alignment (subcategories the project cannot address on the operator's behalf).

## Where to start

1. Read the NIST AI Risk Management Framework 1.0 (AI 100-1) at https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf — note the four functions and their subcategories.
2. Read the Generative AI Profile (NIST AI 600-1) at https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf — note the additional risk categories.
3. Read [`docs/compliance/README.md`](../../compliance/README.md) — note the table-of-frameworks pattern; the NIST AI RMF Profile is added to this table.
4. Read [PRD §1.8 Security Posture](../../PRD.md#18-security-posture), [PRD §3.3 Citation Engine](../../PRD.md#33-citation-engine-exact-quote), and [PRD §4.7 Anonymization Layer](../../PRD.md#47-anonymization-layer-m2). These are the substantive content for several MEASURE and MANAGE subcategories and the gap-disclosure surface for Generative AI Profile categories (GAI-2 Confabulation, GAI-4 Data Privacy).
5. Read [`docs/security/threat-model.md`](../../security/threat-model.md) — the STRIDE coverage is the substrate for several MAP subcategories.
6. Read [`docs/security/audit-logging.md`](../../security/audit-logging.md) and the audit writer at [`api/app/audit.py`](../../../api/app/audit.py) — relevant to MEASURE (system-observability subcategories).
7. Read the gateway's tier-floor enforcement at [`gateway/app/tier_floor.py`](../../../gateway/app/tier_floor.py) and the routing-log persistence at [`gateway/app/routing_log.py`](../../../gateway/app/routing_log.py) — these are the technical surface for several MANAGE subcategories.
8. Read [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md) — the skill-contribution process is relevant to GOVERN subcategories about content review and to GAI-10 (Intellectual Property).
9. Read [PRD Appendix E](../../PRD.md#appendix-e--pre-empted-procurement-objections) — many objections in the appendix correspond directly to AI RMF subcategories and provide a substantive starting point.
10. Pair with the maintainer on code-citation accuracy: when a subcategory points at a specific code module, the maintainer can confirm the line range and the behavior. Open the issue with a draft Profile mapping and ask for citation-pass review before going deep on every subcategory.

## Scope cuts (what's out of scope for this PR)

- The NIST AI RMF Playbook (a companion document with prompts and example evidence for each subcategory) is referenced where useful but not duplicated; the mapping cites the Playbook in places where the operator would benefit from reading it.
- Other AI-governance frameworks (ISO/IEC 42001 AI Management Systems, EU AI Act conformity assessment, Singapore Model AI Governance Framework, OECD AI Principles) are out of scope for this PR. The ISO 42001 alignment document is tracked separately in the Compliance Alignment Pack roadmap.
- Operator-specific AI-policy templates (e.g., "an example AI Acceptable Use Policy your organization can adapt") are out of scope; the mapping points the operator at the policy areas they should address, not at template language.
- Per-release AI RMF re-assessment cadence is documented as a future commitment, not a per-release-of-this-PR commitment.
- Measured detection rates (prompt injection, PII leakage) under the relevant MEASURE subcategories are deferred to the eval-harness work; the mapping names what would be measured and cites the deferral path.

## How this strengthens the project

For federal-aligned and federal-adjacent enterprise procurement, the NIST AI RMF Profile is the substantive document the AI-governance team reads first. Publishing a real Profile mapping — every subcategory with a substantive response and a citation — closes the procurement objection structurally rather than punting it to a later release. The closed-source vendor's equivalent document either does not exist or asserts alignment without citing the implementation; the Profile mapping here is verifiable against source by the operator's AI-governance reviewer.

Internally, the Profile is a forcing function. Each gap honestly named in the mapping is a backlog commitment. The Generative AI Profile categories in particular (Confabulation, Data Privacy, Information Integrity) align with the project's central engineering commitments (the Citation Engine; the Anonymization Layer; the audit log); naming the gaps where these capabilities are still maturing is internally aligning, not just externally trustworthy.

## References

- NIST AI RMF 1.0 (AI 100-1): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- NIST AI RMF Generative AI Profile (AI 600-1): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- NIST AI RMF Playbook: https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook
- [PRD §1.8 Security Posture](../../PRD.md#18-security-posture)
- [PRD §3.3 Citation Engine](../../PRD.md#33-citation-engine-exact-quote)
- [PRD §4.7 Anonymization Layer (M2)](../../PRD.md#47-anonymization-layer-m2)
- [PRD Appendix E — Pre-Empted Procurement Objections](../../PRD.md#appendix-e--pre-empted-procurement-objections)
- [`docs/compliance/README.md`](../../compliance/README.md)
- [`docs/security/threat-model.md`](../../security/threat-model.md)
- [`docs/security/audit-logging.md`](../../security/audit-logging.md)
- [`skills/CONTRIBUTING.md`](../../../skills/CONTRIBUTING.md)
- Related: [Mini-PRD: OWASP LLM Top 10 mapping](owasp-llm-top10-mapping.md), [Mini-PRD: Procurement-Readiness Pack](procurement-readiness-pack.md)

## Definition of "merged"

The PR is merged when (a) the acceptance criteria checklist is fully checked off, (b) the maintainer has reviewed the substance against the cited code paths and the framework documents, and (c) an AI-governance or compliance professional (the contributor, or a paired reviewer if the contributor wants the second-set-of-eyes pass) has reviewed the mapping and provided an attestation in the PR description that the alignment claims are substantively accurate and would not mislead an AI-governance reviewer relying on them. Because the Profile carries substantive AI-governance judgment that downstream organizations will rely on, the domain-expert attestation is required.
