# PRIV-8b — ROPA swap (swap · skill=ropa-maintenance) — deepseek-pro

- **Model:** alias 'deepseek-pro' resolves via the gateway to a DeepSeek V4 model (deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, not tuned green.
- **Change:** replace **Mixpanel** with **Hotjar** on "Product analytics"
- **Generated:** 2026-06-19T14:08:12+00:00

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

- **Status:** `completed` · **steps:** 47 · **model turns:** 9 · **latency:** 43.2s
- **Tools called:** read_file, list_processing_activities, list_vendors, list_systems, list_transfers, propose_vendor, propose_system, link_vendor_to_activity, list_vendors, list_systems, link_vendor_to_activity, link_processing_activity_to_system, unlink_vendor_from_activity, unlink_system_from_activity, retire_vendor, retire_system, list_processing_activities, list_vendors, list_systems
- **Final answer (excerpt):** Here's a summary of exactly what changed:

---

### What I did — Mixpanel → Hotjar swap for Product analytics

| Step | Action | Details |
|------|--------|---------|
| **1. Added Hotjar vendor** | `propose_vendor` | Hotjar as **processor**, DPA status **pending**, based in **Malta** |
| **2. Added Hotjar system** | `propose_system` | Hotjar as **analytics** system |
| **3. Linked Hotjar vendor** | `link_vendor_to_activity` | Hotjar now receives data from "Product analytics" |
| **4. Linked Hotjar system** | `link_processing_activity_to_system` | Hotjar is now the system used by "Product analytics" |
| **5. Unlinked Mixpanel vendor** | `unlink_vendor_from_activity` | Mixpanel no longer receives data from this activity |
| **6. Unlinked Mixpanel system** | `unlink_system_from_activity` | Mi…

## Register before → after

- **before — recipients:** [['Mixpanel']]
- **before — systems:** [['Mixpanel']]
- **after — recipients:** [['Hotjar']]
- **after — systems:** [['Hotjar']]
- **after — vendors (all, incl. retired):** [{'name': 'Hotjar', 'vendor_role': 'processor', 'dpa_status': 'pending', 'country': 'Malta', 'retired': False}, {'name': 'Mixpanel', 'vendor_role': 'processor', 'dpa_status': 'in_place', 'country': 'United States', 'retired': True}]
- **after — systems (all, incl. retired):** [{'name': 'Hotjar', 'system_type': 'analytics', 'ai_usage': False, 'retired': False}, {'name': 'Mixpanel', 'system_type': 'analytics', 'ai_usage': False, 'retired': True}]
