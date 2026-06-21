# PRIV-A2 — assessment build (build · skill=pia-generation) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, not tuned green.
- **Generated:** 2026-06-20T22:22:30+00:00

> The agent composed the assessment tools (propose → link → add_risk → complete) from a plain-language ask. Every write is valid by construction (the guarded, code-validated path, ADR-F018); this report measures whether the agent built a defensible, completed DPIA. Kept verbatim per ADR-F015 — a thin result is a finding, not a failure.

## Verdict: ✅ 1 completed, integrity OK

- **Assessments:** 1 (by type: {'dpia': 1}; by status: {'completed': 1})
- **Completed:** 1
- **Completion-rule integrity** (every completed DPIA/high has a documented mitigation, ADR-F027): **True**
- **Total risks:** 5 (with documented mitigation: 5)
- **Assessments linked to an activity:** 1.0
- **Risks with documented mitigation:** 1.0

## Per assessment

| Title | type | status | rating | risks | mitigated | linked | rule ok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DPIA — AI User Profiling for Churn Prediction and Personalised Offers | dpia | completed | high | 5 | 5 | 1 | True |

## Risks recorded (agent's own text, excerpted)

**DPIA — AI User Profiling for Churn Prediction and Personalised Offers** (dpia, completed, rating=high):
- _mediumxhigh, open_ — Automated pricing and offer decisions without human review (Article 22 UK GDPR): the AI model directly determines what retention offers and prices each customer sees. If the model misclassifies a user or produces an anomalous score, the use…  
  ↳ mitigation: Implement a clear human-review right: any user can request manual review of their profiling score and resulting offer/price by a human agent within 7 calendar days, with a documented outcome and right to correction. Additionally, flag any p…
- _mediumxmedium, open_ — Model inaccuracy and false churn classification: the AI model will inevitably produce false positives (users incorrectly flagged as churn risks) and false negatives. False positives may lead to unnecessary, unsolicited retention offers or d…  
  ↳ mitigation: Quarterly model accuracy monitoring against holdout ground-truth data, with documented precision/recall metrics and automatic retraining if F1 score drops below 0.85. Maintain a dispute log where users can challenge a price or offer decisio…
- _mediumxhigh, open_ — Intrusive inferences from combined data sources: combining behavioural events (in-app actions), account data (contact details, plan type), and demographic data enables the model to infer sensitive attributes the user has not disclosed — suc…  
  ↳ mitigation: (1) Pre-deployment feature-inference mapping: data science team documents every model feature and identifies what latent/sensitive attributes it could serve as a proxy for. (2) Hard-blocking rule: any feature flagged as a proxy for special-…
- _highxmedium, open_ — Lack of transparency and individual-rights friction: users are not clearly told that their in-app behaviour, account data, and demographic data are combined to profile them for automated pricing decisions. This makes it difficult for indivi…  
  ↳ mitigation: (1) Update the privacy notice before launch with a dedicated "Profiling and automated decisions" section describing: the categories of data combined, the logic of the churn model in plain language, the fact that pricing and offers are deter…
- _mediumxhigh, open_ — Bias and indirect discrimination in pricing outcomes: the model uses demographic data alongside behavioural and account data. If the training data contains historical pricing patterns or behavioural correlations linked to protected characte…  
  ↳ mitigation: (1) Pre-launch differential-impact audit: test model outputs across all demographic groups available in the data; publish the results to the DPO and product lead before go-live. (2) Exclude protected characteristics (age band, geo-region) f…

## Run

- **Status:** `completed` · **steps:** 75 · **model turns:** 15 · **latency:** 88.4s
- **Tools called:** search_documents, list_processing_activities, list_systems, list_vendors, list_assessments, read_document, propose_processing_activity, propose_system, list_processing_activities, list_systems, list_data_subject_categories, list_data_categories, add_data_subject_categories, add_data_categories, link_processing_activity_to_system, link_vendor_to_activity, read_file, propose_assessment, link_assessment_to_activity, list_assessments, link_assessment_to_activity, add_risk, add_risk, add_risk, add_risk, add_risk, complete_assessment, list_assessments, list_processing_activities, list_systems
- **Final answer (excerpt):** Here is what I recorded, in full.

---

## DPIA — Completed

**Assessment:** DPIA — AI User Profiling for Churn Prediction and Personalised Offers  
**Status:** Completed · **Residual risk rating:** High  
**ID:** `7b5e4ce5-3942-414a-b79d-c4bf7c4571c8`

**Linked to ROPA activity:** "AI User Profiling for Churn Prediction and Personalised Offers" (`abbc7201-f97d-4d34-8998-e52795d2ff58`)

---

### ROPA entry created for the new processing

| Field | Value |
|---|---|
| **Name** | AI User Profiling for Churn Prediction and Personalised Offers |
| **Purpose** | Profile individual users from in-app behaviour + account + demographic data to predict churn risk and determine personalised retention offers/pricing — automated decisions with significant effects |
| **Lawful basis** | Legitimate inter…
