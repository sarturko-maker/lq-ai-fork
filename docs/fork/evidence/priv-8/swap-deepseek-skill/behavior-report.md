# PRIV-8b — ROPA swap (swap · skill=ropa-maintenance) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, not tuned green.
- **Change:** replace **Mixpanel** with **Hotjar** on "Product analytics"
- **Generated:** 2026-06-19T14:07:28+00:00

> The agent composed the PRIV-8a change verbs (soft-retire + unlink) from a plain-language ask. Every write is valid by construction (the guarded, code-validated path); this report measures whether the *live* register ended up coherent. Kept verbatim per ADR-F015 — a messy result is a finding, not a failure.

## Verdict: ✅ coherent

- **Live register coherent** (new linked + live, old gone-from-live): **True**
- **Register lists BOTH** (the ADR-F023 failure mode): **False**
- **Old tool soft-retired** (kept on record for audit): **True**
- **Old tool still on record** (never destroyed): **True**
- **Whole activity retired** (would hide it from the live register): **False**
- **Duplicate names** (fidelity flag): —

| Axis | new linked+live | old linked | old retired | old live-visible |
| --- | --- | --- | --- | --- |
| recipient (vendor) | True | False | True | False |
| system | True | False | True | False |

## Run

- **Status:** `completed` · **steps:** 53 · **model turns:** 9 · **latency:** 38.4s
- **Tools called:** read_file, search_documents, list_vendors, list_systems, list_processing_activities, read_document, list_data_subject_categories, list_data_categories, list_transfers, propose_vendor, propose_system, list_vendors, list_systems, link_vendor_to_activity, link_processing_activity_to_system, unlink_vendor_from_activity, unlink_system_from_activity, retire_vendor, retire_system, list_vendors, list_systems, list_processing_activities
- **Final answer (excerpt):** All done. Here's exactly what I changed:

---

### Changes made to the ROPA register

| Step | What happened |
|------|--------------|
| **Added** | **Hotjar** as a **vendor** (processor, Malta) — DPA status set to **pending** (I don't have the actual status; the DPA needs to be put in place — see flag below) |
| **Added** | **Hotjar** as a **system** (analytics, hosted in the European Union) |
| **Linked** | Hotjar (vendor + system) to the **Product analytics** processing activity |
| **Unlinked** | Mixpanel (vendor + system) from **Product analytics** |
| **Retired** | **Mixpanel vendor** — company-wide removal, kept on record for audit with reason "Replaced by Hotjar for product analytics" |
| **Retired** | **Mixpanel system** — company-wide removal, kept on record for audit with reason…

## Register before → after

- **before — recipients:** [['Mixpanel']]
- **before — systems:** [['Mixpanel']]
- **after — recipients:** [['Hotjar']]
- **after — systems:** [['Hotjar']]
- **after — vendors (all, incl. retired):** [{'name': 'Hotjar', 'vendor_role': 'processor', 'dpa_status': 'pending', 'country': 'Malta', 'retired': False}, {'name': 'Mixpanel', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'United States', 'retired': True}]
- **after — systems (all, incl. retired):** [{'name': 'Hotjar', 'system_type': 'analytics', 'ai_usage': False, 'retired': False}, {'name': 'Mixpanel', 'system_type': 'analytics', 'ai_usage': False, 'retired': True}]
