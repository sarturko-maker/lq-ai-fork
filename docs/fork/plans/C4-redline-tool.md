# C4 — Adeu surgical-redline validated-write tool (`apply_redline`)

**Status:** DRAFT for maintainer review/edit (CLAUDE.md: explore → written plan → human edits → implement).
Built on a 2-workflow code map (C3 + C4 seams, 8 Explore agents) + a live re-verification of the
`adeu==1.12.1` SDK surface. **Date:** 2026-06-22. **Branch:** `fork/comm-c4-redline`.

> **Reprioritised ahead of C3** (maintainer call, 2026-06-22): C3 and C4 are independent siblings off C0;
> C4 retires the milestone's central technical risk (DeepSeek+Adeu → lawyer-grade surgical `.docx`),
> produces the system's actual work product, and unblocks hands-on operation. C3 (deal-context memory)
> follows; both feed C5 (negotiation rounds).

## North star (the slice's share of it)

A practice-area agent is **a supervised, area-qualified legal counsel**. C4 delivers the *work product*:
**surgical, client-protective redlines as native tracked-changes `.docx`**, behind a guarded validated-write
with a **measurable surgical gate**, where the **human owns** the accept and the audit is counts/types/IDs.
The redline is *balanced, not rip-and-replace* (§5.1): carve-outs over caps, deem-direct requalification,
exclude third-party indemnity — **one narrow edit per discrete change, never a sentence rewrite**.

## Goal

Wrap Adeu behind a guarded `apply_redline` tool granted only to **Commercial** matters
(`area_key == "commercial"`, matter-scoped by `binding.project_id`). The model proposes a batch of narrow
`ModifyText(target_text, new_text, rationale)` edits against a matter `.docx`; **code validates surgical
bias** (the C-R0 D1–D6 gate); the tool **decomposes** each edit into minimal regions
(`adeu.diff.generate_edits_from_text`), runs a **mandatory `dry_run` preview**, applies as **native tracked
changes**, and stores the redlined `.docx` as a downloadable matter `File`. Audit records
counts/types/IDs/classification (accepts/rejects/counters, clause types, escalations) — **never raw
target/new text**.

## Non-goals

- No counterparty-markup extraction or accept/reject/counter *of their* changes (C5).
- No multi-round negotiation state machine (C5; full multi-turn is the held follow-on).
- No in-UI download button / redline viewer (C7 — C4 stores + the existing `GET /files/{id}/content`
  serves it; I hand over the `.docx` from evidence in the meantime).
- No live-Word/COM path (Linux disk `.docx` only). No `python-docx`/`lxml` fallback (decision G — Adeu is
  the sole path). No `langchain-adeu` toolkit (WIP). No deal-context memory (C3).
- No final threshold *calibration* sign-off — the gate ships with C-R0 starting values; calibration against
  the golden corpus is a maintainer decision **before merge** (§Testing).

## Key decisions (and divergences from the COMM C4 sketch — for maintainer steer)

1. **DI = provider-callable, not a startup singleton.** The COMM sketch said "wire the engine in arq
   `on_startup` + API lifespan." But `RedlineEngine` is constructed **per-document** (takes a `BytesIO`) and
   our wrapper is **stateless** (lazy-imports adeu, zero network, no heavy init — Python caches the import).
   So a singleton buys nothing. Instead add `redline_service_provider: Callable[[], RedlineService] =
   build_redline_service` to `compose_and_execute_run`, mirroring the existing `model_builder` /
   `checkpointer_provider` / `skill_registry_provider` seams — the codebase's idiomatic DI, and exactly how
   tests inject a fake. "Injected via DI, no import-time instantiate" intent is met; the startup plumbing is
   dropped as needless. *(Recorded in ADR-F031.)*
