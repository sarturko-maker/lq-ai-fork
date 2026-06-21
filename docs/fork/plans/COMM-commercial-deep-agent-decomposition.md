# COMM — Commercial practice-area Deep Agent (in-house commercial counsel)

**Status:** DRAFT for maintainer review/edit (per CLAUDE.md: explore → written plan → human edits the plan
→ implement). Produced from a 14-agent research workflow (6 codebase scouts + 5 web scouts → synthesize →
adversarial completeness-critic → refine), then **revised against maintainer feedback + a direct read of the
`deepagents==0.6.8` source** (the orchestration question was answered from code, not assumed). Every
load-bearing codebase seam was re-verified against `main` (head `ac659fb`). **Date:** 2026-06-21.

> Compass: this is the **second practice area** built on the same area-agnostic substrate that carried
> Privacy (PRIV-1…A3). Privacy proved the substrate end-to-end; Commercial reuses it and adds the
> document-heavy, negotiation-round, redline-producing capabilities an in-house deal lawyer needs.

---

## Overall goal (the north star — this is the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
This is the design objective every part of the build serves; it is not a system-prompt line. It decomposes
into three things the architecture must *make true*, not merely *assert*:

- **"A legal counsel" (not a chatbot/prompt).** A bounded agent with real **tools** (it acts — reads the
  deal, redlines the `.docx`, extracts positions), real **gates** (it cannot exceed its authority), real
  **memory of the client** (the org profile = the client), and real **work product** (the tracked-changes
  `.docx` + an auditable accept/reject/counter record).
- **"Qualified in that area."** Two layers of qualification: (1) **model/harness qualification** — only a
  qualified `(model, harness-profile)` runs the area (the F0-S9 tier-floor mechanism; DeepSeek is the
  qualified target); (2) **competence in the area** — the area's curated doctrine + tools + the
  **controlling skills** that make it *reliably* apply the firm's positions (not "the model happened to
  recall the right move"). Qualification is enforced, not hoped for.
- **"A human is supervising."** The supervisor is always in control and can always see what counsel did:
  **human-owns** every material write (validated-write, ADR-0013 D4), **escalation-required** gates for
  anything below a playbook's floor or derived from the counterparty's own document, and **auditable
  receipts** (what counsel read, which controlling position it applied, what it deviated and why —
  counts/types/IDs). The agent works *visibly* (streamed tool calls / subagent fan-out / honest receipts).

Read the rest of this plan as: *how do tools, gates, skills, qualification and memory combine into a
supervised, qualified counsel for the Commercial area* — and the same shape generalises to every practice
area (cf. `docs/fork/NORTH-STAR.md`).

## Thesis

The Commercial Deep Agent is **in-house commercial counsel acting for its client**. A deal arrives as an
email (often a whole chain plus attachments); the agent reads all of it, fans out subagents, builds a
**deal context** that lives in matter memory and updates across negotiation rounds, applies the client's
**playbooks as wishlists-with-judgment**, and produces **surgical, client-protective redlines** as native
tracked-changes `.docx` via **Adeu** — escalating anything below a playbook's fallback floor to the human.
Simple deals (an NDA) get a single-pass review; complex ones trigger fan-out. The role, risk posture and
house style come from the **4-level memory** — and **the client *is* the operator's own org profile** (this
is in-house).

We build this **entirely on the existing declarative substrate** — the same seams Privacy uses — adding
exactly **one** per-area code branch (`COMMERCIAL_AREA_KEY`) mirroring the Privacy grant block. No new
pipelines, no legacy-executor edits.

---

## Maintainer decisions folded into this revision (2026-06-21)

