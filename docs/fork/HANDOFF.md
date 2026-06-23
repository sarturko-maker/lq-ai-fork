# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ C8 ✓ C9 ✓ + cockpit chat-UX ✓. C3 REFRAMED → matter-memory track (C3a/b/c); planning + ADR-F042 landed (this session, NO code yet). NEXT = implement C3a.**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns. C9 fact: `deepseek` → `deepseek-v4-flash`;
**`deepseek-pro` → `deepseek-v4-pro`** (both wired in `gateway.yaml`, same DeepSeek account/quota) — the
stronger tier for the "is it the model?" control.

## Done this session (C3 PLANNING ONLY — `fork/c3-matter-memory`; docs only, NO code, NO migration yet)

**What:** the maintainer reframed C3. The old "deal-context propose/accept" plan is **dropped**; the
unit-of-work memory tier is now **auto-write-then-correct** (the agent maintains a brief, evolving *matter
wiki* automatically; the lawyer *corrects* rather than approves each write). Decomposed into a 3-slice track;
governance ADR drafted; reuse research done. **Nothing implemented this session** — next session builds C3a.

- **Two research workflows (web, primary-source-verified):** (1) auto-write vs approve landscape — 11/12
  surveyed systems auto-write-then-manage; per-write approval is the abandoned anti-pattern (Cursor). Both
  maintainer-named systems resolved REAL: **OpenClaw** (MIT, ~380k★, plain-markdown auto-wiki) and **Hermes**
  (Nous, hard-capped always-injected wiki + error-then-consolidate). (2) reuse-vs-build — **zero new deps**:
  take the `MEMORY.md` index+spill+frontmatter format, **port** Graphiti's bi-temporal supersede fields (not
  the pkg → no graph DB), **copy** mem0's ADD/UPDATE/DELETE/NOOP loop as gateway-routed prompts (C3b). Karpathy
  "LLM Wiki" = a real ~38k★ gist but a *concept*, not code. Memos: `docs/fork/research/matter-memory-patterns.md`
  + `matter-memory-reuse.md`.
- **ADR-F042 (proposed)** `docs/adr/F042-unit-of-work-memory-auto-write.md` — unit-of-work memory =
  auto-write-then-correct. **Supersedes F030 §2A** (matter-tier propose/accept; F030 Status-line pointer added,
  body immutable) and **departs from ADR-0013 D4** for the unit-of-work tier ONLY (D4 still governs
  user/autonomous; company/practice stay read-only). **CLAUDE.md §Architecture-rules line edited** to match.
  **Accept before C3a builds.**
- **Track plan** `docs/fork/plans/C3-matter-memory-track.md` — **C3a** (broad MVP: lower-trust fenced injection
  of the matter wiki + corrections, one agent tool `update_matter_memory`, human-authenticated pin endpoint,
  migration `0068`, curation skill) → **C3b** (typed bi-temporal facts + supersede + gateway-routed
  consolidation/Lint) → **C3c** (matter-scoped memory search + cockpit panel + undo endpoint).
- **Adversarial review folded (4 reviewers → 3 blockers fixed):** **B2** the load-bearing one — corrections are
  **human-authenticated only** (`author` from the session via the pin endpoint); **no agent tool may mint a
  `human-pinned` entry** (an agent-asserted "the lawyer said X" is forgeable by injection). Two separate C3a
  tests: **no-fabrication** + **no-overwrite**. B1 (CLAUDE.md contradiction) + B3 (`unit_label` lives on the
  `PracticeArea` row, not `AreaAgentSpec`) fixed; should-fixes folded (lower-trust fence, guard-only audit,
  all-areas + confinement test, additive-nullable C3a→C3b schema, `_load_visible_project` authz, stale-fact
  accepted-limitation).
- **Backlog add:** "search past chat within a matter (all areas)" — distinct from the wiki (`MILESTONES.md`).

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

## ▶ PICK UP EXACTLY HERE — implement C3a (the matter-wiki MVP)

**Read first:** `docs/fork/plans/C3-matter-memory-track.md` (§C3a is implementation-ready, every seam
verified against `main`) + `docs/adr/F042-unit-of-work-memory-auto-write.md`. **Step 0: the maintainer accepts
ADR-F042** (flip `proposed`→`accepted`) — it supersedes F030 §2A + departs from 0013 D4 for this tier; CLAUDE.md
+ F030 already edited to match in this branch.

**C3a build (one PR, at the size line):** ① composition.py — inject the matter wiki (`projects.context_md`) +
the human-pinned corrections block under a **lower-trust fence**, heading from the **`PracticeArea` row**
(`composition.py:230-231`, the local `area`, NOT `area_spec`/`AreaAgentSpec` — it has no `unit_label`; default
"Matter memory" for a no-area matter), area block stays **last**; loads inside the `if project is not None:`
block. ② `api/app/agents/matter_memory_tools.py` — ONE agent tool `update_matter_memory(content_md)` (rewrite
wiki, snapshot prior, reject-not-truncate on oversize, **guard auto-audit only — no domain `audit_action`**).
③ migration `0068_matter_memory_entries.py` (re-check head is `0067`) + ORM (additive-nullable for C3b).
④ `api/app/api/matter_memory.py` — the **human-authenticated** pin endpoint (the ONLY writer of
`trust=human-pinned`, `author` from session, `_load_visible_project` → 404). ⑤ `skills/matter-memory/SKILL.md`
+ binding migration. Grant in the **all-areas** `if binding is not None:` path.

**The two load-bearing C3a tests (B2):** no-fabrication (no agent path mints a `human-pinned` row) AND
no-overwrite (a later `update_matter_memory` can't drop/alter a pinned correction). Plus reject-not-truncate,
audit-carries-no-body, lower-trust-fence-not-obeyed, all-areas incl. Privacy, cross-user/archived 404.

**Then C3b** (typed bi-temporal facts + supersede + gateway-routed consolidation/Lint + as-of "what did we
believe at signing") and **C3c** (matter-scoped memory search + cockpit panel + undo/revert endpoint).

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
- **Migration head is `0067`** (`0067_commercial_surgical_redline_skill.py`, C8). **C3a adds `0068`** (the
  `matter_memory_entries` store — re-check the head before writing in case anything lands first). Fresh-head
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
