# PRIV-7 — ROPA population (build · skill=ropa-population) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT yet scenario-qualified (ADR-F015) — this run is a qualification data point, kept verbatim, not tuned green.
- **Source notice:** Zendesk — https://www.zendesk.co.uk/company/agreements-and-terms/privacy-notice/ (retrieved 2026-06-19; Real public notice, testing-only — held transiently, not committed.)
- **Generated:** 2026-06-19T09:47:20+00:00

> Article 30 register the agent built through the guarded, code-validated ROPA tools. Every persisted row is valid by construction (the write path rejects invalid proposals); this report measures coverage + coherence, not validity. Kept verbatim per ADR-F015 — a thin or messy register is a finding, not a failure.

## Coverage

- **Activities:** 8 · **Systems:** 3 · **Vendors/recipients:** 3 · **Transfers:** 2 (2 restricted)
- **Distinct data-subject categories:** 3 · **distinct data categories:** 6
- **Activities fully linked** (system + recipient + both category axes): 1/8
- **Linkage axis fractions:** {'has_system': 0.12, 'has_recipient': 0.12, 'has_data_subject_category': 0.12, 'has_data_category': 0.12}
- **Invariant integrity (special-category ⇔ Art 9):** OK

## Runs

| Run | Status | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- |
| Build pass 1 — populate the ROPA from the notice | `cap_exceeded` | search_documents, read_document, write_todos, read_file, list_processing_activities, list_systems, list_vendors, list_data_subject_categories, list_data_categories, list_transfers, write_todos, propose_processing_activity, add_data_subject_categories, list_processing_activities, add_data_subject_categories, add_data_categories, propose_system, propose_system, propose_system, list_systems, link_processing_activity_to_system, link_processing_activity_to_system, propose_vendor, propose_vendor, propose_vendor | 60 | 57.2s |
| Build pass 2 — fill gaps without duplicating | `cap_exceeded` | search_documents, list_processing_activities, list_systems, list_vendors, list_transfers, list_data_subject_categories, list_data_categories, read_document, write_todos, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, propose_transfer, propose_transfer, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, list_processing_activities, propose_processing_activity, list_processing_activities | 60 | 58.3s |

## Produced register

### Corporate Transactions

- **Purpose:** Evaluate and execute corporate transactions including sales, mergers, acquisitions, bankruptcies, and other restructuring activities; disclosure of personal dat…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Personal data shared for transaction evaluation retained only during the transaction process; if transaction completes, data retained per successor entity's ret…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Diversity, Equity and Inclusion Initiatives

- **Purpose:** Process optional diversity data (race, ethnicity) for diversity, equity and inclusion monitoring and initiatives, where permitted by law and with explicit conse…
- **Lawful basis:** consent · **role:** controller · special-category (explicit_consent)
- **Retention:** Until consent withdrawn or the specific DEI purpose is achieved; anonymised/aggregated statistics retained indefinitely for reporting purposes.
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Internal Business Administration

- **Purpose:** Maintain internal business records; accounting and auditing; IT security monitoring; business evaluation and research/development; survey response analysis.
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Duration of the business relationship plus 7 years after termination for legal/tax/accounting compliance; survey data retained as long as necessary for the purp…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Legal and Safety Compliance

- **Purpose:** Comply with legal obligations and safety/security requirements; establish and defend legal claims; protect safety, rights and integrity of individuals; investig…
- **Lawful basis:** legal_obligation · **role:** controller
- **Retention:** As long as necessary for the specific legal/safety purpose; retained for the duration of any legal proceedings plus applicable statutory limitation periods (typ…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Marketing and Advertising

- **Purpose:** Market products and services; solicit testimonials; send marketing communications; facilitate contests and promotions; customise advertising (including cross-de…
- **Lawful basis:** consent · **role:** controller
- **Retention:** Until consent withdrawn or marketing relationship ends; after opt-out, retained on suppression list for compliance purposes. Cookie data retained per Cookie Not…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Referral Program

- **Purpose:** Fulfil referral requests using provided name, email, job title, and company name of the referred individual.
- **Lawful basis:** consent · **role:** controller
- **Retention:** Until the referral purpose is fulfilled plus a reasonable period (e.g. 6 months) for follow-up, unless consent renewed.
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Service Delivery and Operations

- **Purpose:** Provide products, services, and Digital Properties; process transactions; enable access; operate, maintain and improve services; communicate with users; diagnos…
- **Lawful basis:** contract · **role:** controller
- **Retention:** Duration of the customer relationship plus 7 years after termination for legal/tax/accounting compliance (assumption based on general retention statement: "as l…
- **Systems:** CCTV and Physical Security Systems, Cookie and Tracking Technologies, Zendesk Platform and Digital Properties
- **Recipients:** Business Partners, Service Providers (Processors), Zendesk Affiliates
- **Data subjects:** Business Partners, Customers, Website Visitors
- **Data categories:** Audio And Visual Data, Commercial Information, Geolocation Data, Identifiers, Inferences, Internet Activity
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates'}, {'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Service Providers (Processors)'}]

### Voluntary Consent-Based Processing

- **Purpose:** Process personal data for specific voluntary purposes where individuals have given their consent (e.g. optional surveys, additional marketing activities, non-es…
- **Lawful basis:** consent · **role:** controller
- **Retention:** Until consent is withdrawn or the specific consented purpose is achieved; thereafter retained only as anonymised/aggregated data.
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Systems (all)

[{'name': 'CCTV and Physical Security Systems', 'system_type': 'other', 'ai_usage': False}, {'name': 'Cookie and Tracking Technologies', 'system_type': 'analytics', 'ai_usage': False}, {'name': 'Zendesk Platform and Digital Properties', 'system_type': 'other', 'ai_usage': False}]

### Vendors/recipients (all)

[{'name': 'Business Partners', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'Global'}, {'name': 'Service Providers (Processors)', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'Global'}, {'name': 'Zendesk Affiliates', 'vendor_role': 'joint_controller', 'dpa_status': 'in_place', 'country': 'Global (multiple jurisdictions)'}]
