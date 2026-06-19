# PRIV-7 — ROPA population (staged) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT yet scenario-qualified (ADR-F015) — this run is a qualification data point, kept verbatim, not tuned green.
- **Source notice:** Zendesk — https://www.zendesk.co.uk/company/agreements-and-terms/privacy-notice/ (retrieved 2026-06-19; Real public notice, testing-only — held transiently, not committed.)
- **Generated:** 2026-06-19T08:17:28+00:00

> Article 30 register the agent built through the guarded, code-validated ROPA tools. Every persisted row is valid by construction (the write path rejects invalid proposals); this report measures coverage + coherence, not validity. Kept verbatim per ADR-F015 — a thin or messy register is a finding, not a failure.

## Coverage

- **Activities:** 10 · **Systems:** 10 · **Vendors/recipients:** 9 · **Transfers:** 10 (10 restricted)
- **Distinct data-subject categories:** 7 · **distinct data categories:** 11
- **Activities fully linked** (system + recipient + both category axes): 0/10
- **Linkage axis fractions:** {'has_system': 0.0, 'has_recipient': 0.0, 'has_data_subject_category': 0.7, 'has_data_category': 0.8}
- **Invariant integrity (special-category ⇔ Art 9):** OK

## Runs

| Run | Status | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- |
| Stage 1 — processing activities | `completed` | search_documents, read_document, list_processing_activities, list_systems, list_vendors, list_data_subject_categories, list_data_categories, write_todos, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, list_processing_activities, write_todos | 48 | 52.9s |
| Stage 2 — systems & recipients | `cap_exceeded` | search_documents, read_document, list_systems, list_vendors, list_processing_activities, write_todos, propose_system, propose_system, propose_system, propose_system, propose_system, propose_system, propose_system, propose_system, propose_system, propose_system, write_todos, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor | 50 | 70.0s |
| Stage 3 — international transfers | `cap_exceeded` | search_documents, list_processing_activities, search_documents, search_documents, search_documents, read_document, list_systems, list_vendors, list_transfers, list_data_subject_categories, list_data_categories, write_todos, propose_transfer, propose_transfer, propose_transfer, propose_transfer, propose_transfer, propose_transfer, propose_transfer, propose_transfer, propose_transfer, propose_transfer | 50 | 64.0s |
| Stage 4 — links & categories | `cap_exceeded` | list_processing_activities, list_systems, list_vendors, list_data_subject_categories, list_data_categories, list_transfers, search_documents, read_document, write_todos, add_data_subject_categories, add_data_categories, add_data_subject_categories, add_data_categories, add_data_subject_categories, add_data_categories, add_data_subject_categories, add_data_subject_categories, add_data_categories, add_data_categories, add_data_subject_categories, add_data_categories, add_data_subject_categories, add_data_categories, add_data_subject_categories, add_data_categories | 50 | 39.4s |

## Produced register

### Business Operations and Administration

- **Purpose:** Internal business records; accounting and auditing; IT security monitoring; business evaluation and forecasting; research and development; customer and user sur…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** 7 years after the end of the financial year to which the records relate (standard limitation period for contractual and legal claims)
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Employees
- **Data categories:** Commercial Information, Contact Details, Device Information, Financial Data
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Consent-Based Voluntary Processing

- **Purpose:** Processing personal data for specific voluntary purposes where the individual has given freely given, specific, informed and unambiguous consent, including part…
- **Lawful basis:** consent · **role:** controller
- **Retention:** Until consent is withdrawn or the specific purpose is fulfilled, whichever is sooner; thereafter securely deleted or anonymised within 90 days
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Cookie and Online Tracking Technologies

- **Purpose:** Operating cookies, web beacons, analytics tools and similar tracking technologies on Zendesk Digital Properties for functionality, analytics, advertising and cr…
- **Lawful basis:** consent · **role:** controller
- **Retention:** Duration of the cookie lifespan as set out in the Cookie Notice (typically session to 24 months); analytics data anonymised after 26 months
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Users, Website Visitors
- **Data categories:** Device Information, Geolocation Data, Inferences, Internet Activity, Marketing Preferences
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Corporate Transactions

- **Purpose:** Processing personal data in connection with potential or actual corporate transactions including sales, mergers, acquisitions, reorganisations and bankruptcy pr…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Until transaction completion plus 7 years for post-transaction legal, tax and regulatory record-keeping; abandoned transaction data deleted within 12 months of …
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** Commercial Information, Contact Details, Financial Data
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Diversity, Equity and Inclusion Initiatives

- **Purpose:** Processing voluntarily provided race, ethnicity and vaccination data for diversity, equity and inclusion analytics and reporting
- **Lawful basis:** consent · **role:** controller · special-category (explicit_consent)
- **Retention:** Anonymised or deleted upon consent withdrawal; identifiable data retained no longer than 3 years for longitudinal trend analysis unless consent renewed
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Employees, Job Applicants
- **Data categories:** Race And Ethnicity, Sensitive Personal Data, Vaccination Data
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Legal Compliance and Fraud Prevention

