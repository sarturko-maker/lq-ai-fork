---
name: pia-generation
description: Use when conducting or drafting a privacy assessment — a PIA, an Article 35 data-protection impact assessment (DPIA), a legitimate-interests assessment (LIA, the Article 6(1)(f) balancing test), or a transfer impact assessment (TIA, Chapter V) — using the assessment tools (propose_assessment, add_risk, complete_assessment, link_assessment_to_activity, list_assessments) over the company's deployment-global register. Teaches the method that produces a defensible assessment — scope it to the processing activities it covers, work a structured template, identify and SCORE concrete risks to individuals, document specific design-tied mitigations, and complete it only when the high-risk mitigation rule is satisfied.
lq_ai:
  title: Privacy Impact Assessment (PIA / DPIA / LIA / TIA)
  version: 1.0.0
  author: LegalQuants
  tags: [privacy, dpia, pia, lia, tia, article-35, gdpr, risk-assessment, assessment]
  jurisdiction: regime-aware
  trigger_examples:
    - "run a DPIA for our new analytics pipeline"
    - "do a data protection impact assessment for this processing"
    - "we need a PIA before we launch this feature"
    - "assess the legitimate interests for our marketing emails"
    - "do a transfer impact assessment for sending data to the US"
  inputs:
    required:
      - name: processing
        type: text
        description: The processing to assess — a feature, system, vendor arrangement, or an existing ROPA activity. The skill works from what you are told; it does not invent facts the source does not state.
    optional:
      - name: type
        type: text
        description: Which assessment to run — pia, dpia, lia or tia. If absent, choose from the Article 35 / 6(1)(f) / Chapter V triggers below (a DPIA when the processing is likely high risk).
---

# Privacy assessments — building a defensible PIA / DPIA / LIA / TIA

You are conducting a privacy assessment and recording it in the company's assessment register through the
assessment tools. **Every write is validated before it commits**: a proposal that breaks a rule comes back to
you with the reason — read it, fix it, and call the tool again. Never fabricate a value to satisfy a field,
and never claim you recorded or completed something you did not.

## Choose the right assessment

- **DPIA** (`dpia`) — Article 35. **Required** when processing is *likely to result in a high risk* to
  individuals: large-scale special-category data, systematic large-scale monitoring (incl. of a public area),
  systematic profiling with legal/significant effects, innovative/novel technology (incl. AI), matching or
  combining datasets, data on vulnerable subjects, or denial of a service/contract. If two or more of the
  EDPB criteria apply, do a DPIA.
- **PIA** (`pia`) — a lighter privacy impact assessment for processing that is not clearly high-risk but still
  warrants a documented risk look (a screening that may conclude "no DPIA needed", or a general privacy review).
- **LIA** (`lia`) — the Article 6(1)(f) legitimate-interests balancing test: (1) **purpose** — is there a
  legitimate interest? (2) **necessity** — is the processing necessary for it, with no less-intrusive means?
  (3) **balancing** — do the individual's interests, rights and reasonable expectations override it? Record the
  three-part reasoning in the summary; the outcome (proceed / proceed-with-conditions / do-not) is the rating.
- **TIA** (`tia`) — a Chapter V transfer impact assessment: assess the destination country's law and practice
  against the chosen transfer mechanism, and whether supplementary measures are needed.

## The method: scope → risks → mitigations → complete

Build the assessment to completion in this order, so a run cut short still leaves a coherent record:

1. **`propose_assessment`** — create it as a **`draft`** with the `type`, a clear `title`, and a `summary`
   that describes the processing: its nature, scope, context and purposes, and (for an LIA) the three-part
   test. Leave `risk_rating` unset for now. *(A high-risk assessment cannot be created already-`completed` —
   it has no documented risk yet — so always start as a draft.)*
2. **`link_assessment_to_activity`** — link every ROPA processing activity this assessment covers. Use
   `list_processing_activities` to get the IDs (and `propose_processing_activity` first if the activity is not
   yet in the register). An assessment that covers real, linked activities is far more defensible than a
   free-floating one.
3. **`add_risk`** — identify the risks to **individuals** (not to the business) and add one finding each, with
   `likelihood` and `impact` scored low/medium/high. Then give each a **mitigation** (see the quality standard
   below) and set its `status` (`open` until mitigated; `mitigated` once the safeguard is in place; `accepted`
   for a residual risk the business knowingly accepts).
4. **`complete_assessment`** — when the assessment is done, set the overall residual `risk_rating` and complete
   it. **The rule the tool enforces:** a **DPIA**, or **any assessment rated `high`**, cannot be completed
   unless **at least one risk carries a documented (non-blank) mitigation**. If you have not recorded a real
   mitigation, the completion is refused — add one with `add_risk` (or update your approach) and try again.
   Use `conditions` on the assessment for any prerequisites before the processing may proceed (e.g. "DPO
   sign-off; re-review at 6 months").

Call `list_assessments` whenever you need an id or to see current state.

## Risk-quality standard (this is what makes the assessment worth anything)

A risk finding is only useful if it is **specific and the mitigation is design-tied**. For each risk:

- **Name a concrete harm to individuals** — not "data could leak" but e.g. "a misconfigured export endpoint
  could expose customers' contact details and purchase history to other tenants."
- **Score it honestly** — `likelihood` and `impact` each low/medium/high. Special-category data, children, or
  irreversible harm push `impact` up; broad exposure or weak controls push `likelihood` up.
- **Tie the mitigation to a design change, not an intention.** A good mitigation names *what changes*:
  "pseudonymise `user_id` at ingest and drop raw IPs after 24h", "tenant-scoped row-level security on the
  export query", "DPA + SCCs in place before go-live; access limited to the support role". A bad mitigation is
  "we will be careful" or "staff are trained" with nothing concrete. Vague mitigations do not reduce risk and
  will not make a high-risk assessment defensible.

## Field rules the tools enforce (get them right the first time)

- **`type`** — one of `pia`, `dpia`, `lia`, `tia`.
- **`status`** — `draft`, `in_progress`, `completed`. A `completed` assessment MUST carry a `risk_rating`.
- **`risk_rating`** — `low`, `medium`, `high` (the overall residual rating).
- **risk `likelihood` / `impact`** — each `low`, `medium`, `high`.
- **risk `status`** — `open`, `mitigated`, `accepted`.

## Grounding and honesty

Ground every statement in what you were given about the processing. If a material fact is missing (the source
does not say where data is hosted, who the recipients are, what the retention is), record what you can, name
the gap in the summary or as a `condition`, and do not invent specifics. A smaller, honest assessment with
real risks and real mitigations beats a long one padded with generic boilerplate.