| # | Decision | Effect on the plan |
|---|---|---|
| A | **Adeu works** — maintainer has used it; it's **MIT**. | C-R0 Adeu work drops to API-surface pinning + transitive-license check; **no go/no-go gate**. |
| B | **No copyleft licenses in dependencies** (hard rule). | New readers + Adeu's tree are permissive (verify at pin). **Tension:** PyMuPDF (current PDF parser) is **AGPL** → a decision (grandfather under the server-side boundary, or replace with a permissive PDF parser). See Open Q. |
| C | **Don't assume deepagents can't orchestrate — read the code.** | Done. The orchestration section is rewritten from the `deepagents` source: subagents *do* fan-out; only *guarantees* need langgraph. See below. |
| E | **The org profile is the client** (find it / create one; ensure it's injected). | `OrganizationProfile` exists but is **not wired into the area agent**. New slice **C-CLIENT** injects it as the read-only company tier. |
| F | **Use DeepSeek** (cost-efficient). | Live-qualification target = DeepSeek (OpenAI-surface gateway path). Open Q #4 resolved. |
| G | **python-docx cannot redline; models choke on XML → Adeu is required.** | C4 has **no python-docx/lxml fallback**; Adeu is the **sole** redline path. Its whole reason for being is to abstract the OOXML `w:ins`/`w:del` so the model only proposes find/replace edits. |
| H | **Multi-turn redlining is the next project** (held). | Added as a **held follow-on milestone**; C5 (negotiation rounds) is its foundation, not the full system. |

---

## Architecture decisions (the spine)

1. **Declarative substrate, fresh migration numbers.** Extend Commercial through seeded
   subagents/skills/profile via **idempotent check-before-write** migrations (ADR-F004), at **fresh numbers
   — head is `0065`** (`0041/0054/0056/0057` taken; `0057` already seeds the Commercial
   `document-researcher`). The single permitted per-area code seam is the area-keyed grant branch in
   `composition.py` (`COMMERCIAL_AREA_KEY`), mirroring the Privacy block at `composition.py:224`. No
   per-area pipelines, no legacy-executor edits.
2. **Lawyer method grounded in a research artifact, not asserted.** A committed method-doctrine doc
   (Alnajafi redlining etiquette / Sterling Miller playbook / Fisher & Ury BATNA-ZOPA) is the substrate from
   which the Commercial `profile_md` and the `playbook-redline` SKILL.md derive, reconciled with the **four
   existing review skills** (`nda-review`, `msa-review-commercial-purchase`, `contract-qa`,
   `dpa-checklist-review`) — references them, never duplicates/diverges.
3. **Redline = Adeu (MIT, maintainer-confirmed) as a pinned, upgradeable PyPI library** via its SDK
   (`RedlineEngine`/`ModifyText`/`process_batch`), **never** its bundled FastMCP server (a second egress).
   Adeu makes zero provider calls, so it doesn't breach gateway-only egress; it is wrapped behind a
   `guarded_dispatch` tool. **Adeu is the SOLE redline path — no python-docx/lxml fallback** — because
   python-docx cannot author tracked changes and **models choke on raw OOXML `w:ins`/`w:del`**; Adeu exists
   precisely to abstract that XML so the model only proposes narrow find/replace edits. **Surgical bias is a
   MEASURABLE code-side gate** (per-edit diff-ratio + token-span thresholds + mandatory rationale + mandatory
   `dry_run` preview), not prompt alone — the direct answer to Adeu's over-redlining tendency (Adeu faithfully
   applies whatever it's sent; the gate is what keeps edits narrow).
4. **Document ingestion extends via a MIME→reader registry** injected into `ingest_file` (replacing the
   `is_pdf_mime` early-reject in `pipeline/ingest.py`), each reader returning the existing `ParsedDocument`
   contract. New readers — **all permissive (no copyleft, maintainer hard rule B):** python-docx MIT,
   python-pptx MIT, openpyxl-read (already a dep, MIT), stdlib `email`, python-oxmsg MIT for `.msg` (NOT
   GPLv3 extract-msg; olefile transitive is BSD). All readers are strictly **fitz-free**, enforced by a **CI
   import-guard test** (not a manual grep). Office XML parsed with **external-entity resolution disabled**
   (defusedxml/lxml hardening — lxml is BSD) — XXE *and* Office external-relationship / remote-template SSRF.
   **Copyleft tension to resolve:** the *current* PDF parser, **PyMuPDF, is AGPL** (held under the
   server-side-only boundary in NOTICES.md). Rule B now sits in tension with it → a decision (Open Q).
5. **Deal context = matter memory keyed on `project_id`** — the so-far-unrealised unit-of-work tier. v1
   injects `projects.context_md` at the composition seam (**currently never read**) and adds a guarded
   `propose_deal_context_update` tool feeding a **NEW deal-context proposal table** (`0041` is precedent-bound
   — `precedent_id NOT NULL` — and doesn't fit; new-table-vs-nullable-precedent decided in F030 before build).
   Context is **reconcilable/supersedable** (not blind append).
6. **The CLIENT is the org profile.** `OrganizationProfile` (single row, `content_md`) **already exists**
   (`models/organization_profile.py`, served by `internal.py`), is the operator's own-org voice, and for an
   in-house agent **is the client**. BUT it is **not wired into the area Deep Agent path** (`api/app/agents/`
   has zero org-profile references — it only reaches the legacy skill-assembly path). Acting-for-its-client
   therefore needs slice **C-CLIENT**, which injects the org profile as the **read-only company/client memory
   tier** at the composition seam. (This is the 4-level memory's company tier; operator-owned via the existing
   org-profile endpoint, **read-only to the agent**.)
7. **Commercial records are MATTER-SCOPED** (filter by `binding.project_id`) — the **opposite** of ROPA's
   deployment-global rule (ADR-F019). A **security boundary** (cross-deal leakage), not a style choice → ADR
   **F035**.
8. **Playbooks stay in their Postgres tables** (migration `0031`). The agentic path adds a **read-only
   guarded** `list_playbooks`/`read_playbook` tool (clone of the ROPA list tools) + a `playbook-redline`
   SKILL.md that applies the wishlist with judgment. The **severity-scale conflict is structural** — DB CHECK
   `critical/high/medium/low` (`0031:139`) vs the review skills' `critical/material/minor` — so the canonical
   scale (+ any stored-position data migration) is decided in **pre-C6 ADR F036**. The inert
   `agent_config.playbooks` by-reference list becomes the run-time least-privilege scope with run-time
   ownership validation (404-not-403). The legacy linear executor is **not** extended.
9. **Lawyer method = readable artifacts** (transparency rule): surgical / accept-reject-counter / escalation
   discipline lives in `profile_md` + `playbook-redline` SKILL.md + the existing review skills.
   accept/reject/counter is a **first-class auditable classification** (counts/types/IDs only, never raw
   clause text). Deal-complexity triage sets autonomy/fan-out budget. Escalation-beyond-fallback is a
   **tool-level gate** (`escalation-required`), not a prompt suggestion.
10. **Gateway tool-calling premise = the OpenAI-surface path** (`openai.py` forwards tools), and we qualify on
    **DeepSeek** (decision F). NOTE: CLAUDE.md blocker #2 ("Anthropic adapter is text-only") is **stale** —
    `anthropic.py` now maps `tool_use ↔ tool_calls`. So no claim of a frozen adapter; Anthropic tool-calling
    is simply out of scope here. *(Worth a one-line CLAUDE.md correction.)*
11. **Orchestration: deepagents subagents do the fan-out; only *guarantees* need langgraph.** Read from the
    `deepagents` source (see the dedicated section). Most of the brief is covered by the existing
    model-driven `task`-tool subagent mechanism the fork already uses. A deterministic outer layer is a
    **deferred track** opened only by the O0 spike, behind the cost router.

---

## The slice ladder

C-series vertical slices — each end-to-end, runnable, testable, ≤2–3 days, **one PR**, full 4-discipline
DoD. Dependency-first. **Two ADRs must be accepted before their dependents build:** F030 (before C3) and
F036 (before C6).

```
C-R0 ─► C0 ─┬─► C-CLIENT ─┐
            ├─► C3 ───────┤
            │             ├─► C5 ─► C7
   C1 ─► C2 ┘             │
   C0,C-R0,C1 ─► C4 ──────┘   C4 ─► C6 (needs F036+F038)   C4 ─► O0 (deferred-track spike)
```

### C-R0 — Research spike: lawyer-method doctrine + Adeu pinning *(2d, gates C0 & C4)*
**Goal.** Two grounded deliverables. (a) **Lawyer method** — a committed method-doctrine doc grounded in
practitioner/theory sources (Alnajafi, Sterling Miller, Fisher & Ury), reconciled against the four existing
review skills so `profile_md` *derives from sources + extends shipped skills*. (b) **Adeu pinning** (Adeu is
confirmed working + MIT per decision A — no go/no-go) — pin the exact version; verify the
`RedlineEngine`/`ModifyText`/`process_batch` SDK signatures **on the pinned version** (AI_CONTEXT.md is stale
at v1.6.0; PyPI is 1.12.x); confirm **zero provider/network calls**; confirm the **transitive tree is all
permissive — no copyleft** (decision B: `fastmcp`/lxml/rapidfuzz etc.); produce a **concrete checkable
definition of "surgical"** (diff-ratio + token-span thresholds) for C4's gate.
**Non-goals.** No code; no `profile_md` edit (C0); no Adeu in `pyproject` yet (C4); no orchestration research (O0).
**Key files.** `docs/fork/research/commercial-lawyer-method.md` (new), `docs/fork/research/adeu-pinning.md`
(new), the four `skills/*/SKILL.md`, `api/pyproject.toml`.
**Verify.** Docs only: every method claim cites a source; the surgical definition is concrete numeric
thresholds C4 can test; Adeu pinning records the exact pin + a verified **permissive** license chain + a
throwaway-venv `pip install adeu==<pin>` import smoke (SDK symbols exist, **no network call**).
**ADR.** F028 drafted here (accepted with C0).

### C0 — Commercial profile + lawyer-method spine *(2d)* — depends C-R0
**Goal.** Make the seeded Commercial agent behave like in-house counsel: encode the source-grounded surgical /
accept-reject-counter / must-have-vs-nice-to-have / escalation discipline + deal-complexity triage into the
Commercial `profile_md`, **explicitly referencing and reconciling with the four review skills**. Pure config +
scenarios; the lowest-risk build slice.
**Non-goals.** No redline tool (text-only proposals); no deal-context injection (C3); no org-profile wiring
(C-CLIENT); no re-authoring the review skills.
**Key files.** `api/alembic/versions/0066_commercial_profile_doctrine.py` (new, idempotent),
`api/app/models/practice_area.py`, `api/app/agents/area_agent.py`, the review SKILL.md files,
`api/tests/agents/scenarios/test_commercial_scenarios.py`, `api/tests/test_practice_areas.py`.
**Verify.** CI: `test_agent_composition.py` asserts the new profile clauses appear in the assembled system
prompt; `test_practice_areas.py` pin updated via the idempotent seed at fresh `0066`. Live (DeepSeek):
Commercial scenario (NDA single-pass + a coarse-edit prompt) shows triage, `nda-review` invocation, and refusal
of whole-clause rewrites in favour of surgical edits with rationale.
**ADR.** F028. *(Encodes the lawyer method as a curated **abstract method skill**; establishes the
controlling-vs-advisory convention — see Tools & Skills architecture §Plane 2.)*

### C-CLIENT — Org profile = client: inject as read-only company memory *(2d)* — depends C0
**Goal.** Realise the **company/client memory tier**: inject the `OrganizationProfile.content_md` at the
composition seam as a **fenced, read-only "Client / house context" block** so the Commercial agent acts *for*
the operator's org. Today `OrganizationProfile` exists (`models/organization_profile.py`, `internal.py`
endpoint) but is **never referenced in `api/app/agents/`** — this slice wires it into the area run, read-only
to the agent (operator-owned via the existing endpoint; "system proposes, user owns" applies to *edits*, which
already go through the org-profile UI/endpoint).
**Non-goals.** No counterparty entity (the *other* side stays implicit in deal context — separate follow-on);
no new write path (org profile is edited via its existing endpoint); no CompositeBackend `/memories/company`
backend yet (read-on-demand target is a later migration).
**Key files.** `api/app/agents/composition.py`, `api/app/agents/area_agent.py`,
`api/app/models/organization_profile.py`, `api/app/api/internal.py` (reuse the loader),
`api/tests/agents/test_agent_composition.py`.
**Verify.** CI: composition test asserts the org-profile block is fenced-injected and **read-only** (no tool
mutates it; treated as untrusted-but-trusted-source company context); absence (empty profile) degrades cleanly
to no block. Authz: single-tenant company-global (one row), so no per-user scoping — assert it's the operator's
org. Live (DeepSeek): a Commercial run visibly reflects the client's risk posture from the profile.
**ADR.** Records the **company-tier** decision under F030 (memory model for Commercial: company + matter tiers)
— no separate ADR unless the injection mechanism proves novel.

### C1 — Document-reader registry: DOCX/PPTX/XLSX/EML *(3d)*
**Goal.** Replace the single PDF MIME gate with an injected **MIME→reader registry** so a matter ingests the
formats a deal arrives in. Each reader returns the existing `ParsedDocument`; chunker/embed/Document model
untouched. Cheapest first: XLSX (openpyxl already a dep), EML (stdlib, zero new dep), DOCX (python-docx), PPTX
(python-pptx). **All permissive (decision B).**
**Non-goals.** No `.msg` (C2); no email-chain threading/nested-attachment recursion (C2); no OCR; no
Docling/VLM swap (deferred spike).
**Key files.** `api/app/pipeline/ingest.py`, `parsers.py`, `chunker.py`,
`api/app/workers/document_pipeline.py`, `api/pyproject.toml`, `NOTICES.md`,
`docs/adr/0006-document-pipeline-architecture.md`.
**Verify.** Per-reader unit tests assert the **Citation Engine invariant** `content ==
normalized_content[start:end]` byte-for-byte + generalized unit-spans (slide#/sheet-name/paragraph-block).
Server-side MIME sniff (filetype/python-magic) rejects spoofed types at the boundary (reject-don't-guess).
**CI import-guard test** asserts no non-PDF reader imports `fitz`. Office XML parsed with external entities
disabled (XXE + remote-template SSRF). Live: upload one of each format → ready + searchable chunks (rebuild
api+arq-worker+ingest-worker together).
**ADR.** F029 (extends/supersedes ADR-0006).

### C2 — Email-chain + .msg + nested-attachment reader (deal-origin) *(3d)* — depends C1
**Goal.** A deal starts with an email; complex ones are the whole chain + attachments. Add `.msg`
(python-oxmsg MIT) and an **email-chain reader** that walks multipart parts, stitches by
`Message-ID`/`In-Reply-To`/`References`, carries per-message From/Date as span metadata, and recurses **one
level** into attached office docs by delegating to the C1 registry. All bodies untrusted (sanitize HTML, no
remote fetch).
**Non-goals.** No quoted-history splitting lib unless proven needed; no counterparty/deal **entity** model
(crux lives in matter memory, C3); no recursion deeper than one level.
**Key files.** `api/app/pipeline/parsers.py`, `ingest.py`, `api/app/models/document.py`,
`api/pyproject.toml`, `NOTICES.md`.
**Verify.** Unit: multi-message `.eml` → ordered per-message spans with sender/date in `metadata_json`; `.msg`
parses sender/recipients/subject/body+attachment bytes; an attached office doc is recursed + chunked.
Security: HTML sanitized, `cid:`/`http(s)` **not** fetched, nesting depth + per-part size capped
(zip-bomb/XXE/billion-laughs guard, external entities disabled); the C1 import-guard extends to the new
readers. Live: ingest a real multi-attachment deal email; agent answers a question grounded in a buried
attachment.
**ADR.** F029 (extended).

### C3 — Deal context as matter memory (inject + propose/accept with reconcile) *(3d)* — depends C0
**Goal.** Realise the unit-of-work memory tier: inject `projects.context_md` at the composition seam as a
**fenced read-only "Deal context" block**, and add a guarded `propose_deal_context_update` tool feeding a
**deal-context proposal → user-accept** write (ADR-0013 D4/D5). `0041` is precedent-bound and doesn't fit →
this slice creates a **new** deal-context proposal table. Context is **reconcilable/supersedable**.
**Non-goals.** No typed deal-context schema (free-form `context_md` + proposal table v1); no
CompositeBackend backend yet; no reuse of `0041`; no auto-accept of material changes.
**Key files.** `api/app/agents/composition.py`, `api/app/models/project.py`, `api/app/models/autonomous.py`,
`api/app/api/autonomous.py`, `api/alembic/versions/0067_deal_context_proposals.py` (new),
`api/app/agents/guard.py`, `ropa_tools.py`.
**Verify.** CI: composition test asserts `context_md` fenced-injected + read-only; guarded-tool test asserts
`propose` writes a **proposal row** (not `context_md` directly) through `guarded_dispatch` with counts/types/IDs
audit only; accept endpoint applies exactly-once (`accepted_at` guard); supersede test shows a replaced fact
doesn't duplicate. Authz: matter-memory owner-scoped + archived-aware, cross-user 404. New migration applies on
a throwaway pgvector container at fresh number. Live (DeepSeek): two-turn run — agent proposes, user accepts,
next run reflects it.
**ADR.** F030 (**accept before build**; covers the company + matter tiers — see C-CLIENT).

### C4 — Adeu surgical-redline validated-write tool (measurable gate) *(3d)* — depends C-R0, C0, C1
**Goal.** Wrap Adeu behind a guarded `apply_redline` tool (matter-scoped, filter by `binding.project_id`).
Model proposes a batch of narrow `ModifyText` edits; **code validates surgical bias** against the C-R0
definition (per-edit diff-ratio + token-span thresholds + required rationale per substantive edit + mandatory
`dry_run` self-review preview), then applies to the original `.docx` as **native tracked changes**. Audit
records counts/types/IDs (accepts/rejects/counters, clause types, escalations), **never raw target/new text**.
**Adeu is the sole redline path** (decision G — no python-docx/lxml fallback; python-docx can't author
tracked changes and models choke on OOXML; Adeu abstracts it).
**Non-goals.** No counterparty-markup extraction (C5); no multi-round state machine (C5; the full multi-turn
system is the held follow-on, see below); no live-Word/COM path (Linux disk `.docx` only); no `langchain-adeu`
toolkit (WIP, not on PyPI) — use the stable adeu SDK.
**Key files.** `api/app/agents/composition.py`, `commercial_tools.py` (new), `guard.py`,
`api/app/schemas/commercial.py` (new), `ropa_tools.py`, `api/pyproject.toml`, `NOTICES.md`.
**Verify.** CI: `*Input` validators reject over-broad edits using the C-R0 thresholds and missing rationale
(reject-don't-sanitize) — a justified full-clause rewrite is **not** rejected, a phrase-where-a-word-suffices
**is** (the gate has teeth); `guarded_dispatch` tested with a `COMMERCIAL_AREA_KEY` grant; Adeu engine injected
via DI (no import-time instantiate; wired in the arq worker `on_startup` **and** API lifespan); round-trip test
reopens the redlined `.docx` and asserts `w:ins`/`w:del` carry author/date + Accept/Reject yields expected
clean text. Adversarial: input `.docx` untrusted; no `fastmcp` egress imported; audit carries no clause text.
Live (DeepSeek): a surgical tracked-changes `.docx` on a real NDA, narrow edits only.
**ADR.** F031. Cites F018, F010, **F035**.

### C5 — Negotiation rounds + counterparty-position extraction *(3d)* — depends C3, C4
**Goal.** Teach the agent rounds: a guarded **read-side** `extract_counterparty_position` tool/skill reads the
other side's markup (tracked changes surfaced by C1/C2) as their revealed position, classifies each change
**accept/reject/counter** against the playbook tier, and where it counters **drafts concrete replacement
language itself** (asking-party-drafts rule). accept/reject/counter is surfaced as a tool/plan SSE frame.
Relationship to the `0057` `document-researcher` is explicit: the researcher reads documents generally;
`extract_counterparty_position` is the specialised markup-diff tool the lead (or researcher) calls.
**Non-goals.** No automatic acceptance of counterparty changes (human owns concessions beyond fallback); no
persisted negotiation-round entity beyond matter memory + documents. **This is the *foundation* for multi-turn
redlining (the held follow-on), not the full system.**
**Key files.** `commercial_tools.py`, `composition.py`, `api/app/agents/stream.py`, `nda-review/SKILL.md`,
`area_agent.py`, `subagent_fixtures.py`.
**Verify.** CI: extraction tool re-asserts **both** `binding.user_id` **and** `binding.project_id` +
`deleted_at IS NULL` (no cross-user *and* no cross-matter doc read); a fixture markup yields per-change
accept/reject/counter with matched tier; SSE frame mirror tested (reuse the `data-ropa-change` pattern). Live
(DeepSeek): round-2 scenario — counterparty pushback on a redlined NDA; agent extracts positions, classifies
each, counters with drafted language, escalates a below-fallback demand via the `escalation-required` gate.
**ADR.** F032. **Safety:** `extract_counterparty_position` output is tagged `provenance=counterparty`
(untrusted model input); any redline derived from it is **escalation-required**, not auto-applied (Tools &
Skills §Plane 3).

### C6 — Playbooks as *controlling* skills: deterministic binding + apply-with-judgment *(3d)* — depends C0, C4, F036, F038
**Goal.** Apply relevant playbooks IF they exist, as wishlists with judgment. Add a read-only guarded
`list_playbooks(contract_type?)`/`read_playbook(id|name)` tool (clone of the ROPA list tools, returning
`Position[]`/`FallbackTier`) scoped to the area's `agent_config.playbooks` by-reference list with **run-time
ownership validation (404-not-403)**. Pair with a `playbook-redline` SKILL.md that loads the playbook, treats
`standard_language` as target + `fallback_tiers` as ranked retreats, judges each clause in context, and emits a
severity-rated redline. The canonical severity scale + any stored-position data migration are decided in
**F036 before this slice**. The skill **reuses** the four review skills.
**Non-goals.** No extension of `api/app/playbooks/executor.py` or `/api/v1/playbooks/execute`; no new playbook
authoring UI (the Easy-Playbook wizard stays the source); no first-class playbook→area FK.
**Key files.** `api/app/models/playbook.py`, `api/app/schemas/playbooks.py`, `commercial_tools.py`,
`area_agent.py`, `skills/playbook-redline/SKILL.md` (new), `nda-review/SKILL.md`,
`api/alembic/versions/0056_default_area_skill_bindings.py` (pattern for the fresh binding migration).
**Verify.** CI: read tool through `guarded_dispatch`, validates playbook ownership at run time (404-not-403),
treats stored positions as untrusted; new SKILL.md binds via a **fresh** idempotent skill-binding migration
(`0056` taken); the canonical scale (F036) enforced + any data migration verified on a throwaway container; a
guardrail test: tier-deviation allowed **only** with a recorded rationale; assert the legacy executor is
**not** touched. Live (DeepSeek): scenario applies a stored playbook **with judgment** → a severity-rated
surgical redline citing the playbook tier.
**ADR.** F033 + **F036 + F038 (all pre-C6, blocking)**. A playbook is a **controlling skill**: a code-gated
instrument classifier deterministically injects the bound playbook **body** (not relevance-surfaced),
jurisdiction-gated, with an apply-**receipt**; user/team skills stay advisory-only (never controlling); the
controlling namespace is **non-shadowable** (Tools & Skills §Plane 2). The relevance-surfaced "wishlist with
judgment" framing now applies to *advisory* supplementary skills, not the controlling position.

### C7 — Complex-deal fan-out: roster + deal-context live signal + redline download UI *(3d)* — depends C2, C3, C5
**Goal.** Not every deal is complex; the complex ones need fan-out. **Extend the existing `0057`
`document-researcher`** (do **not** introduce a parallel roster) with a drafter/reviewer roster via a fresh
idempotent migration (reconcile by editing the same `agent_config.subagents`, check-before-write), model-free
(ADR-F010), referencing only area-bound skills (ADR-F017). The lead triages complexity and **fans out via
deepagents' `task` tool** over the email chain + attachments (this is the model-driven subagent path the fork
already runs — see the orchestration section). Add a **deal-context live signal** (clone the `data-ropa-change`
ledger→drain→SSE seam). Add the missing **output surface**: a UI path to download the redlined `.docx` and to
see/act on the accept/reject/counter classification.
**Non-goals.** No per-subagent tool subsetting (v1 inherits parent tools); no deterministic outer-StateGraph
orchestration (deferred; only O0 here); no guaranteed parallelism beyond deepagents' `task` tool; no new
counterparty entity.
**Key files.** `api/alembic/versions/0068_commercial_roster.py` (new), `area_agent.py`, `composition.py`,
`stream.py`, `web/src/lib/lq-ai/agents/run-stream.ts`, `helpers.ts`,
`web/src/lib/lq-ai/components/agents/ConversationPanel.svelte`.
**Verify.** CI: `reject_model_bearing_subagents` gates the extended roster; subagent-skills-subset-of-area
enforced; migration idempotent + fresh number (reconciles `0057`); `parent_step_id` nesting test covers
multi-subagent fan-out; new `data-*` part parsed in `run-stream.ts`; download endpoint test asserts the
redlined `.docx` is owner+matter-scoped (404 cross-user). Live (DeepSeek): a multi-attachment deal fans out N
readers nested in the timeline; `max_steps`/wall-clock sized for N readers; a halt-mid-fan-out test confirms
cancellation; user downloads the redlined `.docx` and sees the classification.
**ADR.** F034 (optional). **Adds** a mandatory **post-fan-out reconciliation** pass — a consistency check
across subagents' proposed positions before a single work product is emitted (independence across legal
subagents is a *defect*, not a feature; Tools & Skills §Plane 3).

### O0 — Orchestration embed-validation spike *(2d, deferred-track opener)* — depends C4
**Goal.** Validate — against pinned `deepagents==0.6.8` / `langgraph 1.2.4` — the two load-bearing claims that
let us add *deterministic guarantees* later (see the orchestration section): (1) a **deterministic langgraph
subgraph wrapped as a `CompiledSubAgent`** runs through the fork's stack with gateway-bound models + brakes
intact — **and what `reject_model_bearing_subagents` must allow** for it (currently it rejects non-dict specs);
(2) a compiled deep agent **embeds as a node in a hand-authored `StateGraph`** with Send fan-out → reducer
fan-in → conditional-edge critic loop. Smallest prototype of each; confirm R4 cost aggregation across branches
and an R5 halt cancelling in-flight branches are observable. **The only orchestration work in the milestone.**
**Non-goals.** No production factory (O1); no router (O2); no judge panel/verifier in production (O3); no
revival of the legacy executors.
**Key files.** `api/app/agents/factory.py`, `area_agent.py`, `guard.py`,
`docs/fork/research/orchestration-embed-spike.md` (new), `docs/adr/F037-orchestration-layer.md` (new).
**Verify.** Throwaway spike test proves both embed paths on the pinned versions; every node routes through
`build_gateway_chat_model` (egress preserved); reducer barrier fan-in works; a conditional-edge loop terminates
under a Python iteration cap; N branches are N guarded dispatches; an R5 halt mid-fan-out cancels branches;
documents exactly what an ADR-F010 carve-out for vetted app-built compiled subagents would need to say.
Findings + go/no-go for the deferred O1/O2/O3. No production wiring.
**ADR.** F037 (proposed; accept only if the track is greenlit).

---

## Deep-agent orchestration — answered from the `deepagents` source (brief #9)

> The maintainer asked: *why can't the deterministic "workflows" be done with the subagent orchestration
> already in Deep Agents?* This section is rewritten from a direct read of `deepagents==0.6.8`
> (`middleware/subagents.py`, `middleware/async_subagents.py`, `graph.py`, `area_agent.py`,
> `factory.py`) — not assumed.

**What deepagents subagent orchestration actually is.** `SubAgentMiddleware` adds **one tool — `task`** —
to the agent (`subagents.py:600`). A subagent is a spec with its own `system_prompt`, `tools`, `skills`,
optional `model`, and optional `response_format` (structured output). The orchestrator **LLM decides** to call
`task(description, subagent_type)`; deepagents runs that subagent to completion and feeds **one final message**
(or structured JSON) back (`subagents.py:494–564`). **Parallel fan-out happens when the model emits multiple
`task` calls in one turn** — the tool description explicitly pushes "launch multiple agents concurrently …
single message with multiple tool uses" (`subagents.py:288`). **The fork already runs exactly this** (the
`0057` `document-researcher` is a declarative `SubAgent`).

**So for most of the brief, subagents are enough — no custom graph.** Fanning out document-readers over an
email chain, delegating clause review, synthesizing deal context (C7) is precisely the model-driven `task`
mechanism. The maintainer's instinct is correct, and this plan uses it for C5/C7 with **no** new orchestration
layer.

**The one thing subagents can't do: *guarantee* a flow.** Because `task` is invoked at the model's
discretion, you cannot *enforce*:
- "**Always** run an adversarial over-reach/under-protect verifier before a redline is emitted."
- "**Always** convene a K-judge panel to pick a fallback position."
- "**Loop** until a completeness critic passes (≥K times)."
- "**Deterministically route** simple clauses → cheap model, hard clauses → expensive model."
The model *approximates* these from instructions; it doesn't *guarantee* them. Also missing: **exact
map-reduce over an enumerated list** (one branch per clause/email, exactly N) — the model does "roughly N";
langgraph's `Send` does "exactly N." For most legal work model-driven is fine; for a few high-stakes
guarantees you want the guarantee in Python. **That — and only that — is what langgraph buys.**

**Two ways to get the guarantee, both additive, neither touching the legacy executors:**
- **(a) A deterministic subgraph wrapped as a subagent.** `CompiledSubAgent.runnable` can be *any* langgraph
  graph (`subagents.py:201–232`). So a hand-authored reviewer→verifier→judge `StateGraph` can be exposed as a
  *single* subagent the orchestrator calls once; determinism lives **inside** it. The lighter option.
  **Blocker found:** the fork's `reject_model_bearing_subagents` guard (`area_agent.py:68`) rejects non-dict
  specs (so `CompiledSubAgent` is currently disallowed) — O0 + an ADR-F010 carve-out for **vetted, app-built**
  compiled subagents is the unlock.
- **(b) A deterministic outer `StateGraph`** with deep agents as nodes (Send fan-out / reducer fan-in /
  conditional-edge loops / subgraph stages). For when the **top-level** flow must be guaranteed. Heavier.

**The router (your idea) — buildable in soft form *today*.** The guard at `area_agent.py:89` rejects a
*provider-string* model (gateway bypass) but **allows a gateway-bound `BaseChatModel` instance**. So a
**soft router** — a `cheap-reviewer` subagent and an `expensive-reviewer` subagent, each carrying a
gateway-bound model, the orchestrator picking — is allowed by the guard and needs no graph (it must be built in
**app code**, not DB config: the area-config renderer's key whitelist forbids `model`). A **hard/deterministic
router** (guaranteed routing by code) needs option (b). Either way the gateway **alias** (`budget`/`fast`/
`smart`) is the cost knob and `combine_tier_floors` keeps routing above the matter's security floor. Caveat
kept honest: published ~50–75% cost-cut figures are general-workload, **not legal** — re-measure on a
Commercial pilot.

**Not applicable:** `AsyncSubAgent` (`async_subagents.py`) launches subagents on a **remote LangGraph server**
(`ASYNC_TASK_TOOL_DESCRIPTION`, line 164) — its own egress + deployment infra. That violates gateway-only
egress and the no-exposure rule; we don't use it.

**Conclusion for the plan:** C0–C7 ride deepagents' model-driven subagents (no orchestration layer). The
O-series exists **only** to add deterministic *guarantees* (always-verify, judge-panel, loop-until-critic, hard
router). O0 validates both unlock paths (subgraph-as-subagent + the F010 carve-out; and the outer-graph embed);
O1/O2/O3 are a separate, cost-router-gated milestone.

---

## Tools & skills architecture (capability model — adversarially reviewed)

> Produced from a direct read of `deepagents` (`SkillsMiddleware`, `subagents.py`, `area_agent.py`,
> `factory.py`, `guard.py`) + a 4-lens adversarial review (security / legal-correctness / architecture /
> harness-analogy). The review **confirmed** the load-bearing posture against the code and **sharpened** it.
> This is how a *supervised, qualified counsel* (the north star) is assembled from tools, gates and skills.

**The contribution is a decision rule, not three boxes.** The "three planes" below largely *describe* what
deepagents + the fork already do; the real design rule is **where a guarantee lives:**

> **Single-dispatch predicate → a TOOL GATE** (precondition/validation/audit of one call: matter-scope,
> surgical-edit bounds, validated-write schema). **Sequence/completion predicate → DETERMINISTIC FLOW**
> (must-happen-before, coverage, consistency: "every material clause checked", "escalation offered before
> conceding", "the controlling playbook was applied", "the fan-out reconciled into one position").
> **Substantive legal correctness → HUMAN-OWNS** (+ optional substantive review) — *never* claimed by a
> structural gate. A gate can prove a redline is well-formed/surgical/scoped; it cannot prove it is *right
> for the client*.

This is the disciplined form of "we don't need deterministic adversarial review for everything": put the
guarantee in the **gate** when it's a single-call property; reach for **deterministic flow** only for the
enumerated must-guarantee *flows*; and keep substance with the **supervising human**.

### Plane 1 — Tools (code) = the hard floor (confirmed by the review)
Abstract primitives (`read`/`grep`/`fetch`/`write`/`plan`/`task`) + domain-abstract legal verbs (`redline`
via Adeu, `extract_counterparty_position`, `propose_deal_context_update`, `read_playbook`). Capability comes
**only** from the per-run granted frozenset assembled at `composition.py` from the **area key** — never from a
skill. Every dispatch passes `guarded_dispatch` (R6/R5/R4); domain writes are validated-write (ADR-F018). **A
skill cannot grant capability or relax a gate — verified true in the current wiring.** (`allowed_tools` in
SKILL.md frontmatter is **decorative** — `extra="allow"` silently drops it; it is **not** a security boundary
and the design must not imply it is. The grant set is the only tool boundary.)

### Plane 2 — Skills (prompts) = judgment, split by ENFORCEMENT (not just abstract/specific)
The useful split is **controlling vs advisory**, because a relevance *miss* on the firm's controlling position
is malpractice-grade — the exact place the Claude-Code "a missed skill is cheap, just re-run" analogy breaks.
- **Controlling / mandatory skills** — curated only. A **code-gated instrument classifier** identifies the
  document type; if a curated playbook is bound to that instrument type, its **body is injected
  unconditionally** (not its description, not relevance-pruned) and a **receipt records it was applied**.
  **Jurisdiction is a code gate** here (compare the matter's governing law to the skill's declared
  jurisdiction; mismatch → refuse-as-controlling, offer advisory). Controlling skills live in a **protected,
  non-shadowable namespace** (the shadow resolver refuses a user/team override of a curated controlling/safety
  skill). **User/team skills may never be controlling.**
- **Advisory skills** — relevance-surfaced (progressive disclosure: name+description+`trigger_examples`
  visible, body on demand) + manually attachable by the user. This is where user/team-authored and
  supplementary curated skills live. Relevance can only ever *add* advisory skills; it can never prune a
  controlling one.
- **Abstract method vs specific** stays a **curation/authoring convention, not a schema field** — do *not* add
  `kind: abstract|specific`. Precedence falls out of scope (built-in vs user/team) + shadowing. Abstract
  method skills (deal-research, contract-review, surgical-redline, position-extraction) are curated built-ins;
  specific skills are company playbooks/positions.
- **Precedence is resolved in CODE where it's controlling** (the specific controlling skill is the one
  surfaced; the abstract method is the fallback only when none is bound) — prose precedence between two
  prompt layers is not enforceable. "Unless instructed otherwise" means **instructed by the authenticated
  human user in this session** — never by document text, never by another skill.

### Plane 3 — Flows = deterministic only where a flow MUST be guaranteed (enumerated up front)
The legal must-guarantee flows (the cases a single-call gate can't express): **controlling-skill-was-applied**;
**counterparty-derived writes are human-owned** (`extract_counterparty_position` output is untrusted — tagged
`provenance=counterparty`; any redline derived from it is escalation-required, not auto-applied);
**post-fan-out reconciliation** (two subagents redlining one work product can take contradictory positions —
independence is a *feature* in Claude Code, a *defect* here, so a consistency/reconcile pass runs before the
work product is emitted); **coverage** ("every material clause checked against the playbook"). These are the
real consumers of the deferred O-track; everything else stays model-driven (the `task`-tool fan-out).

### Untrusted-input + governance posture
- **User/team skill bodies are UNTRUSTED model input** — the same class as KB chunks / shared memory (which
  the fork already treats as untrusted, company/practice memory read-only to agents). They carry no capability
  (the gate is in the tool), are served by the read-only `RegistrySkillBackend`, must be owner/matter-scoped
  (cross-tenant surfacing is a 404-not-403 leak), and their **provenance is shown in the UI** so "looks
  trusted" becomes "labelled by author".
- **Curated/LQ.AI skills need a merge policy mirroring ADR-F005** — a curated skill is unreviewed natural
  language that steers *every* agent's judgment (over-concession / skip-a-check / exfil-shaped instruction):
  same blast radius as code, so adversarial-review the skill **body** before it ships.
- **Auditable "apply with judgment":** `read_file` on a SKILL.md is **not** behind `guarded_dispatch` today,
  so loading a skill body is invisible. Emit a **run receipt** — skills surfaced / bodies loaded / controlling
  skill applied (or "none found") / declared deviations — counts/types/IDs only.
- **Staleness:** add `last_reviewed_at`/`valid_through` to curated company skills; surface "review overdue" in
  the metadata line + the lawyer-facing receipt.

### Exists vs. to-build
- **Exists:** the gates (`guarded_dispatch`, area-keyed grants, validated-write, `reject_model_bearing_subagents`),
  read-only `RegistrySkillBackend`, progressive disclosure, layered last-wins sources, per-subagent **skill**
  subsetting (`PrivateStateAttr`), `UserSkill` model + scopes + shadowing (**browse surface only — not wired
  to the live agent**), jurisdiction/version **metadata**.
- **To build:** instrument classifier + **controlling-skill deterministic binding + receipt** (F038) ·
  jurisdiction **gate** · the **user/team→live-agent untrusted-skill wiring** (F039 — gated; today the agent
  registry is filesystem-only, so this is the most dangerous future change) · **protected non-shadowable
  namespace** · **skill-governance policy** (F040, ADR-F005 analogue) · the **run receipt** · per-subagent
  **tool** subsetting (optional — today every subagent inherits the full area tool set; fine at the current
  tool count) · post-fan-out reconciliation (C7) · counterparty-provenance tagging (C5) · **relevance-based
  source selection** (explicitly a **separate, unstarted milestone** — the architecture's scalability must
  **not** rest on it; until it exists, catalogues are manually bound).

## Held follow-on — Multi-turn redlining (the maintainer's next project, decision H)

**Not built in COMM.** COMM delivers single-round redlining (C4) + the *foundation* for rounds (C5:
counterparty-position extraction + accept/reject/counter + escalation). The full **multi-turn redlining
system** — persistent negotiation-round state across many exchanges, version/turn lineage, diffing a new
counterparty markup against our last position, carrying agreed/open issues forward, and orchestrating the
back-and-forth — is a **separate milestone the maintainer owns**, held here so COMM's seams stay compatible
with it: C3's reconcilable deal-context, C5's auditable accept/reject/counter classification, and (if needed) a
deterministic verify/judge loop from the O-series are its natural substrate. Revisit scope when COMM lands.

---

## Document-parsing landscape (brief #2, forward-looking survey)

Default stack = the **per-format native readers** in C1/C2 (python-docx / python-pptx / openpyxl / stdlib
email / python-oxmsg) — **all MIT/BSD (no copyleft, decision B)**, all in-process, all fitz-free, all behind
the gateway boundary. The **cloud SOTA** (Azure Document Intelligence, AWS Textract, Google Document AI, hosted
LlamaParse/Reducto) is **ruled out** — each is an external egress, violating gateway-only egress. The **one
newer approach worth a time-boxed spike** (deferred) is a **self-hosted, layout-aware / vision-LLM page-fallback
for scanned & complex-layout documents** — e.g. Docling (IBM, Apache-2.0) or a granite-docling-style VLM,
**routed through the gateway like every other model call**. OCR / scanned content is explicitly **out of
scope** for the first ingestion slices. **PDF-parser note:** the current PDF path uses **PyMuPDF (AGPL)** — see
the copyleft Open Q; a permissive replacement (pypdfium2 BSD/Apache, pdfminer.six/pypdf MIT) would also remove
the only copyleft dep in the tree.

---

## ADRs to draft (F-series)

| ADR | Title | When |
|---|---|---|
| **F028** | Commercial agent method doctrine (surgical redline + accept/reject/counter + human-owned escalation), source-grounded | C-R0/C0 |
| **F029** | Multi-format + email-chain ingestion via injected MIME→reader registry (extends/supersedes ADR-0006) | C1 (extended C2) |
| **F030** | Commercial memory model: company tier (org-profile injection, C-CLIENT) + matter tier (`context_md` + NEW propose/accept table, reconcile) | **accept before C3** |
| **F031** | Adeu redline tool — versioned MIT dep, MEASURABLE surgical code gate, gateway-egress-safe (**sole path, no fallback**) | C4 |
| **F032** | Negotiation rounds: counterparty-position extraction + accept/reject/counter classification | C5 |
| **F033** | Agentic playbook application (playbooks as wishlists with judgment) | C6 |
| **F034** | Commercial subagent roster (extends 0057) + deal-context live ledger + redline-download surface *(optional)* | C7 |
| **F035** | Commercial domain records are MATTER-SCOPED (diverges from ADR-F019) — security boundary | before any structured Commercial register (C4/C5) |
| **F036** | Canonical Commercial severity scale + stored-position data migration | **accept before C6** |
| **F037** | Deterministic orchestration layer: subgraph-as-subagent (+ ADR-F010 carve-out) and/or outer StateGraph; router-as-alias | O0 (proposed; accept only if track greenlit) |
| **F038** | Controlling-skill binding: instrument classifier + deterministic body-injection + jurisdiction gate + apply-receipt + non-shadowable protected namespace | **accept before C6** |
| **F039** | User/team-authored skills reaching the live agent — untrusted-input posture, owner/matter-scope (404-not-403), advisory-only (never controlling), provenance in UI | gated future (see Open Q — decides if it exists) |
| **F040** | Skill-governance policy (curated/LQ.AI skills) — ADR-F005 analogue: adversarial-review the skill *body* for injection/over-concession/exfil before it ships | when curated skills are authored |

---

## Global non-goals

- No extension of the legacy executors (`api/app/playbooks/executor.py`, `autonomous/`, `tabular/`) — agentic
  read tool + SKILL.md only.
- **No machine/external exposure**: internal in-house counsel only; no public/unauthenticated endpoint, no
  inbound email gateway, no Adeu MCP server, no `AsyncSubAgent` remote server, no auto-fetch of
  `cid:`/`http(s)` from email bodies **or** Office external-relationship/remote-template references.
- **No copyleft licenses in new dependencies** (decision B). New readers + Adeu's tree are permissive
  (verify at pin). The pre-existing PyMuPDF AGPL dep is a flagged decision, not a new addition.
- No re-invention of shipped artifacts: the four review skills + the `0057` `document-researcher` already
  exist; slices reconcile/extend, never recreate. No migration reuses a taken number (head `0065`).
- No OCR / scanned-document handling in the first ingestion slices.
- No new LLM provider/egress path; Adeu + all parsers are pure byte→text/XML, no network. Provider-agnostic
  (LLM injected via gateway; **DeepSeek** is the qualified target, decision F).
- No deployment-global Commercial registers — records are matter-scoped (do **not** copy ADR-F019's rule).
- No Anthropic tool-calling work (Commercial runs on the OpenAI-surface gateway path) — a scope choice, not a
  claim the Anthropic adapter is frozen (it isn't).
- Orchestration deterministic layer is **not** built beyond the O0 spike — cost-deferred later track.
- **No counterparty ENTITY model** this milestone — the *client* is the org profile (C-CLIENT); the
  *counterparty* stays implicit in matter deal-context; a first-class counterparty profile is a flagged
  follow-on.
- **Multi-turn redlining is not built** here (held follow-on, decision H).

---

## Open questions / decisions for the maintainer

1. **Copyleft vs PyMuPDF (decision B tension).** Rule B forbids copyleft deps, but the *current* PDF parser
   **PyMuPDF is AGPL** (held under a server-side-only boundary). Options: **(a)** grandfather PyMuPDF under its
   existing boundary (rule B applies to *new* deps only); **(b)** replace it with a permissive PDF parser
   (pypdfium2 BSD/Apache, or pdfminer.six/pypdf MIT) — removes the only copyleft dep, but is its own slice with
   citation-invariant re-verification. Which?
2. **Counterparty entity timing.** The *client* = org profile (resolved, C-CLIENT). The *counterparty* stays
   implicit in deal-context this milestone. Build a first-class counterparty profile **inside** COMM, or as a
   follow-on?
3. **Typed deal-context schema.** Free-form `context_md` + the C3 proposal table for v1, or do you want typed
   fields (parties, governing law, deal type, agreed positions, key dates, open issues) soon (later slice,
   triggers F035)?
4. **Playbook ownership model.** Single-tenant company-global vs per-matter ownership for
   `agent_config.playbooks` before wiring 404-not-403 (C6)?
5. **Orchestration greenlight.** After O0 validates the two unlock paths, fund the deferred O1/O2/O3 track as
   its own milestone? (Quality of the router can only be measured on DeepSeek for now.)
6. **Multi-turn redlining handoff.** Confirm COMM stops at single-round + the C5 foundation, and the full
   multi-turn system is your separate next project (held above).
7. **Do user/team-authored skills ever reach the live agent (F039)?** Point (B) wants self-serve company
   skills, but today the agent registry is filesystem-only and that wiring is the most dangerous future
   change. Two postures: **(a)** allow it — advisory-only, never controlling, untrusted-input posture,
   owner/matter-scoped, provenance shown (build F039 as a gated milestone); or **(b)** keep authored skills
   **curated-only** (LQ.AI/built-in/community, code-reviewed) and treat "company-specific" as curated-by-LQ.AI
   rather than self-serve (F039 never exists). This decision determines whether F039 is built.

*Resolved by this revision:* Adeu (confirmed, MIT, sole path — A/G); provider (DeepSeek — F); client identity
(= org profile, C-CLIENT — E); orchestration feasibility (subagents suffice for C0–C7; guarantees are the
deferred O-track — C); the tools/skills capability model (gate-vs-flow decision rule + controlling/advisory
split, adversarially reviewed — folded into "Tools & skills architecture").

---

## Risks (top, with mitigations)

- **AGPL contagion** — a new reader importing `fitz` widens the AGPL surface → **CI import-guard test**
  (machine-enforced). (Compounded by Open Q #1 — PyMuPDF is the existing AGPL path.)
- **Citation Engine invariant breakage** — every reader must keep `chunk.content ==
  normalized_content[start:end]` byte-for-byte → per-reader invariant tests.
- **Prompt injection / XXE / SSRF / zip-bomb** from untrusted documents, email HTML, **and Office external
  relationships** → sanitize HTML, disable external entities, bound decompression, cap nesting; treat all
  extracted text + stored playbook text + injected company/matter memory as untrusted.
- **Cross-deal data leakage** — copying ADR-F019's no-project-filter into any Commercial record leaks one
  matter's positions across all → **F035 matter-scoping**; C5 re-asserts user_id **and** project_id.
- **Toothless surgical gate** — not code-checkable without a measurable definition → C-R0 numeric thresholds;
  C4 CI proves teeth (false-positive **and** true-positive fixtures). Adeu is value-neutral (applies what it's
  sent) → the gate, not Adeu, enforces narrowness.
- **Severity-scale data-layer conflict** — `0031` DB CHECK vs the skills' scale → **F036 before C6** (+ data
  migration if needed).
- **Org-profile injection scope (C-CLIENT)** — company-global singleton injected read-only; must not become a
  second writer and must degrade cleanly when empty → read-only assertion + empty-profile test.
- **Fan-out budget exhaustion (C7)** — N readers can blow `max_steps`/wall-clock → `cap_exceeded` (deep
  fan-out burns langgraph supersteps; `recursion_limit = max_steps*4`) → size the budget, test halt-mid-fan-out
  cancellation.
- **Orchestration F010 interaction** — a `CompiledSubAgent` (the light determinism path) is currently rejected
  by `reject_model_bearing_subagents` → O0 documents the precise carve-out an ADR must grant for vetted
  app-built compiled subagents (no provider strings).
- **Cross-process worker wiring** — runs execute in the arq worker; any new engine/loader (Adeu engine,
  deal-context loader, org-profile loader) must be wired in the worker `on_startup`, not just API lifespan.
- **Audit leakage** — tool results return text verbatim; a redline/extraction tool echoing clause text into
  the audit breaks the counts/types/IDs contract → audit carries no clause text.
- **Stale-codebase collision** — synthesis once referenced taken migration numbers as greenfield; corrected to
  head `0065` + reconcile-don't-recreate → **fresh-head check** before every migration slice.

---

## Cross-cutting (every slice)

- **4-discipline DoD**: build/lint/typecheck/tests SHOWN (containerized per touched service, counts quoted);
  fresh-context adversarial review incl. a security pass + a simplification pass; live verification on the dev
  stack (DeepSeek); HANDOFF.md overwritten.
- **Fresh-head check** before any migration: head `0065` — `ls api/alembic/versions | sort | tail`, take the
  next free number. C1/C2 likely need **no** migration (free-text parser column); C3/C6/C7 add migrations at
  fresh numbers.
- **Ruff version drift**: format with the **CI ruff version** + run CI's exact commands before pushing.
- **Migrations**: never host-side `alembic upgrade` against the live dev DB; verify on a throwaway pgvector
  container; rebuild api+arq-worker+ingest-worker together; never `docker compose down -v`.
- **Gateway-only egress**: never a direct provider call or a second egress (no Adeu MCP server, no parser
  network calls, no remote `AsyncSubAgent`). DI everywhere; no import-time I/O; wire cross-process consumers in
  the worker `on_startup` **and** the API lifespan.
- **No copyleft in new deps** (decision B); record every new SBOM entry + license in NOTICES.md.
- **ADR discipline**: reference ADR numbers in commits + a one-line comment at each governed seam; draft the
  ADR in the same PR; the human accepts. **F030 and F036 must be accepted before C3 and C6 respectively.**
- **Keep the substrate honest**: prefer declarative config over per-area code; the single per-area code seam is
  the `COMMERCIAL_AREA_KEY` grant branch in `composition.py`. Build ON the four review skills + the `0057`
  researcher.

---

## Sequencing summary

**Wave 1 (foundation):** C-R0 → C0 → **C-CLIENT** — research-grounded config spine + the client (org profile)
wired in; no new deps, lowest risk.
**Wave 2 (inputs):** C1 → C2 — the agent can read the formats a deal arrives in (incl. the email chain).
**Wave 3 (memory + redline, parallelizable):** C3 (needs F030) and C4 (needs C-R0/C0/C1) — the two headline
capabilities.
**Wave 4 (judgment + rounds):** C5 (rounds — the multi-turn foundation) → C6 (playbooks, needs F036).
**Wave 5 (scale + surface):** C7 — fan-out (deepagents `task` tool) + the human-facing output.
**Deferred-track opener:** O0 (anytime after C4) — validates the two determinism unlock paths; O1/O2/O3 and the
full multi-turn redlining system are separate, gated milestones.