- **Purpose:** Complying with legal, safety and security obligations; establishing, exercising and defending legal claims; protecting the safety and integrity of Zendesk's ser…
- **Lawful basis:** legal_obligation · **role:** controller
- **Retention:** Duration of the legal obligation or 7 years after case closure, whichever is longer
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Employees, Website Visitors
- **Data categories:** Commercial Information, Contact Details, Device Information, Financial Data, Internet Activity
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Marketing and Advertising

- **Purpose:** Marketing Zendesk products and services; soliciting testimonials; sending marketing and promotional communications; facilitating contests and promotions; custom…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Until consent is withdrawn or 2 years after last interaction, whichever is sooner, unless a longer period is justified by an ongoing commercial relationship
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Marketing Contacts, Website Visitors
- **Data categories:** Contact Details, Geolocation Data, Inferences, Internet Activity, Marketing Preferences
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Physical Security and CCTV Monitoring

- **Purpose:** Operating CCTV systems and visitor logs at Zendesk office premises; recording in-person interactions for security, safety and incident investigation purposes
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** 30 days for standard CCTV footage; extended to 90 days where an incident is being investigated; visitor logs retained for 12 months
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Referral Programme

- **Purpose:** Fulfilling referral requests using the referrer's and referred individual's name, email, job title and company name
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Until the referral is fulfilled plus 90 days, unless the referrer has separately consented to longer marketing retention
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Referred Individuals
- **Data categories:** Contact Details
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Service Provision and Account Management

- **Purpose:** Providing access to Zendesk Digital Properties (website, mobile apps, Marketplace, Developer Portal); processing transactions; enabling account access; operatin…
- **Lawful basis:** contract · **role:** controller
- **Retention:** Duration of the contractual relationship plus 90 days, subject to longer retention where required by legal/tax/accounting obligations (e.g., 7 years for financi…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** Customers, Users, Website Visitors
- **Data categories:** Commercial Information, Contact Details, Device Information, Financial Data, Internet Activity
- **Transfers:** [{'destination': 'United States', 'restricted': True, 'mechanism': 'standard_contractual_clauses', 'recipient': 'Zendesk Affiliates (Group Companies)'}]

### Systems (all)

[{'name': 'CCTV and Physical Access Control Systems', 'system_type': 'other', 'ai_usage': False}, {'name': 'Cookie and Analytics Tracking Infrastructure', 'system_type': 'analytics', 'ai_usage': False}, {'name': 'Finance and Accounting Systems', 'system_type': 'database', 'ai_usage': False}, {'name': 'HR and People Operations Systems', 'system_type': 'database', 'ai_usage': False}, {'name': 'Internal IT and Security Monitoring Systems', 'system_type': 'logs', 'ai_usage': False}, {'name': 'Marketing and Advertising Platform', 'system_type': 'email_marketing', 'ai_usage': False}, {'name': 'Referral Programme System', 'system_type': 'other', 'ai_usage': False}, {'name': 'Survey and Feedback Platform', 'system_type': 'other', 'ai_usage': False}, {'name': 'Zendesk Customer Platform (CRM / Support)', 'system_type': 'crm', 'ai_usage': False}, {'name': 'Zendesk Digital Properties', 'system_type': 'other', 'ai_usage': False}]

### Vendors/recipients (all)

[{'name': 'Business Partners', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'United States (and global)'}, {'name': 'Consenting Third Parties', 'vendor_role': 'recipient', 'dpa_status': 'not_required', 'country': 'United States (and global)'}, {'name': 'Cookie and Tracking Technology Providers', 'vendor_role': 'separate_controller', 'dpa_status': 'pending', 'country': 'United States (and global)'}, {'name': 'Corporate Transaction Counterparties', 'vendor_role': 'recipient', 'dpa_status': 'not_required', 'country': 'United States (and global)'}, {'name': 'Law Enforcement and Government Bodies', 'vendor_role': 'recipient', 'dpa_status': 'not_required', 'country': 'United States (and global)'}, {'name': 'Professional Advisors', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'United States (and global)'}, {'name': 'Service Providers (Processors)', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'United States (and global)'}, {'name': 'Transaction Partners', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'United States (and global)'}, {'name': 'Zendesk Affiliates (Group Companies)', 'vendor_role': 'recipient', 'dpa_status': 'in_place', 'country': 'Multiple (US, UK, Ireland, Germany, France, Australia, Japan, Brazil, Singapore, India, Canada, Sweden, Mexico, Spain, Italy, Netherlands, Poland, Serbia, Portugal, Korea)'}]
