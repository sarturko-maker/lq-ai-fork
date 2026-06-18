# PRIV-4a — Article 30 RoPA export

**Status:** DRAFT for maintainer edit. **Date:** 2026-06-18. **Milestone:** Oscar Edition / Agentic Modules
(Privacy/ROPA). **Branch:** `priv-4a-article-30-export` (off `main` @ 1931acd, PRIV-3 merged).
Governing: ADR-F018 (agentic modules), ADR-F019 (relational, deployment-global ROPA). Feeds the PRIV roadmap
(`PRIV-onetrust-to-lqai-functionality-map.md` § B — "Article 30 one-click report"). Memory:
[[oscar-privacy-modules-vision]].

## Goal

OneTrust/TrustArc ship a "one-click RoPA report." PRIV-3 made the register **relational + browsable**; PRIV-4a
makes it **extractable** — a structured Article 30 export over the deployment-global register (every processing
activity with its lawful basis / retention / special-category, joined across the M:N to its linked systems).
A **read-and-render slice**: no new domain entity, no migration. Agent maintains the register; the user
exports + owns the deliverable.

## Non-goals (this slice)

- **No new ROPA entities.** Vendors/processors, transfers (+ the outside-UK/EEA⇒mechanism invariant),
  data-subject/data-element taxonomy, recipients → **PRIV-5**. (See "Honest Article 30 scope" below — the
  export renders what the model is, and is honest about the GDPR Art 30(1) fields not yet captured.)
- **No edit/CRUD** on the register (PRIV-6+).
- **No heavyweight document deps** (DOCX/PDF rendering) unless the maintainer chooses that format — see Decision.
- **No scheduled/attestation export** (recertification is PRIV-7+).

## Decision the maintainer should make — export format(s)

GDPR Article 30 has two real audiences: a **machine/queryable** form (the agent, downstream queries, re-import)
and a **regulator/lawyer-facing** document (what you hand the ICO or keep on file). Options:

| Option | Deps | Audience | Notes |
|---|---|---|---|
| **JSON** | none | machine / agent / queries | cheap; mirrors the `*Read` DTOs; the natural query+re-import substrate |
| **CSV** | none (stdlib `csv`) | spreadsheet / Excel | the everyday OneTrust "export to Excel" expectation; flat — one row per activity, systems joined into a cell |
| **XLSX** | `openpyxl` (new SBOM entry) | spreadsheet, multi-sheet | OneTrust's actual shape (Activities sheet + Systems sheet); a real dependency to justify |
| **DOCX / PDF** | `python-docx` / a PDF lib (new dep) | regulator-facing doc | the lawyer deliverable; heaviest; best deferred until the content set is fuller (post-PRIV-5) |

**Recommendation:** ship **JSON + CSV** in PRIV-4a (both **dependency-free**, cover machine + spreadsheet, and
are honest about partial content). Defer **XLSX/DOCX/PDF** to a follow-up once PRIV-5 fills the Art-30 field set
(a richer doc over a half-populated register would look more complete than it is).

**DECIDED (maintainer, 2026-06-18): JSON + CSV + XLSX.** XLSX = OneTrust's actual shape (multi-sheet:
Activities + Systems). **Update: `openpyxl` is ALREADY a dependency** (`api/pyproject.toml:166` — Tabular
Review's XLSX export uses it), so XLSX adds **no new SBOM entry** and needs **no image rebuild** — cheaper
than the decision assumed. DOCX/PDF still deferred to post-PRIV-5.

## Honest Article 30(1) scope (important — don't over-claim)

GDPR Art 30(1) content vs. what the current domain captures:

| Art 30(1) field | In the model today? | Source |
|---|---|---|
| Controller name + contact | partial — `controller_role` per activity; no org contact entity | activity / org profile |
| Purposes of processing | ✅ `ProcessingActivity.purpose` | activity |
| Categories of data subjects | ❌ not yet | PRIV-5 |
| Categories of personal data | partial — `special_category` flag only | PRIV-5 |
| Categories of recipients | ❌ (vendors/processors) | PRIV-5 |
| Third-country transfers + safeguards | ❌ | PRIV-5 |
| Retention / erasure time limits | ✅ `retention` (activity + system) | model |
| Security measures (TOMs) | ✅ `System.security_measures` | system |
| Lawful basis (not strictly Art 30 but core) | ✅ `lawful_basis` / `art9_condition` | activity |

The export **renders what exists** and **labels the not-yet-captured fields** (e.g. a header note or a
"— not yet recorded (PRIV-5)" cell) so the deliverable is honest, not falsely complete. This honesty is itself
the point — code disposes, the user owns, nothing is invented.

## Files (target)

- **`api/app/api/ropa.py`** — add `GET /ropa/export` (auth `_active`, the same shared-read posture as the read
  endpoints per ADR-F019; `?format=json|csv`, default `json`). JSON → the joined register as a typed payload;
  CSV → a `StreamingResponse` with `Content-Disposition: attachment; filename="article-30-ropa-<date>.csv"`.
  `selectinload` the M:N so there's no N+1. (Date in the filename comes from the request/server, not a model
  field.)
