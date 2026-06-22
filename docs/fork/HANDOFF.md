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

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ DELIVERED; building continues at C3.**

The full COMM decomposition is written + adversarially reviewed:
**`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md` — read it first.** **Privacy is PARKED**
→ `docs/fork/plans/PRIV-BACKLOG.md`. A new **MCP capability** milestone is approved (own milestone, not part
of Commercial) → `docs/fork/MILESTONES.md` § MCP capability.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL, STILL ACTIVE):** `smart`/`fast`/`budget` are repointed
`minimax/MiniMax-M3 → deepseek/deepseek-v4-flash` on the local gateway (MiniMax out of quota; survives restarts
via the `gateway-config` volume). DeepSeek is the qualified live-test target (decision F). Revert when MiniMax
quota returns.

## Done this slice (C2 — email-chain + `.msg` + one-level attachment recursion; NO migration)

- **`api/app/pipeline/readers/_message.py`** (NEW) — the shared email assembler. `NormalizedMessage(headers,
  body, attachments)` (format-agnostic intermediate); `assemble_email(message, *, recurser, parser_label,
  parser_version)` emits **one top-message unit + one unit per attachment**, each prefixed with an **inline
  provenance label** (header block + `[Attached file: name (mime) — status]`), and writes the thread/attachment
  map to `structured_content`. Offsets via the existing `join_units`. Houses the shared `strip_html` + a
  `RecursingReader` mixin (the recurser-wiring seam). Caps enforced here.
- **`api/app/pipeline/readers/_base.py`** — `AttachmentRecurser(registry, depth_remaining)`: **immutable,
  per-call depth** (recursing passes a `depth-1` child as an argument → concurrency-safe under `to_thread`),
  **sniff-gated + fail-soft** (unknown mime / spoof / parse-error / depth-exhausted → `None`). `MSG_MIME` +
  `MSG_MIME_ALT`; caps `MAX_EMAIL_ATTACHMENTS=50`, `MAX_RECURSED_TEXT_CHARS=40M` (bounds **extracted text**, not
  compressed input — review fix).
- **`eml.py`** upgraded (stdlib `email`): collects nested `message/rfc822` parts + attachments → recurser; **`msg.py`**
  NEW (`python-oxmsg==0.0.2`, MIT; `Message.load`; OLE-magic sniff; `_normalize` split from the load boundary for
  stub-testability). **`__init__.py`** wires a depth-1 recurser factory onto eml+msg at the composition root.
  Both inherit `RecursingReader`.
- **One File → one `ParsedDocument`**: chunker / `Document`/`DocumentChunk` models / persist / `search_documents`
  **UNTOUCHED**; Citation invariant holds via `join_units`. **No migration** (`structured_content` already JSONB).
  Provenance the agent uses is **inline** (search returns chunk content verbatim); the map is the audit record.
- **Deps:** +`python-oxmsg==0.0.2` (MIT; transitives `olefile` BSD-2, `click` BSD-3 — no new copyleft; NOT GPLv3
  `extract-msg`). mypy override + `NOTICES.md` row added. **ADR-F029 extended** (C2 section).
