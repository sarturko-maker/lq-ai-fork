# PRIV-6a — adversarial multi-agent audit (ultracode)

Workflow `priv-module-adversarial-audit` (54 agents, 7 review lenses × the whole ROPA/Privacy module
PRIV-1..6a → per-finding refute-by-default skeptics → synthesis). Run `wf_e0212c0f-532`, branch
`priv-6a-personal-data-taxonomy` @ 817621b. **23 candidates → 20 survived verification → 13 deduped
confirmed.** Initial verdict: **BLOCK** (2 high-severity defects in the find-or-create path). All highs +
the cheap correctness/transparency/test findings were fixed in-slice (commit after 817621b); the remaining
items are flagged to the maintainer or recorded as accepted-low.

## Fixed in-slice

| # | Sev | Finding | Fix |
|---|-----|---------|-----|
| 1 | high | `_add_categories` did unguarded SELECT-then-INSERT against `UNIQUE(name)`: a concurrent/retried create raised `IntegrityError` that the guard **re-raised** (violating ADR-F018 "rejection returned, not raised"), discarded already-linked sibling names, AND leaked the failing SQL + bound params (raw name + `source_project_id`) into `AgentRun.error` + the SSE error frame. | New `_find_or_create_category`: per-name create in a **SAVEPOINT** (`begin_nested`); on `IntegrityError` absorb + re-select the winner. Never raises out of the dispatch, never loses siblings, never leaks. |
| 2 | high | Vocabulary was case-/whitespace-sensitive — "Health data"/"Health Data"/"health data" fragmented into distinct rows, defeating the "reused, not duplicated" guarantee + splitting regulator-facing counts. | Collapse-internal-whitespace `field_validator` on both `*Input`; case-insensitive find (`func.lower`); **functional UNIQUE index on `lower(name)`** (migration 0062 + model) as the DB backstop. First-seen casing is the display form. |
| 4 | low | `ROPA_TOOL_NAMES` (R6 grant set) vs the built closure list could drift; the cover test compared against a 3rd hand-typed literal. | Test now also asserts `{t.__name__ for t in build_ropa_tools(...)} == ROPA_TOOL_NAMES`. |
| 5 | low | `export_article_30` docstring still said the taxonomy "arrives with PRIV-6" (stale; it shipped). | Docstring updated — full Article 30(1) captured, coverage note empty, mechanism retained. |
| 7 | low | The category fetch query was hand-copied 4× (2 endpoints + 2 export fetches). | Extracted `_all_categories(db, model)` (PEP 695 generic). |
| 8 | nit | Category list ordering differed: API `name` vs tool `created_at, name`. | API aligned to `created_at, name` (matches the agent tool + System/Vendor). |
| 9 | nit | Emptying `ART30_FIELDS_NOT_YET_RECORDED` deleted the only proof the coverage mechanism renders gaps. | Added a monkeypatch test asserting a populated gap renders in the JSON envelope. |
| 10 | nit | No test pinned the ADR-F019 shared-read posture (cross-user read + no `source_project_id` on the wire). | Added a regression test: user B reads a row provenance-stamped under user A's matter; asserts 200 + no provenance keys. |
| 11 | nit | `_data_subject_category_row` / `_data_category_row` were byte-identical single-use helpers. | Folded into one `_category_row`. |
| — | — | `UP047` (PEP 695): the original generic helpers used classic `TypeVar` and would have failed CI ruff. | Converted all 4 generic helpers to PEP 695 `def f[T: (A, B)]` (mypy 2.1 clean). |

## Flagged to the maintainer (design decision — not fixed unilaterally)

- **#3 (medium) — confused-deputy private→shared laundering.** The ROPA register is deployment-global
  shared-read (the accepted ADR-F019 design). A privileged/private matter's confidential narrative could be
  distilled by the agent into a register free-text field (purpose/description/details) and then read by any
  authenticated firm user. `project.privileged` is plumbed into the binding but gates only the inference
  tier, not ROPA writes. This is a **module-wide information-flow policy question** (predates PRIV-6a; spans
  all `propose_*` free-text), so it is recorded as a backlog decision rather than bolted onto a taxonomy
  slice. Options for the maintainer: (a) profile_md + tool-docstring guardrail ("register is firm-wide;
  generic facts only"); (b) gate writes originating from a privileged matter behind user confirmation;
  (c) document the boundary in a superseding ADR. See MILESTONES § Backlog.

## Accepted-low (recorded, not changed this slice)

- **#6** RopaRegister data-subjects/data-categories tab blocks are near-duplicate markup — a Svelte
  `{#snippet}` would dedupe ~48 lines; deferred to avoid UI churn + screenshot re-verification (no runtime
  risk; DOM unchanged).
- **#12** `DataSubjectCategorySummary`/`DataCategorySummary` (+ TS interfaces) are structurally identical —
  kept as intentional divergence headroom, mirroring the System/Vendor split.
- **Guard message scrubbing** (belt-and-braces): mapping `DBAPIError` → value-free text in `guard.py` was
  flagged as defense-in-depth. The reachable leak path is closed by fix #1; the shared chokepoint is left
  untouched this slice (broad blast radius) — recorded as a defense-in-depth backlog item.

## Coverage / limits (from the synthesis)

Reviewed in full: `agents/ropa_tools.py`, `guard.py` (90-141), `runner.py` error sink, `factory.py`,
`composition.py` grant seam, `schemas/ropa.py`, `models/ropa.py`, `api/ropa.py`, `ropa_export.py`,
migration 0062, the read UI + `api/ropa.ts`, the ropa tests. NOT executed live by the audit:
langgraph/langchain/deepagents library internals (verified by source-reading the fork seams + pinned-wheel
behavior, not run); no live concurrency reproduction (the TOCTOU race is established by code analysis — the
fix removes it regardless). The earlier merged slices' migrations (0058-0061) were confirmed only insofar as
0062 chains from 0061.
