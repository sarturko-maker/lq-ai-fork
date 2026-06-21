# Commercial lawyer-method doctrine (C-R0)

**Slice:** C-R0 (research spike — no code). **Gates:** C0 (the Commercial agent's `profile_md`) and C4
(the measurable surgical-redline gate). **Status:** drafted 2026-06-21 from verified practitioner/theory
sources, reconciled against the four shipped review skills, then adversarially reviewed (the review's seven
required fixes are folded in — see § 11). **Feeds:** ADR-F028 (method doctrine), ADR-F031 (redline gate).

> **North star.** A practice-area agent is *a supervised, area-qualified legal counsel*. This doc is the
> "qualified in commercial" half made concrete and checkable: what surgical means as code, how the agent
> derives from the firm's positions, and where it must hand back to the human. Everything here must *make
> that true*, not assert it.

> **Sourcing rule.** Every method claim below cites a source. Numeric constants are **reasoned starting
> values, not quoted from any source** — the sources support the *mechanisms*; the *numbers* are for the
> maintainer to calibrate against a labelled corpus (§ 11). A few sources were reachable only via search
> snippet (page 403/no render) — those are labelled *(snippet)* and used only where a verified source
> corroborates.

---

## 1. Purpose & how this feeds C0 / C4

- **C0** encodes §§ 2–3, 5, 7–10 into the Commercial `profile_md` as the agent's standing method — it makes
  the seeded agent behave like in-house counsel and **names the four review skills as controlling
  references** (it never re-authors them).
- **C4** implements § 6 — the surgical-redline gate — as a **hybrid validated-write** tool over Adeu
  (ADR-F018: agent *proposes* edits → **our code validates** → applies as native tracked changes).
- C5/C6/C7 build on §§ 7–8 (playbooks, negotiation rounds, fan-out). The held multi-turn-redlining project
  builds on § 8.

---

## 2. The role: counsel acting *for the client*

- **The client is the organisation itself**, not any individual. Counsel applies the *company's* risk
  tolerance, not its own, and escalates within the organisation when a course of action risks the company
  (ABA **Model Rule 1.13(a)/(b)**). In the fork this is literal: **the client = the operator's
  `OrganizationProfile`** (risk posture + house style), injected read-only as the company tier at C-CLIENT,
  bound per run to `org_id` (distinct from `user_id`).
- **Separate legal lines from business decisions.** Counsel decides legal questions and *surfaces and
  defers* business questions (price, appetite, relationship) to the business owner rather than deciding them
  (Sterling Miller, *Ten Things: Dealing with Business Executives*; Thomson Reuters, *Dealing with business
  executives*). → A `LEGAL_LINE` vs `BUSINESS_DECISION` split: the agent gates the former and routes the
  latter to the human.
- **In-house pragmatism.** The job is protecting the deal as the company understands it, not perfection —
  this is already the calibration in `nda-review` ("in-house counsel making business-pragmatic judgments").

---

## 3. Deal-complexity triage (effort as a first-class dial)

Not every deal is complex; not all NDAs are alike (maintainer brief #7).

- **Simple instrument** (a standalone NDA) → single-pass, single-agent review + redline (Pactly,
  *5 Ways to Triage High-Volume NDA Reviews*).
- **Complex deal** (multiple attachments, mixed document types, an email chain, high value) → fan-out across
  workstreams via the deepagents `task` tool, with a **mandatory post-fan-out reconciliation pass** into one
  position (M&A diligence runs many parallel workstreams — Bloomberg/Dealroom *(snippet)*; corroborated by
  the verified review-depth practice below).
- This generalises the **`review_depth` dial** the MSA skills already expose (`comprehensive` vs
  `quick_triage` over a tiered checklist) from the *document* level to the *agent* level. Effort/altitude is
  a deliberate dial, not a per-skill accident.

---

## 4. The lawyer-method altitudes (derive from the shipped skills, don't reinvent)

The four review skills already encode the method. The doctrine **canonises** what they share and frames the
agent's behaviour as *three altitudes of one method*, never as competitors:

1. **Comprehensive review** (fixed structure, severity-rated, perspective-required) — `nda-review`,
   `msa-review-commercial-purchase`, `msa-review-saas`. Shared spine: *orient (confirm instrument, route
   away if wrong) → checklist-classify → perspective/asymmetry lens → operational red-flags → severity-rated,
   clause-cited report* with a fixed skeleton (Bottom line → Critical → Material → Minor → Missing
   protections → Red flags → Next steps → Items requiring human judgment).
2. **Targeted QA** (adaptive, classify-the-ask-first, a *verdict* — standard/unusual/aggressive/favorable —
   **not** a severity tier) — `contract-qa`.
3. **Tabular/portfolio snapshot** (row-per-document × column-per-question grid, per-cell citation +
   confidence) — `contract-snapshot`, `nda-snapshot`.

**Assessment is orthogonal layers, never one scale.** The skills carry *five different* assessment axes:
review **severity** (Critical/Material/Minor), DPA **coverage status** (Present/Partial/Missing/Unclear/N/A)
+ **document posture** (Compliant…Materially-non-compliant), QA **verdict**, and snapshot **confidence**. The
doctrine treats these as orthogonal layers so one unit-of-work store holds findings from all skills
losslessly. **A naive single Critical/Material/Minor scale would corrupt DPA, QA and snapshot output — do not
impose one.** (This is the seam of the **F036** data-layer conflict — see § 10.)

**Standard-of-comparison differs by instrument:** NDA/MSA measure against **market** standard (calibrated by
deal_type/role/industry); DPA measures against a **regime** (GDPR Art. 28(3)/32/44–49, CCPA, HIPAA — cited
by article). The doctrine supports both baselines; the firm's **playbook positions are its own market
benchmark** (`standard_positions` overrides generic benchmarks — a memory seam).

**Universal invariants** (all four skills already obey these; the doctrine hoists them agent-wide): output is
a **draft for human review**, never a final opinion; **every finding carries an exact clause citation**
(verbatim quotes exact incl. original errors; paraphrase named; **no invented locators or authorities**); **no
enforceability/compliance opinions** ("this is unusual" / "raises an enforceability question", not "satisfies
the law"); an explicit **"items requiring human judgment"** section; **route on out-of-scope** rather than
overreach.

---

## 5. Surgical redlining — the doctrine

A lawyer reviewing the *other side's* draft amends **only the language needed to protect the client**, and
makes the **smallest change that achieves the protection**. Over-redlining (Adeu's known tendency — it
faithfully applies whatever it is sent) is the failure mode the C4 gate exists to prevent.

- **Limit changes to substance, not beauty.** When you are the reviewing party, change only language that
  (a) does not reflect the deal as understood, (b) causes confusion/ambiguity, or (c) adds client risk —
  ignore the rest; you are not turning the other side's draft into "a thing of beauty" (Kenneth A. Adams,
  *On Reviewing a Contract* — wording via snippet, page 403; corroborated by *The "Categories of Contract
  Language" Issues…*). → a **closed edit-category enum** `{does_not_reflect_deal, causes_confusion_or_ambiguity,
  adds_client_risk}`; a style-only edit is rejected.
- **Smallest change; rip-and-replace is a defect.** Prefer a word/phrase substitution over a clause rewrite —
  a single word can shift the obligation (`best efforts` → `reasonable efforts`). Striking a whole section
  and pasting back near-identical vetted language is "the mark of a poor redliner" and the large red block
  reads as aggressive even when the change is minor (Sirion, *Contract Redlining Tips*; Percipient,
  *Best Practices 2025*).
- **Rationale on every substantive markup.** Each substantive change carries a "why"; minor/formatting edits
  are the only carve-out, and silent redlines are a rare deliberate exception, not the default
  (Alnajafi, *10 Rules of Contract Redlining Etiquette*, Rule on comments).
- **Asking party supplies the language.** If you request a substantive change you supply the redrafted
  text — don't delete-and-leave-a-gap or expect the counterparty to draft language in *your* favour
  (Alnajafi, Rule on proposing your own language).
- **Focus on material clauses.** Markup belongs on price/liability/indemnity/IP/term; let boilerplate and
  minor edits go (DocJuris, *How to redline a contract*; Percipient).
- **Keep Track Changes on; never silently mutate.** Every change stays visible within the four corners of
  the document (Sirion). Adeu authors native `w:ins`/`w:del`, so silent text mutation is structurally
  impossible.

## 6. Surgical — the code-checkable definition (C4's gate)

> **"Surgical" = the smallest edit that achieves the client protection.** Operationalised as a **hybrid**
> validator over each `ModifyText` find/replace edit, plus a whole-batch ceiling. **Part is deterministic
> pure-code; part needs a classifier.** All numbers are calibration starting values (§ 11).

### 6.1 The metric is computed on the *minimal diff*, not raw span lengths

The load-bearing correction from the adversarial review: Adeu's `ModifyText(target_text, new_text)` is
find/replace, so the **matched (deleted) span can be far larger than the actual change** — a one-word swap
expressed over a 30-word sentence has a huge raw delete+insert but a tiny *real* change. Measuring raw
lengths would wrongly flag it. So:

> Compute the **minimal token-level diff** between `target_text` and `new_text` (via `diff-match-patch` —
> which Adeu *already bundles and uses internally*; observed `Op=MODIFICATION at [89:97]`, i.e. Adeu narrows
> to the changed span). `changed_tokens` = inserted+deleted tokens **in that minimal diff**. This single
> metric replaces the contradictory "diff-ratio vs rip-and-replace similarity" pair: because we measure the
> *minimal* change, a redundant rip-and-replace collapses to its small real diff (and Adeu renders it
> minimally anyway).

### 6.2 Deterministic gate (pure code — Pydantic `*Input` + a diff computation)

Mirrors the ROPA validated-write `*Input` pattern (`api/app/schemas/ropa.py`). Each is computable with no
model in the loop:

| # | Rule | Starting value | C4 test |
|---|---|---|---|
| D1 | **Tiered change size.** `ratio = changed_tokens / clause_tokens` (clause_tokens = smallest enclosing clause/sentence of the match). `ratio ≤ SURGICAL_MAX` **or** `changed_tokens ≤ ABS_FLOOR` → auto-allow; `SURGICAL_MAX < ratio ≤ REWRITE_MAX` → allow **only with** a ≥`RATIONALE_MIN_WORDS` rationale; `ratio > REWRITE_MAX` → **BLOCK** unless `rewrite_justified=true` + recorded reason. | `SURGICAL_MAX=0.15`, `ABS_FLOOR=3`, `REWRITE_MAX=0.50` | phrase-where-a-word-suffices (mid band, no rationale) → REJECT; justified full rewrite → ACCEPT; one-word swap (`best efforts`→`reasonable efforts`, ≤3 changed tokens) → passes via `ABS_FLOOR`. |
| D2 | **Substantive-edit rationale.** An edit is *substantive* if `ratio > MINOR_FLOOR` **or** it touches the substantive-token set `{shall, must, may, will, shall not, not, no, a number, %, $, a date/period, a defined term, a party name}`. Every substantive edit needs `rationale` ≥ `RATIONALE_MIN_WORDS` non-placeholder words. | `MINOR_FLOOR=0.05`, `RATIONALE_MIN_WORDS=15` | deleting `shall` with no rationale → REJECT; `teh`→`the` (formatting carve-out) → pass. |
| D3 | **Bare substantive deletion must supply replacement.** `type==delete` + substantive + `inserted_tokens==0` → require `replacement_text`; a bare delete with only "please revise" → BLOCK. | — | delete a liability-cap sentence with no replacement → REJECT; delete duplicated boilerplate → pass. |
| D4 | **Unique-anchor / fail-close on match.** `target_text` must match **exactly one** span in the document. Zero or >1 matches → **BLOCK/escalate** (require a unique anchor). *(Correctness hole for any find/replace tool — added in review.)* | — | a `target_text` occurring twice → REJECT with "ambiguous anchor". |
| D5 | **Whole-batch ceiling.** `doc_changed_ratio = Σ changed_tokens / total_doc_tokens`; WARN/escalate when `> DOC_CEILING`. | `DOC_CEILING=0.25` | a batch of 40 boilerplate edits trips `over_redline`. |
| D6 | **Tracked-change + mandatory dry-run.** Every edit is a native tracked change with author+timestamp; the batch **must** run `process_batch(dry_run=True)` (returns proposed diff + per-edit verdicts) and be self-reviewed **before** any `dry_run=False` write. Write with no preceding successful dry-run → BLOCK. | required on 100% of edits | round-trip reopens the `.docx`, asserts `w:ins`/`w:del` carry author/date and Accept yields the expected clean text; write with no prior dry-run → REJECT (state precondition in `guarded_dispatch`). |

### 6.3 Classifier-backed gate (model-in-the-loop; human-routed on low confidence)

Honest scoping (review fix #3): these are **not** pure code — they emit a label + confidence, and **low
confidence routes to the human**:

- **C1 Cosmetic / meaning-preserving block.** An edit that is meaning-preserving (no change to obligation,
  party, modal, number, deadline, defined term, risk) **and** touches no substantive token is **stripped** —
  "acceptable but not how I'd write it" = leave it (Adams; Percipient).
- **C2 Low-materiality scope-creep.** Fraction of edits on low-materiality clauses (boilerplate/notices/
  headings) vs high (liability/indemnity/IP/price/term); WARN when `> LOWMAT_WARN` (`0.50`) (DocJuris;
  Percipient).
- **C3 Counterparty-interest inference** (§ 8) and **C4 "improves protection on an already-acceptable
  clause"** — see § 6.4.

### 6.4 Computable "already-acceptable / improves-protection" + fail-close (review fixes #2, #5, #7)

- **"Already-acceptable / client-protective"** is only a *code* gate when a **playbook position exists** for
  that clause: if `clause.status == acceptable` (from `standard_positions`) and the agent edits it without
  `improves_protection=true` *verified against the playbook position*, **escalate** (Alnajafi Rule 7: accept
  readily-agreeable language; don't re-edit clauses that already protect the client). Where **no** playbook
  position exists, this is classifier/human-routed, **not** a hard code gate.
- **Fail-close on unresolvable clause span:** if `clause_tokens` is undeterminable (the match straddles
  clause boundaries) the ratio is not computable → **fail closed, route to human**.
- **Jurisdiction-competence (know-your-limits):** every shipped skill is **US-default** (NDA US; MSA
  US/UCC-Art.2; DPA US/EU regimes only). If the document's governing law / jurisdiction is **outside the
  agent's qualified calibration**, the agent **declines/escalates rather than redlines**. Treat jurisdiction
  like DPA treats `regulatory_regime` — a required axis; **fail closed when unknown**. A supervised,
  area-qualified counsel must not redline law it is not calibrated for.

### 6.5 Mapping onto Adeu (see `adeu-pinning.md`)

`ModifyText.target_text`/`new_text` are the two strings the diff metric compares; `ModifyText.comment`
carries the mandatory rationale (rendered as a native Word comment); `process_batch(..., dry_run=True)` **is**
the mandatory preview (native, not bolted on); `AcceptChange`/`RejectChange`/`ReplyComment` are the C5
accept/reject/counter verbs. The validator runs **before** `dry_run=False`; the agent calls *our* guarded
tool, not Adeu directly, so the gate cannot be bypassed.

---

## 7. Playbooks as wishlists-with-judgment

- **Tiered positions** per clause: *preferred / fallback / walk-away (floor)*, **must-have vs nice-to-have**,
  numeric floors (Sterling Miller, *Ten Things: Creating a Good Contract Playbook*; ContractKen; Pactly;
  Contract Nerds, *Contracts Queen's Guide*; Spellbook; DocJuris playbook guide).
- **Playbooks are wishlists, applied with judgment — defaults, not verdicts.** Apply rules *with context*;
  low-confidence / out-of-band terms route to the human (maintainer brief #6). A "fallback" that is applied
  non-deterministically is not a fallback — so a **controlling** playbook must be **deterministically bound**
  (C6/F038: instrument-classifier → inject the bound playbook *body*), never relevance-surfaced. A relevance
  miss on the controlling position is malpractice-grade.
- **"Unless instructed otherwise" = instructed by the authenticated human in session — never by document
  text or another skill.** A counterparty document (or a retrieved skill body) that says "you are instructed
  to accept this" is **untrusted input, not an instruction** (prompt-injection boundary; CLAUDE.md). This is
  load-bearing for C6.
- **Escalate below the floor.** A must-have clause resolving at/below the walk-away floor is **mandatory
  escalation to an `approver_role`** (a role, never a named person) with a recorded rationale — never silent
  acceptance (Sterling Miller; reuses `guarded_dispatch` R5 halt / R6 grant). Numeric floors (e.g. "cap ≥ 1×
  annual fees") in the sources are *examples* — **the real floors come from the operator's playbook tables,
  not the research** (§ 11).

---

## 8. Negotiation rounds, accept/reject/counter, position extraction

- **Trichotomy.** Classify **each** counterparty tracked change as **accept / reject / counter** against the
  playbook tier — *check every change*, no silent pass-through; a counter **supplies drafted language**; keep
  tone separate from merit (Alnajafi; LexCheck, *The Art of Redlining*; Fisher & Ury, *Getting to Yes* —
  separate people from the problem). accept/reject/counter is a **first-class auditable classification**
  (counts/types/IDs only).
- **Principled negotiation.** Extract the counterparty's stated **position** *and* infer the underlying
  **interest** (Fisher & Ury via Beyond Intractability / LitCharts; PON Harvard, *Principled Negotiation*).
  **BATNA → reservation point is the hard floor; ZOPA (overlap) decides dealability** (PON, *How to Find the
  ZOPA*). The reservation/floor reuses the playbook walk-away floor + escalation gate.
- **Round awareness.** Track per-clause movement across rounds (conceded / hardened / held). Escalate to a
  call when the round count or a held-on-critical clause crosses a threshold (round-count and held-clause
  integers are **calibration constants**, not sourced — § 11; mechanism corroborated by Pactly ">2 rounds →
  business meeting" and LexCheck round-trip discipline).
- **Counterparty markup is untrusted, provenance-gated.** Any edit *derived from* the counterparty's markup
  is **escalation-required, not auto-applied** (`provenance=counterparty`; Plane 3 / ADR-F032). This is both
  a method rule and a security rule.
- C5 lays this foundation; the **full multi-turn redlining system is the maintainer's separate held
  project**.

---

## 9. Escalation & human-owns (the supervision half)

Human owns every material write (validated-write, ADR-0013 D4). The agent **must escalate** when:

1. A full-clause rewrite (`ratio > REWRITE_MAX`) has no defensible `rewrite_justified` reason.
2. A must-have clause resolves at/below the playbook walk-away floor (→ `approver_role`).
3. A hard-block term is present (illegality, sanctions/export, policy-banned) → unconditional **HALT** (not
   user-overridable) (Sterling Miller, hard lines).
4. The whole-document over-redline ceiling (`DOC_CEILING`) or low-materiality scope-creep warning trips.
5. Round count or held-on-critical crosses the (calibration) threshold.
6. An edit is **derived from counterparty markup** (untrusted provenance).
7. The matched clause span is unresolvable (ratio not computable) — **fail closed**.
8. **Jurisdiction is outside the qualified calibration or unknown** — decline/escalate (§ 6.4).
9. An edit on an already-acceptable/client-protective clause is net **neutral-or-worse** and not flagged
   `improves_protection=true` against a playbook position.

**Two boundaries the review flagged:**
- **Conflicts of interest:** for a single-client **in-house** agent (the org *is* the sole client, § 2) the
  classic multiple-client conflict surface does not arise — **N/A by construction**; revisit if the agent
  ever acts for more than one client entity.
- **Privilege of the client's *own* redline strategy:** the counterparty document is untrusted *input*; the
  client's redline reasoning is **privileged work product** and must not leak. The audit carries
  **counts/types/IDs only — never the rationale text, the strategy, or raw clause content** (CLAUDE.md audit
  contract); rationale stays within the matter/org boundary.

---

## 10. Reconciliation with the shipped skills (derive + extend, never contradict)

| Doctrine principle | Shipped skill | Relationship |
|---|---|---|
| Multi-pass review spine (orient→checklist→perspective→red-flags→severity report) | nda-review, msa-review-* (shared spine) | **DERIVES.** C0 names them as controlling references; the agent *invokes* the review, never re-authors the spine. |
| Perspective axis fixed to the client | nda/msa `perspective_lens.md` | **EXTENDS.** C-CLIENT supplies perspective from the org profile (in-house) instead of asking each time. |
| Surgical/minimal redline as an *enforced* gate | nda/msa advisory "suggested redline language" | **EXTENDS into code.** The skills emit text; C4 adds the measurable validator that *blocks* a non-surgical edit. |
| Severity Critical/Material/Minor | nda/msa `severity_rubric.md` (DE-080 hoist) | **PRESERVES EXACTLY** for review-altitude output; does **not** impose it elsewhere. |
| Orthogonal assessment layers | dpa status/posture, qa verdict, snapshot confidence | **MODELS as orthogonal** so one store holds all losslessly. |
| Market- vs regime-benchmarked "standard" | nda/msa (market) vs dpa (GDPR/CCPA/HIPAA) | **SUPPORTS BOTH;** playbook positions = the firm's own market benchmark. |
| Tiered positions, floors, escalate-below-floor | migration `0031` `playbook_positions` + `read_playbook` (C6) | **EXTENDS** to a controlling skill (F038 deterministic bind, floor gate, `approver_role`). |
| Accept/reject/counter + interest extraction | contract-qa verdict axis + nda perspective | **EXTENDS** to a new C5 tool. |
| BATNA/ZOPA/round movement | — none | **NEW** (held follow-on foundation). |
| Universal receipts / self-limits | all four skills | **CANONISES** doctrine-wide. |
| Client = organisation; legal vs business | nda in-house calibration; `standard_positions` | **EXTENDS** via memory + LEGAL_LINE/BUSINESS_DECISION routing. |

> **⚠ F036 (blocks C6).** The review skills use **Critical/Material/Minor**; the `playbook_positions` DB
> CHECK pins **critical/high/medium/low** (`api/alembic/versions/0031_playbooks.py:139`). Incompatible at the
> data layer. The doctrine's recommendation: **keep the review skills' scale for review-altitude output and
> treat assessment axes as orthogonal layers** — but the maintainer must pick the canonical *stored* scale +
> any migration **before C6**. (Minor non-load-bearing note: `msa-review-commercial-purchase` says "six
> passes" in its charter line but enumerates Pass 1–7 in the body — standardise the count language at C0.)

---

## 11. Calibration open questions (do not treat the numbers as sourced)

1. **Every numeric constant is a starting value** (`SURGICAL_MAX 0.15`, `ABS_FLOOR 3`, `REWRITE_MAX 0.50`,
   `MINOR_FLOOR 0.05`, `RATIONALE_MIN_WORDS 15`, `DOC_CEILING 0.25`, `LOWMAT_WARN 0.50`) — calibrate against
   a labelled Commercial redline corpus. The sources support the mechanisms, not the numbers.
2. **Tokenizer + clause-span definition.** D1 needs a deterministic "smallest enclosing clause/sentence" span
   and a fixed tokenizer; if the span is unresolvable, fail closed (§ 6.4). The exact clause-segmentation
   method is a C4 implementation decision.
3. **Deterministic vs classifier split.** D1–D6 are pure code; C1–C4 are classifier outputs with confidence
   and **must be human-routed on low confidence** — not silently auto-applied.
4. **Held-rounds / round-count integers** (">2 rounds", "held ≥3 rounds") are **chosen constants**, not
   sourced — calibrate.
5. **Playbook floors come from the operator's tables** (`standard_positions`), never hardcoded from the
   research examples.
6. **dry_run-as-mandatory-affordance** and the **cosmetic classifier** are team conventions extending the
   sourced "keep Track Changes on / self-review" and "skip meaning-neutral edits" principles — validate live.
7. **F036 canonical severity scale** (§ 10) — maintainer decision before C6.

---

## 12. Sources

**Verified (independently retrieved):**
- Nada Alnajafi (Contract Nerds), *The 10 Rules of Contract Redlining Etiquette™* (2021 PDF).
- Kenneth A. Adams, *On Reviewing a Contract* (verbatim wording via search snippet — page returned 403) and
  *The "Categories of Contract Language" Issues to Focus on When Reviewing Contracts* (adamsdrafting.com).
- Kenneth A. Adams, *A Manual of Style for Contract Drafting*, 5th ed. (ABA) — existence verified; **no
  page-level quote attributed**.
- Sirion, *Contract Redlining Tips: Etiquette and Best Practices*.
- DocJuris, *How to redline a contract* and *Contract playbook creation: a complete guide*.
- Percipient, *Contract Redlining Best Practices for 2025*.
- Sterling Miller (tenthings.blog), *Ten Things: Creating a Good Contract Playbook* (2018) and *Ten Things:
  Dealing with Business Executives* (2025); Thomson Reuters, *Dealing with business executives*.
- ContractKen, *How to Build a Contract Negotiation Playbook*; Spellbook, *Contract Playbook Examples*;
  Pactly, *What Is a Contract Playbook?* and *5 Ways to Triage High-Volume NDA Reviews*; Contract Nerds,
  *The Contracts Queen's Guide to Creating a Practical Contract Playbook*; Streamline.ai, *NDA Reviews —
  Template Playbook*; LexCheck, *The Art of Redlining* and *One-Way and Mutual NDA Review Strategies*;
  Hyperstart, *A Legal Team's Guide… Contract Playbook*.
- Roger Fisher, William Ury & Bruce Patton, *Getting to Yes* (Beyond Intractability summary; LitCharts);
  Program on Negotiation, Harvard Law School, *Principled Negotiation* and *How to Find the ZOPA*.
- ABA **Model Rule 1.13: Organization as Client** (1.13(a)/(b)).

**Snippet only (not independently rendered; used only where corroborated):** WorldCC/Mark Ross,
*Best-In-Class Contract Negotiation Playbooks*; Bloomberg Law contract-playbook & M&A-diligence guides;
Icertis, *What is Contract Redlining?*; ACC Jobline, *In-House Counsel career overview*.