2. **Output = a new matter `File` (ready, no `Document`), not work-product-attribution.** Store the redlined
   bytes via `storage.upload_bytes` under a fresh UUID key → `File(owner_id, project_id=matter,
   mime=OOXML_DOCX, ingestion_status='ready', filename="<orig> (redlined).docx")`. **No `Document`** (it's
   work product, not a search source — no parser/chunks/embeddings). The existing owner-gated streaming
   `GET /files/{id}/content` serves it (404 cross-user) — **no new endpoint**. `work_product_attribution`
   is the wrong table (one-inference-per-message; breaks under batches/rounds — CLAUDE.md blocker #6); audit
   via `audit_action`.
3. **Surgical gate = D1–D6 from C-R0 §6.2** (verbatim), thresholds as **calibration starting values**.
   **Decompose (§6.1's preferred route) was BUILT then REJECTED** in the slice: `generate_edits_from_text`
   produces micro-anchors (`target_text="3"`) that Adeu fuzzy-matches to the wrong span (live corruption
   `Ven12or`) and bypasses the D4 anchor gate. The tool sends the agent's edit as **one raw `ModifyText`** —
   the anchor is the full gate-validated unique `target_text`, and Adeu's prefix/suffix trim still renders it
   surgically. Surgical *rendering* preserved; correctness over micro-granularity.
4. **The gate is structural; quality is review (the maintainer's emphasis).** The gate proves an edit is
   narrow/well-formed/scoped/unique-anchored; it **cannot** prove the redline is *good for the client*. So
   C4 ships a **substantive redline-quality evaluation** (the 4-layer design below), not just the metric.

## Architecture

### Apply path (model-free core — `RedlineService`)
1. Fetch the original `.docx` bytes: matter-scoped `File` query (`owner_id == binding.user_id` AND
   (`project_files` join OR `File.project_id == binding.project_id`) AND `deleted_at IS NULL` → 404
   cross-user), `stream_download(file.storage_path)` buffered. Validate `mime == OOXML_DOCX_MIME` **and**
   `ooxml_subtype(bytes) == 'docx'` **and** `guard_ooxml(bytes)` (XXE/zip-bomb) — fail closed.
2. `RedlineEngine(BytesIO(bytes), author="LQ.AI Commercial counsel")`.
3. For each proposed edit, `generate_edits_from_text(target, new)` → minimal `ModifyText` regions
   (surgical rendering; turns a sentence-rewrite into per-change edits).
4. **D6 precondition:** `process_batch(changes, dry_run=True)` → preview dict (`edits_applied/edits_skipped`).
   D4 anchor check rides this (skipped == anchor not unique/found → BLOCK).
5. Gate validates D1–D5 on the proposed edits + the dry-run result (reject-don't-sanitize; verbatim error
   to the model).
6. `process_batch(changes, dry_run=False)` → `save_to_stream()` → redlined bytes → persist as a `File`.
7. **Import boundary:** only `from adeu import RedlineEngine, ModifyText`; `from adeu.diff import
   generate_edits_from_text`. **Never** `adeu.server` / `adeu.mcp_components` (second egress) — enforced by
   an AST import-guard test (mirror C1's fitz guard).

### Surgical gate (`api/app/schemas/commercial.py`, mirrors ROPA `*Input`)
`ConfigDict(extra='forbid', str_strip_whitespace=True)` + `field_validator`/`model_validator(mode='after')`.
D1 tiered size (`SURGICAL_MAX=0.15`, `ABS_FLOOR=3`, `REWRITE_MAX=0.50`, `changed_tokens` from the minimal
diff-match-patch diff, `clause_tokens` = smallest enclosing clause/sentence; **fail-closed** if unresolvable);
D2 substantive-edit rationale (`MINOR_FLOOR=0.05`, `RATIONALE_MIN_WORDS=15`, substantive-token set); D3 bare
substantive deletion needs replacement; D4 unique-anchor (exactly one match else BLOCK — silent-corruption
guard); D5 whole-batch ceiling (`DOC_CEILING=0.25`); D6 mandatory dry-run before write. All constants are
named module-level so calibration is a one-line edit.

### DI + grant seam
`COMMERCIAL_AREA_KEY = "commercial"` (mirror `PRIVACY_AREA_KEY`). `build_commercial_tools(session_factory, *,
run_id, binding, redline_service) -> list[Callable]` mirrors `build_ropa_tools`; constructs `GuardContext`
with `granted=COMMERCIAL_TOOL_NAMES = frozenset({"apply_redline"})`. Composition adds the parallel branch:
`if binding is not None and area_key == COMMERCIAL_AREA_KEY: tools += build_commercial_tools(...)` — the
first Commercial domain-tool branch (the HANDOFF gotcha guessed C4; this is it).

## Testing design — judge the PRODUCED `.docx`, not the word count (maintainer's core requirement)

The surgical gate is *structural*; "is the redline good?" is *substantive*. Four layers, separating
**mechanism-quality** (does the system render a good redline from good edits — model-free) from
**model-quality** (did the model pick good edits):

- **Layer 1 — Golden-redline fixture corpus (model-free spine).** Committed clauses (vendor-favoured LoL;
  broad indemnity; one-sided IP/data) each with: original text, a **hand-authored known-good surgical
  redline** (the §5.1 edits a senior lawyer makes), the expected rendered result, and a **technique rubric**
  (super-cap carve-outs, deem-direct, 3rd-party-indemnity exclusion, mutualisation). Authoring these *is* the
  calibration corpus for the gate thresholds.
- **Layer 2 — Render-and-read (deterministic, CI-gating).** Feed Layer-1 golden edits through the real
  pipeline → reopen `word/document.xml` → reconstruct a readable `[-del-][+ins+]` per-paragraph view (the
  c4-prep technique, promoted to a first-class util) → assert: head/tail/**interior** stay bare (decompose
  worked); each change is its own narrow region; and **accept-to-clean text contains the expected balanced
  language and no longer contains the superseded one-sided language**. Golden edits ⇒ measures the **system**.
- **Layer 3 — Redline-quality judge (substantive review; live + evidence; NOT a gate).** A gateway-routed
  adversarial "redline critic" reads {original in full context, the *rendered* redline, client posture,
  playbook position} and scores the §5.1 rubric holistically (surgical? rebalance vs rip-replace? right
  techniques? coherent across the whole agreement? over/under-protective?), refute-by-default, multiple
  judges → structured verdict + rationale. **Human still owns the accept.** It is the concrete form of the
  `dry_run` self-review preview *and* the C5/O-track verifier; on live runs it **attributes each weakness to
  model-choice vs system-rendering**.
- **Layer 4 — Human artifact.** Every scenario (golden + live) emits to `docs/fork/evidence/c4/`: the
  `.docx`, the readable reconstructed redline, the accept-to-clean clause, and the judge scorecard — so the
  maintainer reads the actual redline first.

**Merge-gate split:** Layers 1–2 = model-free CI (gating). Layers 3–4 = live verification / evidence
(ADR-F005). First live scenario = the **vendor-favoured SaaS MSA** (re-run the prior live scenario too).

## Files

- `api/pyproject.toml` (+`adeu==1.12.1`, SBOM note, mypy override), `NOTICES.md` (Adeu MIT + transitive tree).
- `api/app/agents/redline_service.py` (NEW — the stateless Adeu adapter + `build_redline_service`).
- `api/app/schemas/commercial.py` (NEW — `ApplyRedlineInput` + per-edit schema + the D1–D6 validators + the
  minimal-diff/clause-token helpers).
- `api/app/agents/commercial_tools.py` (NEW — `COMMERCIAL_AREA_KEY`, `COMMERCIAL_TOOL_NAMES`,
  `build_commercial_tools`, the guarded `apply_redline`, the matter-`File` fetch + output persist).
- `api/app/agents/composition.py` (+the Commercial grant branch + `redline_service_provider` seam).
- `api/app/agents/redline_render.py` (NEW — the `word/document.xml` → readable redline reconstruction util,
  shared by tests + the judge + evidence).
- Tests: `api/tests/agents/test_redline_gate.py` (D1–D6), `test_redline_service.py` (apply/decompose/
  round-trip + import-guard), `test_commercial_tools.py` (guarded dispatch + matter-scope 404 + output File),
  `api/tests/fixtures/redline_corpus/` (Layer-1 golden), `test_redline_corpus.py` (Layer-2).
- Evidence: `docs/fork/evidence/c4/` (the live harness + scorecards + `.docx`).
- ADRs: `docs/adr/F031-adeu-redline-tool.md` (NEW), `docs/adr/F035-commercial-matter-scoped-records.md` (NEW).

## ADRs

- **F031** — Adeu redline tool: pinned MIT dep via SDK (never the MCP server), the **measurable** D1–D6
  surgical gate, decompose-before-apply, provider-callable DI, output as matter `File`, gateway-egress-safe
  (Adeu makes zero provider calls). Cites F018, F010, F035.
- **F035** — Commercial domain records are **matter-scoped** (filter by `binding.project_id`) — the
  *opposite* of ROPA's deployment-global rule (F019). A security boundary (cross-deal leakage). The C4 output
  `File` + fetch are the first records under it.

## Verification

- **CI (model-free, gating):** D1–D6 unit tests with teeth (phrase-where-a-word-suffices → REJECT; justified
  full rewrite → ACCEPT; ambiguous anchor → REJECT; bare substantive delete → REJECT; missing rationale →
  REJECT); decompose splits a two-change sentence into two narrow edits (Layer-2 XML assertion); round-trip
  reopens the redlined `.docx` → `w:ins`/`w:del` carry author+date, `accept_all_revisions` yields the
  expected clean text; matter-scope 404 cross-user; `guarded_dispatch` with the Commercial grant; AST guard:
  no `adeu.server`/`adeu.mcp_components` import; audit carries no clause text. Golden corpus (Layer-1/2)
  green. Full suite counts quoted.
- **Live (DeepSeek):** re-run the prior scenario + the new vendor-favoured SaaS MSA → DeepSeek-authored
  surgical tracked-changes `.docx` (narrow edits only) → Layer-3 judge scorecard → Layer-4 evidence. Hand the
  `.docx` files to the maintainer to review.

## Slice steps (ordered to front-load a reviewable `.docx`)

1. Pin adeu + NOTICES/SBOM + import-guard test.
2. `redline_service.py` adapter (decompose → dry_run → gate → apply → save) + `redline_render.py`.
3. `schemas/commercial.py` D1–D6 gate.
4. **Layer-1 golden corpus + Layer-2 tests** → first **model-free golden `.docx`** to review (system quality,
   discounting model). 
5. `commercial_tools.py` guarded `apply_redline` + matter-File fetch/persist + composition grant + DI seam.
6. SaaS MSA scenario (contract `.docx` + deal email) → **live DeepSeek run** (+ re-run) → `.docx` + Layer-3
   judge + Layer-4 evidence to review.
7. CI tests green + counts + ADR-F031/F035 + adversarial review (security/simplification) + HANDOFF →
   squash-merge per ADR-F005.

## Open decisions for the maintainer

1. **Gate threshold calibration.** Ship C-R0 starting values, calibrate against the Layer-1 golden corpus
   before merge — do you want to set/approve `SURGICAL_MAX`/`REWRITE_MAX`/`DOC_CEILING` after seeing the
   corpus, or trust the starting values for v1?
2. **Judge model.** Layer-3 critic on DeepSeek (the qualified provider) — or a stronger model for *judging*
   only (judging ≠ acting; a stronger critic is defensible since it's review, not the work product)?
3. **Scenario clause set.** Confirmed: vendor-favoured SaaS MSA. Golden corpus also includes broad-indemnity
   + one-sided IP/data — add/trim?
