# PRIV-A2 — assessment build (build · skill=off) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, not tuned green.
- **Generated:** 2026-06-20T22:21:01+00:00

> The agent composed the assessment tools (propose → link → add_risk → complete) from a plain-language ask. Every write is valid by construction (the guarded, code-validated path, ADR-F018); this report measures whether the agent built a defensible, completed DPIA. Kept verbatim per ADR-F015 — a thin result is a finding, not a failure.

## Verdict: ✅ 1 completed, integrity OK

- **Assessments:** 2 (by type: {'dpia': 2}; by status: {'completed': 1, 'draft': 1})
- **Completed:** 1
- **Completion-rule integrity** (every completed DPIA/high has a documented mitigation, ADR-F027): **True**
- **Total risks:** 6 (with documented mitigation: 6)
- **Assessments linked to an activity:** 0.5
- **Risks with documented mitigation:** 1.0

## Per assessment

| Title | type | status | rating | risks | mitigated | linked | rule ok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI User Profiling for Churn Prediction & Personalised Pricing | dpia | completed | high | 6 | 6 | 1 | True |
| AI User Profiling for Churn Prediction & Personalised Pricing | dpia | draft | — | 0 | 0 | 0 | True |

## Risks recorded (agent's own text, excerpted)

**AI User Profiling for Churn Prediction & Personalised Pricing** (dpia, completed, rating=high):
- _mediumxhigh, open_ — Automated pricing decisions without a valid Article 22 UK GDPR basis — the current lawful basis (legitimate interests) does not satisfy Article 22(2), which requires either contract necessity or explicit consent for automated decisions prod…  
  ↳ mitigation: Identify and document the Article 22(2) gateway: if pricing is part of the contractual relationship, rely on 22(2)(a) (contract necessity) and implement suitable safeguards (human review right, explainability). Alternatively, obtain explici…
- _mediumxhigh, open_ — Model bias or unfair discrimination — the AI model could systematically disadvantage certain customer groups (e.g. newer users, lower-engagement users, specific demographic cohorts) by assigning them higher prices based on churn predictions…  
  ↳ mitigation: Conduct pre-launch bias testing across protected characteristics (age, gender, location). Implement ongoing fairness monitoring with automated drift detection. Set price bands so the model cannot produce prices outside a pre-approved range.…
- _highxmedium, open_ — Lack of transparency — customers are not informed that their behaviour, account and demographic data are being used for AI profiling that determines what they pay. This breaches Articles 13-14 UK GDPR (fair processing information), undermin…  
  ↳ mitigation: Update the privacy notice to clearly disclose: (a) the profiling and automated decision-making; (b) the categories of data used; (c) the logic involved and the significance of the decisions; (d) the right to obtain human intervention and co…
- _mediumxmedium, open_ — International transfer to the United States via Mixpanel — personal data of UK data subjects is transferred to a US processor. The EU SCCs (2021) + UK Addendum are in place but no Transfer Impact Assessment has been completed to confirm tha…  
  ↳ mitigation: Complete a Transfer Impact Assessment (TIA) for the Mixpanel transfer, documenting supplementary measures (technical encryption, contractual provisions) sufficient to address the gap identified in the ICO's guidance on US transfers. If the …
- _mediumxmedium, open_ — Data inaccuracy causing incorrect churn predictions or pricing — stale or incorrect behavioural, account or demographic data could produce a misclassification (e.g. predicting a loyal user as high-churn and offering a discount they don't ne…  
  ↳ mitigation: Implement data-quality checks and staleness rules on all feature inputs. Give users a means to view and correct their account and demographic data. Include a confidence threshold: if the model's prediction confidence is below a set level, d…
- _lowxhigh, open_ — Data security incident exposing profiling data and churn scores — the AI model's input data (behavioural, account, demographic) and output scores (churn prediction, personalised pricing) are sensitive commercial data. A breach could expose …  
  ↳ mitigation: Encryption at rest and in transit; role-based access control limiting model outputs to authorised personnel only; audit logging of all model inference requests; regular penetration testing; separate the model scoring API from the customer-f…

**AI User Profiling for Churn Prediction & Personalised Pricing** (dpia, draft, rating=None):
- (no risks recorded)

## Run

- **Status:** `cap_exceeded` · **steps:** 100 · **model turns:** 25 · **latency:** 117.3s
- **Tools called:** search_documents, list_processing_activities, list_systems, list_vendors, read_document, list_data_categories, list_data_subject_categories, list_assessments, write_todos, propose_processing_activity, list_processing_activities, write_todos, add_data_subject_categories, add_data_categories, write_todos, link_processing_activity_to_system, link_vendor_to_activity, propose_system, list_systems, link_processing_activity_to_system, list_transfers, propose_transfer, write_todos, propose_assessment, list_assessments, add_risk, add_risk, add_risk, add_risk, add_risk, add_risk, write_todos, complete_assessment, propose_assessment, link_assessment_to_activity, list_assessments, propose_assessment, list_assessments
- **Final answer (excerpt):** —
