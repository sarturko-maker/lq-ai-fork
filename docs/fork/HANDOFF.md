# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ C8 ✓ C9 ✓ + cockpit chat-UX ✓. C3 REFRAMED → matter-memory track (C3a/b/c); ADR-F042 ACCEPTED. C3a ✓ (matter-wiki MVP). C3b SPLIT (maintainer: split + in-run tool) → C3b-1 ✓ (typed bi-temporal fact ledger + guarded `record_matter_fact` + supersede + as-of query, ZERO model calls, live-proven on DeepSeek). NEXT = C3b-2 (gateway-routed consolidation/Lint — the ADR-F010 egress slice).**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns. C9 fact: `deepseek` → `deepseek-v4-flash`;
**`deepseek-pro` → `deepseek-v4-pro`** (both wired in `gateway.yaml`, same DeepSeek account/quota) — the
stronger tier for the "is it the model?" control.

## Done this session (C3b-1 — typed bi-temporal fact ledger SHIPPED; branch `fork/c3b1-typed-facts`)

(C3a shipped last session — PR #133, memory `matter-memory-c3a-shipped`: the auto-write matter wiki +
human-pinned corrections, all areas, live-proven.)

**What:** the matter now keeps a **dated, supersede-able fact ledger** beside the C3a prose wiki — the
headline answer to *"what did we believe at signing"*. The agent records individual typed facts; superseding
a fact closes its world-time window (never deletes), so the bi-temporal history is queryable.
**Maintainer split C3b** (AskUserQuestion): **C3b-1 = the store + write + as-of (ZERO model calls)**;
**C3b-2 = the gateway-routed consolidation/Lint (the egress slice), in-run guarded tool**. Plan:
`docs/fork/plans/C3b-typed-facts-consolidation.md`. **Zero new deps; zero model calls in C3b-1.**

- **Migration `0070`** (additive-nullable on `matter_memory_entries`, NO backfill — the `0068` contract):
  `author`·`source_citation`·`fact_type`·`valid_at`·`invalid_at`·`superseded_by`; extends the `kind` CHECK
  to add `'fact'`; new nullable-enum + temporal (`invalid_at > valid_at`) + source-length CHECKs. Downgrade
  deletes `kind='fact'` rows then reverts. **Head is now `0070`.** Up/down/up verified on a throwaway pgvector.
- **ORM** — extended `MatterMemoryEntry` (`models/project.py`): the 6 nullable columns + enum tuples
  (`_MATTER_MEMORY_AUTHORS`, `_MATTER_FACT_TYPES`, `'fact'` in `_MATTER_MEMORY_KINDS`) + an `_opt_in_set` helper;
  CHECK literals mirror the migration (single source of truth). A fact's **statement reuses `body_md`** (no
  separate `value` column — inherits the body-len CHECK + no-leak audit). `superseded_by` is a plain UUID
  (forward link, like `run_id`).
- **`app/agents/matter_fact_tools.py` (NEW)** — `MATTER_FACT_TOOL_NAMES = {record_matter_fact}` (disjoint),
  `build_matter_fact_tools(...)`; the guarded `record_matter_fact(fact, fact_type, source=, valid_from=,
  supersedes=)` — validate via `schemas.matter_memory.RecordMatterFactInput` (reject-not-truncate), reload
  project (owner+active), insert a `kind='fact'` row (`author='agent'`/`trust='normal'` **tool-fixed**), and on
  supersede close the prior's window (`invalid_at`+`superseded_by`). Guard auto-audit only. + pure read helpers
  `facts_valid_at` (the as-of query `valid_at ≤ T < invalid_at`), `live_facts`, `memory_log` — the **C3c**
  retrieval/panel substrate.
- **`app/agents/composition.py`** — grants `build_matter_fact_tools(...)` to **every** matter-bound run (all
  areas), beside the matter-memory grant; disjoint from ROPA/assessment/commercial.
- **`schemas/matter_memory.py`** — `MatterFactType(StrEnum)` (party/term/date/decision/open_point/fact) +
  `RecordMatterFactInput` (`extra='forbid'`, blank-source→None, **`valid_from` normalised to UTC-aware** —
  review fix, see gotcha). **`skills/matter-memory/SKILL.md`** — added the fact-ledger craft section.
