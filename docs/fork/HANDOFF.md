# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ DELIVERED. Pickup = C8 (surgical-redline craft).**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns.

## Done this slice (C4 — Adeu surgical-redline tool `apply_redline`; NO migration)

- **`api/app/schemas/commercial.py`** (NEW) — the **model-free D1-D6 surgical gate**. Key refinement vs C-R0
  §6.1: the ratio measures **struck (deleted) tokens / clause_tokens**, NOT insertions — so adding protective
  carve-outs (the §5.1 move) is surgical, while *striking* existing text is what stays minimal. `ApplyRedlineInput`
  /`RedlineEditInput` validators (D2 rationale, D3 bare-deletion, no-op guard) + `evaluate_gate` (D1 tiered
  strike, D4 unique-anchor, D5 batch ceiling; fail-closed clause resolution). All thresholds are calibration
  starting values (named module constants).
- **`api/app/agents/redline_service.py`** (NEW) — the Adeu SDK adapter (`dry_run`/`apply`/`accept_all`). **Raw
  `ModifyText` per edit — decompose REJECTED** (it emitted micro-anchors like `target_text="3"` that Adeu
  fuzz-matched to the wrong span → live corruption `Ven12or`, and it bypassed the D4 gate; raw is safe + Adeu's
  prefix/suffix trim still renders surgically). **Fresh ModifyText per call** (Adeu's `process_batch` mutates
  them into a cycle → reusing across dry_run+apply was a `RecursionError`).
- **`api/app/agents/redline_render.py`** (NEW) — `word/document.xml` → readable `[-del-][+ins+]` reconstruction
  (Layer-2 tests, the judge, evidence).
- **`api/app/agents/commercial_tools.py`** (NEW) — `COMMERCIAL_AREA_KEY="commercial"`, `build_commercial_tools`,
  the guarded `apply_redline` + `_apply_redline` (validate → matter-scoped fetch → gate → dry-run → apply →
  persist as a new `File`). **Matter-scoped (ADR-F035)**: reuses `tools._matter_files_query` (owner+matter,
  404 cross-deal/cross-user). Audit = counts/types/IDs only (`commercial.redline_applied`), never clause text.
- **`composition.py`** — `redline_service_provider` provider-callable seam (stateless adapter, no startup
  singleton) + the **Commercial grant branch** (`elif area_key == COMMERCIAL_AREA_KEY`).
- **Deps:** Adeu installed **`--no-deps`** (api/Dockerfile, api/Dockerfile.dev, ci.yml) — its `fastmcp[apps]`
  hard dep would bump starlette/pydantic and break our FastAPI (`APIRouter`, 89 errors). We never use the
  server, so fastmcp is **absent** → `adeu.server` is a hard `ModuleNotFoundError` (second egress structurally
  gone). Its real SDK deps `diff-match-patch` (Apache-2.0) + `structlog` are in pyproject. NOTICES updated.
- **ADRs F031 + F035** (both accepted, written this slice). **No migration** (output is a `File` row).
- **Verification:** ruff + mypy clean; **42** C4 unit/integration tests; full api suite **2509 passed / 2
  skipped** (the 11 "failures" = test-DB contamination from a killed mid-run container + the 1 documented
  env-sensitive health test — all confirmed clean in a fresh container). **Live (DeepSeek):** comprehensive,
  mostly-surgical redline of a vendor-favoured SaaS MSA; **redline-quality judge → STRONG**; evidence in
  `docs/fork/evidence/c4/`. **Adversarial review (11 agents) → SHIP, 0 confirmed findings** (every flag refuted
  as already-correct).

## ▶ PICK UP EXACTLY HERE — slice **C8 — surgical-redline craft** (the maintainer's next priority)

**Why (from the C4 live run):** DeepSeek's §8 indemnity edit **struck the whole clause and retyped it** instead
of keeping "shall indemnify, defend and hold harmless" bare + making narrow edits (swap party, narrow scope,
INSERT the third-party indemnity). The C4 gate is *structural* — it proved the edit well-formed but can't prove
"a surgical alternative existed" (the model set `rewrite_justified=true`). **C8 makes structure-preserving,
sub-sentence, multi-narrow-edits-per-clause the reliable behaviour.** Full scope + the §8 worked example:
**memory `surgical-redline-craft-slice.md`** (read it). Sketch: (1) a **controlling redline skill** with
before/after examples pushing clause-decomposition into several narrow edits; (2) make `rewrite_justified`
**expensive** — a whole-clause strike triggers a Layer-3 critic that must confirm no structure-preserving
alternative; (3) reuse C4's batched `apply_redline` + golden corpus + judge harness; likely a new ADR.

