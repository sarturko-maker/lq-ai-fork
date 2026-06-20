# PRIV-A2 — assessment build (build · skill=pia-generation) — deepseek-pro

- **Model:** alias 'deepseek-pro' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, not tuned green.
- **Generated:** 2026-06-20T22:24:20+00:00

> The agent composed the assessment tools (propose → link → add_risk → complete) from a plain-language ask. Every write is valid by construction (the guarded, code-validated path, ADR-F018); this report measures whether the agent built a defensible, completed DPIA. Kept verbatim per ADR-F015 — a thin result is a finding, not a failure.

## Verdict: ✅ 1 completed, integrity OK

- **Assessments:** 1 (by type: {'dpia': 1}; by status: {'completed': 1})
- **Completed:** 1
- **Completion-rule integrity** (every completed DPIA/high has a documented mitigation, ADR-F027): **True**
- **Total risks:** 6 (with documented mitigation: 6)
- **Assessments linked to an activity:** 1.0
- **Risks with documented mitigation:** 1.0

## Per assessment

| Title | type | status | rating | risks | mitigated | linked | rule ok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DPIA: AI-driven churn prediction and personalised retention/pricing | dpia | completed | high | 6 | 6 | 1 | True |

## Risks recorded (agent's own text, excerpted)

**DPIA: AI-driven churn prediction and personalised retention/pricing** (dpia, completed, rating=high):
- _highxmedium, open_ — Inadequate transparency — Articles 13-15 &amp; 22(2)(b): Individuals are unlikely to know they are being profiled by AI or understand how the model's logic affects the pricing and offers they see. GDPR requires meaningful information about …  
  ↳ mitigation: Before launch: (1) Publish a plain-English notice in the privacy policy and in-app at the point users first see a personalised offer, explaining: that AI profiling is used, the categories of data used (behavioural, account, demographic), ho…
- _highxhigh, open_ — Article 22 — Unlawful automated individual decision-making: The AI model automatically determines the retention offers and pricing shown to each user with no human intervention. These decisions have a significant financial effect on individ…  
  ↳ mitigation: Before launch: (1) Conduct a legal analysis to identify the correct Article 22(2) gateway — if contract necessity cannot be established (i.e., churn prediction is not essential to perform the service), obtain explicit consent from each data…
- _mediumxhigh, open_ — Discriminatory or biased outcomes: The AI model combines demographic data with behavioural events to predict churn and set pricing. If demographic data includes protected characteristics (age, gender, ethnicity, postcode-proxy for socioecon…  
  ↳ mitigation: Before launch: (1) Conduct a bias audit of the training data and model outputs — test for statistically significant disparities in churn scores and offer/pricing decisions across demographic subgroups (age band, gender, geography). Publish …
- _mediumxmedium, open_ — International transfer risk — Mixpanel (US): Behavioural and account data flows to Mixpanel in the United States for analytics processing and then feeds the AI model. The DPA with SCCs is in place but no transfer risk assessment (TRA) has b…  
  ↳ mitigation: Before launch: (1) Conduct and document a transfer risk assessment for the Mixpanel US transfer, assessing US intelligence services' access powers against the data categories in transit (behavioural events, account data) and the likelihood/…
- _highxmedium, open_ — Purpose limitation breach — repurposing analytics data for automated decisions: The existing Product analytics processing collects behavioural and account data for the purpose "Understand product usage to improve the service." Feeding that …  
  ↳ mitigation: Before launch: (1) Conduct and document an Article 6(4) compatibility assessment — evaluate: (a) the link between the original analytics purpose and the new profiling/pricing purpose, (b) the context of collection (did users reasonably expe…
- _mediumxmedium, open_ — Data minimisation — unbounded demographic data: The processing combines "demographic data" with behavioural events, but the scope of demographic data is not defined. If it includes unnecessary or excessive categories (e.g., precise age, eth…  
  ↳ mitigation: Before launch: (1) Produce a definitive list of the demographic data fields that will be used by the model, with a written necessity justification for each field tied to its predictive value for churn. (2) Any demographic field that cannot …

## Run

- **Status:** `completed` · **steps:** 95 · **model turns:** 21 · **latency:** 109.7s
- **Tools called:** read_file, list_processing_activities, list_assessments, list_systems, list_vendors, list_transfers, search_documents, read_document, write_todos, propose_processing_activity, add_data_subject_categories, add_data_categories, list_processing_activities, add_data_subject_categories, add_data_categories, write_todos, propose_system, link_processing_activity_to_system, link_processing_activity_to_system, link_vendor_to_activity, propose_transfer, list_systems, link_processing_activity_to_system, write_todos, propose_assessment, list_assessments, link_assessment_to_activity, write_todos, add_risk, add_risk, add_risk, add_risk, add_risk, add_risk, complete_assessment, list_assessments, write_todos
- **Final answer (excerpt):** ---

## DPIA Complete — AI-driven churn prediction and personalised retention/pricing

**Assessment ID:** `17ecf5a3-332d-43cd-812a-3caa6ab66060`  
**Status:** Completed | **Risk rating:** **HIGH**

### What was recorded

#### New ROPA activity
Created **"AI-driven churn prediction and personalised retention/pricing"** (`ac961311-ba85-4944-9df8-953464de3783`) — separate from the existing "Product analytics" activity because the purpose (automated decisions affecting individuals' financial terms) is materially different and higher risk. Key attributes:

| Field | Value |
|---|---|
| Purpose | AI profiling of in-app behaviour + account + demographic data to predict churn and determine per-user retention offers and pricing |
| Lawful basis | Legitimate interests (flagged for Article 22 review …