- **B2 carries over (structural):** `record_matter_fact` writes only `kind='fact'` rows — it can neither mint a
  `human-pinned` correction (no-fabrication) nor touch a `correction` row (no-overwrite; `supersedes` filters
  `kind='fact'`, so it cannot target a correction or another matter's/user's fact). **C3b-1 makes ZERO gateway
  calls** — the ADR-F010 egress obligation is C3b-2.
- **Adversarial review (workflow, 4 lenses → per-finding refutation): 0 blockers, 1 should-fix + 1 nit, both
  fixed.** Should-fix = the `valid_from` tz-naive crash (now normalised + a regression test); nit = the
  `author='lawyer'` docstrings overstated (softened — the pin endpoint is untouched in C3b-1, so corrections'
  `author` stays NULL).
- **Live (DeepSeek, evidence `docs/fork/evidence/c3b1/live-matter-facts.json`):** the agent called
  `record_matter_fact` 4× — 3 party facts then read the agreement and recorded the liability cap as a `term`
  fact with a real source (`Acme-MSA.txt §7`); all `author='agent'`/`trust='normal'`; `facts_valid_at(now)`
  ran live and returned all 4. **Finding:** the agent over-searches before recording (first run thrashed to
  `cap_exceeded`); a front-loaded prompt fixed it — a craft note, not a code issue.
- **Verify:** ruff+format+check clean; `mypy` clean; targeted suites green; **full api suite 2564 passed / 2
  skipped** (the lone "failure" is the documented env-sensitive `test_ready_reports_per_dependency_status`,
  untouched by this diff). No new endpoint → no `test_openapi`/`test_endpoints` churn.

### Previous slice (cockpit chat-UX render polish — merged #132, on main): dark-mode markdown parity
(`dark:prose-invert` on the agent-surface prose containers — the GFM-parser theory was a red herring) +
quieter tool calls. `vitest` 904/904. Redline download deferred to C7.

## Previous slice (C9 — Claude-judged manual redline tests; merged #131; no migration; no new ADR)

**What:** upgraded C8's craft signal from DeepSeek-judging-itself to **Claude (Opus 4.8) judging DeepSeek**
over a corpus spanning contract types **and** complexity, with the produced `.docx` surfaced for the
maintainer. Reuses C4/C8 (`apply_redline`/`preview_redline`, `seed_doc_matter`/`capture_redline`,
reconstruction). Plan `docs/fork/plans/C9-claude-judged-redline-tests.md`.

