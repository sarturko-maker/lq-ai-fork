# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
Everything serves this: *counsel* = real tools + gates + client memory + work product (not a chatbot);
*qualified* = enforced model/harness qualification (F0-S9 tier floor) **+** area competence via curated tools
and **controlling skills**; *supervised* = human-owns every material write + escalation gates + auditable
receipts. Generalises to every practice area (cf. `docs/fork/NORTH-STAR.md`). Full statement at the top of the
COMM plan.

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ DELIVERED; building continues at C2.**

The full COMM decomposition is written + adversarially reviewed:
**`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md` — read it first.** **Privacy is PARKED**
→ `docs/fork/plans/PRIV-BACKLOG.md`. A new **MCP capability** milestone is approved (own milestone, not part
of Commercial) → `docs/fork/MILESTONES.md` § MCP capability.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL, STILL ACTIVE):** `smart`/`fast`/`budget` are repointed
`minimax/MiniMax-M3 → deepseek/deepseek-v4-flash` on the local gateway (MiniMax out of quota; survives restarts
via the `gateway-config` volume). DeepSeek is the qualified live-test target (decision F). Revert when MiniMax
quota returns.

## Done this slice (C1 — document-reader registry: DOCX/PPTX/XLSX/EML; NO migration)

- **`api/app/pipeline/readers/`** (NEW pkg) — `_base.py` (`DocumentReader` protocol, `ReaderRegistry`,
  `join_units` = the single offset-truth helper mirroring `parsers._run_pymupdf`, `build_parsed_document`,
  `guard_ooxml` = DOCTYPE/ENTITY reject + zip-bomb caps, `ooxml_subtype` = deep `[Content_Types].xml` sniff);
  `pdf.py` (thin wrapper over the existing `parse_pdf` — **fitz/AGPL stays contained here**), `xlsx.py`,
  `docx.py`, `pptx.py`, `eml.py`; `__init__.py` (`build_default_registry(settings)` composition root). Heavy
  libs (openpyxl/python-docx/python-pptx) are **lazy-imported inside each reader** so the pkg imports cleanly
  without them.
- **`api/app/pipeline/ingest.py`** — the single PDF gate (`is_pdf_mime`/`parse_pdf`) is replaced by an
  **injected** `registry: ReaderRegistry | None = None` (defaults to `build_default_registry(settings)`, so
  every caller is unchanged): look up reader by declared MIME → server-side `sniff()` content cross-check
  (reject a spoof as `unsupported_type`) → `reader.read` via `to_thread`. Each reader returns the SAME
  `ParsedDocument`; **chunker / Document model / persist UNTOUCHED**, so the Citation-Engine invariant
  `normalized_content[start:end] == content` holds by construction. PDF behaviour byte-identical. Error mapping
  preserved (`ParserUnsupported`→`unsupported_content`, `ParserError`→`parse_failed`).
- **Deps:** +`python-docx`>=1.1,<2 (MIT), +`python-pptx`>=1.0,<2 (MIT) — both permissive (rule B). XLSX reuses
  the already-present openpyxl; EML uses stdlib `email` (no dep). **Dropped** the planned `filetype` +
  `defusedxml`: the dep-free per-reader `sniff` + the pre-parse DOCTYPE reject are more precise + version-proof.
  mypy overrides added; **NOTICES.md** gained a Python license-posture table (incl. the AGPL PyMuPDF boundary).
- **Security:** OOXML XXE/entity-expansion killed by rejecting `<!DOCTYPE`/`<!ENTITY` in XML-part prologs
  **before** lxml opens the file; zip-bomb size/entry caps; MIME-spoof rejected at the boundary; **CI AST
  import-guard** asserts no reader imports `fitz`. Untrusted-text only (openpyxl `data_only` = no formula eval;
  no remote fetch; EML reads ONE message, no attachment recursion). The 3 OOXML readers **fail closed**
  (wrap library errors → `ParserError`) so a malformed-but-sniff-passing file becomes `parse_failed`, not a
  retriable worker crash (review should-fix).
