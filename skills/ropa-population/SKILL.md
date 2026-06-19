---
name: ropa-population
description: Use when building or extending an Article 30 Record of Processing Activities (ROPA) from a source — a privacy notice, a data-processing agreement, an intake questionnaire, or system documentation — using the ROPA tools (propose_processing_activity / propose_system / propose_vendor / propose_transfer, link_processing_activity_to_system, link_vendor_to_activity, add_data_subject_categories, add_data_categories, and the list_* tools). Teaches the method that produces a coherent, fully-linked register efficiently — work activity by activity to completion so partial progress still leaves complete records, reuse the controlled vocabulary instead of duplicating it, and satisfy the validation invariants the write tools enforce.
lq_ai:
  title: ROPA Population
  version: 1.0.0
  author: LegalQuants
  tags: [privacy, ropa, article-30, gdpr, data-mapping, onboarding]
  jurisdiction: regime-aware
  trigger_examples:
    - "build our ROPA from this privacy notice"
    - "populate the record of processing activities from this document"
    - "map our processing activities into the register"
    - "create our Article 30 register from this notice"
  inputs:
    required:
      - name: source
        type: document
        description: The source to populate the register from — typically a privacy notice, DPA, or intake. The skill works from the source as written; it does not fetch external documents the source merely references.
    optional:
      - name: scope
        type: text
        description: Which activities or areas to focus on if the source is large (e.g. "just the customer-facing processing", "HR processing only"). If absent, cover the principal activities a privacy officer would expect.
---

# ROPA population — building an Article 30 register from a source

You are populating the company's **Article 30 Record of Processing Activities** from a source document.
The ROPA tools validate every write before it commits: a proposal that breaks a rule comes back to you with
the reason — read it, fix it, and call the tool again. Never fabricate a value just to satisfy a field, and
never claim you recorded something you did not.

## The method: work one activity to completion, then the next

The single most important habit: **finish each processing activity's whole record before starting the next**
— do not record every activity first and leave the systems, recipients, categories and transfers for a final
pass. A run can be cut short; working activity-by-activity means whatever you finished is *complete*, not a
pile of unlinked entities. Concretely, for each activity:

1. **`propose_processing_activity`** — name, purpose, Article 6 lawful basis, controller/processor role,
   retention. Set `special_category=true` *and* an `art9_condition` when it processes Article 9 data.
2. **`add_data_subject_categories`** and **`add_data_categories`** — tag whose data and what data this
   activity processes (e.g. "Customers"/"Employees"; "Contact details"/"Financial data"). These find-or-create
   by name, so reuse is automatic.
3. **Systems** — for each system the activity uses: reuse an existing one (`list_systems`) or create it
   (`propose_system`), then **`link_processing_activity_to_system`**.
4. **Recipients** — for each category of recipient the activity discloses to: reuse (`list_vendors`) or create
   (`propose_vendor`, with a role and DPA status), then **`link_vendor_to_activity`**.
5. **Transfers** — for each third-country transfer of this activity's data: **`propose_transfer`** with the
   destination, whether it is restricted (recipient outside the UK/EEA), and — only when restricted — the
   Chapter V mechanism.

Then move to the next activity. Call `list_processing_activities` / `list_systems` / `list_vendors` whenever
you need an id, and to avoid creating a duplicate of something already in the register.

## Identifying the activities

Read the source once (use `read_document` for the whole text, `search_documents` for specific facts — don't
re-read repeatedly). Group the source's stated *purposes* into coherent processing activities — a privacy
notice's purpose-and-lawful-basis table is usually the best backbone. Aim for the principal activities a
privacy officer would expect (service delivery, marketing, security/compliance, HR, analytics/cookies,
transfers, corporate transactions…), not an exhaustive list of every sentence.

## Field rules the tools enforce (get them right the first time)

- **Lawful basis** — exactly one of: `consent`, `contract`, `legal_obligation`, `vital_interests`,
  `public_task`, `legitimate_interests`.
- **Controller role** — `controller`, `joint_controller`, or `processor`.
- **Retention** — required and non-empty. If the source gives only a general approach, state a *defensible*
  concrete period and note it as an assumption (e.g. "assumption: 6 years post-relationship for
  legal/accounting"). Do not leave it blank.
- **Special category ⇔ Article 9** — if `special_category` is true you MUST give an `art9_condition` (e.g.
  `explicit_consent`); if it is false you must NOT give one.
- **Vendor** — needs a `vendor_role` (`processor`, `sub_processor`, `joint_controller`,
  `separate_controller`, `recipient`) and a `dpa_status` (`in_place`, `pending`, `not_required`, `none`).
- **Transfer restricted ⇔ mechanism** — a restricted transfer requires a mechanism
  (`standard_contractual_clauses`, `uk_idta`, `binding_corporate_rules`, `adequacy_regulations`,
  `derogation`); a non-restricted one must NOT carry one.

## Grounding and honesty

Ground each record in the source and prefer its own wording for purpose. The only value you may supply that
the source does not state is a defensible retention (flag it). If the source is silent on something material
(e.g. it names no systems), record what you can and say what is missing rather than inventing specifics.

## Be economical

Tool calls are budgeted. Don't re-read the whole document between every write, don't re-list after every
create, and don't pursue minor edge-case activities at the expense of completing the principal ones. A
smaller register where every activity is fully linked is more useful than a large one of bare, unlinked rows.