- **`api/app/schemas/ropa.py`** — a small `Article30Export` DTO (or reuse `ProcessingActivityRead` + a top-level
  envelope) carrying activities-with-systems + a `generated_at` + a `coverage`/`fields_not_yet_recorded` note.
  Pure read DTO, `from_attributes=True`.
- **`api/app/services/` (or a `ropa_export.py` helper)** — the pure flatten/serialize functions (activity →
  Art-30 row; systems joined). Pure + unit-testable, no DB/HTTP in the formatter.
- **`web/src/lib/lq-ai/api/ropa.ts`** — an `exportRopa(format)` client (fetch → blob → download), bearer auth.
- **`web/src/lib/lq-ai/components/ropa/RopaRegister.svelte`** — a calm "Export Article 30" control (F013 style;
  a small menu if two formats) that triggers the download. Honest empty state (export disabled / noted when the
  register is empty).
- **Tests:**
  - `api/tests/test_ropa_read.py` (or a new `test_ropa_export.py`) — JSON shape (activities + joined systems +
    coverage note); CSV headers + one row per activity + systems-in-cell; **401 without bearer**; empty-register
    case; an unknown `format` → 422 (Pydantic/enum at the boundary, reject-don't-sanitize).
  - pure-formatter unit tests (Art-30 row mapping; the "not yet recorded" labelling).
  - **GLOBAL contract tests (the PRIV-3 lesson):** register `GET /ropa/export` in
    `tests/test_endpoints.py` `IMPLEMENTED_ROUTES` (no new path param) and in `tests/test_openapi.py`
    `EXPECTED_PATHS` (+ bump the route count 133→134). **Run the FULL `pytest -q`, not just the slice's files.**
  - `web` — a `format.ts`/client unit test for the download wiring if it has pure logic; otherwise a vitest
    over any new pure helper.

## Build order

1. Pure formatter (`activity+systems → Art-30 JSON row` / `→ CSV row`) + unit tests — TDD the honest field set.
2. `GET /ropa/export` endpoint + DTO; api tests incl. auth + empty + bad-format; **register both global contract
   tests**; run the FULL api suite.
3. Web client `exportRopa()` + the register Export control; vitest; web check.
4. Live-verify on localhost (download JSON + CSV from the seeded demo matter; open the CSV in a spreadsheet;
   screenshot the control + a sample export). Evidence → `docs/fork/evidence/priv-4a/`.
5. Security + simplification pass (no secrets; the export is the shared register so no per-user leak; CSV
   injection — prefix-guard formula-trigger chars `= + - @` in cell values per OWASP, since a malicious
   model-proposed string could otherwise execute in Excel; bounded streaming).

## Verification (ADR-F005 gate)

`docker run … pytest -q` (FULL suite, counts quoted) + ruff/mypy from the **repo root** (line-length 100);
`web && npm run check` + vitest; live download evidence; fresh-context adversarial+security+simplification
review (CSV-injection guard is a named check); HANDOFF updated. Squash-merge against
`sarturko-maker/lq-ai-fork`. **Compact after.**

## Security notes (fold into the slice, not an afterthought)

- **Shared-read, authenticated.** `_active` only; no per-user scoping (ADR-F019). 404/empty, never an existence
  leak about private matters (the export carries no `source_project_id`).
- **CSV injection.** Any cell beginning `= + - @ \t \r` gets a `'` prefix (or is quoted) so a spreadsheet won't
  execute it — the register holds model-proposed strings, treat them as untrusted on the way out too.
- **No secrets**, no raw audit values in the export; provider keys remain gateway-only.
- **Bounded.** Stream CSV; cap or paginate if the register is very large (the read API already caps the agent's
  list dump at 100 — the export is the place a full register legitimately flows, so stream rather than buffer).
