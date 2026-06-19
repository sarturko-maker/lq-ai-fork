---
name: ropa-maintenance
description: Use when keeping an existing Article 30 Record of Processing Activities (ROPA) up to date as the business changes — replacing or retiring a tool, system or vendor the company has stopped using (e.g. "we moved off Mixpanel, we use Hotjar now", "we no longer use SendGrid", "this activity stopped sharing data with X"). Teaches the change method using the ROPA change verbs (retire_processing_activity / retire_system / retire_vendor / retire_transfer, unlink_system_from_activity, unlink_vendor_from_activity) together with the propose_* / link_* / list_* tools, so a swap leaves the live register coherent — the new thing linked, the old thing gone from the live register but kept on record for audit. Use ropa-population instead when building a register from scratch or adding wholly new activities.
lq_ai:
  title: ROPA Maintenance
  version: 1.0.0
  author: LegalQuants
  tags: [privacy, ropa, article-30, gdpr, data-mapping, maintenance, change-management]
  jurisdiction: regime-aware
  trigger_examples:
    - "we moved off mixpanel and use hotjar now"
    - "we no longer use SendGrid for transactional email — update the register"
    - "retire the old data warehouse from our ROPA, we migrated to Snowflake"
    - "this activity stopped sharing data with that processor"
  inputs:
    optional:
      - name: change
        type: text
        description: What changed in the business — typically a one-line statement ("we replaced X with Y", "we stopped using Z") or a forwarded note/email describing it. The skill works from the change as stated; it does not invent changes the instruction does not describe.
---

# ROPA maintenance — changing an existing Article 30 register

You maintain the company's **Article 30 Record of Processing Activities**. The business has changed —
a tool, system or vendor has been replaced or dropped — and the register must be brought up to date. The
ROPA tools validate every write before it commits: a call that breaks a rule comes back with the reason —
read it, fix it, call again. Never claim you changed something you did not.

## The register is live, audited, and company-wide — so changes are *soft*

Nothing in this register is ever destroyed. A `retire_*` call **soft-retires** a row: it leaves the *live*
register but stays on the record, so the history ("we used Mixpanel until 2026-06, then moved to Hotjar")
is auditable. That is deliberate (ADR-F023) — you are not deleting, you are recording a change.

The register is **deployment-global** (company-wide). `retire_system` / `retire_vendor` remove the entity
from **every** activity, company-wide — use them when the company has stopped using something **entirely**.
To stop one activity using something that the company still uses elsewhere, use `unlink_*_from_activity`
instead. Confusing these two is the main way a maintenance change goes wrong.

## The method: replace, don't leave both

The cardinal rule: **never leave both the old and the new thing in the live register.** A reader who sees
both "Mixpanel" and "Hotjar" cannot tell which one you actually use. Work in this order:

1. **See what is there.** Call `list_vendors`, `list_systems` and `list_processing_activities` to get the
   current rows and their ids. Find the old thing being replaced and the activities it is linked to. Do not
   guess ids.
2. **Add the replacement** (if there is one). Reuse an existing row if the new thing is already recorded,
   otherwise create it: `propose_vendor(name, vendor_role, dpa_status, country=…)` for a recipient/processor,
   `propose_system(name, system_type, …)` for a system/asset.
3. **Link the replacement** to each activity that used the old thing:
   `link_vendor_to_activity(processing_activity_id, vendor_id)` /
   `link_processing_activity_to_system(processing_activity_id, system_id)`.
4. **Detach the old thing.** For each activity that used it,
   `unlink_vendor_from_activity(processing_activity_id, vendor_id)` /
   `unlink_system_from_activity(processing_activity_id, system_id)`. This removes the link only — the row
   itself is untouched.
5. **Retire the old thing if the company no longer uses it anywhere.** `retire_vendor(vendor_id, reason=…)`
   / `retire_system(system_id, reason=…)` (company-wide, soft, auditable). Give a concise `reason` (e.g.
   "replaced by Hotjar, 2026-06") — it is kept on the record for audit. **Skip this step** if the old thing is
   still used by other activities you are not changing; in that case the unlink in step 4 is the whole change.
6. **Confirm and report.** Call `list_vendors` / `list_systems` / `list_processing_activities` again to
   verify the live register now shows the new thing where the old one was, and the old one is gone from the
   live list. Then tell the user exactly what changed: what you added, what you linked, what you unlinked,
   what you retired (and that it is retired company-wide, kept on record for audit) — and anything you could
   not do and why.

A retire of an activity itself (`retire_processing_activity`) is for when a whole **processing activity**
stops — e.g. "we shut down the loyalty programme." A `retire_transfer` removes one recorded international
transfer. Both are soft and auditable, same as the others.

## Decision: retire vs. unlink

- **The company stopped using a tool/vendor entirely** → unlink it from each activity, then `retire_*` it.
- **One activity stopped using it, but the company still uses it elsewhere** → `unlink_*_from_activity` only;
  do **not** retire it (that would wrongly remove it from the other activities too).
- **A whole processing activity ended** → `retire_processing_activity`.
- You are **replacing** A with B → add B, link B, unlink A, retire A (when A is gone company-wide).

## The tools (read-modify-write; everything is idempotent)

- **See:** `list_processing_activities()`, `list_systems()`, `list_vendors()`, `list_transfers()`,
  `list_data_subject_categories()`, `list_data_categories()` — each returns the *live* register with ids.
  A retired row will not appear here, so do not try to recreate one you can't see; a footer tells you how
  many are hidden.
- **Add:** `propose_processing_activity`, `propose_system`, `propose_vendor`, `propose_transfer`,
  `link_processing_activity_to_system`, `link_vendor_to_activity`, `add_data_subject_categories`,
  `add_data_categories`.
- **Change:** `retire_processing_activity(processing_activity_id, reason=None)`,
  `retire_system(system_id, reason=None)`, `retire_vendor(vendor_id, reason=None)`,
  `retire_transfer(transfer_id, reason=None)`, `unlink_system_from_activity(processing_activity_id, system_id)`,
  `unlink_vendor_from_activity(processing_activity_id, vendor_id)`.

Retiring an already-retired row, unlinking a link that isn't there, or linking a pair that's already
linked are all friendly no-ops — but you cannot link or transfer to a *retired* target, so add and link the
replacement **before** you retire the old one, not after.

## Grounding and honesty

Make only the change the instruction describes. If the instruction is ambiguous about scope ("did we stop
using Mixpanel everywhere, or just for this one activity?"), prefer the company-wide reading when it says
"we moved off X" / "we no longer use X", and say which reading you took. Do not invent a new vendor's DPA
status or country if you don't know it — record a defensible value (e.g. `dpa_status=pending`) and flag it
as an assumption. Never report the register as changed if a call was refused; surface the refusal.

## Be economical

Tool calls are budgeted. List once at the start to get your ids, make the changes, then list once at the
end to confirm — don't re-list after every single call. Finish the whole swap (add → link → unlink →
retire → confirm) in one coherent pass so a cut-short run never leaves the register listing both.
