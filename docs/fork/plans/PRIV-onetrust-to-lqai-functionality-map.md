# OneTrust + TrustArc (privacy arena) → LQ.AI functionality map

**Status:** DRAFT for maintainer edit. **Date:** 2026-06-18; **refreshed 2026-06-19** (TrustArc added,
shipped-state reconciled, transfer-map + AI-layer findings — see § Update 2026-06-19 at the foot, which is
the current view; the body below is the original OneTrust-only draft). Feeds the PRIV roadmap
(`PRIV-privacy-ropa-module-decomposition.md`, `PRIV-3-ropa-read-ui-and-relational-reshape.md`).
Governing: ADR-F018 (agentic modules), ADR-F019 (relational, deployment-global ROPA). Memory:
[[oscar-privacy-modules-vision]].

## The inversion (why ours is different, not just cheaper)

OneTrust/TrustArc are **configuration platforms**: a privacy team builds templates, connectors, rules and
forms; humans (and lately bolt-on AI) fill records. LQ.AI is **agent-first**: the Privacy Deep Agent *does
the work* — interviews people, reads documents, and **proposes** records that **deterministic code
validates** before commit; the human **owns** (ADR-F018). Every OneTrust capability below is re-expressed as
"what the agent does," not "what the admin configures."

**The headline differentiator — conversational-link assessments.** OneTrust's flagship privacy workflow is:
send a stakeholder ("Project Respondent") a **no-login web-form link**; they answer skip/show-logic
questions; on approval the answers **write back into the data-inventory record**. We keep the
**write-back-to-inventory architecture** and **replace the form with a conversation**: send a link; the
SME / system owner **talks to the LQ.AI Privacy agent**; the agent extracts, **code-validates**, and files
records into the ROPA — which is then **queryable and extractable** (Article 30). Oscar already proved the
agent-driven intake works ("this isn't a form to send them") but kept it single-user with no link and no
structured filing; OneTrust proved the send-to-respondent + write-back loop but with a static form. **LQ.AI
is the first to join the two.**

## What we reuse

- **Substrate (built):** practice-area Deep Agent, gateway sole-egress, `guarded_dispatch` chokepoint,
  the **code-validated write path** (ADR-F018), the **relational two-tier ROPA** (System ↔ Processing
  Activity, ADR-F019, PRIV-3), the read register UI.
- **Oscar's workflow/knowledge layer (port-and-improve, reference-only):** `pia-generation` (7-section PIA
  template + risk-quality standards), `use-case-triage` (PROCEED / PIA-REQUIRED / DPIA-MANDATORY / STOP
  gates), `dpa-review` (9-term playbook + processor/controller positions), `dsar-response` (classify →
  verify → walk-systems → exempt → draft), `policy-monitor` (drift sweep), `reg-gap-analysis`, the matter-
  kind taxonomy, regulator + sectoral taxonomies, the currency-watch discipline.

---

## The map (by capability area)

Legend — **Priority:** P0 in-flight · P1 flagship-next · P2 agentic-track · P3 not-our-wedge (infra; later/
partner/out). **Slice** = PRIV roadmap target.

### A. Assessment Automation  — **P1 flagship**

