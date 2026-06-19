# PRIV-7 — ROPA population (build · skill=off) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT yet scenario-qualified (ADR-F015) — this run is a qualification data point, kept verbatim, not tuned green.
- **Source notice:** Zendesk — https://www.zendesk.co.uk/company/agreements-and-terms/privacy-notice/ (retrieved 2026-06-19; Real public notice, testing-only — held transiently, not committed.)
- **Generated:** 2026-06-19T09:45:24+00:00

> Article 30 register the agent built through the guarded, code-validated ROPA tools. Every persisted row is valid by construction (the write path rejects invalid proposals); this report measures coverage + coherence, not validity. Kept verbatim per ADR-F015 — a thin or messy register is a finding, not a failure.

## Coverage

- **Activities:** 8 · **Systems:** 0 · **Vendors/recipients:** 0 · **Transfers:** 0 (0 restricted)
- **Distinct data-subject categories:** 6 · **distinct data categories:** 7
- **Activities fully linked** (system + recipient + both category axes): 0/8
- **Linkage axis fractions:** {'has_system': 0.0, 'has_recipient': 0.0, 'has_data_subject_category': 1.0, 'has_data_category': 1.0}
- **Invariant integrity (special-category ⇔ Art 9):** OK

## Runs

| Run | Status | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- |
| Build pass 1 — populate the ROPA from the notice | `cap_exceeded` | search_documents, read_document, list_processing_activities, list_systems, list_vendors, list_transfers, list_data_subject_categories, list_data_categories, write_todos, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, write_todos, list_processing_activities, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories | 60 | 48.9s |
| Build pass 2 — fill gaps without duplicating | `cap_exceeded` | list_processing_activities, list_systems, list_vendors, list_transfers, list_data_subject_categories, list_data_categories, search_documents, read_document, write_todos, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, write_todos, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, write_todos | 60 | 55.2s |

## Produced register

### Corporate Transactions

- **Purpose:** Process personal data in connection with corporate transactions including sales, mergers, acquisitions and bankruptcy proceedings
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Duration of the transaction process plus legal retention periods (typically 6-7 years after completion)
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Website Visitors
- **Data categories:** Audio/Visual/Sensory Information, Commercial Information, Identifiers, Internet/Electronic Network Activity
- **Transfers:** —

### Diversity, Equity & Inclusion Initiatives

- **Purpose:** Process optional diversity, equity and inclusion data (including race/ethnicity) where voluntarily provided
- **Lawful basis:** consent · **role:** controller · special-category (explicit_consent)
- **Retention:** Duration of the DEI initiative plus anonymisation or deletion upon completion of the specific initiative
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Event Registrants, Office Visitors
- **Data categories:** Identifiers, Sensitive Personal Data
- **Transfers:** —

### Internal Business Operations

- **Purpose:** Internal business records; accounting; auditing; IT security; business evaluation; research and development; survey responses
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Duration of business relationship plus legal/regulatory retention periods (typically 6-7 years for financial/tax records)
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Event Registrants, Office Visitors, Website Visitors
- **Data categories:** Audio/Visual/Sensory Information, Commercial Information, Identifiers, Inferences, Internet/Electronic Network Activity
- **Transfers:** —

### Legal & Compliance Processing

- **Purpose:** Legal, safety and security compliance; establish and defend legal claims; protect safety and integrity; investigate violations; detect and prevent fraud
- **Lawful basis:** legal_obligation · **role:** controller
- **Retention:** Duration required by law plus applicable statutory limitation periods (typically 6-7 years after the relevant event)
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Event Registrants, Office Visitors, Website Visitors
- **Data categories:** Audio/Visual/Sensory Information, Commercial Information, Identifiers, Internet/Electronic Network Activity, Sensitive Personal Data
- **Transfers:** —

### Marketing & Advertising

- **Purpose:** Market products and services; solicit testimonials; send marketing communications; facilitate contests; customise advertising
- **Lawful basis:** consent · **role:** controller
- **Retention:** Until consent is withdrawn or the marketing relationship ends, then up to 2 years for suppression records
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Contest Participants, Customers, Event Registrants, Website Visitors
- **Data categories:** Geolocation Information, Identifiers, Inferences, Internet/Electronic Network Activity
- **Transfers:** —

### Product & Services Delivery

- **Purpose:** Provide products, services and Digital Properties; process transactions; enable access; operate, maintain and improve; communicate with users; diagnose and repa…
- **Lawful basis:** contract · **role:** controller
- **Retention:** Duration of the business relationship plus legal/regulatory retention periods (typically 6-7 years after termination for tax/accounting compliance)
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Event Registrants, Office Visitors, Website Visitors
- **Data categories:** Audio/Visual/Sensory Information, Commercial Information, Geolocation Information, Identifiers, Internet/Electronic Network Activity
- **Transfers:** —

### Referral Programs

- **Purpose:** Fulfil referral requests using provided names, email addresses, job titles and company names of referred individuals
- **Lawful basis:** consent · **role:** controller
- **Retention:** Duration of the referral programme plus 1 year for verification purposes
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Referred Individuals
- **Data categories:** Identifiers
- **Transfers:** —

### Voluntary Consent-Based Processing

- **Purpose:** Process personal data for any specific purpose for which individuals have given explicit, freely given consent
- **Lawful basis:** consent · **role:** controller · special-category (explicit_consent)
- **Retention:** Until consent is withdrawn or the specific consented purpose is completed
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Contest Participants, Customers, Event Registrants, Office Visitors, Referred Individuals, Website Visitors
- **Data categories:** Audio/Visual/Sensory Information, Commercial Information, Geolocation Information, Identifiers, Inferences, Internet/Electronic Network Activity, Sensitive Personal Data
- **Transfers:** —
