# PRIV-7 — ROPA population (one-shot) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT yet scenario-qualified (ADR-F015) — this run is a qualification data point, kept verbatim, not tuned green.
- **Source notice:** Zendesk — https://www.zendesk.co.uk/company/agreements-and-terms/privacy-notice/ (retrieved 2026-06-19; Real public notice, testing-only — held transiently, not committed.)
- **Generated:** 2026-06-19T08:13:41+00:00

> Article 30 register the agent built through the guarded, code-validated ROPA tools. Every persisted row is valid by construction (the write path rejects invalid proposals); this report measures coverage + coherence, not validity. Kept verbatim per ADR-F015 — a thin or messy register is a finding, not a failure.

## Coverage

- **Activities:** 8 · **Systems:** 6 · **Vendors/recipients:** 8 · **Transfers:** 0 (0 restricted)
- **Distinct data-subject categories:** 0 · **distinct data categories:** 0
- **Activities fully linked** (system + recipient + both category axes): 0/8
- **Linkage axis fractions:** {'has_system': 0.0, 'has_recipient': 0.0, 'has_data_subject_category': 0.0, 'has_data_category': 0.0}
- **Invariant integrity (special-category ⇔ Art 9):** OK

## Runs

| Run | Status | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- |
| One-shot — build the full ROPA from the notice | `cap_exceeded` | search_documents, read_document, write_todos, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, list_processing_activities, propose_system, propose_system, propose_system, propose_system, propose_system, propose_system, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor | 60 | 88.5s |

## Produced register

### Cookie & Tracking Data Processing

- **Purpose:** Collect and process browsing history, device information, search history, and interaction data via cookies and similar tracking technologies for analytics, site…
- **Lawful basis:** consent · **role:** controller
- **Retention:** Duration set in cookie preference manager; reviewed periodically and deleted upon consent withdrawal (Section 5 — cookies and tracking technologies described in…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Corporate Transactions

- **Purpose:** Evaluate and execute corporate transactions including sales, mergers, acquisitions, and bankruptcy proceedings; conduct due diligence and post-transition integr…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Duration of the transaction plus 6 years after completion for legal/audit purposes (Section 6 — retained for legal/tax/accounting compliance; Section 3 — corpor…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Diversity, Equity & Inclusion Initiatives

- **Purpose:** Collect and process optional demographic data (race, ethnicity, vaccination proof) for diversity, equity, and inclusion initiatives and reporting
- **Lawful basis:** consent · **role:** controller · special-category (explicit_consent)
- **Retention:** Until consent is withdrawn, or data is anonymised for aggregate reporting purposes (Section 6 — deleted when no legitimate need exists; Section 2 — data optiona…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Internal Business Operations

- **Purpose:** Maintain internal business records; perform accounting and auditing; ensure IT security; conduct business evaluation, research and development; analyse survey r…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** 6 years after creation/collection for accounting and audit compliance (Section 6 — retained for business purposes and legal/tax/accounting compliance; deleted, …
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Legal & Security Compliance

- **Purpose:** Comply with legal and safety requirements; establish and defend legal claims; protect safety and integrity of systems and premises; investigate policy violation…
- **Lawful basis:** legal_obligation · **role:** controller
- **Retention:** Duration required by applicable law plus 6 years for litigation holds (Section 6 — retained for legal/tax/accounting compliance; CCTV retention: assumed 30 days…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Marketing & Advertising

- **Purpose:** Market products and services; solicit testimonials; send marketing communications; facilitate contests and promotions; customise advertising on digital properti…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Until consent is withdrawn or 2 years after last engagement for legitimate-interest marketing; consent-based marketing data deleted upon withdrawal (Section 6 —…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Referral Programs

- **Purpose:** Process and fulfil referral requests using provided name, email, job title, and company name
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** 2 years after referral completion (assumption — the notice states retained as long as necessary for collection purposes; Section 6)
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Service Delivery & Product Operations

- **Purpose:** Provide products, services, and digital properties; process transactions; enable user access; operate, maintain, and improve services; communicate with users; d…
- **Lawful basis:** contract · **role:** controller
- **Retention:** Duration of the user relationship plus 6 years after last interaction for legal/accounting compliance (Section 6 — personal data retained as long as necessary f…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Systems (all)

[{'name': 'CCTV & Physical Security Systems', 'system_type': 'other', 'ai_usage': False}, {'name': 'Cookie & Analytics Infrastructure', 'system_type': 'analytics', 'ai_usage': False}, {'name': 'Internal Corporate Systems', 'system_type': 'other', 'ai_usage': False}, {'name': 'Marketing & Event Systems', 'system_type': 'email_marketing', 'ai_usage': False}, {'name': 'Zendesk.com & Digital Properties', 'system_type': 'other', 'ai_usage': False}, {'name': 'Zendesk Product Platform', 'system_type': 'support', 'ai_usage': False}]

### Vendors/recipients (all)

[{'name': 'Business Partners', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'United States (primary); potentially global'}, {'name': 'Cookie & Tracking Companies', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'United States (primary); potentially global'}, {'name': 'Corporate Transaction Counterparties', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'Global'}, {'name': 'Government & Law Enforcement Agencies', 'vendor_role': 'recipient', 'dpa_status': 'not_required', 'country': 'Global'}, {'name': 'Professional Advisors', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'United States (primary); local advisors in other jurisdictions'}, {'name': 'Service Providers (Processors)', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'United States (primary); potentially global'}, {'name': 'Transaction Partners', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'United States (primary)'}, {'name': 'Zendesk Affiliates', 'vendor_role': 'joint_controller', 'dpa_status': 'in_place', 'country': 'Multiple (US, UK, Ireland, Germany, France, India, Brazil, Australia, Japan, Singapore, Canada, Spain, Italy, Netherlands, Sweden, Mexico, Portugal, Poland, Serbia)'}]
