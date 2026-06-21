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

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ DELIVERED; building continues at C1.**

The full COMM decomposition is written + adversarially reviewed:
**`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md` — read it first.** **Privacy is PARKED**
→ `docs/fork/plans/PRIV-BACKLOG.md`. A new **MCP capability** milestone is approved (own milestone, not part
of Commercial) → `docs/fork/MILESTONES.md` § MCP capability.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL, STILL ACTIVE):** `smart`/`fast`/`budget` are repointed
`minimax/MiniMax-M3 → deepseek/deepseek-v4-flash` on the local gateway (MiniMax out of quota; survives restarts
via the `gateway-config` volume). DeepSeek is the qualified live-test target (decision F). Revert when MiniMax
quota returns.

## Done this slice (C-CLIENT — org profile = company/client memory tier, NO migration)

- **`api/app/agents/composition.py`** — the company/client tier of the 4-level memory model goes live.
  `system_prompt_for(binding, area, client_context)` gains a 3rd arg; a new `CLIENT_CONTEXT_PROMPT` fences the
  operator's `OrganizationProfile.content_md` as a read-only **"Client / house context"** block, injected
  **BEFORE** the area profile (so the C0 doctrine stays the controlling *last* word — base → matter → client →
  area). `_load_client_context_md(db)` reads the singleton (migration 0010), treats empty as absent, and is
  loaded **once per run for EVERY run** (bound/unbound, any area) — closing CLAUDE.md **blocker #5** (plain
  runs had zero company context). **Read-only**: no agent tool mutates it; the operator owns edits via the
  existing `PUT /organization-profile`. The block is operator-trusted but still **fenced** (defense in depth).
- **`docs/adr/F030-commercial-memory-model.md`** — **accepted** (company tier = this slice's injection; matter
  tier = `context_md` + a code-validated propose/accept path at **C3**). This **satisfies the "F030 before C3"
  gate**. No counterparty entity, no CompositeBackend yet.
- **Tests:** composition file now **17/17** — pure `system_prompt_for` (fenced + ordered-before-area +
  read-only language + None/whitespace degrade) + **e2e seeded-injection** (the org-profile body reaches the
  model's system prompt; the run does **not** mutate the row) + **empty-degrades-clean**. Fixed the
  `_seen_system_text` helper (extract content-block text instead of `str(list)`, which repr-escaped
  apostrophes when a matter name added double quotes — the bug that masked the first e2e run).
  Plus a provider-marked **A/B live test** (`tests/agents/scenarios/test_commercial_client_context.py` +
  `zendesk_client.py`).
- **Verification:** ruff clean (formatted with **CI ruff 0.15.18**, not the dev image's 0.15.17 — see Gotchas);
  mypy clean; full api suite containerized (CI-parity). Live (DeepSeek, alias `smart`): an **A/B** with a
  synthetic **Zendesk** house context — same matter + prompt, profile **OFF→ON**. ON holds the house cap
  position and **escalates uncapped liability to the General Counsel** (+ the 2x-annual super-cap rule); the
  procurement leg **flips** to buyer and **requires a DPA** — none derivable from the document. Evidence:
  `docs/fork/evidence/c-client/` (`c-client-verification.md` narrative + `ab-report.md`/`.json` +
  `zendesk-org-profile.md`).

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

## ▶ PICK UP EXACTLY HERE — slice **C1** (Document-reader registry: DOCX/PPTX/XLSX/EML, ~3d) — depends C-R0/C0 ✓

**Goal.** Replace the single PDF MIME gate with an injected **MIME→reader registry** so a matter ingests the
formats a deal arrives in. Each reader returns the existing `ParsedDocument`; the chunker/embed/`Document`
model stay untouched. Cheapest-first: **XLSX** (openpyxl already a dep), **EML** (stdlib, zero new dep),
**DOCX** (python-docx), **PPTX** (python-pptx) — all permissive licences (decision B).
**Non-goals.** No `.msg` (C2); no email-chain threading / nested-attachment recursion (C2); no OCR; no
Docling/VLM swap (deferred spike).
**Key files.** `api/app/pipeline/ingest.py`, `parsers.py`, `chunker.py`,
`api/app/workers/document_pipeline.py`, `api/pyproject.toml`, `NOTICES.md`,
`docs/adr/0006-document-pipeline-architecture.md`.
**Watch.** Each reader must hold the **Citation Engine invariant** `content == normalized_content[start:end]`
byte-for-byte, with generalised unit-spans (slide#/sheet-name/paragraph-block). Server-side **MIME sniff**
(filetype/python-magic) rejects spoofed types at the boundary (reject-don't-guess). A **CI import-guard test**
asserts no non-PDF reader imports `fitz`. Parse Office XML with **external entities disabled** (XXE +
remote-template SSRF). New deps are SBOM entries → update `NOTICES.md`.
**ADR.** **F029** (extends/supersedes ADR-0006). *(Open question #1 — PyMuPDF/AGPL — is adjacent: C1 keeps
PyMuPDF for PDF and adds only permissive readers; the grandfather-vs-replace call is the maintainer's, not a
C1 blocker. Flag it, don't resolve it here.)*
**Verify.** Per-reader unit tests assert the invariant + spans; spoofed-MIME rejection test; the fitz
import-guard test. Live: upload one of each format → `ready` + searchable chunks (**rebuild api + arq-worker +
ingest-worker together** after the migration/dep change). Then HANDOFF → **C2**.

**Ladder:** C-R0 ✓ → C0 ✓ → C-CLIENT ✓ → **C1** → C2 → C3 → C4 → C5 → C6 → C7 (+ O0 spike). ADR gates:
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

- **Migration head is still `0066`** (C-CLIENT added none — it reads the existing `OrganizationProfile`).
  Fresh-head check before any migration (`ls api/alembic/versions | sort | tail`); never reuse a number. C1
  likely needs none (readers + deps, no schema change); C3/C6/C7 do.
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
