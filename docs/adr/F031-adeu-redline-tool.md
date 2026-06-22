# F031 — Adeu surgical-redline tool: pinned MIT dep, measurable gate, egress-safe

- Status: accepted (2026-06-22, with slice C4)
- Date: 2026-06-22
- Relates: ADR-F018 (code-validated agent writes — the pattern this reuses), ADR-F010 (gateway-only egress —
  why the bundled MCP server is forbidden), ADR-F035 (Commercial records are matter-scoped), ADR-F028
  (Commercial method doctrine — §5.1 surgical strategy this enforces), ADR-F029 (the OOXML hardening reused
  on the input), C-R0 `adeu-pinning.md` + `commercial-lawyer-method.md` §6
- Milestone: COMMERCIAL — slice C4

## Context

The Commercial agent's work product is a **surgical, client-protective redline** as a native tracked-changes
`.docx` (ADR-F028 thesis). Two facts from C-R0 shape the design: (1) **python-docx cannot author tracked
changes and models choke on raw OOXML `w:ins`/`w:del`** — so a redline library that abstracts the XML is
required; (2) **Adeu** (`adeu==1.12.1`, MIT, maintainer-confirmed) does exactly this via a small SDK
(`RedlineEngine` / `ModifyText` / `process_batch`), makes **zero network calls**, and — verified by reading
`word/document.xml` — emits genuinely **surgical sub-sentence** tracked changes. Adeu also ships a FastMCP
**server** (`adeu.server` / `adeu.mcp_components`), which is a second network egress we must not touch.

Adeu "faithfully applies whatever it is sent" — so quality control is **ours**. The redline must be surgical
(change the few words that need changing, never restate a clause to alter part of it) and *balanced* (weave in
protection — carve-outs, deemed-direct, super-cap — rather than rip-and-replace; §5.1). That cannot be left to
the prompt; it must be a measurable code gate on each proposed edit, plus the human owning the accept.

## Considered Options

**1. Integration path** — A. **SDK in-process (chosen).** Import the Adeu SDK and call it inside a guarded
tool, so our validator sits *between* the model's proposal and the applied edit for free. B. Adeu's bundled
MCP server (rejected) — a second egress (violates ADR-F010) and still needs our validator interposed; routing
a local, zero-network call through a client+server+transport buys nothing. C. python-docx/lxml fallback
(rejected, decision G) — cannot author tracked changes.

**2. DI shape** — A. **Provider-callable default (chosen):** `redline_service_provider: Callable[[],
RedlineService] = build_redline_service` on `compose_and_execute_run`, mirroring `model_builder` /
`checkpointer_provider`. The engine is per-document (it takes the `.docx` `BytesIO`) and the wrapper is
stateless, so there is nothing to keep as a startup singleton; tests swap a fake through the same seam.
B. A singleton constructed in the API lifespan + arq `on_startup` (rejected) — needless plumbing for a
stateless adapter (Python caches the lazy `import adeu`), and `compose_and_execute_run` runs in the arq
worker where `app.state` isn't reachable anyway.

**3. The "surgical" metric** — A. **Strike-based ratio (chosen):** measure tokens *struck from the existing
text* (`deleted_tokens / clause_tokens`), governed insertions by the rationale requirement + the quality
judge. B. The literal C-R0 metric `changed = inserted + deleted` (refined): it wrongly **blocks additive
carve-outs** — adding a long protective carve-out has a large `changed` but strikes ~nothing, and adding
protection is the §5.1 doctrinal move. So C4 keys D1/D5 on struck text; "surgical" = *don't over-strike
existing language*, and large protective *additions* are surgical by construction (still substantive → still
need a rationale → still judged for substance).

## Decision Outcome

Wrap Adeu behind a guarded `apply_redline` tool (granted only to Commercial matters; matter-scoped, ADR-F035).
The loop is ADR-F018's: the model PROPOSES narrow `{target_text, new_text, rationale}` edits; **code
disposes** against the measurable surgical gate; Adeu renders the survivors; the **human owns** the accept
(the redline is saved as a downloadable matter document with tracked changes the supervisor accepts/rejects in
Word). Mechanics:

- **Import boundary (enforced by an AST test):** only `adeu.RedlineEngine` / `adeu.ModifyText` /
  `adeu.diff.generate_edits_from_text`; **never** `adeu.server` / `adeu.mcp_components`.
