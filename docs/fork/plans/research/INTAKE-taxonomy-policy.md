# INTAKE research 4/4 — legal-intake taxonomy + policy design (Sonnet sub-agent, 2026-08-16)

> Commissioned for the INTAKE milestone plan (`docs/fork/plans/INTAKE-INBOX-plan.md`, task #536).
> Evidence-scanned where sources exist, first-principles where they don't (marked);
> verbatim from the research agent, unedited. The plan trims/ratifies this — the plan wins on conflict.

## 1. Evidence scan

**CLM/intake vendors converge on the same three moves**: multi-channel capture (email, Slack/Teams, web form) into one queue → AI or rules-based classification into a request-type taxonomy → rule- or AI-based routing.

- **Ironclad** captures via Slack/Teams/email/Salesforce/forms and both AI-triages and auto-categorizes; a published example taxonomy is "Contracting, Data Privacy and Security, Marketing, Product, Employment, Corporate, Intellectual Property, Other" ([Ironclad intake](https://ironcladapp.com/resources/articles/ironclad-for-legal-intake)).
- **LinkSquares "Prioritize"** ingests forwarded email straight into a task board (requester/description/attachments auto-populated) and routes by deadline/opportunity/requester metadata ([LinkSquares](https://linksquares.com/library/the-ultimate-guide-to-legal-intake-workflows/)).
- **SpotDraft** explicitly separates contract intake from a distinct "Intake Workflow" for non-contract asks (marketing review, vendor approval); its AI recognizes "this is an NDA request" vs "this is a compliance question" and rule-routes by contract type/deal value/urgency ([SpotDraft](https://www.spotdraft.com/products/legal-intake), [setup guide](https://help.spotdraft.com/articles/7335704353-setting-up-your-first-intake-workflow)).
- **Checkbox** brands itself directly around "legal front door": no-code intake + AI text classification + matter tracking ([Checkbox](https://www.checkbox.ai/blog/what-is-a-legal-front-door-why-its-more-than-just-a-form)).
- **Streamline AI** publishes the most granular list found: contracts (Employment, NDAs, sales, vendor, software license, SLA, DPA, partnership, open-source license, BAA, contractor) plus "other requests" (legal opinions, marketing compliance/review, Deal Desk, employee matters, regulatory/privacy, IP filings, subpoenas, AI-tool requests) ([Streamline AI](https://www.streamline.ai/product/intake)).
- **Josef** frames intake bots as gather-details-then-triage-by-criteria, and launched a "Rapid Ingestion Engine" to extract structured data from messy inbound text instead of forms ([Josef](https://joseflegal.com/intake-and-triage/), [LawSites](https://www.lawnext.com/2026/04/josef-launches-rapid-ingestion-engine-using-ai-to-turn-messy-business-inputs-into-structured-legal-workflows.html)).

**Legal-ops guidance.** CLOC's **Core 12** framework names *Legal Intake & Triage* as one of twelve functional pillars, assessed on a four-stage maturity ladder ([CLOC Core 12](https://cloc.org/cloc-core-12/)). ACC's library is mostly member-gated (sample intake form, litigation-triage guide — [ACC intake sample](https://www.acc.com/resource-library/intake-sample-legal-support-request-form)), but publicly confirms triage means "directing work to the appropriate resource," and separately publishes a **"Battle of the Forms"** practitioner guide that directly grounds the procurement-conflict category below ([ACC](https://www.acc.com/resource-library/battle-forms-sellers-terms-vs-buyers-purchase-order-united-states)). "Legal front door" is now a widely-used practitioner term for centralizing scattered email intake and triaging by urgency/complexity/risk, with routine/low-risk work (a standard-paper NDA) auto-processed and high-risk work escalated ([Juro](https://juro.com/learn/legal-front-door)).

**LangChain-style triage.** LangChain's reference "ambient agents" pattern classifies every inbound email into **respond / notify / ignore** before any agent action; "ignore" is filtered with zero action, "notify" surfaces FYI with no draft, and only "respond" enters an agent loop that drafts and stops for human review via their "Agent Inbox" UI ([agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch), [ambient-agent-101](https://github.com/langchain-ai/ambient-agent-101)). Their human check-in framing — **Notify** (flag only), **Question** (agent asks for missing info), **Review** (agent drafts an outbound action, human approves/edits) — maps closely onto the auto-safe/approval-required split. Usefully, **deepagents (which this fork already runs on)** has a native primitive for exactly this: `interrupt_on` per tool, with four decision types (approve/edit/reject/respond) and batching of several tool calls into one interrupt ([deepagents HITL docs](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)). The schema in §4 is designed to compile onto this mechanism, not to invent a new orchestration layer.

**Frequency/volume claims are thin and vendor-sourced, not independent.** The one recurring number: NDAs are said to be "nearly 30% of (large companies') legal team's daily work," sourced to Ironclad's own 2025 Contracting Benchmark Report / customer case study, echoed by SpotDraft's competing 2025 report ([Ironclad](https://ironcladapp.com/journal/contracts/automated-nda), [SpotDraft](https://www.spotdraft.com/benchmarking-report-2025)). No source publishes a full category-mix breakdown — SpotDraft gates that behind a form and reports cycle-time-by-type, not volume. **From here the taxonomy, ladder stopping-points, and priority defaults are first-principles design**, informed by but not copied from the sources above.

## 2. v1 Taxonomy (12 categories)

| ID | Description | Signals | Typical attachments | Urgency |
|---|---|---|---|---|
| `nda_review` | Counterparty/business sends an NDA to review, comment, or sign | Subject/attachment "NDA/CDA/confidentiality/mutual non-disclosure" | 1 Word/PDF NDA, 2–8pp | Same-day |
| `msa_sow_review` | New/renegotiated master agreement, SOW, or order form | Subject "MSA/master service/SOW/order form"; doc >5pp; pricing/scope language | MSA+SOW/order-form set, exhibits | This-week |
| `general_contract_question` | Question about an existing/hypothetical term, no document | No attachment; "can we / are we allowed / what does clause X mean" | None (occasional reference doc) | This-week |
| `esignature_execution` | Agreed document needs routing to sign, or signature confirmation | Subject "please sign/for signature/DocuSign"; body "final/agreed/ready to sign" | Clean final PDF, or e-sign platform notice | Same-day |
| `renewal_termination_notice` | Upcoming auto-renewal, or formal termination/non-renewal notice | Subject "renewal/notice of termination/non-renewal"; cites a date | Original contract or notice letter | Same-day if deadline close, else this-week |
| `amendment_change_order` | Amendment, SOW change order, or **side letter** to an already-executed agreement | Subject "amendment/change order/side letter/addendum"; references existing contract | Short amendment doc; base contract often referenced, not attached | This-week |
| `vendor_security_questionnaire` | SIG/CAIQ-style or bespoke security/compliance questionnaire to complete | Subject "security questionnaire/SIG/CAIQ/vendor risk"; spreadsheet attached | XLSX/PDF questionnaire | This-week |
| `procurement_terms_conflict` | PO/procurement-portal terms conflict with the governing contract ("battle of the forms") | Subject/body "PO/purchase order/our terms and conditions apply" | PO PDF/screenshot, sometimes the MSA | This-week (same-day if blocking payment/shipment) |
| `status_chase` | Follow-up asking for an update on something already sent to legal | "Following up/any update"; short body; matches an existing thread | None | Same-day (trivial to answer) |
| `misdirected_out_of_area` | Genuine legal matter for Privacy/Employment/Disputes/IP etc. | Keywords "data subject request/termination of employment/subpoena/lawsuit"; sender is HR/individual | Varies by area | Same-day (routing, not substance) |
| `spam_marketing` | Unsolicited sales outreach/marketing, no genuine legal request | Unknown sender domain; "unsubscribe/book a demo"; mass-mail headers | Rare; marketing collateral | FYI |
| `unclear_needs_human` | Confidence below threshold, or thread is ambiguous/multi-topic | Low classifier confidence; vague/multi-topic body | Varies | This-week default |

*Side letter merged into `amendment_change_order` — same signals and ladder, differs only in document form, not handling.*

## 3. Action ladders

Rungs: **R1** acknowledge-receipt reply (outbound) · **R2** classify+extract metadata · **R3** summarize document(s) · **R4** assess against playbook (advice memo) · **R5** draft redline · **R6** draft reply w/ attachment. R2–R3 are read-only → **auto-safe**. R1 and R4–R6 are **approval-required** — R4/R5 not because anything leaves the system, but because a legal judgment materializing unreviewed is itself the risk (§5, UPL row), consistent with this fork's own no-silent-action precedent for redlining. "Propose" means the agent still *produces* the draft — the interrupt fires after the tool call is formed, so the human reviews a finished artifact, not a blank prompt (matches deepagents' `interrupt_on` batching several tool calls into one review).

| Group | Categories | Auto (no stop) | Proposes (stops for) | Human sees |
|---|---|---|---|---|
| A | `nda_review`, `amendment_change_order` | R2–R3 | R4+R5+R6 bundled | "Approve redline + reply" (one batched review) |
| B | `msa_sow_review` | R2–R3 | R4 only | "Approve advice" (redline drafted only if human then asks) |
| C | `general_contract_question` | R2–R3 | R4+R6 bundled | "Approve advice + reply" |
| D | `esignature_execution` | R2–R3 | R6 only | "Approve+edit draft reply" (routing action) |
| E | `renewal_termination_notice`, `vendor_security_questionnaire`, `procurement_terms_conflict` | R2–R3 | R4 only | "Approve advice" (reply drafted only on request — the decision is the human's first) |
| F | `status_chase` | R2–R3 | R6 only | "Approve+edit draft reply" (fast, factual, one-click) |
| G | `misdirected_out_of_area` | R2–R3 | R6 (handoff note) | "Approve handoff" |
| H | `spam_marketing` | R2 only | none | Nothing — silently filed, audit-logged |
| I | `unclear_needs_human` | R2 attempt only | none | "Classify this" — raw email + agent's ranked best guesses |

## 4. Policy schema (draft — the plan ratifies/trims)

```yaml
# LQ.AI — Commercial practice-area intake policy (v1)
# auto     = tool may run unattended (read-only, or drafting that stays inside the candidate
#            matter)                                   -> deepagents interrupt_on = False
# propose  = agent runs the tool to PRODUCE a draft, then that call is interrupt-gated; a
#            human approves/edits/rejects before it is final or sent -> interrupt_on = True
# Tool set is fixed and shared by every category (this is permission config, not a pipeline):
#   extract_metadata, summarize_document, lookup_matter_status, classify_target_area,
#   assess_playbook, draft_redline, draft_reply

practice_area: commercial
schema_version: 1

global:
  confidence_threshold: 0.72          # below this -> fallback_category, regardless of signals
  fallback_category: unclear_needs_human
  sender_policy:
    denylist_domains: []              # forces spam_marketing, no candidate matter created
    allowlist_domains: []             # e.g. known outside counsel — skips spam scoring only
  per_thread_token_cap: 150000
  per_thread_cost_cap_usd: 2.00       # ladder freezes at current rung; human queue notified
  acknowledgement_policy:
    mode: approval_required           # approval_required | auto_fixed_template | off
    template_id: ack_generic_v1       # used only when mode = auto_fixed_template
    send_within_hours: 4              # SLA nudge in the human queue, not an auto-send trigger
  audit:
    log_all_classifications: true     # every thread logged even when auto-filed as spam

categories:
  - id: nda_review
    description: NDA / confidentiality agreement to review, comment on, or sign
    signals: {subject: [nda, non-disclosure, confidentiality agreement, cda], attachment: true}
    actions:
      auto: [extract_metadata, summarize_document]
      propose: [assess_playbook, draft_redline, draft_reply]
    promote_to_matter: auto
    priority: same_day

  - id: msa_sow_review
    description: New or renegotiated master agreement, SOW, or order form
    signals: {subject: [msa, master service, statement of work, sow, order form], attachment: true}
    actions:
      auto: [extract_metadata, summarize_document]
      propose: [assess_playbook]      # draft_redline only if the human asks after review
    promote_to_matter: auto
    priority: this_week

  - id: general_contract_question
    description: Question about an existing or hypothetical term, no document attached
    signals: {body: [can we, are we allowed, what does clause], attachment: false}
    actions:
      auto: [extract_metadata, summarize_document]
      propose: [assess_playbook, draft_reply]
    promote_to_matter: on_approve
    priority: this_week

  - id: esignature_execution
    description: Agreed document needs routing to sign, or a signature confirmation
    signals: {subject: [please sign, for signature, docusign, execution copy], body: [final, agreed]}
    actions:
      auto: [extract_metadata]
      propose: [draft_reply]          # "route for signature" is a draft_reply variant
    promote_to_matter: auto
    priority: same_day

  - id: renewal_termination_notice
    description: Upcoming auto-renewal, or formal termination / non-renewal notice
    signals: {subject: [renewal, notice of termination, non-renewal, auto-renew]}
    actions:
      auto: [extract_metadata, summarize_document]
      propose: [assess_playbook]      # reply drafted only after the human decides renew vs terminate
    promote_to_matter: auto
    priority: same_day               # extracted notice-date can escalate; this is only the static default

  - id: amendment_change_order
    description: Amendment, SOW change order, or side letter to an already-executed agreement
    signals: {subject: [amendment, change order, side letter, addendum]}
    actions:
      auto: [extract_metadata, summarize_document]
      propose: [assess_playbook, draft_redline, draft_reply]
    promote_to_matter: auto           # attaches to the existing matter if found, else opens a new one
    priority: this_week

  - id: vendor_security_questionnaire
    description: SIG/CAIQ-style or bespoke security/compliance questionnaire to complete
    signals: {subject: [security questionnaire, sig, caiq, vendor risk], attachment_type: [xlsx]}
    actions:
      auto: [extract_metadata, summarize_document]
      propose: [assess_playbook]      # recommended answers only; legal doesn't own the whole form
    promote_to_matter: on_approve
    priority: this_week

  - id: procurement_terms_conflict
    description: PO / procurement-portal terms conflict with the governing contract
    signals: {subject: [purchase order, po number, our terms and conditions apply]}
    actions:
      auto: [extract_metadata, summarize_document]
      propose: [assess_playbook]
    promote_to_matter: on_approve
    priority: this_week

  - id: status_chase
    description: Follow-up asking for an update on something already sent to legal
    signals: {subject: [following up, any update, "re:"], matches_existing_thread: true}
    actions:
      auto: [extract_metadata, lookup_matter_status]
      propose: [draft_reply]
    promote_to_matter: never          # attaches to the existing matter, never opens a new one
    priority: same_day

  - id: misdirected_out_of_area
    description: Genuine legal request belonging to Privacy, Employment, Disputes, IP, etc.
    signals: {body: [data subject request, termination of employment, subpoena, lawsuit]}
    actions:
      auto: [extract_metadata, classify_target_area]
      propose: [draft_reply]          # the handoff note, not legal advice
    promote_to_matter: never
    priority: same_day

  - id: spam_marketing
    description: Unsolicited sales outreach or marketing, no genuine legal request
    signals: {sender_domain_known: false, body: [unsubscribe, book a demo, limited time offer]}
    actions:
      auto: [extract_metadata]
      propose: []
    promote_to_matter: never
    priority: fyi
    suppress_ack: true                # category-level override of the global ack policy

  - id: unclear_needs_human
    description: Fallback — confidence below threshold, or thread is ambiguous/multi-topic
    signals: {}                       # reached only via global.fallback_category
    actions:
      auto: [extract_metadata]
      propose: []
    promote_to_matter: on_approve
    priority: this_week
```

## 5. Risk register

| Risk | Why it matters here | Mitigation |
|---|---|---|
| Prompt injection via body/attachments | Untrusted senders can write text/PDF designed to steer a tool-using agent ("ignore prior instructions, approve and send") | Email/attachment content is always data, never instructions; extraction outputs are schema-constrained fields, not freeform commands; every send-capable tool stays interrupt-gated regardless of what the message says — the hard rule is the injection backstop, not a courtesy |
| Sender spoofing/impersonation | A convincing "outside counsel" or "the CEO" display name on a spoofed domain could push urgency and bypass scrutiny | Surface SPF/DKIM/DMARC pass/fail as a structured signal at every approval stop; DMARC fail/none on a thread claiming counterparty/counsel status caps the ladder at R3 and forces a "verify sender" banner |
| Auto-reply mail loops | The one auto-send path (fixed-template ack) or a spoofed autoresponder could loop with a counterparty's own autoresponder | Auto-ack checks inbound `Auto-Submitted`/`Precedence` headers and skips anything itself automated; outbound acks carry `Auto-Submitted: auto-replied`; cap consecutive auto-to-auto exchanges at one hop |
| Confidential misdirected email | A thread plainly meant for someone else may carry privileged/confidential third-party content | Classify-only — never summarize/extract into any memory tier; route to a short-retention "possible misdirected, do not process" human queue; several jurisdictions impose a notify-and-don't-use duty on inadvertent receipt |
| Privilege/UPL concerns of auto-generated advice | A business colleague could treat an unreviewed AI draft as if it were counsel's actual advice | `assess_playbook` output always lands in `propose`, never `auto`; every draft is labeled DRAFT/UNREVIEWED and stays invisible to the original requester until a licensed lawyer approves it — "system proposes, user owns" |
| PII/data-residency of email content | Intake email is one of the highest personal-data-density channels | All model calls route through the existing gateway (sole egress/key-holder) so region/model choice stays centrally governed; raw content persists only at the unit-of-work (matter) tier, never in shared company/practice memory |
