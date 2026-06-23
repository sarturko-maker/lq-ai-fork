# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ C8 ✓ C9 ✓ + cockpit chat-UX ✓. C3 REFRAMED → matter-memory track (C3a/b/c); ADR-F042 ACCEPTED. C3a ✓ (matter-wiki MVP — auto-write tool + human-pinned corrections + injection, all areas; live-proven on DeepSeek). NEXT = C3b (typed bi-temporal facts + gateway-routed consolidation).**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns. C9 fact: `deepseek` → `deepseek-v4-flash`;
**`deepseek-pro` → `deepseek-v4-pro`** (both wired in `gateway.yaml`, same DeepSeek account/quota) — the
stronger tier for the "is it the model?" control.

## Done this session (C3a — matter-wiki MVP SHIPPED; branch `fork/c3-matter-memory`)

**What:** the unit-of-work memory tier is now **auto-write-then-correct** (ADR-F042, accepted). The agent
auto-maintains a brief *matter wiki* (the existing `projects.context_md`) via ONE guarded tool; the lawyer
*corrects* via a human-authenticated endpoint; both inject read-only into every run under a lower-trust fence.
**All areas** ("Matter memory" / "Programme memory"). Proven live on DeepSeek.

- **Migration `0068`** (`matter_memory_entries`: id·project_id·user_id·kind(correction|wiki_snapshot)·body_md·
  trust(normal|human-pinned)·run_id·superseded_at·created_at; additive-nullable so C3b layers typed bi-temporal
  columns with no backfill) + **`0069`** (binds the `matter-memory` skill to all 5 areas) + ORM
  `MatterMemoryEntry` in `models/project.py`. **Head is now `0069`.** Up/down/up verified on a throwaway DB.
- **`app/agents/matter_memory_tools.py`** — the ONE agent tool `update_matter_memory(content_md)`: rewrite the
  wiki in place through `guarded_dispatch` (validate via `schemas/matter_memory.UpdateMatterMemoryInput`,
  **reject-not-truncate** on oversize/blank), snapshot the prior body (`kind='wiki_snapshot'`, undo), **guard
  auto-audit ONLY** (no domain audit row — no body leak). Writes only the wiki + snapshot, **never** a
  correction/`human-pinned` row. + `load_pinned_corrections` / `format_corrections_block` for injection.
- **`app/agents/composition.py`** — inject the wiki + pinned corrections under a **lower-trust fence**
  (`MATTER_MEMORY_PROMPT` / `MATTER_CORRECTIONS_PROMPT`), order base→matter→client→**wiki→corrections**→area
  (area LAST); heading from the **`PracticeArea` ORM row** `unit_label` (default "Matter memory"); loaded inside
  `if project is not None:`; the tool granted to **every** matter-bound run (disjoint from ROPA/commercial grants).
- **`app/api/matter_memory.py`** — `POST /api/v1/matters/{project_id}/memory/corrections`, the **only** writer
  of `trust='human-pinned'`: `author` from the **session** (B2 — no agent path can mint a pin), `_load_visible_project`
  → **404** on cross-user/archived, audited `matter_memory.pin` (IDs/counts only).
- **`skills/matter-memory/SKILL.md`** — curation craft (keep brief, fold in, record facts with source, never
  contradict a pin); bound to all areas via `0069`.
- **ADR-F042 accepted**; CLAUDE.md + F030 §2A pointer were aligned in the prior planning commit.
- **Adversarial review (workflow, 3 lenses → per-finding verify): 0 blockers, 2 should-fix + 5 nits, all
  addressed** (Privacy end-to-end heading test added; dead constants wired live via `_in_set`; `extra="forbid"`;
  deterministic ordering; archived re-check; redundant `.strip()` dropped). 1 nit deferred (marker-fence
  delimiter-injection — inherited convention shared with the client block; cross-cutting hardening, not C3a).
- **🔴 Discovered + fixed a PRE-EXISTING bug:** `skills/surgical-redline/SKILL.md` (C8) had an unquoted `": "`
  in its `description:` frontmatter → **silently failed to load** (the loader logs a warning + skips). The C8
  craft skill was **never in the registry** — plausibly part of C9's "pervasive mutualisation" craft weakness.
  Fixed (same `": "` bug bit matter-memory). Added a **CI guard** (`test_every_real_skill_loads_no_silent_drops`)
  asserting no on-disk SKILL.md is silently dropped. **19/19 skills now load (was 17/19).**
- **Live (DeepSeek, evidence `docs/fork/evidence/c3a/live-matter-memory.json`):** run A — the agent called
  `update_matter_memory` and wrote a high-quality structured wiki (parties/roles/doc/headline-terms table);
  the lawyer pinned a correction; run B (new run) — the agent recalled the matter AND the **pinned correction
  survived** the agent's own re-curation. (Run predated the skill-load fix; the agent succeeded on the tool
  docstring alone — the skill is additive craft, now loading.)
- **Tests:** `test_matter_memory_tools.py` (grant/disjoint, auto-write+snapshot, reject-not-truncate, blank,
  no-fabrication, no-overwrite, audit-no-body) · `test_matter_memory_api.py` (pin author-from-session,
  cross-user/archived 404, blank/oversize 422, audit-no-body) · `test_agent_composition.py` (+lower-trust fence
  ordering, empty-degrades, default + **Privacy "Programme memory"** heading end-to-end, all-areas grant) ·
  `test_skill_loader.py` (no-silent-drops guard). Full local gate green: ruff+format+mypy (189 files);
  new+affected+regression suites pass.

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

## ▶ PICK UP EXACTLY HERE — C3b (typed bi-temporal facts + gateway-routed consolidation)

**Read first:** `docs/fork/plans/C3-matter-memory-track.md` §C3b + `docs/adr/F042-...`. C3a shipped the wiki +
enforced corrections; C3b adds the typed depth over the **same `0068` store** (additive-nullable, no backfill):
- Typed entry columns (port Graphiti): `value/fact`, `author`, `source_citation` (→ Citation Engine ids),
  `superseded_by`, `valid_at`, `invalid_at`, `type`. Supersede = set `invalid_at`, never delete; pinned
  corrections stay immutable to the loop.
- The append-only **log** + a **gateway-routed consolidation/Lint pass** (port mem0's extract→retrieve→
  ADD/UPDATE/DELETE/NOOP loop + Karpathy/OpenClaw Lint). **C3b is where the ADR-F010 egress obligation lands** —
  every model/embedding call routes through `guarded_tool_call`; add the no-`api.openai.com` assertion on any
  ported path (C3a made ZERO model calls).
- The "**what did we believe at signing**" as-of query (`valid_at ≤ T < invalid_at`).

**Then C3c** (matter-scoped `memory_search`/`memory_get` + cockpit memory panel: see/edit/undo/provenance +
the undo/revert REST endpoint — C3a already writes `wiki_snapshot` rows as the undo substrate).

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
- **Migration head is `0069`** (`0069_matter_memory_skill_binding.py`, C3a; `0068_matter_memory_entries.py` is
  the store). Re-check the head before writing in case anything lands first. Fresh-head check before any
  migration; rebuild api+arq-worker+ingest-worker after one; never host-side `alembic upgrade` on the dev DB;
  never `compose down -v`.
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