- **Raw `ModifyText` per edit — decompose REJECTED (empirical, C4 build):** the C-R0 §6.1 plan preferred
  routing each edit through `generate_edits_from_text` for finer regions. We built it and rejected it:
  decomposition emits **micro-anchors** (a region with `target_text="3"`) that Adeu **fuzzy-matches to the
  wrong span** — observed live: `"3"` landed on the `d` in "Vendor" → `Ven12or`, silent corruption — and it
  **bypasses the D4 unique-anchor gate** (the gate validated the agent's anchor, not the micro-regions). So
  the tool sends the agent's edit as ONE `ModifyText`; the anchor is the full, gate-validated unique
  `target_text`, and Adeu's prefix/suffix trim still renders it surgically (`"three (3) months" → "twelve
  (12) months"` marks only `[-three (3)-][+twelve (12)+]`, the rest bare). Surgical *rendering* is preserved;
  correctness wins over the marginal extra granularity decompose offered.
- **Gate (D1–D6, `app/schemas/commercial.py`, all model-free):** D1 tiered *strike* size; D2 substantive edit
  needs a rationale; D3 a bare substantive deletion must supply replacement language; D4 unique anchor (exactly
  one match — the silent-corruption guard); D5 whole-batch strike ceiling; D6 mandatory `dry_run` self-review
  before any write (any edit Adeu cannot place blocks the whole write — never a partial redline). All
  thresholds are **calibration starting values**, named at module level, calibrated against the golden corpus.
- **Quality is review, not a gate.** The gate proves a redline is well-formed/surgical/scoped; it cannot prove
  it is *good for the client*. Substantive quality is human-owned plus an adversarial redline-quality **judge**
  (review, never auto-accept) — the §5.1 rubric read against the *produced* document, separating
  mechanism-quality from model-quality. Tested via a model-free **golden-redline corpus** (render-and-read the
  `.docx`, not the word count) — the maintainer's C4 requirement.
- **Egress-safe:** Adeu makes zero provider/network calls, so the in-process call does not breach
  gateway-only egress; it still passes `guarded_dispatch` (R6/R5/R4) like every action. Audit carries
  counts/types/IDs only — never `target_text`/`new_text`/clause content.
- **Dependency install: `--no-deps` (build finding).** Adeu hard-requires `fastmcp[apps]>=3.1.1`, which pulls
  **starlette 0.48 / mcp / pydantic 2.13** and breaks our pinned FastAPI stack (`APIRouter` kwargs — 89
  collection errors). Since we never use the FastMCP server, Adeu is installed **`--no-deps`** (api/Dockerfile,
  api/Dockerfile.dev, ci.yml) and its *real* SDK deps are declared in `pyproject.toml` (`diff-match-patch`,
  `structlog`; `lxml`/`python-docx`/`rapidfuzz`/`pydantic` already in-tree). Verified: the SDK path imports +
  redlines with no fastmcp, and `adeu.server` then raises `ModuleNotFoundError` — the second egress is
  **structurally absent**, so the AST import-guard becomes belt-and-suspenders. Net: ~80 fewer SBOM packages,
  no copyleft, no FastAPI bump.
- **Output (ADR-F035):** the redlined `.docx` is stored via `storage.upload_bytes` as a new matter `File`
  (`ingestion_status='ready'`, no `Document` — work product, not a search source), served by the existing
  owner-gated `GET /files/{id}/content`. No new endpoint; C7 adds the UI button.

## Consequences

- **C4** ships `apply_redline` + `RedlineService` + the gate + the golden corpus + ADR-F031/F035; no migration
  (output is a `File` row). `adeu==1.12.1` is pinned exact (the surface moves across minors); its transitive
  tree is all permissive (`diff-match-patch` Apache-2.0; `fastmcp[apps]` ~80 pkgs MIT/Apache/BSD,
  runtime-isolated behind the unused server modules; `lxml` BSD-3) — **no new copyleft** (rule B). NOTICES.md
  records the posture.
- The strike-based metric is a deliberate **refinement** of the C-R0 §6.1 metric; the C-R0 thresholds remain
  the calibration starting values. Threshold calibration against the golden corpus is a maintainer decision
  recorded before merge.
- **C5** builds on this: counterparty-position extraction feeds escalation-gated counter-redlines through the
  same tool; the redline-quality judge becomes the round's accept/reject/counter reviewer. The held multi-turn
  redlining project reuses `apply_redline` + the judge.
- Bumping Adeu stays trivial (one pin) but must re-verify the SDK surface (the `adeu-pinning.md` §8 check) —
  the import-guard + round-trip tests catch a breaking bump.
