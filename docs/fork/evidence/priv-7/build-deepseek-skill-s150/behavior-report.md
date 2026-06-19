# PRIV-7 — ROPA population (build · skill=ropa-population · max_steps=150) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT yet scenario-qualified (ADR-F015) — this run is a qualification data point, kept verbatim, not tuned green.
- **Source notice:** Zendesk — https://www.zendesk.co.uk/company/agreements-and-terms/privacy-notice/ (retrieved 2026-06-19; Real public notice, testing-only — held transiently, not committed.)
- **Generated:** 2026-06-19T09:55:11+00:00

> Article 30 register the agent built through the guarded, code-validated ROPA tools. Every persisted row is valid by construction (the write path rejects invalid proposals); this report measures coverage + coherence, not validity. Kept verbatim per ADR-F015 — a thin or messy register is a finding, not a failure.

## Coverage

- **Activities:** 9 · **Systems:** 6 · **Vendors/recipients:** 8 · **Transfers:** 0 (0 restricted)
- **Distinct data-subject categories:** 10 · **distinct data categories:** 7
- **Activities fully linked** (system + recipient + both category axes): 9/9
- **Linkage axis fractions:** {'has_system': 1.0, 'has_recipient': 1.0, 'has_data_subject_category': 1.0, 'has_data_category': 1.0}
- **Invariant integrity (special-category ⇔ Art 9):** OK

## Runs

| Run | Status | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- |
| Build pass 1 — populate the ROPA from the notice | `failed` | search_documents, read_document, write_todos, list_processing_activities, list_systems, list_vendors, list_data_subject_categories, list_data_categories, list_transfers, write_todos, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, propose_processing_activity, list_processing_activities, propose_system, propose_system, propose_system, propose_system, propose_system, propose_system, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, propose_vendor, write_todos, list_systems, list_vendors, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories | 113 | 74.3s |
| Build pass 2 — fill gaps without duplicating | `cap_exceeded` | search_documents, list_processing_activities, list_systems, list_vendors, list_transfers, list_data_subject_categories, list_data_categories, read_document, write_todos, add_data_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_subject_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, add_data_categories, write_todos, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, write_todos, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity | 150 | 89.9s |

## Produced register

### Corporate transactions

- **Purpose:** Process personal data in connection with corporate transactions including sales, mergers, acquisitions, and bankruptcy
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Retained as long as necessary for the transaction and any surviving legal obligations; deleted, anonymised or aggregated when no longer needed
- **Systems:** Internal IT and Business Systems, Zendesk.com and Digital Properties
- **Recipients:** Corporate Transaction Entities, Professional Advisors, Transaction Partners, Zendesk Affiliates
- **Data subjects:** Customers, Employees, Users
- **Data categories:** Audio Visual And Sensory Information, Commercial Information, Identifiers
- **Transfers:** —

### Diversity, equity and inclusion initiatives

- **Purpose:** Collect and process optional sensitive personal data (race/ethnicity, vaccination proof) for diversity, equity and inclusion monitoring
- **Lawful basis:** consent · **role:** controller · special-category (explicit_consent)
- **Retention:** Retained as long as necessary for DEI purposes; deleted, anonymised or aggregated when no legitimate need exists
- **Systems:** Internal IT and Business Systems
- **Recipients:** Service Providers, Zendesk Affiliates
- **Data subjects:** Employees, Job Applicants
- **Data categories:** Identifiers, Sensitive Personal Data
- **Transfers:** —

### Internal business operations and analytics

- **Purpose:** Internal business records; accounting; auditing; IT security; business evaluation; research and development; survey response analysis
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Retained as long as necessary for business purposes; deleted, anonymised or aggregated when no legitimate need exists
- **Systems:** CRM and Marketing System, Internal IT and Business Systems
- **Recipients:** Professional Advisors, Service Providers, Zendesk Affiliates
- **Data subjects:** Customers, Employees, Job Applicants, Survey Participants, Users, Website Visitors
- **Data categories:** Commercial Information, Identifiers, Inferences
- **Transfers:** —

### Legal, security and fraud prevention

- **Purpose:** Legal, safety and security compliance; establish and defend legal claims; protect safety and integrity of services; investigate violations; detect and prevent f…
- **Lawful basis:** legal_obligation · **role:** controller
- **Retention:** Retained as long as necessary for legal and compliance purposes; deleted, anonymised or aggregated when no legitimate need exists
- **Systems:** CCTV and Office Security Systems, Internal IT and Business Systems, Zendesk.com and Digital Properties
- **Recipients:** Government and Law Enforcement, Professional Advisors, Service Providers, Zendesk Affiliates
- **Data subjects:** Customers, Employees, Office Visitors, Users, Website Visitors
- **Data categories:** Audio Visual And Sensory Information, Identifiers, Internet And Electronic Network Activity
- **Transfers:** —