| OneTrust capability | LQ.AI AI-native replication | Reuse | Slice |
|---|---|---|---|
| Template library (OnePIA, DPIA, TIA, LIA) + drag-drop builder | Skills-as-templates: the PIA/DPIA/LIA structure lives in a SKILL.md the agent follows (readable in source) — no GUI builder | Oscar `pia-generation` 7-section template | PRIV-A1 |
| Skip/Show conditional logic | The agent asks only what's relevant — conversation, not branching form | Oscar triage question sequencing | PRIV-A1 |
| **Send questionnaire to "Project Respondent" via no-login link** | **Conversational-link intake: tokenized link → SME talks to a scoped Privacy agent → agent files code-validated records** (the differentiator) | new + ADR-F020 | **PRIV-A2** |
| Risk-scoring rules; Risk Register; treat/reduce workflow | Agent proposes a risk rating + mitigations (Oscar's risk-quality standard: specific, design-tied); a typed `assessment`/`risk` record, code-validated; human owns the rating | Oscar PIA risks table | PRIV-A1 |
| Write-back to inventory on approval (Primary Record) | Already ours: agent → `propose_processing_activity`/`propose_system`/link → validated commit. Assessment **completion files the ROPA** | ADR-F018/F019 write path | PRIV-A1/A2 |
| Auto-trigger follow-up assessment (rules / Launch API) | Triage gate routes to PIA/DPIA in-conversation; an `assessment` record can flag "DPIA required" | Oscar triage gates | PRIV-A1 |
| AI autofill from documents / inventory; Privacy Agent | Native — the agent reads the matter's documents + existing ROPA and proposes; this is our default, not an add-on | substrate | PRIV-A1 |
| Multi-stage approval; reminders; save-and-resume | Assessment record has status + owner; conversational link is resumable; reminders later | new | PRIV-A2+ |

**New entities:** `assessment` (type: PIA/DPIA/LIA/TIA; status; risk rating; conditions; links to processing
activities/systems), `risk` (likelihood/impact/mitigation/owner/status). **ADR-F020** = the conversational-
link external-intake surface (tokenized, scoped agent, code-validated writes, human review) — its own design.

### B. Data Mapping / Inventory / RoPA  — **P0 in-flight**

| OneTrust capability | LQ.AI replication | Slice |
|---|---|---|
| Inventory records: Assets, Processing Activities | **Built** — System ↔ ProcessingActivity (PRIV-3, ADR-F019) | ✅ PRIV-3 |
| Vendors / third parties | `vendor` entity (role, DPA/contract, risk) + links | PRIV-5 |
| Legal Entity (Article 30 export scope) | `legal_entity` as report scope (controller/processor outputs) | PRIV-6 |
| Personal-data taxonomy (data subjects, categories, elements) | typed taxonomy linked onto records | PRIV-5/6 |
| Transfers + mechanism | `transfer` entity + **outside-UK/EEA ⇒ mechanism-required** validated invariant | PRIV-5 |
| Article 30 one-click report | structured export deliverable | PRIV-4a |
| Visual data map / lineage | data-flow view generated from the graph | PRIV-6 |
| Population: assessment write-back, AI autofill | the agent (conversational-link + doc-reading) IS the population channel | PRIV-A* |
| Attestation / recertification (staleness triggers) | scheduled agent re-confirmation runs (`/schedule`) | PRIV-7+ |
| Bulk import (CSV/Excel) | optional importer; low priority vs agent population | backlog |
| Tabular searchable record UI | the register UI (PRIV-3) + filters/CRUD | PRIV-4+ |

### C. DSAR / Data Subject Rights  — **P2**

| OneTrust capability | LQ.AI replication | Reuse |
|---|---|---|
| Intake webform / portal | tokenized **conversational-link** intake (same surface as assessments) | ADR-F020 |
| Identity verification | lightweight verification step; escalation triggers | Oscar `dsar-response` |
| "Walk the systems" retrieval | **query our `systems` inventory** — the ROPA we built directly powers DSAR scoping | PRIV-3 graph |
| Routing, redaction, deletion, legal-hold, secure delivery | agent drafts the response + exemption memo; fulfillment integrations later | Oscar `dsar-response` letters/exemptions |
| Deadline/SLA clocks | matter-kind `deadline` extra + `/schedule` reminders | Oscar taxonomy |

Own track (PRIV-DSAR-*). Synergy: the systems inventory makes the DSAR "walk" real, not a config list.

### D. Incident / Breach  — **P2**

| OneTrust capability | LQ.AI replication | Reuse |
|---|---|---|
| Multi-channel intake (intelligent questionnaire) | conversational-link breach intake | ADR-F020 |
| Notifiability determination (Databreachpedia law engine) | agent reasons notifiability + **cites primary sources** (no proprietary law DB; currency-watch discipline) | Oscar regulator/sectoral taxonomies |
| 72-hour clock; regulator + individual notification drafting | deadline tracking + agent-drafted notifications | Oscar breach kinds |
| Incident register + audit trail | typed `incident` record + our audit contract | substrate |

Own track (PRIV-BREACH-*). Maps to Oscar `breach_internal`/`breach_vendor` matter kinds.

### E. DPA / Vendor review  — **P2** (bridges Commercial/redlining)

| OneTrust | LQ.AI | Reuse |
|---|---|---|
| Vendor DPA tracking + risk | `vendor` record + DPA review output linked to the vendor | Oscar `dpa-review` 9-term playbook |
| Term-by-term review | agent applies the positions playbook; redline output | Oscar `dpa-review` + adeu (redline track) |

### F. Regulatory intelligence / program maturity  — **P2**

| OneTrust | LQ.AI | Reuse |
|---|---|---|
| DataGuidance library + trackers | agent regulatory research via gateway (web/MCP later) + **cited** answers; **no RAG** (ICO RAG dropped) | Oscar currency-watch |
| Gap analysis vs frameworks | agent diffs the company ROPA/policy against a regime | Oscar `reg-gap-analysis`, `policy-monitor` |
| Maturity scoring / benchmarking | programme dashboard + gap view over the real ROPA | PRIV-6+ |

### G. Reporting / dashboards  — **P2 incremental**

| OneTrust | LQ.AI |
|---|---|
| Article 30 / RoPA report | PRIV-4a export |
| Risk dashboard / register | programme dashboard + gap view (PRIV-6+) |
| Audit trail / activity logs | **already ours** (audit contract: counts/types/IDs) |
| NL conversational analytics (Copilot Analytics) | **native** — ask the Privacy agent; it queries the ROPA via read tools |

### H. Consent & Preference management  — **P3 not-our-wedge**

Collection points, branded preference centers, immutable receipts, MarTech bi-directional sync, SDKs. This is
an **end-user consent infrastructure** play (JS SDKs + integrations), low agentic value. **De-prioritise**;
the agent can *advise on* consent architecture (Oscar's `consent` kind / Diana-Park Phase 4) and record a
consent *design* in the ROPA, but we don't build the runtime consent platform near-term. Revisit / partner.

### I. Cookie consent / website scanning  — **P3 out (near-term)**

CMP banner, cookie scanner, tag auto-blocking, IAB TCF/GPP, Consent Mode. Pure front-end compliance infra,
no agentic wedge. **Out of near-term scope** — name it so it isn't mistaken for a gap.

### J. Data discovery & classification  — **P3 split**

Enterprise data-store scanning across 200–500 connectors is heavy infra — **later/integration**. BUT a
**lighter, native slice is high-value now**: the agent **classifies the personal data in the matter's own
ingested documents/KB** and proposes ROPA entries from it (discovery-from-documents). That rides our existing
ingestion + the write path. Full live-data-store discovery → backlog/partner.

---

## Sequencing into the PRIV roadmap

- **P0 (in-flight):** PRIV-3 ✅ (System↔PA) → **PRIV-4a** Article 30 export → **PRIV-5** Vendors + Transfers
  (+ mechanism invariant) → **PRIV-6** data-flow view + Legal-Entity report scope + programme dashboard/gap.
- **P1 (flagship, in parallel after PRIV-4a):** **PRIV-A1** assessment domain + skill (PIA/DPIA/triage,
  write-back to ROPA); **PRIV-A2** the **conversational-link external intake** (ADR-F020) — the
  differentiator; **PRIV-J** discovery-from-documents (agent proposes ROPA from the matter's docs).
- **P2 (own tracks, sequenced after the spine):** DSAR, Incident/Breach, DPA/Vendor review (bridges
  redlining), Regulatory gap/maturity, Reporting/query.
- **P3 (deliberately deferred / out):** Consent & Preference platform, Cookie CMP/scanning, full data-store
  discovery connectors. Recorded as conscious non-goals, not omissions.

## New ADRs this map implies

- **ADR-F020 — conversational-link external intake.** Tokenized, time-boxed public link → a **scoped**
  Privacy agent (can only propose into one assessment's ROPA scope; no other tools/matters) → code-validated
  writes → human review/own. Security-sensitive (unauthenticated external surface): rate-limited, no data
  exfil, audit every turn. The flagship's prerequisite.
- **ADR-F02x — assessment domain** (PIA/DPIA/LIA/TIA + risk records, linked to the inventory) if it grows
  beyond a thin extension of ADR-F019.

## Deliberate non-goals (so the map isn't misread as a backlog)

Cookie CMP + scanner; runtime consent/preference platform + MarTech SDKs; enterprise data-store discovery
connector fleet; a proprietary regulatory-content library (we cite, we don't license a RAG — ICO RAG dropped).
These are where OneTrust's moat is *infrastructure*, not lawyering — not LQ.AI's wedge.

---

## Update 2026-06-19 — refreshed vs current OneTrust + TrustArc + our shipped state

Three cited web-research runs (OneTrust 2025–26 docs, TrustArc/Nymity 2025–26 docs, OSS map libraries) +
reconciliation against what we actually shipped (PRIV-3→9b). Source URLs inline. Marketing figures (e.g.
"80% autofill") are vendor-sourced — not treated as fact. Both vendors' help centers are JS/403-gated, so a
few deep UI mechanics are flagged "unverified" rather than asserted.

### A. What we have now (reconciled — the RoPA spine is ~at parity)

Shipped & live: relational two-tier register (System↔Activity, PRIV-3), vendors/recipients (PRIV-5a),
transfers + the **restricted⇒mechanism invariant** (PRIV-5b), personal-data taxonomy **closing all of
Article 30(1)** (PRIV-6a), Article 30 export JSON/CSV/XLSX (PRIV-4a), programme dashboard + gaps (PRIV-6b),
**node-link** data-flow map (PRIV-6c, `@xyflow/svelte`), agent population/change/swap with live cockpit +
changed-row highlight (PRIV-7…9b). This is the surface both vendors lead with; we're there.

### B. The data-transfer-map finding (the headline of this refresh)

**Both incumbents ship TWO visualizations — a node-link graph AND a geographic map. We have only the
node-link one.**
- **OneTrust:** explicitly names "an improved **cross-border map to visualize transfers**, a **new data
  graph visualization**" as separate features
  (https://www.onetrust.com/blog/onetrust-unveils-latest-platform-innovations-to-drive-responsible-data-use-and-business-resilience/).
  The **Asset Map** is a world map "organized by hosting location" with per-country counters (hover splits
  3rd-party/internal); a separate patent-described "Cross-Border Visualization Generation System" draws
  transfers between locations (https://www.onetrust.com/schrems-solutions/). Node-link side = "AI Inventory
  Graph" + manual **Data Lineage Diagrams** (drag-icons-on-canvas).
- **TrustArc:** one Business Process Record renders as a switchable **Flowchart View** (node-link:
  systems/data-subjects/vendors via "Sends Data To" connectors) **and** a **Map View** plotted "by hosting
  location"; product page names "interactive data flow maps, **transfer maps**, and relationship views"
  (https://trustarc.com/products/privacy-data-governance/data-mapping-risk-manager/).

**The opening:** neither vendor's geographic map could be confirmed to show the **legal transfer mechanism**
inline — both look like hosting-location plots with counters/pins. We already store destination + restricted
+ mechanism + recipient (PRIV-5b) and enforce restricted⇒mechanism. A geo arc map that surfaces the Chapter
V safeguard on click and **flags restricted-without-mechanism** beats them on legal substance. → **Plan:
`PRIV-6e-geographic-transfer-map.md`.**

**OSS library verdict (for PRIV-6e):** **Apache ECharts** (Apache-2.0; native animated geo arcs; no WebGL;
tree-shakeable; Svelte-5 wrapper; also does Sankey) — top pick. Runner-up **d3-geo** (ISC, ~20KB, on-brand,
hand-rolled, we already have d3 transitively). **amCharts DISQUALIFIED** — proprietary "linkware" forcing a
visible logo unless licensed (https://github.com/amcharts/amcharts5/blob/master/LICENSE). New dep → ADR +
NOTICES, the ADR-F022 precedent.

### C. Genuine gaps that fit our wedge (build these)

1. **Assessment automation — biggest gap; it IS our P1 flagship.** Both vendors strong: PIA/DPIA/TIA/LIA +
   AI-impact templates, conditional logic, risk register/scoring, stakeholder questionnaires, write-back.
   We have **none** yet. TrustArc Assessment Manager: 10+ templates incl. **AI Risk Assessment**, role-based
   routing, automated scoring → remediation tasks
   (https://trustarc.com/products/privacy-data-governance/assessment-manager/). OneTrust: PIA/DPIA/AIIA/EU
   AI Act conformity, Skip/Show logic, consolidated Risk Register, auto-trigger follow-on assessments
   (https://www.onetrust.com/news/onetreust-announces-collaboration-features-assessment-automation-pia-dpia/).
   → **Track PRIV-A (decomposition: `PRIV-A-assessment-automation-decomposition.md`).**
2. **Legal-Entity report scope** (controller/processor Article 30 outputs; OneTrust parent/child entity
   hierarchy). We deferred it (PRIV-6d, needs migration). Real Article-30 completeness gap.
3. **Attestation / recertification** (staleness triggers → scheduled re-confirmation). Both ship it
   (OneTrust: record-not-updated-in-N-days / recurring-cycle / contract-expiry triggers, prior answers
   pre-populate). We have the `/schedule` substrate, unbuilt. Strong agentic fit.
4. **Discovery-from-documents** (PRIV-J): agent classifies personal data in the matter's own ingested docs →
   proposes ROPA. Lighter than their connector fleets, rides our ingestion, high value.
5. Lower: bulk CSV/Excel import (both have it; backlog); a **seeded common-systems/vendors record library**
   (TrustArc "Record Exchange" 800+ pre-built records; OneTrust template packs) — nice-to-have population
   accelerator.

P2 tracks (DSAR, Incident/Breach, DPA review, regulatory gap) remain unbuilt but already sequenced, each
with a differentiator (systems inventory makes the DSAR "walk" real; we cite primary sources, no licensed
RAG).

### D. Deliberate non-goals (NOT gaps — restating so they're not misread)

Consent & preference platform; cookie CMP/scanner (OneTrust 45M-cookie DB + scanner, TrustArc #1 enterprise
CMP per G2); enterprise data-store discovery connector fleet (OneTrust 200+ connectors + SDK); proprietary
regulatory-content RAG (TrustArc Nymity Research ~52k references / OneTrust DataGuidance). These are
**infrastructure moats, not lawyering** — conscious non-goals; the agent can *advise on* consent/transfer
architecture and *cite* regulators without us building the runtime infra or licensing a content library.

### E. The AI-layer contrast — do NOT mistake their 2025 launches for parity-closing

Both shipped AI in 2025: **OneTrust Copilot** (NL query, Azure OpenAI, Oct 2024) + Privacy Agent (Sept 2025,
docs→PIA responses) + Winter-'26 agents (AI Evidence Analysis, Copilot Analytics) — several still
preview/roadmap, names drift across announcements
(https://www.onetrust.com/blog/evolving-privacy-programs-with-ai-whats-new-in-the-onetrust-winter-26-release/).
**TrustArc Arc** (GA **Dec 18 2025**): Ask Arc (cited answers over program data) + Arc Intelligence,
grounded in Nymity content; AI Analyzer still preview
(https://trustarc.com/press/trustarc-launches-arc-the-ai-powered-privacy-management-platform-built-for-modern-teams/).
**These are retrieval-and-cite assistants + autofill bolt-ons, not agent-native workflow execution.** Our
ADR-F018 loop (agent proposes → deterministic code validates → human owns), code-validated writes, and the
planned **conversational-link intake** (ADR-F020, our PRIV-A2 differentiator) remain architecturally
distinct. Their AI narrows the optics gap; it does not replicate the validated agentic write path.

### F. Revised near-term priority

1. **P1 NOW — PRIV-A assessment automation** (start with PRIV-A1: `assessment`+`risk` domain + code-validated
   write + a PIA/DPIA skill; then PRIV-A2 = ADR-F020 conversational-link intake, the differentiator).
2. **PRIV-6e geographic transfer map** — self-contained, visible, out-classes incumbents on legal substance;
   slot when convenient (independent of P1).
3. Then PRIV-6d (legal entity), attestation/recertification, discovery-from-documents.