- **ADR-F029** accepted (extends/supersedes ADR-0006's PDF-only scope; inherits its offset contract). **No
  migration** (`parser`/`parser_version` free-text, `page_count` nullable; the `page` field is reinterpreted
  per format — sheet/paragraph-block/slide/whole-message, documented in F029).
- **Tests:** `tests/test_readers.py` (offset invariant + tiling spans per format, registry dispatch,
  sniff/spoof, DOCTYPE + zip-bomb guards across ALL OOXML, **fitz import-guard**, EML non-recursion / HTML-strip
  / plain>html, **malformed-OOXML-fails-closed**, empty-docs) + 5 per-format ingest e2e in
  `test_pipeline_ingest.py`. The pre-existing corrupt-PDF test now feeds `%PDF`-prefixed garbage (the new sniff
  rejects non-PDF-declared-as-PDF earlier — a legitimate behaviour change).
- **Verification:** ruff clean (**CI ruff 0.15.18**); mypy clean (readers+ingest, 8 files); full api suite
  containerized **2476 passed / 2 skipped** (the 1 "fail" = `test_ready_reports_per_dependency_status`, which
  expects services UNREACHABLE — my run was on the live compose network; CI runs it isolated → passes).
  **Live** (real rebuilt image + real MinIO + real DB): all 4 formats → `ready` + fidelity OK. **28-agent
  adversarial review → SHIP**, 0 blockers; 2 should-fix fixed (OOXML fail-closed + plain>html test), nits folded.

## Maintainer decisions already locked (don't re-litigate)

- **Adeu** = sole redline path, **MIT**, integrated via **SDK in-process** (not its MCP server); pin
  `adeu==1.12.1`; bumping must stay trivial. No python-docx/lxml fallback. (C4.)
- **DeepSeek** = qualified provider/test target. **No copyleft in new deps** (Adeu adds none).
- **Client = the org profile** (`OrganizationProfile`) — **wired into the area agent as the read-only company
  tier (C-CLIENT ✓, ADR-F030).**
- **Orchestration:** deepagents' `task`-tool subagents suffice for C0–C7; deterministic langgraph only for
  *guarantees* (deferred O-track; O0 validates feasibility).
- **MCP capability** = its own milestone (sanction-sync upstream's MCP client, approval-gated). Independent of
  Commercial; does not block C0–C7.
- **Multi-turn redlining** = the maintainer's separate next project (held; C5 is its foundation).

## ▶ PICK UP EXACTLY HERE — slice **C2** (Email-chain + .msg + nested-attachment reader, ~3d) — depends C1 ✓

**Goal.** A deal starts as an email; complex ones are the whole chain + attachments. Add **`.msg`**
(python-oxmsg, **MIT** — NOT GPLv3 extract-msg; olefile transitive is BSD) and an **email-chain reader** that
walks multipart parts, stitches by `Message-ID`/`In-Reply-To`/`References`, carries per-message From/Date as
span metadata, and recurses **ONE level** into attached office docs by delegating to the C1 registry.
**Non-goals.** No quoted-history splitting lib unless proven needed; no counterparty/deal ENTITY (matter memory
= C3); no recursion deeper than one level.
**Key files.** the readers pkg (add `msg.py` + an email-chain reader extending `eml.py`'s single-message
reader), `ingest.py`, `api/app/models/document.py` (per-message spans in `metadata_json`), `api/pyproject.toml`,
`NOTICES.md`.
**Watch.** Extend the C1 **fitz import-guard** to the new readers. The current `EmlReader` reads ONE message
(`page_count=1`) and does **NOT** recurse — C2 is where threading + the one-level attachment recursion land.
Reuse `guard_ooxml` for any recursed office doc (zip-bomb/XXE already handled). HTML sanitized (the `eml.py`
stripper is HTML5-correct); `cid:`/`http(s)` **never** fetched; nesting depth + per-part size capped
(billion-laughs/zip-bomb). The Citation-Engine invariant holds via `join_units` per message unit.
**ADR.** F029 (extended).
**Verify.** Multi-message `.eml` → ordered per-message spans with sender/date; `.msg` parses
sender/recipients/subject/body+attachment bytes; an attached office doc is recursed + chunked; HTML sanitized +
no remote fetch. Live: ingest a real multi-attachment deal email; agent answers grounded in a buried
attachment. **Rebuild api + arq-worker + ingest-worker together** if deps change. Then HANDOFF → **C3**.

**FIRST live-verification vehicle (buildable NOW): Scenario A — `docs/fork/plans/scenarios/scenario-a-securescan.md`**
(Zendesk buy-side first-pass on clean SecureScan paper → prose redline; exercises C1 + C-CLIENT + C0, NO C4/C5).
**Scenario B — `scenario-b-meridian.md`** (inbound redlines) needs C2's chain + C5.

**Ladder:** C-R0 ✓ → C0 ✓ → C-CLIENT ✓ → C1 ✓ → **C2** → C3 → C4 → C5 → C6 → C7 (+ O0 spike). ADR gates:
**F030 accepted ✓** (C3 unblocked), **F036 + F038 before C6**.

## Open decisions still pending the maintainer (COMM plan § Open questions)

1. **PyMuPDF/copyleft** — current PDF parser is **AGPL**; rule B forbids copyleft. Grandfather under the
   server-side boundary, or replace with pypdfium2/pypdf? (Adeu itself adds no new copyleft — verified.)
2. Counterparty-entity timing (client is resolved). 3. Typed deal-context schema vs free-form. 4. Playbook
   ownership model (company-global vs per-matter). 5. Orchestration greenlight (fund O1/O2/O3?). 6. Confirm
   multi-turn handoff. 7. **F039 — do user/team skills ever reach the live agent** (advisory-only gated build)
   or stay curated-only?
*Resolved:* Adeu integration (SDK in-process — decision I); MCP-as-a-capability (own milestone, sanction-sync
— decision I).

## Gotchas / durable traps

- **Migration head is still `0066`** (C-CLIENT and **C1 added none** — readers reuse the existing
  `Document`/`DocumentChunk` schema: `parser` free-text, `page_count` nullable). Fresh-head check before any
  migration (`ls api/alembic/versions | sort | tail`); never reuse a number. C2 likely needs none (readers +
  deps); C3/C6/C7 do.
- **Document-reader registry (C1, ADR-F029) = `api/app/pipeline/readers/`.** `ingest_file(..., registry=None)`
  defaults to `build_default_registry(settings)`; dispatch is by **declared MIME** then a server-side
  `reader.sniff(bytes)` content cross-check (PDF magic / OOXML deep `[Content_Types].xml` subtype / EML always
  True). Every reader returns the existing `ParsedDocument` and owns offset fidelity via `join_units` (the +1
  join-newline accounting, mirror of `parsers._run_pymupdf`). **fitz lives ONLY behind `PdfReader`** —
  the AST import-guard test (`test_readers.py::test_no_reader_module_imports_fitz`) fails the build otherwise.
  OOXML security is `guard_ooxml` (DOCTYPE/ENTITY reject BEFORE lxml + zip-bomb caps); the 3 OOXML readers wrap
  library errors → `ParserError` (fail closed). NO `filetype`/`defusedxml` dep — dep-free sniff + DOCTYPE scan
  replace them. `EmlReader` reads ONE message, no attachment recursion (that's C2).
- **New Python deps need a worker rebuild.** The readers run in the **ingest-worker**, so adding a dep
  (`docker compose build api arq-worker ingest-worker` then `up -d --force-recreate`) is required before live
  tests — the running container keeps the old site-packages until recreated. (C1 added python-docx + python-pptx.)
- **The prod `lq-ai-api` image has NO dev tools** (pytest/mypy/ruff are `[dev]` extras, not installed). To run
  the suite / mypy / CI-ruff via the dev image: `docker compose run --rm --no-deps --entrypoint bash
  -v "$PWD/api:/app" -v "$PWD/skills:/skills" -v "$PWD/ruff.toml:/ruff.toml" -e LQ_AI_SKILLS_DIR=/skills -w /app
  api -c "pip install -q pytest pytest-asyncio respx mypy types-PyYAML 'ruff>=0.6' && <cmds>"`; `--entrypoint
  bash` skips the auto-`alembic upgrade` so it never touches the dev DB (the conftest builds its own test DB).
  `chown -R $(id -u):$(id -g) app tests` after (the container writes root-owned files).
- **`mypy app` via an UNPINNED mypy flags false unused-`type: ignore`** in untouched files
  (`ropa_export.py`, `tabular.py`) — newer mypy than CI's pinned `mypy>=1.11`. Trust the **targeted** run on
  your own files (`mypy app/pipeline/readers app/pipeline/ingest.py` was clean); those 2 files are unchanged
  from green main, so CI passes them. Don't "fix" them in an unrelated slice.
- **`test_health.py::test_ready_reports_per_dependency_status` is environment-sensitive** — it asserts **503 /
  not_ready** because it assumes DB/Redis/MinIO/gateway are UNREACHABLE (unit mode). Running the suite inside
  the live `lq-ai_default` compose network makes `/ready` healthy → it "fails." Not a regression; CI runs it
  isolated. (Set the suite off-network or ignore that single assertion when running in-stack.)
- **arq-worker docker network glitch:** a `compose up -d --force-recreate arq-worker` can hit `endpoint with
  name lq-ai-arq-worker-1 already exists` (a docker daemon network-state bug, endpoint stuck in the name index
  but not the container index). `disconnect -f`/`rm -f` don't clear it; a docker daemon restart or full
  `compose down` (NOT `-v`) does. api + ingest-worker are unaffected; arq-worker only runs cron jobs
  (export-GC / hard-delete) — non-blocking for ingest/dev work.
- **Company/client tier = the org profile, injected read-only (C-CLIENT, ADR-F030).** `_load_client_context_md`
  + `system_prompt_for(..., client_context)` in `composition.py` inject the **singleton**
  `OrganizationProfile.content_md` for **every** run, BEFORE the area profile. It is **read-only** (no agent
  tool writes it; the only writer stays `PUT /organization-profile`) and **company-global** (one row, same for
  every user — by design, single-tenant). Empty/absent → no block. The same `select(OrganizationProfile)
  .limit(1)` now lives in 3 layers (api/internal/agents) — kept separate on purpose (different response
  shapes); consolidate only if it grows.
- **Org profile is a SINGLETON in tests** — partial unique index on `((true))`, and migration 0010 seeds **no
  row**. Tests that need one **upsert then delete in `finally`** (the committing `commit_factory` bypasses the
  per-test rollback). See `_set_org_profile`/`_clear_org_profile` in `test_agent_composition.py` /
  `test_commercial_client_context.py`.
- **Ruff version drift bit C-CLIENT — format with the CI version.** The dev image ships ruff **0.15.17**; CI
  installs **`ruff>=0.6` → 0.15.18**, and they disagree on wrapping (0.15.17 *split* pre-existing lines 0.15.18
  keeps single-line → phantom churn that fails `ruff format --check`). Before committing, format with CI ruff:
  `docker run --rm -v "$PWD/api:/app" -v "$PWD/ruff.toml:/ruff.toml" -w /app lq-ai-api-dev pip install -qU
  'ruff>=0.6' && ruff format --config /ruff.toml <files> && ruff format --check ... && ruff check ...`. CI runs
  `ruff check api scripts` + `ruff format --check api scripts` (root `ruff.toml`, line-length 100).
- **Running the provider/live tests via the dev image:** mount `api`→`/app` **and** `skills`→`/skills` (else
  migration 0032's playbook-seed fails on a missing `/skills/playbooks/...`); pass `DATABASE_URL`,
  `LQ_AI_GATEWAY_URL`, `LQ_AI_GATEWAY_KEY`, `LQ_AI_SKILLS_DIR=/skills` from the api container; set
  `UX_B1_EVIDENCE_DIR` to a **mounted host path** (parents[4] is `/` inside the container, not the repo) and
  `chown` the root-owned evidence before `git add`.
- **Profile is a data migration, never an edit to an applied one.** To change a seeded `profile_md`/config on
  already-migrated DBs, add a NEW idempotent migration guarded on the prior value (`WHERE … = :old`) — mirror
  `0066` (and `0054`/`0055`). The api auto-migrates on boot; rebuild api+arq-worker+ingest-worker after a
  migration; **never `docker compose down -v`**; never host-side `alembic upgrade` on the live dev DB (verify
  on a throwaway pgvector container / the test DB conftest carves out).
- **C-R0 artefacts:** the surgical-gate definition lives in `commercial-lawyer-method.md` § 6 (C4 implements
  it); ALL numeric thresholds are **calibration starting values**, not sourced. Adeu verified at `adeu==1.12.1`
  (`adeu-pinning.md`).
- **Adeu is SDK-only, never its server (C4):** import only `adeu.RedlineEngine`/`ModifyText`/`process_batch`;
  **never** `adeu.server` / `adeu.mcp_components` (a second egress). Installing Adeu pulls `fastmcp[apps]`
  (~80-pkg, all-permissive, runtime-isolated) — a C4 SBOM decision.
- **The one per-area code seam** is the area-keyed grant branch in `composition.py:224`
  (`area_key == PRIVACY_AREA_KEY`) — mirror it for Commercial **only when Commercial gains domain tools (C4)**;
  C-CLIENT does not need it. There is **no `COMMERCIAL_AREA_KEY` constant** — the key is the literal
  `"commercial"`. Everything else is declarative config (seeded subagents/skills/profile via migrations).
- **`allowed_tools` in SKILL.md is decorative** (`extra="allow"` drops it) — NOT a security boundary; the only
  tool boundary is the per-run area-keyed granted frozenset.
- **Controlling company skills must be deterministically bound** (instrument classifier → inject body), NOT
  relevance-surfaced (F038, C6). User/team skills are advisory-only, never controlling; the controlling
  namespace must be non-shadowable. (C0 stated the convention in the profile; C6 enforces the binding.)
- **Scenario harness:** `_MAX_STEPS=16` (harness default) is a TIGHT cap — a multi-step run can hit
  `cap_exceeded` (a tier-4 finding, not a defect). Pass `max_steps=` higher and `skill_registry=` to give a
  realistic run room (skills-on + 40 steps got a clean surgical answer at C0). Provider tests are CI-skipped
  (need `LQ_AI_GATEWAY_KEY`); run them via the dev image on the `lq-ai_default` network with the api
  container's gateway env. Live evidence dir is overridable (`UX_B1_EVIDENCE_DIR`); docker writes root-owned
  files → `chown` before `git add`.
- **Severity-scale conflict (F036):** playbook DB CHECK `critical/high/medium/low` (`0031:139`) vs review
  skills' `critical/material/minor` — incompatible at the data layer; **resolve before C6**. C0 deliberately
  kept assessment as **orthogonal layers** (did NOT impose one scale).
- **Security every slice:** treat retrieved docs / email HTML / Office XML / counterparty markup / stored
  playbook text / user skills as **untrusted**; audit carries counts/types/IDs only (never rationale text or
  raw clause content); cross-user → 404 (NOT the matter-scoped Commercial records, which filter by
  `binding.project_id`, ADR-F035).
- Dev login `admin@lq.ai` (password in your local `.env`, not committed); api :8000, web :3000, gateway
  internal :8001 (admin header `X-LQ-AI-Gateway-Key`). Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) when behavior changes + HANDOFF
updated. `gh` always with `--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
