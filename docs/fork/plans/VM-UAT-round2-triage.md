# VM UAT round 2 — TaskHarbour QA triage + fix plan

Source: external tester "Technical QA Notes" (10 items, TaskHarbour SaaS renewal, **IT Procurement** area)
+ maintainer's 3 observations (branding accent, PDF convert-then-ask, no memory recorded). Investigated
2026-07-14 via a 12-way adversarially-verified workflow (each claim checked against code by an investigator,
then re-checked by a second agent). "Grain of salt" honoured — several tester claims did **not** survive.

**Nothing here is implemented yet.** This is the triage + proposed slice ladder for maintainer edit.

## Verdict table (severity ordered within group)

| # | Issue | Verdict | Code bug? | Sev | Effort | Where |
|---|---|---|---|---|---|---|
| 3 | Redline comment author hardcoded "LQ.AI Commercial counsel" (all areas) | **confirmed-bug** | ✅ | med | S | `redline_service.py:69` |
| 12 | No matter memory recorded (custom area) | **partial** | ✅ | med | S | `composition.py` coaching asymmetry + profile bindings |
| 10 | Participant from forgeable email header over-trusted downstream | **partial** | ✅ | med(low-end) | S+M | `matter_roster_tools.classify_author` + `review_edited_document_tools` |
| 5 | Redline target-resolution error wording conflates 4 causes | **partial** | ✅ | low | S | `schemas/commercial.py:356` |
| 4 | PDF redline: no pre-tool type signal + not machine-actionable | **partial** | ⚠️ | low | S (+L convert) | `tools.py:814` inventory omits mime; `commercial_tools.py:413` |
| 1 | Unchanged headings appear as `<ins>` in redlined DOCX | **needs-repro** | ❓ | med | M | `redline_service.py:298` offset-index bypass (ties to #524 adeu bump) |
| 2 | Preview omits changes present in applied DOCX | **not-a-bug** | ❌ | — | — | same bytes (`commercial_tools.py:521`); folds into #1 |
| 11 | Branding accent colours "don't work" — maintainer says **NOTHING recoloured** | **needs-repro** (re-test post-#276) | ❓ | low | — | prime suspect: branding PUT save was broken until #276; palette never persisted |
| 6 | No post-redline contradiction check | **feature** | ❌ | low | S | preview ±N context; `adversarial_review` already covers semantic |
| 7 | Grid defaults rows=documents, needed rows=fields | **feature** | ❌ | med | L (S guidance) | grids tool document-row axis baked in; **product decision** |
| 9 | Two "Items requiring human judgment" sections | **model-behaviour** | ❌ | low | S | doctrine (mig 0066) + skill template both mandate it |
| 8 | Grid text truncated when pasted ("rene form") | **model-behaviour** | ❌ | low | — | LLM re-typing; no owned code clips interior chars |

## What the tester got wrong (grain of salt paid off)
- **#1 "DOCX corruption"** — overstated as confirmed corruption. Real state = *needs-repro*: our own readback
  (`reconstruct_redline`) emits `[+..+]`/`[-..-]`, never `<ins>`, so the tester's `<ins>` came from an
  external Word/pandoc render of a **genuine** `w:ins` — which means IF reproduced it's real, but it can't be
  confirmed without the pinned `adeu==1.12.1` (box has a stray 0.7.0) + a numbered-heading doc. Plausible code
  cause: `redline_service.py:298` trusts a full-text **character** offset as a **run** index (`_resolved_start_idx
  = _match_start_index`), which can drift on auto-numbered/field-bearing headings. Same class as the #524 adeu bump.
- **#2 preview≠apply** — no code divergence; preview reconstructs the *same* applied bytes.
- **#10 "no provenance"** — false: `MatterParticipant` already has `trust` (inferred/confirmed) + `source_citation`.
  The real defect is downstream: `classify_author` ignores `trust`, so an *inferred* side='ours' participant's
  tracked changes are incorporated as authoritatively as a human-confirmed one.
- **#8 truncation** — no owned code truncates interior characters; signature is LLM transcription.

## Proposed slice ladder (all under the ADR-F005 gate)

**Tier 1 — cheap confirmed code fixes (do first):**
- **VM2-A · redline attribution + error clarity** [S]: (a) #3 make the Adeu comment author configurable —
  thread it from area/House Brief config (default neutral, e.g. the org/area display name), retire the
  hardcoded `"LQ.AI Commercial counsel"`; (b) #5 branch the D1 target-resolution message on `occ`
  (0→not-found / >1→not-unique / ==1→`target_crosses_clause_boundary`), fix "sentence"→"clause/line".
- **VM2-B · matter-memory coaching area-agnostic** [S] ⭐ (maintainer's "no memory" observation): add an
  unconditional `MATTER_MEMORY_DOCTRINE` beside the roster doctrine (`composition.py:568`) so every
  matter-bound run is coached to `update_matter_memory` / `record_matter_fact` regardless of area or empty
  wiki; also bind the `matter-memory` skill in the B-7a profile manifests so custom areas inherit the full
  craft skill. (G13-class gap. Write path + grants are already correct — do NOT touch them.)
- **VM2-C · PDF type-awareness** [S]: #4A add `File.mime_type` to the agent document inventory
  (`tools.py:814`) + render a per-file type label so the model sees "PDF (not redlinable)" *before* acting;
  make the reject line machine-actionable (`unsupported_file_type: pdf …`) while staying a fix-and-retry string.

**Tier 2 — medium confirmed fix:**
- **VM2-D · participant provenance + trust-aware attribution** [S+M]: (1) make `classify_author`/`_classify_edits`
  trust-aware — an *inferred* 'ours'/'counterparty' row routes to a "confirm before adopting" bucket, not
  silent incorporation (S, no migration); (2) add a structured `source_kind` enum ('email_header' | … ) column
  + cockpit badge marking email-derived rows untrusted (M, migration).

**Tier 3 — repro-gated, pair with the adeu bump:**
- **VM2-E · redline fidelity repro** [M]: fold into #524 (adeu 1.12.1→1.19.1). Install the **pinned** adeu,
  build a numbered-heading (`numPr=True`) + field-run fixture, run 3–4 narrow edits, unzip and assert **no**
  heading run lands in `w:ins`. If it does → fix the offset-index bypass (`redline_service.py:290-301`; validate
  each sub-edit offset against the run map, or drop `_resolved_start_idx` and let adeu re-resolve). Add a
  numbered-heading golden-corpus case (current corpus is `numPr=False` only). Covers #1 and #2.

**Tier 4 — cheap prompt/doctrine fixes:**
- **VM2-F · prompt hygiene** [S]: #9 reword the area doctrine so the section defers to a controlling skill
  (one owner for "Items requiring human judgment"); #6 widen `_preview_redline` to ±1 neighbouring paragraph
  so adjacent contradictions reach the model's self-review + nudge the agent to OFFER `adversarial_review`
  (its `inconsistency` pass already exists) after obligation-touching redlines.

**Decisions needed before building (no code yet):**
- **#11 branding accent** — maintainer reports **NOTHING recoloured** (not just muted). The static code
  pipeline is intact end-to-end, so a total no-effect is NOT explained by design. **Prime suspect: the branding
  PUT save was broken until #276 (CORS/PUT "Failed to fetch") — the palette likely never persisted, so nothing
  was applied.** ACTION: re-test accent after pulling `2e6e62f4`+ (#276). If accent then hits its designed
  surfaces (focus rings / links / running-state / stepper / first chart series) it was the save bug — done. If
  it STILL recolours nothing, re-open as a genuine browser-side apply bug (suspects: theme-class placement, a
  Tailwind cascade regression, or empty singleton row). SEPARATELY (design, only if wanted): the accent is
  deliberately scarce — it does NOT recolour primary buttons/header (ink #111 by ADR-F068/F013); broadening it
  is an ADR reversal + WCAG re-check. Not priority (maintainer).
- **#7 grid row-model** — **RESOLVED / WON'T-DO (maintainer 2026-07-14): one-row-per-document is correct.**
  The document-row axis stays as designed; no work.
- **#4B PDF→DOCX convert-then-ask** [L] — no conversion path exists; needs a headless converter (SBOM +
  PyMuPDF AGPL boundary) + lossy-DOCX-as-new-file provenance + a HITL confirm card (ADR-F071). Own ADR'd slice.

## Non-goals / out of scope
- #8 (grid paste truncation) — model transcription, not code; only a verbatim grid→DOCX exporter would prevent
  it [M], not warranted now.
- Any prompt/doctrine *calibration* the tester explicitly excluded, beyond the two cheap authoring edits above.