**Other COMM slices still pending:** **C3** (deal-context matter memory — inject `projects.context_md` +
propose/accept; first Commercial migration `0067`; mapping already done, see memory + the C3 plan section) ·
**C5** (negotiation rounds, needs C3+C4) · **C6** (controlling playbook skills, needs F036+F038) · **C7**
(complex-deal fan-out — the answer for 50-page docs). Order is the maintainer's call; **C8 is next per the
2026-06-22 steer.**

## Gotchas / durable traps (C4 + carried)

- **Adeu is installed `--no-deps`** (4 places: api/Dockerfile, api/Dockerfile.dev, ci.yml, + any dev-image test
  command). Its `fastmcp[apps]` dep bumps starlette 0.48/pydantic 2.13/mcp → breaks `APIRouter`. The SDK
  (`RedlineEngine`/`ModifyText`/`process_batch`) needs only `diff-match-patch` + `structlog` (+ lxml/python-docx
  /rapidfuzz/pydantic already in-tree). **Dev-image test commands MUST `pip install diff-match-patch structlog`
  + `pip install --no-deps adeu==1.12.1`** or `from adeu import …` fails `ModuleNotFoundError: structlog`.
- **`apply_redline` redlines the named doc FRESH each call (no stacking)** — the agent must pass ALL edits in
  ONE batched call (the tool docstring says so). Multiple calls each re-redline the ORIGINAL → only the last
  call's edits survive in its output File. For long docs needing >50 edits/call → chain on the prior output or
  fan out (C7). A redline run is step-intensive; ADR-F026 budget is 100 steps/900s (fine for one batched
  single-doc redline; **50-page docs need C7 fan-out + a redline budget tier** — recorded as a finding).
- **`max_steps` is API-capped at `le=100`** (`schemas/agent_runs.py`); the harness sets it directly on the
  AgentRun row (bypasses the schema), so live scenarios can exceed 100 if needed — but production is 100.
- **Killed-container test-DB contamination:** killing a `docker compose run` suite container mid-run leaves the
  reused test DB dirty (leftover admin/session rows) → spurious CLI/audit/last-admin failures on the next run.
  Re-run the suspect files in a FRESH container to confirm. The `test_ready_reports_per_dependency_status`
  health test is separately env-sensitive (passes isolated; "fails" on the live network).
- **Provider tests need the gateway key UNSET to skip:** `docker compose run api` inherits `LQ_AI_GATEWAY_KEY`
  from the api service env, so the full suite would RUN the provider tests (slow/hangs on real gateway calls).
  Run the regression suite with `-e LQ_AI_GATEWAY_KEY= -m 'not provider and not e2e'`.
- **Live redline scenario:** `tests/agents/scenarios/test_commercial_redline_scenario.py` (provider-marked) seeds
  the real `securescan_msa.build_msa_docx()` into MinIO + runs DeepSeek + writes `.docx`/reconstruction/
  accept-clean/judge to `UX_B1_EVIDENCE_DIR`. The judge's input was truncated at first (false WEAK); caps are
  now generous (must fit the full redline). Run via the dev image on `lq-ai_default` with the api gateway env +
  `UX_B1_EVIDENCE_DIR` mounted; `chown` the root-owned evidence before `git add`.
- **Migration head is still `0066`** (C4 added none — output is a `File` row). **C3 adds `0067`.** Fresh-head
  check before any migration; rebuild api+arq-worker+ingest-worker after one; never host-side `alembic upgrade`
  on the dev DB; never `compose down -v`.
- **The per-area grant seam** is `composition.py` (`area_key == PRIVACY_AREA_KEY` / now `== COMMERCIAL_AREA_KEY`).
  `COMMERCIAL_AREA_KEY = "commercial"` lives in `commercial_tools.py` (mirrors `PRIVACY_AREA_KEY` in ropa_tools).
- **Dev-image suite/lint recipe:** `docker compose run --rm --no-deps --entrypoint bash -v "$PWD/api:/app"
  -v "$PWD/skills:/skills" -v "$PWD/ruff.toml:/ruff.toml" -e LQ_AI_SKILLS_DIR=/skills api -c "pip install -q
  pytest pytest-asyncio respx mypy types-PyYAML 'ruff>=0.6' diff-match-patch structlog && pip install --no-deps
  adeu==1.12.1 && <cmds>"`; `chown -R $(id -u):$(id -g) app tests` after. CI ruff = `ruff>=0.6`; format with it
  before pushing (version drift). `mypy app` via unpinned mypy false-flags `ropa_export.py`/`tabular.py` — ignore.
- Dev login `admin@lq.ai` (password in local `.env`, not committed); api :8000, web :3000, gateway :8001.
  Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`. Adeu SDK-only — never `adeu.server`/`adeu.mcp_components`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) when behaviour changes + HANDOFF
updated. `gh` always `--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