### Marketing and advertising

- **Purpose:** Market products and services; solicit testimonials; send marketing communications; facilitate contests; customise advertising based on browsing and interaction …
- **Lawful basis:** consent · **role:** controller
- **Retention:** Retained as long as necessary for the collection purposes; deleted, anonymised or aggregated when no legitimate need exists
- **Systems:** Branded Social Media, Cookie and Tracking Infrastructure, CRM and Marketing System, Zendesk.com and Digital Properties
- **Recipients:** Business Partners, Cookie and Tracking Companies, Service Providers, Zendesk Affiliates
- **Data subjects:** Customers, Marketing Contacts, Users, Website Visitors
- **Data categories:** Geolocation Information, Identifiers, Inferences, Internet And Electronic Network Activity
- **Transfers:** —

### On-premises security and visitor management

- **Purpose:** Process CCTV recordings and interaction recordings for office security; manage visitor data for in-person interactions at offices
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** Retained as long as necessary for security purposes; deleted, anonymised or aggregated when no legitimate need exists
- **Systems:** CCTV and Office Security Systems
- **Recipients:** Service Providers, Zendesk Affiliates
- **Data subjects:** Employees, Office Visitors
- **Data categories:** Audio Visual And Sensory Information, Identifiers
- **Transfers:** —

### Referral programme

- **Purpose:** Fulfil referral requests using provided name, email, title and company information
- **Lawful basis:** consent · **role:** controller
- **Retention:** Retained as long as necessary for referral fulfilment; deleted when no longer needed
- **Systems:** CRM and Marketing System, Zendesk.com and Digital Properties
- **Recipients:** Service Providers, Zendesk Affiliates
- **Data subjects:** Customers, Referral Contacts
- **Data categories:** Identifiers
- **Transfers:** —

### Service delivery and product operations

- **Purpose:** Provide products, services, and Digital Properties; process transactions; enable customer access; operate, maintain and improve services; communicate with users…
- **Lawful basis:** contract · **role:** controller
- **Retention:** Retained as long as necessary for the collection purposes; after relationship termination, retained for surviving contract provisions, business purposes, and le…
- **Systems:** Internal IT and Business Systems, Zendesk.com and Digital Properties
- **Recipients:** Business Partners, Service Providers, Transaction Partners, Zendesk Affiliates
- **Data subjects:** Customers, Users, Website Visitors
- **Data categories:** Audio Visual And Sensory Information, Commercial Information, Geolocation Information, Identifiers, Inferences, Internet And Electronic Network Activity, Sensitive Personal Data
- **Transfers:** —

### Webinar and event management

- **Purpose:** Register and manage attendees for webinars, events, programmes and marketing activities; communicate with attendees about event logistics
- **Lawful basis:** contract · **role:** controller
- **Retention:** Retained as long as necessary for event purposes; deleted, anonymised or aggregated when no legitimate need exists
- **Systems:** CRM and Marketing System, Zendesk.com and Digital Properties
- **Recipients:** Business Partners, Service Providers, Zendesk Affiliates
- **Data subjects:** Customers, Event Attendees, Marketing Contacts
- **Data categories:** Commercial Information, Identifiers
- **Transfers:** —

### Systems (all)

[{'name': 'Branded Social Media', 'system_type': 'other', 'ai_usage': False}, {'name': 'CCTV and Office Security Systems', 'system_type': 'other', 'ai_usage': False}, {'name': 'Cookie and Tracking Infrastructure', 'system_type': 'analytics', 'ai_usage': False}, {'name': 'CRM and Marketing System', 'system_type': 'crm', 'ai_usage': False}, {'name': 'Internal IT and Business Systems', 'system_type': 'other', 'ai_usage': False}, {'name': 'Zendesk.com and Digital Properties', 'system_type': 'other', 'ai_usage': False}]

### Vendors/recipients (all)

[{'name': 'Business Partners', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': None}, {'name': 'Cookie and Tracking Companies', 'vendor_role': 'processor', 'dpa_status': 'pending', 'country': None}, {'name': 'Corporate Transaction Entities', 'vendor_role': 'recipient', 'dpa_status': 'not_required', 'country': None}, {'name': 'Government and Law Enforcement', 'vendor_role': 'recipient', 'dpa_status': 'not_required', 'country': None}, {'name': 'Professional Advisors', 'vendor_role': 'processor', 'dpa_status': 'pending', 'country': None}, {'name': 'Service Providers', 'vendor_role': 'processor', 'dpa_status': 'pending', 'country': 'Multiple jurisdictions'}, {'name': 'Transaction Partners', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': None}, {'name': 'Zendesk Affiliates', 'vendor_role': 'recipient', 'dpa_status': 'pending', 'country': 'Multiple jurisdictions'}]