- **Security:** depth=1 (nested email lists-but-doesn't-extract its own attachments); attachment-count + extracted-
  text caps; office-doc recursion inherits `guard_ooxml` (zip-bomb/XXE); `cid:`/`http(s)` never fetched; HTML
  stripped (inert); fail-soft (a bad attachment never sinks the email); fitz import-guard auto-covers new modules.
- **Verification:** ruff + mypy clean (`mypy app` 182 files); **53** reader+ingest tests on real postgres (38
  reader unit + 15 ingest); full api suite containerized **2494 passed / 2 skipped** (the 1 non-pass =
  `test_ready_reports_per_dependency_status`, env-sensitive — asserts services unreachable, passes isolated in
  CI). **Live** (rebuilt image + `python-oxmsg` baked): multi-attachment
  `.eml` → buried docx grounded, png listed-not-extracted, fidelity OK, `.msg` sniff works. **19-agent
  adversarial review → SHIP**, 0 blockers, 4 should-fix **all fixed** (inert→extracted-text cap; fail-soft test
  gap; 2 doc corrections), nits folded (recurser mixin DRY + 3 tests). Evidence: `docs/fork/evidence/c2/`.

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

## ▶ PICK UP EXACTLY HERE — slice **C3** (Deal context as matter memory: inject + propose/accept, ~3d) — depends C0; **F030 accepted ✓**

**Goal.** Realise the unit-of-work memory tier: inject `projects.context_md` at the composition seam as a
**fenced read-only "Deal context" block** (mirror the C-CLIENT company-tier injection in `composition.py`,
ordered base→matter→**client**→area so C0 doctrine stays the controlling last word), and add a guarded
`propose_deal_context_update` tool feeding a **proposal → user-accept** write (ADR-0013 D4/D5 "system proposes,
user owns"). `0041` is precedent-bound → create a **new** deal-context proposal table. Context is
reconcilable/supersedable.
**Non-goals.** No typed deal-context schema (free-form `context_md` + proposal table v1); no CompositeBackend
yet; no reuse of `0041`; no auto-accept of material changes; no counterparty ENTITY (still deferred — Open Q #2).
**Key files.** `api/app/agents/composition.py`, `api/app/models/project.py`, `api/app/models/autonomous.py`,
`api/app/api/autonomous.py`, `api/alembic/versions/0067_deal_context_proposals.py` (NEW — **migration head is
`0066`**, fresh-number check first), `api/app/agents/guard.py`, `ropa_tools.py`.
**Watch.** This is the first Commercial slice that **needs a migration** (verify on a throwaway pgvector
container; rebuild api+arq-worker+ingest-worker after; NEVER host-side `alembic upgrade` on the live DB; NEVER
`compose down -v`). Audit carries counts/types/IDs only (no raw context text). Matter-memory owner-scoped +
archived-aware; cross-user → **404** (matter-scoped by `binding.project_id`, ADR-F035). Accept applies
exactly-once (`accepted_at` guard); supersede must not duplicate.
**ADR.** F030 (**accepted** — covers company + matter tiers; C-CLIENT shipped the company half).
**Verify.** CI: composition test (`context_md` fenced-injected + read-only); guarded-tool test (`propose`
writes a **proposal row**, not `context_md`, via `guarded_dispatch`); accept-endpoint exactly-once; supersede
no-dup; cross-user 404. Live (DeepSeek): two-turn run — agent proposes, user accepts, next run reflects it.

**Live-verification vehicles:** **Scenario A** (`docs/fork/plans/scenarios/scenario-a-securescan.md`, buy-side
first-pass, buildable now — C1+C-CLIENT+C0, NO C4/C5; C2's `.eml` chain now makes the multi-attachment intake
real). **Scenario B** (`scenario-b-meridian.md`, inbound redlines) needs C4/C5. Wiring Scenario A's live run is
the natural place to exercise C2's email-chain ingest end-to-end through the agent.

**Ladder:** C-R0 ✓ → C0 ✓ → C-CLIENT ✓ → C1 ✓ → C2 ✓ → **C3** → C4 → C5 → C6 → C7 (+ O0 spike). ADR gates:
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

- **Migration head is still `0066`** (C-CLIENT, **C1, and C2 added none** — readers reuse the existing
  `Document`/`DocumentChunk` schema, and C2's thread/attachment map rides the already-present
  `Document.structured_content` JSONB). Fresh-head check before any migration
  (`ls api/alembic/versions | sort | tail`); never reuse a number. **C3 adds `0067`** (deal-context proposals);
  C6/C7 also need migrations.
- **Document-reader registry (C1, ADR-F029) = `api/app/pipeline/readers/`.** `ingest_file(..., registry=None)`
  defaults to `build_default_registry(settings)`; dispatch is by **declared MIME** then a server-side
  `reader.sniff(bytes)` content cross-check (PDF magic / OOXML deep `[Content_Types].xml` subtype / EML always
  True). Every reader returns the existing `ParsedDocument` and owns offset fidelity via `join_units` (the +1
  join-newline accounting, mirror of `parsers._run_pymupdf`). **fitz lives ONLY behind `PdfReader`** —
  the AST import-guard test (`test_readers.py::test_no_reader_module_imports_fitz`) fails the build otherwise.
  OOXML security is `guard_ooxml` (DOCTYPE/ENTITY reject BEFORE lxml + zip-bomb caps); the 3 OOXML readers wrap
  library errors → `ParserError` (fail closed). NO `filetype`/`defusedxml` dep — dep-free sniff + DOCTYPE scan
  replace them.
- **Email assembly (C2, ADR-F029 ext) = `api/app/pipeline/readers/_message.py`.** EML/MSG readers normalise to
  `NormalizedMessage` → `assemble_email` emits **one top-message unit + one unit per attachment** (`message_count`
  is always 1; a forwarded `message/rfc822`/`.msg` is an **attachment** unit, not a message — no per-message
  tree; inline-quoted history kept verbatim). Provenance the agent sees is **inline** (header block +
  `[Attached file: …]` labels — `search_documents` returns chunk text verbatim, never `structured_content`); the
  thread/attachment **map** is the audit record in `Document.structured_content` (no migration; not agent-visible).
  **`AttachmentRecurser` (in `_base.py`) is immutable + per-call depth** (recursing passes a `depth-1` child as an
  arg → concurrency-safe; nested email read at depth-0 lists-but-doesn't-extract its own attachments = the
  one-level bound), **sniff-gated + fail-soft** (bad attachment → `not text-extracted`, never sinks the email).
  Wired onto eml+msg via `set_recurser_factory` at the composition root (`build_default_registry`); both inherit
  the `RecursingReader` mixin. **`MAX_RECURSED_TEXT_CHARS` bounds EXTRACTED text, not compressed input** — a
  compressed-bytes cap is inert (each attachment ⊆ the already-capped upload), so the cap is accounted in
  `_recurse_attachment` *after* parsing (review fix; the decompression-amplification guard).
- **`.msg` = `python-oxmsg==0.0.2` (MIT), READ-ONLY** (no `.msg` writer exists). So `.msg` is covered by unit
  tests — `_normalize` via a stub message + OLE-magic sniff + a patched-`Message.load` e2e — plus the empirical
  API verification; the first **real** `.msg` byte-parse lands at **Scenario B**. `MsgReader` lazy-imports oxmsg
  inside `read()`, so the readers pkg imports cleanly without it. `sniff` = OLE magic `D0CF11E0A1B11AE1`.
- **Running an in-image script (no mounts):** `docker run --rm -e PYTHONPATH=/app -v /tmp/x.py:/x.py:ro
  --entrypoint python lq-ai-api /x.py` — `docker compose run` shadows `/app` (dev volume) and script execution
  doesn't add cwd to `sys.path`, so set `PYTHONPATH=/app` and use `docker run` (not compose) to test the BAKED
  code. (`get_settings()` needs env; pass a `types.SimpleNamespace(lq_ai_docling_enabled=...)` to
  `build_default_registry` to avoid it in a pure-reader check.)
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
