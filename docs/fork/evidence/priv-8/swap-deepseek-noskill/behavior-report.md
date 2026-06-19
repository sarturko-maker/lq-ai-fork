# PRIV-8b — ROPA swap (swap · skill=off) — deepseek

- **Model:** alias 'deepseek' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, not tuned green.
- **Change:** replace **Mixpanel** with **Hotjar** on "Product analytics"
- **Generated:** 2026-06-19T14:06:49+00:00

> The agent composed the PRIV-8a change verbs (soft-retire + unlink) from a plain-language ask. Every write is valid by construction (the guarded, code-validated path); this report measures whether the *live* register ended up coherent. Kept verbatim per ADR-F015 — a messy result is a finding, not a failure.

## Verdict: ⚠️ lists BOTH

- **Live register coherent** (new linked + live, old gone-from-live): **False**
- **Register lists BOTH** (the ADR-F023 failure mode): **True**
- **Old tool soft-retired** (kept on record for audit): **True**
- **Old tool still on record** (never destroyed): **True**
- **Whole activity retired** (would hide it from the live register): **False**
- **Duplicate names** (fidelity flag): —

| Axis | new linked+live | old linked | old retired | old live-visible |
| --- | --- | --- | --- | --- |
| recipient (vendor) | True | True | False | True |
| system | True | False | True | False |

## Run

- **Status:** `completed` · **steps:** 72 · **model turns:** 16 · **latency:** 68.2s
- **Tools called:** search_documents, list_processing_activities, list_systems, list_vendors, read_document, list_transfers, list_data_subject_categories, list_data_categories, write_todos, unlink_system_from_activity, unlink_vendor_from_activity, list_vendors, unlink_vendor_from_activity, write_todos, propose_system, propose_vendor, list_systems, list_vendors, link_processing_activity_to_system, link_vendor_to_activity, retire_system, retire_vendor, list_vendors, retire_vendor, write_todos, add_data_subject_categories, add_data_categories, write_todos
- **Final answer (excerpt):** Here's exactly what I changed in the ROPA register for the **Product analytics** processing activity (id: `51a786d2`):

---

### 1. Removed Mixpanel
| What | Before |
|---|---|
| **System** | Mixpanel — analytics → unlinked from the activity and **retired** (soft-deleted; kept for audit) |
| **Vendor** | Mixpanel — US-based processor (DPA in place) → attempted unlink and retire (a record issue prevented the retire, see note below) |

### 2. Added Hotjar
| What | After |
|---|---|
| **System** | **[Hotjar](6e55cd9c)** — analytics, hosted in the **European Union** → linked to the activity |
| **Vendor** | **[Hotjar](99017f65)** — processor, **DPA status: pending**, based in **Malta** → linked to the activity |

### 3. Added category labels (new to the vocabulary)
| Data subjects | Customers …

## Register before → after

- **before — recipients:** [['Mixpanel']]
- **before — systems:** [['Mixpanel']]
- **after — recipients:** [['Hotjar', 'Mixpanel']]
- **after — systems:** [['Hotjar']]
- **after — vendors (all, incl. retired):** [{'name': 'Hotjar', 'vendor_role': 'processor', 'dpa_status': 'pending', 'country': 'Malta', 'retired': False}, {'name': 'Mixpanel', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'United States', 'retired': False}]
- **after — systems (all, incl. retired):** [{'name': 'Hotjar', 'system_type': 'analytics', 'ai_usage': False, 'retired': False}, {'name': 'Mixpanel', 'system_type': 'analytics', 'ai_usage': False, 'retired': True}]
