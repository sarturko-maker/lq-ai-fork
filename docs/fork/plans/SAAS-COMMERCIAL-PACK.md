# SAAS commercial pack — checklist for the maintainer (lawyer-owned)

**Status: SAAS-0 skeleton — the maintainer drafts/signs off the legal instruments; this file
tracks WHAT must exist and the product-specific content each needs. Nothing here is legal
advice; it is the engineering-side inventory of obligations from ADR-F058 + SAAS-HOSTING.md §7.
Gate: every ☐ below is a blocker before the FIRST PAYING TENANT (not before staging).**

## 1. Contract stack (MSA/ToS + annexes)

- ☐ **MSA / Terms of Service** — liability cap; warranty disclaimer; IP (customer owns their
  documents + outputs; we own the platform); term/termination; **data destruction on exit**
  (Mode 2 makes this strong: stack destroyed, confirmed in writing).
- ☐ **AI work-product framing** (the clause legal buyers will read first): tool for qualified
  professionals; output is a *draft requiring review by a qualified lawyer*; no attorney-client
  relationship; no legal advice. Mirrored **in-product** on export surfaces (redline downloads,
  verdict badges, grids) — the AIC verdict disclaimer (`app/aiact/ruleset.DISCLAIMER`) is the
  precedent; UI surfaces land with SAAS-6/8A.
- ☐ **SLA schedule** — proposal: best-effort with a 99.5 % monthly availability target,
  business-hours support (support@<domain>, response within 1 business day), planned-maintenance
  windows (the ~30–60 s deploy pause), status page reference. No credits at v1.
- ☐ **AUP** — no prohibited-practice use (mirror Art 5 categories), no scanning/pen-testing
  without consent, no resale, fair-use bounds tied to the spend ceiling (§4).
- ☐ **Order form** — plan, seats, tenant subdomain, chosen model menu (EU default / BYOK),
  monthly LLM allowance.
- ☐ **DPA (Art. 28(3)) as annex** — instructions-only processing; confidentiality; Art. 32
  measures (encryption at rest/in transit, per-tenant isolation, encrypted backups); subprocessor
  authorisation + notice/objection; flow-down; DSR/breach assistance; deletion-or-return; audit
  rights. **Subprocessor table v1:** Hetzner (DE — infra), model providers per the tenant's menu
  (Bedrock-EU / Azure-EU / Mistral; *omitted for BYOK tenants*), Scaleway (FR — transactional
  email), Sentry (EU — error telemetry). Keep public on the trust page.
- ☐ **Operator-access policy** (one paragraph, DPA Art. 32 annex): named person only; access on
  customer request or incident only; host logins logged; disclosed.

## 2. Incident response + breach notification

- ☐ One-page IR runbook: severity levels; evidence preservation (audit rows, session tables,
  host logs); **24 h controller-notification commitment** (their GDPR Art. 33 72 h clock starts
  on our notice); notification template; paging path (Uptime Kuma → phone).
- ☐ Security-fix discipline (public repo): fork `SECURITY.md` contact; GitHub private
  advisories; patch-then-deploy-then-push (SAAS-1).

## 3. Billing v1

- ☐ Selling entity + invoicing (manual, B2B **reverse-charge VAT**, VAT-ID validation).
- ☐ Pricing model: flat platform fee + usage tier that covers per-tenant LLM spend (meter =
  `agent_runs.total_tokens`/`cost_usd`, per-tenant report from SAAS-8A); lower flat fee for
  BYOK tenants (their key, their spend). Stripe deferred to the Mode-3 trigger.
- ☐ **E&O / cyber insurance decision** — priced quote before first tenant; record the outcome
  either way.

## 4. Product-side hooks this pack depends on (engineering, tracked in the SAAS ladder)

- Per-tenant **monthly** LLM spend ceiling at the gateway + 80 % alert (SAAS-6) — the AUP's
  fair-use bound and the billing meter.
- Per-tenant usage/cost report (SAAS-8A) — the invoice input.
- Export-surface disclaimers (SAAS-6/8A) — the AI-framing mirror.
- Trust page: certifications roadmap (none at v1 — say so honestly), named model providers +
  ZDR/no-training terms, EU residency, subprocessor list, `SAAS-AIACT-SELF-ASSESSMENT.md`
  result, security posture summary, source-availability link (PyMuPDF §13 hygiene).