- **7 corpus instruments** (single-source `.docx`==normalized text): *moderate* — `securescan_msa`,
  `databridge_license`, NEW `aegis_mutual_nda`, `northwind_dpa`, `meridian_services_sow`; *complex*
  (dense multi-limb, added mid-slice on the maintainer's "the real test is long clauses where most language
  must be LEFT ALONE") — NEW `helios_master_agreement`, `orion_dev_licence`.
- **`tests/agents/scenarios/test_commercial_redline_manual.py`** (NEW, provider-marked) — purposive
  per-instrument prompts (names the one-sided heads, leaves surgical technique to the bound skill); runs the
  chosen model with the skill registry active; writes `c9/<id>/` (`original-*.docx`, `* (redlined).docx`,
  `reconstruction.txt`, `accepted-clean.txt`) + a merge-safe `manifest.json`; `LQ_AI_C9_ONLY` runs a subset;
  `LQ_AI_SCENARIO_MODEL` selects `deepseek` (flash) vs `deepseek-pro`. `complexity` field added to
  `RedlineScenarioDoc`.
- **Substrate bugfix `api/app/agents/skill_backend.py`** — `RegistrySkillBackend.grep`/`glob` now return a
  graceful unsupported `GrepResult`/`GlobResult` instead of inheriting the protocol's `raise
  NotImplementedError`. deepagents' `agrep`/`aglob` do NOT catch that, so **any run where the model called the
  builtin grep/glob hard-failed** (observed live: the NDA crashed mid-redline). Fixes every area agent
  (Privacy too). Test in `tests/agents/test_skill_backend.py`.
- **Judge deliverables (Claude):** `docs/fork/evidence/c9/SUMMARY.md` + `verdicts/<id>.md` + `flash/` & `pro/`
  `.docx`. **Finding:** flash surgical-craft **5/7** by the strong judge (vs C8's self-judged 2/6); the
  **complex** docs scored *among the best on both models* — complexity is NOT the craft predictor. The one
  consistent weakness is **pervasive mutualisation** (one-directional-throughout clauses → whole-clause
  rewrite). Pro re-run of the flash failures: fixed the SOW *robustness* (flash produced no redline) but did
  **worse** on the NDA (looped to `cap_exceeded`) — so the stronger tier does NOT reliably fix craft; the
  lever is **method** (a mutualisation worked-example in `surgical-redline` + a redline step-budget tier).
- **Live cockpit UAT (maintainer, end of C9):** drove the agent in the real UI on a "Project Atlas" deal
  suite (`/home/sarturko/atlas-deal-suite/`: an `.eml` with a **nested** term-sheet PDF, the Cirrus MSA
  `.docx`, a processor DPA PDF; org profile seeded as Northwind). The agent read all four (incl. the nested
  attachment), used **company memory**, produced a correct gap analysis + a successful tracked-changes
  redline. **Real fix committed:** the **arq-worker had no S3/MinIO env** (api/ingest did) → storage-backed
  agent tools failed in the worker; added the S3 block to `docker-compose.yml`. Dev-only/local (NOT
  committed): `LQ_AI_DOCLING_ENABLED=false` (Docling hung PDFs to its 300s timeout) and the seeded org
  profile. Full findings: memory `commercial-agent-live-uat-findings`.

## ▶ PICK UP EXACTLY HERE — C3b-2 (gateway-routed consolidation/Lint — the ADR-F010 egress slice)

**Read first:** `docs/fork/plans/C3b-typed-facts-consolidation.md` §C3b-2 + `docs/adr/F042`. C3b-1 shipped the
typed fact store + the guarded `record_matter_fact` write + supersede + the as-of/`live_facts`/`memory_log`
read helpers (all ZERO model calls). C3b-2 adds the **automated** hygiene on top:
- The **in-run guarded tool** `consolidate_matter_memory` (maintainer's choice — no arq post-run hook exists,
  agent tools need a running run). It loads the matter's live fact set **whole** (tens of rows — NO embeddings;
  the gateway `/v1/embeddings` is 501 until B6) + the wiki, routes the mem0 extract→judge
  ADD/UPDATE/DELETE/NOOP loop + Karpathy/OpenClaw Lint through **`GatewayClient.chat_completion`** (precedent:
  `playbooks/easy/extractor.py`, `autonomous/guard.py:_handle_gateway_inference`) under a **new `lq_ai_purpose`**
  (register in `gateway/app/api/inference.py` `_KNOWN_PURPOSES`), then supersedes stale facts (sets
  `invalid_at`/`superseded_by`) — **pinned corrections stay immutable to the loop**.
- **This is where the ADR-F010 egress obligation lands** — every model call through the gateway; add the
  no-`api.openai.com`/no-direct-provider assertion on the path; guard + cost-meter via `guarded_dispatch`.
  **Draft ADR-F043** (egress + the new purpose + the model-calling tool).

**Then C3c** (matter-scoped `memory_search`/`memory_get` + cockpit memory panel: see/edit/undo/provenance +
the undo/revert REST endpoint — C3a writes `wiki_snapshot` rows, C3b-1 ships `facts_valid_at`/`live_facts`/
`memory_log` as the read substrate).

**Carried C3a follow-up (small):** the deferred nit — marker-fence delimiter-injection hardening (strip/escape
a block's own BEGIN/END markers from untrusted bodies, OR a per-run nonce delimiter) applies uniformly to the
client block + matter-memory blocks; do it as a cross-cutting hardening slice, not piecemeal.

**Other COMM slices (maintainer's call, after the C3 track):** **C5** negotiation rounds (needs C3+C4) · **C6**
controlling playbook skills (needs F036+F038) · **C7** complex-deal fan-out + **redline download UI** (the
redlined `File` is created `status ready` but nothing surfaces it). **C9 follow-up (small, C8/F041 track):**
mutualisation worked-example in `skills/surgical-redline/SKILL.md` + a redline step-budget tier (NDA hit
`cap_exceeded` on pro); pre-teach the D-gate rules (flash thrashed ~8 preview retries). **C8 follow-ups
(optional):** broaden worked examples beyond MSAs; the ~1/6 no-redline runs; re-run the eval on a stronger model.

## Gotchas / durable traps (C8 + C4 + carried)

- **C8 — Adeu crashes on a PURE zero-width insertion** (`new_text` that merely appends after an unchanged
  anchor → `Op=INSERTION at [n:n]` → `AttributeError` in `adeu/redline/engine.py`). Fold an addition into
  the **boundary** instead (end the anchor at the clause's punctuation, replace it and continue — the working
  §9 carve-out shape). The skill teaches this; `preview_redline`/`apply_redline` catch the crash and return
  `_EDITOR_ERROR_MSG` (no partial write). Golden/skill examples MUST use the boundary pattern.
- **C8 — the surgical-craft eval is provider-marked** (`test_commercial_redline_eval.py`): run live with
  `LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_REDLINE_EVAL_REPS=N UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c8`.
  It regenerates ALL eval files in one run — if a (doc,rep) yields no redline, no per-rep file is written, so
  reconcile the dir against `eval-report.json` before committing (delete stale files from a prior run).
- **C9 — builtin `grep`/`glob` crash a run if the backend doesn't implement them.** deepagents exposes
  `grep`/`glob` filesystem tools; `BackendProtocol`'s default `grep`/`glob` `raise NotImplementedError`, and
  the async wrappers (`agrep`/`aglob`) do NOT catch it → the exception leaves the tools node and fails the
  whole run. Any custom backend MUST override `grep`/`glob` to return a `GrepResult`/`GlobResult` (even just
  an `error=`), never inherit the raise. Fixed for `RegistrySkillBackend` (C9); watch for it in any future
  backend. **C9 manual harness** (`test_commercial_redline_manual.py`, provider-marked) writes per-MODEL dirs
  (`c9/flash`, `c9/pro`) with a merge-safe `manifest.json`; `LQ_AI_C9_ONLY` runs a subset. The one open craft
  weakness it found is **pervasive mutualisation** (see pickup) — flash rip-and-replaces, pro can `cap_exceeded`.

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
- **Migration head is `0070`** (`0070_matter_memory_typed_facts.py`, C3b-1 — additive-nullable typed-fact
  columns on `matter_memory_entries`; `0068` is the store, `0069` the skill binding). Re-check the head before
  writing in case anything lands first. Fresh-head check before any migration; rebuild api+arq-worker+
  ingest-worker after one; never host-side `alembic upgrade` on the dev DB; never `compose down -v`.
- **C3b-1 — a Pydantic `datetime` field accepts a tz-NAIVE value from a bare ISO date** ("2026-01-01" parses
  with `tzinfo=None`). Comparing it against a tz-aware `DateTime(timezone=True)` column raises `TypeError`,
  which escapes a guarded tool as a CRASH (audited error + re-raised), not a reject-and-retry. Any datetime the
  model supplies must be normalised to UTC-aware at the schema boundary (`RecordMatterFactInput._valid_from_utc`
  is the pattern: `replace(tzinfo=UTC)` if naive, else `astimezone(UTC)`). Tests using only `+00:00` offsets
  mask it — add a bare-date case.
- **🔴 SKILL.md frontmatter must not contain an unquoted `": "` (colon-space) in any value (`description:` is
  the usual culprit).** The loader does `yaml.safe_load`; an unquoted plain scalar with `": "` parses as a
  mapping → `frontmatter YAML is invalid: mapping values are not allowed here` → the loader logs a WARNING and
  **silently skips the skill** (it vanishes from the registry; bound skills are filtered to known names, so the
  binding is silently dropped). This bit C8's `surgical-redline` (never loaded until C3a fixed it) and C3a's
  `matter-memory`. Use " — " / "," / "(…)", or quote the value. Guarded now by
  `test_every_real_skill_loads_no_silent_drops` (`tests/test_skill_loader.py`) — run it after adding/editing any SKILL.md.
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
