# PRIV-7 — ROPA population (build · skill=ropa-population) — deepseek-pro

- **Model:** alias 'deepseek-pro' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT yet scenario-qualified (ADR-F015) — this run is a qualification data point, kept verbatim, not tuned green.
- **Source notice:** Zendesk — https://www.zendesk.co.uk/company/agreements-and-terms/privacy-notice/ (retrieved 2026-06-19; Real public notice, testing-only — held transiently, not committed.)
- **Generated:** 2026-06-19T09:49:35+00:00

> Article 30 register the agent built through the guarded, code-validated ROPA tools. Every persisted row is valid by construction (the write path rejects invalid proposals); this report measures coverage + coherence, not validity. Kept verbatim per ADR-F015 — a thin or messy register is a finding, not a failure.

## Coverage

- **Activities:** 3 · **Systems:** 3 · **Vendors/recipients:** 3 · **Transfers:** 0 (0 restricted)
- **Distinct data-subject categories:** 3 · **distinct data categories:** 5
- **Activities fully linked** (system + recipient + both category axes): 2/3
- **Linkage axis fractions:** {'has_system': 0.67, 'has_recipient': 0.67, 'has_data_subject_category': 0.67, 'has_data_category': 0.67}
- **Invariant integrity (special-category ⇔ Art 9):** OK

## Runs

| Run | Status | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- |
| Build pass 1 — populate the ROPA from the notice | `cap_exceeded` | read_file, search_documents, read_document, list_processing_activities, list_systems, list_vendors, list_data_subject_categories, list_data_categories, list_transfers, write_todos, propose_processing_activity, add_data_subject_categories, add_data_categories, list_processing_activities, add_data_subject_categories, add_data_categories, propose_system, propose_system, propose_system, list_systems, link_processing_activity_to_system, link_processing_activity_to_system, link_processing_activity_to_system, propose_vendor, propose_vendor, propose_vendor | 60 | 70.3s |
| Build pass 2 — fill gaps without duplicating | `cap_exceeded` | list_processing_activities, list_systems, list_vendors, list_transfers, list_data_subject_categories, list_data_categories, search_documents, read_document, read_file, write_todos, link_processing_activity_to_system, link_processing_activity_to_system, link_vendor_to_activity, link_vendor_to_activity, propose_processing_activity, list_processing_activities, add_data_subject_categories, add_data_categories, link_processing_activity_to_system, link_vendor_to_activity, link_vendor_to_activity, link_vendor_to_activity, write_todos, propose_processing_activity, list_processing_activities | 60 | 63.9s |

## Produced register

### Internal Business Records & Operations

- **Purpose:** Internal business records; accounting; auditing; IT security; business evaluation; research and development; survey responses
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** 7 years after termination of the relevant commercial relationship (assumption: standard limitation period plus accounting/legal hold buffer)
- **Systems:** Zendesk CRM & Transaction Systems
- **Recipients:** Professional Advisors, Service Providers (Zendesk), Zendesk Affiliates
- **Data subjects:** Customers, Prospective Customers, Website Visitors
- **Data categories:** Commercial Information, Identifiers, Internet/Electronic Network Activity
- **Transfers:** —

### Legal, Safety & Security Compliance

- **Purpose:** Legal, safety and security compliance; establish and defend legal claims; protect safety and integrity of services; investigate violations; detect and prevent f…
- **Lawful basis:** legitimate_interests · **role:** controller
- **Retention:** 7 years after termination of the relevant commercial relationship (assumption: standard limitation period plus accounting/legal hold buffer; legal claims limita…
- **Systems:** —
- **Recipients:** —
- **Data subjects:** —
- **Data categories:** —
- **Transfers:** —

### Service Delivery & Operations

- **Purpose:** Provide products, Services and Digital Properties; process transactions; enable access; operate, maintain and improve services; communicate with users; diagnose…
- **Lawful basis:** contract · **role:** controller
- **Retention:** 7 years after termination of the relevant commercial relationship (assumption: standard limitation period plus accounting/legal hold buffer)
- **Systems:** Zendesk Cookie & Tracking Infrastructure, Zendesk CRM & Transaction Systems, Zendesk Digital Properties
- **Recipients:** Service Providers (Zendesk), Zendesk Affiliates
- **Data subjects:** Customers, Prospective Customers, Website Visitors
- **Data categories:** Audio/Visual/Sensory Information, Commercial Information, Geolocation Information, Identifiers, Internet/Electronic Network Activity
- **Transfers:** —

### Systems (all)

[{'name': 'Zendesk Cookie & Tracking Infrastructure', 'system_type': 'analytics', 'ai_usage': False}, {'name': 'Zendesk CRM & Transaction Systems', 'system_type': 'crm', 'ai_usage': False}, {'name': 'Zendesk Digital Properties', 'system_type': 'other', 'ai_usage': False}]

### Vendors/recipients (all)

[{'name': 'Professional Advisors', 'vendor_role': 'separate_controller', 'dpa_status': 'not_required', 'country': 'Various'}, {'name': 'Service Providers (Zendesk)', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'Various'}, {'name': 'Zendesk Affiliates', 'vendor_role': 'joint_controller', 'dpa_status': 'not_required', 'country': 'Various (US, UK, Ireland, Brazil, Japan, Australia, Singapore, France, Poland, India, Canada, Korea, Portugal, Sweden, Mexico, Spain, Netherlands, Italy, Serbia — per Section 14)'}]
