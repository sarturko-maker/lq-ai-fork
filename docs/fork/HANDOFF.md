# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ C8 ✓ C9 ✓ + cockpit chat-UX ✓. C3 REFRAMED → matter-memory track (C3a/b/c); ADR-F042 ACCEPTED. C3a ✓ · C3b-1 ✓ · C3b-2 ✓ (ADR-F043) · C3c-1 ✓ (READ backend, ADR-F044) · C3c-2 ✓ (cockpit Memory panel) · C3-UM ✓ (the human "update memory" UX — pin composer + inline correct-a-fact + retire). The ENTIRE matter-memory track (read + write + human-correct) is SHIPPED. **C8/C9 redline-eval RE-RUN ✓** (2026-06-24): re-ran both
craft evals with the `surgical-redline` skill LOADED — confound removed, finding CONFIRMED. **REDLINE WORD-DIFF ✓**
(2026-06-24, branch `fork/redline-worddiff-adeu`, **ADR-F045**): the redline tool now renders surgically via Adeu's
NATIVE `adeu.diff.generate_edits_from_text` (applied via `engine.apply_edits` to bypass `validate_edits`) instead of
the wholesale prefix/suffix-trim path that SWALLOWED interiors; skill simplified to "quote the clause, change only the
necessary words — the tool diffs it." **Live-judged (Claude Opus 4.8): C9 surgical-pass 3/7 → 6/7, the Aegis NDA
pervasive-mutualisation case now STRONG·surgical (survived the refuter), seam defects eliminated.** **NEXT = maintainer's
call: C7 (fan-out + redline-download UI) / C5 (negotiation rounds) / C6 (controlling playbook skills).**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns. C9 fact: `deepseek` → `deepseek-v4-flash`;
**`deepseek-pro` → `deepseek-v4-pro`** (both wired in `gateway.yaml`, same DeepSeek account/quota) — the
stronger tier for the "is it the model?" control.

## Done this session (REDLINE WORD-DIFF — branch `fork/redline-worddiff-adeu`; ADR-F045; NO migration / deps)

**What:** the redline TOOL now produces surgical tracked changes itself, so the model only has to preserve unchanged
wording. Root cause of the C8/C9 swallow (read from Adeu's engine source): our adapter sent ONE wholesale
`ModifyText` per edit → Adeu's `_pre_resolve_heuristic_edit` trims only common prefix/suffix → **swallows unchanged
interiors**. Plan `docs/fork/plans/redline-worddiff-via-adeu.md`; ADR-F045; headline `docs/fork/evidence/c9/SUMMARY.md`.

- **`api/app/agents/redline_service.py` (the fix):** new `_word_diff_edits(engine, edits)` — for each
  `(target,new)`, diff `full` vs `full.replace(target,new)` via `adeu.diff.generate_edits_from_text` (sub-edits carry
  full-document `_match_start_index`), rationale on the first sub-edit; `dry_run`/`apply` now call
  **`engine.apply_edits(...)` directly, NOT `process_batch`** (the canonical `adeu.sanitize.core` pattern — bypasses
  `validate_edits`' per-sub-edit uniqueness check, which would reject a short region like "the Customer"; `apply_edits`
  trusts the positional index). **Wholesale fallback** when `full.count(target)!=1` (rare whitespace mismatch; D4
  already guarantees uniqueness in the doc text) — logged counts-only. Removed dead `_counts`.
- **`skills/surgical-redline/SKILL.md` → v2.0.0:** dropped the anchor-mechanics / decompose / "split the block" /
  "fold into the boundary" coaching; teaches "quote the clause, change only the necessary words, keep the rest
  verbatim — the tool diffs it." Skill-loader guard re-run green (no `": "` silent-drop).
- **`api/app/agents/commercial_tools.py`:** tool docstrings + preview self-review text realigned to the new approach.
- **`api/app/schemas/commercial.py`:** removed dead `changed_regions()`. **Gate D1–D5 UNCHANGED** — it keys on the
  minimal token diff (renderer-agnostic) and still guards genuine over-rewording; no threshold change (unverifiable
  at n=1, ADR-F045).
- **Empirically proven before coding** (read Adeu's `engine.py`/`diff.py`/`sanitize/core.py`; scratchpad
  `worddiff_design_probe2.py`): indemnity → 3 regions verb-phrase bare, multi-edit batches don't cross-contaminate,
  genuine rewrite still ONE block (renderer doesn't fake surgery), hyphen/underscore no corruption.
- **Verify:** `test_redline_service.py` 10/10 (5 new word-diff cases) · gate/loader/tools 52 · broad non-provider
  regression **513 passed** · ruff check+format clean · mypy clean on changed files. **Live (DeepSeek flash, C9
  harness, all 7 instruments + Claude-judge via `scratchpad/c9-judge.js`): surgical-pass 3/7 → 6/7, STRONG 6/7,
  redlined 7/7, boilerplate-bare 6/7 → 7/7; Aegis NDA mutualisation STRONG·surgical (refuter held); seam-defect
  duplication eliminated (deterministic scan).** The lone ADEQUATE (Meridian) is the model *choosing* to
  wholesale-rewrite a warranty disclaimer — a genuine rewrite the renderer correctly preserves, NOT a swallow.
  Evidence: `c9/flash`, `c9/verdicts/*.md`, `c9/SUMMARY.md` (v3) + `c9/v2-wholesale-render/` (archived v2).

### Earlier (C3c-2 — cockpit matter-memory panel SHIPPED; PR #137, branch `fork/c3c2-cockpit-memory-panel`)

**What:** the **frontend half** of the matter-memory tier (ADR-F042 §C3c) — a new **"Memory" tab** in the
cockpit's matter view rendering the C3c-1 composite + a human-authenticated wiki revert. **Pure frontend over
existing endpoints: no backend change, NO migration** (head stays `0070`), **zero new deps**. **Maintainer
chose** (AskUserQuestion): **Memory tab on ALL matters, any area** + **revert behind a confirm dialog**
(disabled while a run is active). No new ADR — F044 stays the governing decision (noted in the PR).

- **`web/src/lib/lq-ai/components/matter/MemoryPanel.svelte` (NEW)** — one scrollable view, four sections
  (Working summary / Facts / Pinned corrections / Activity log). `<script module>` exports the pure helpers
  (`logKindLabel`/`isRevertable`/`shortRunId`/`logTailNote`/`canRevert`) — the codebase has **no
  @testing-library/svelte**, so logic is tested at the helper layer (pattern: `MatterCard`/`AttachKBModal`).
  Mirrors `RopaRegister` for the `loadGeneration` out-of-order guard + the `runActive` `schedulePoll`/`stopPoll`
  poll + the `reloadKey` settle-reconcile. Revert = a `wiki_snapshot` log row → confirm `Dialog` → POST →
  refetch; **disabled while `runActive`** (don't race the agent). **Every** model-authored body
  (`content_md`/`body_md`/`body_preview`) renders through `renderModelMarkdown` (DOMPurify, media-forbid) —
  the only `{@html}`, never raw.
- **`web/src/lib/lq-ai/api/matterMemory.ts` (NEW)** — `readMatterMemory(id)` (GET) + `revertWiki(id, snap)`
  (POST `{snapshot_id}`) over `apiRequest` (base already `/api/v1`); barrel-exported as `matterMemoryApi`.
- **`web/src/lib/lq-ai/types.ts`** — hand-written interfaces mirroring the C3c-1 Pydantic models exactly
  (datetimes = ISO strings); **no frontend OpenAPI contract test exists** (verified) so nothing else to update.
- **`web/src/lib/lq-ai/cockpit/ConversationHost.svelte`** — widened `matterTab` to add `'memory'`; derived
  `matterTabs` (conversation always; `register` only narrow-Privacy; `memory` whenever a matter is set; **none
  for the unfiled bucket**). The conversation/register region stays **MOUNTED** under `class:hidden` so the
  live SSE stream + `runActive` never drop on a tab switch; `MemoryPanel` is a sibling `{#if}`. **No-remount
  invariant preserved** (verified by the reviewer).
- **Adversarial review (fresh-context, 8 lenses → per-finding refutation): SHIP — 0 blockers, 0 should-fixes,
  2 NITs, both folded:** (1) reset `matterTab`→`conversation` when the active tab leaves the strip (Privacy
  widen retires the register tab → nothing highlighted); (2) clear the revert dialog's target/error on close.
- **Verify:** `npm run check` 0 errors (5 pre-existing warnings); vitest **915 passed** (+11 new); eslint +
  prettier clean on all touched files. **Real-stack smoke** (rebuilt `api`): `GET /matters/{id}/memory` → 200
  with the exact composite shape. **Headed Cypress** (`c3c2-matter-memory.cy.ts`, rebuilt `web`): **2/2** —
  render-the-four-sections + revert round-trip (confirm dialog → POST `{snapshot_id}` → refetch) + the
  screenshot matrix → `docs/fork/evidence/c3c2/` (light/dark × wide/narrow, all visually verified clean; the
  Privacy capture shows Memory **beside** the ROPA register, proving the all-areas placement).

### Previous slice (C3c-1 — matter-memory READ backend; merged #136, ADR-F044, branch `fork/c3c1-matter-read-revert`)

The read/manage **backend** (this slice's dependency): two guarded agent read tools — `search_matter_memory`
(Python keyword match over the **LIVE** corpus, no SQL from the model, superseded facts never resurface) +
`matter_facts_as_of` (bi-temporal as-of; the date is reject-not-crash hardened via a `mode='before'`
`_require_iso_date_string` + `_utc_aware`) — granted to every matter-bound run, all areas, disjoint grant. A
composite `GET /matters/{id}/memory` (wiki + live facts + live corrections via the new uncapped
`live_corrections` + capped/counted log) and a human-authenticated `POST .../memory/wiki/revert {snapshot_id}`
(restore a chosen `wiki_snapshot`, snapshot-current-first → reversible, append-only; triple-scoped lookup →
404; **no agent revert tool**). **No migration; no model calls.** Full detail: memory `c3c1-matter-read-revert-shipped`.

### Previous slice (C3b-2 — gateway-routed consolidation/Lint SHIPPED; merged #135; branch `fork/c3b2-gateway-consolidation`)

(C3a — PR #133; C3b-1 — PR #134 [[matter-facts-c3b1-shipped]]: the typed bi-temporal fact ledger, ZERO model
calls. C3b-2 builds the automated hygiene on top.)

**What:** the matter agent can now **consolidate its own memory** in one tool call — the **first matter-memory
code that calls a model**, so the **ADR-F010 egress obligation lands here**. `consolidate_matter_memory` loads
the matter's live fact set whole + the wiki + the pinned corrections, routes **ONE** gateway chat completion
(mem0 extract→judge + Lint) under a new `lq_ai_purpose`, then applies the proposal **supersede-only** (retire /
replace — never delete, never edit a body in place) and **rewrites the wiki**. **Maintainer chose** (AskUserQuestion):
**facts + wiki**, **supersede-only**, **match the R4-no-op cost posture + gateway audit**. **No migration** (reuses
`0070` + `context_md`); **zero new deps**. Plan `docs/fork/plans/C3b-2-gateway-consolidation.md`; **ADR-F043** (proposed).

- **`app/agents/matter_consolidation.py` (NEW)** — `MATTER_CONSOLIDATION_TOOL_NAMES` (disjoint),
  `build_matter_consolidation_tools(session_factory, *, run_id, binding, gateway_factory=get_gateway_client)`
  (the **gateway DI seam** tests override), the zero-arg guarded `consolidate_matter_memory()`, and
  `_consolidate_matter_memory` = load → ONE `gateway.chat_completion` (`max_tokens` cap, `anonymize=False`,
  `lq_ai_purpose="consolidate_matter_memory"`) → lenient JSON parse → **pure validation pass** (every op id a
  LIVE `kind='fact'` row of THIS matter; no double-ref; temporal coherence for retire AND replace) → **all-or-nothing
  supersede-only apply** + `snapshot_and_rewrite_wiki`. A gateway error / truncation / malformed output / bad id
  → **reject-and-retry string, never a crash, zero writes**.
- **`schemas/matter_memory.py`** — `RetireConsolidationOp`/`ReplaceConsolidationOp` (discriminated on `op`) +
  `ConsolidationResult` (`extra='forbid'`, `new_wiki` ≤ wiki budget); extracted shared `_utc_aware` /
  `_absent_if_blank` helpers (C3b-1's `RecordMatterFactInput` now reuses them — single-sources the tz fix).
- **`app/agents/matter_memory_tools.py`** — extracted `snapshot_and_rewrite_wiki(...)` from `_update_matter_memory`
  (single-sources the snapshot+overwrite for C3a + C3b-2).
- **`app/agents/composition.py`** — grants `build_matter_consolidation_tools(...)` to **every** matter-bound run
  (all areas), beside the memory + fact grants; disjoint.
- **Gateway** — `consolidate_matter_memory` added to `_KNOWN_PURPOSES` (`gateway/app/api/inference.py`) +
  documented (`openai_schema.py`) + the propagation test (`test_inference_b4.py`). **⚠ frozenset at module load
  → the gateway must be RESTARTED to recognise the purpose** (unknown purposes fall back to `chat`, so the call
  still succeeds — only the routing-log tag differs until restart).
- **B2 carries over (structural):** corrections are read-only prompt input; the apply only touches live
  `kind='fact'` rows (a correction/cross-matter/superseded/invented id is unreachable) — no-fabrication +
  no-overwrite hold without prose. The tool's only model access is the injected `GatewayClient` (asserted by a
  unit test + an AST-parse egress guard — no provider SDK).
- **Adversarial review (workflow, 5 lenses → per-finding refutation): 0 blockers, 1 should-fix + 6 nits; 2 refuted.**
  Folded: **should-fix** = a `retire` of a *future-dated* fact set `invalid_at=now < valid_at` → DB CHECK crash
  (now rejected in validation, + regression test); nits = bound the echoed parse-error text, detect
  `finish_reason='length'` truncation → diagnosable reject, single-source the resolved `valid_at`
  (validation→apply), drop the dead `model_alias` builder kwarg, distinct `MAX_SUPERSEDES` constant. **Deferred**
  (documented): the DB connection held across the gateway await (consistent with every guarded tool; no lock).
- **Verify:** ruff (CI-exact 0.15.18) + format + mypy `app` clean; gateway mypy `--strict` + ruff clean;
  gateway suite **595 passed** (purpose test 3/3; lone `test_model_discovery` failure is pre-existing env-sensitive,
  reproduces in isolation, CI-green on main); **full api suite 2585 passed / 2 skipped** (lone failure = the
  documented env-sensitive `test_ready`).
- **Live (DeepSeek, `docs/fork/evidence/c3b2/live-matter-consolidation.json`):** seeded a duplicate party fact +
  a stale draft cap; the agent called `consolidate_matter_memory` → **`deepseek-pro` retired the duplicate**
  (`superseded_count=1`, `live_fact_count` 3→2, `total_fact_rows` stays 3 — **supersede-only, history preserved**)
  + rewrote the wiki; `status=completed`, no crash. **Craft finding (ADR-F015):** flash returned an all-NOOP (didn't
  dedupe); pro's first attempt set a `valid_from` ≤ the prior's `valid_at` → the temporal check **correctly
  rejected it** (no crash, agent surfaced "consolidation failed") — proving the validation works; a **prompt fix**
  (dedupe = RETIRE the redundant copy; `valid_from` only for a genuine LATER value change) then made pro
  consolidate cleanly. The supersede/wiki mechanics are deterministically covered by 19 unit tests.

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

## ▶ PICK UP — REDLINE WORD-DIFF SHIPPED (ADR-F045); next = maintainer's call (C7 / C5 / C6)

**C3-UM (the human "update memory" UX) is DONE** on branch `fork/c3-update-memory-ux` (squash-merged; the whole
matter-memory track is now complete). What shipped — three human gestures on `MemoryPanel.svelte`, all
overlay/append-only per ADR-F042, disabled while a run is active:
1. **Pin a correction** — `+ Pin a correction` composer (textarea + char cap) → `POST .../memory/corrections`
   (the existing C3a human-authenticated pin, `trust='human-pinned'`). Pin VISUAL = F013 brand-left-accent.
2. **Correct a fact** — a quiet `Correct` on each Fact row pre-fills the composer with a `Re: "…" →` stub
   (free-text, **no DB link** — maintainer chose free-text over an anchor column → NO migration). Still a
   plain correction (B2 no-overwrite).
3. **Retire** — quiet `Retire` on a correction (soft `superseded_at`) AND on a fact (close `invalid_at`),
   shared confirm dialog. **Maintainer chose corrections + facts.** NO free-edit of the working summary (it's
   agent-regenerated; levers stay pin + revert).

**Backend (NO migration, head stays `0070`):** two new endpoints in `api/app/api/matter_memory.py` —
`POST .../memory/corrections/{entry_id}/retire` (idempotent soft-retire) + `POST .../memory/facts/{entry_id}/retire`
(close window; **future-dated fact `valid_at >= now` → 409 Conflict**, never the `invalid_at > valid_at` CHECK 500;
the C3b-2 trap). Both owner-scoped 404 + kind-scoped, audit IDs-only, tz-aware `datetime.now(UTC)`. Frontend:
`api/matterMemory.ts` (`pinCorrection`/`retireCorrection`/`retireFact`) + `types.ts` + the `MemoryPanel.svelte`
gestures (`canWrite` aliases `canRevert`; one shared retire dialog). **Traps hit:** new endpoints must be
registered in BOTH `tests/test_endpoints.py` `IMPLEMENTED_ROUTES` AND `tests/test_openapi.py` `EXPECTED_PATHS`
(+ bump the hardcoded `len(actual) == N` path count) or the meta-tests fail; new path params need a value in
`test_endpoints.py` `_PARAM_VALUES` (`entry_id`).
**Verify:** api 2627 passed (lone failure = the documented env-flake `test_ready` — expects 503 but the dev-image
runs on the live network so deps are reachable → 200; CI-green in a clean env). web 926 vitest + `npm run check`
0 err + Cypress 2/2 + live Atlas smoke (pin→retire-correction→retire-fact, idempotent, cross-kind 404). Evidence
`docs/fork/evidence/c3-um/`. No new ADR (F042/F044 govern).

**Disk-cleanup folded into the same PR** (Crostini hit 100% full, 2026-06-24): root cause = btrfs storage-driver
subvolume leak (690+ orphaned layers from frequent ~6 GB rebuilds). Reclaimed ~100 GB (3.9 GB → 82 GB free; rebuild
brought it to ~74 GB). Prevention = CLAUDE.md rebuild-time rule (`docker image prune -f` after every build,
dangling-only) + `scripts/docker-prune.sh` (dangling + stopped containers + leftover `lq_ai_test_*`), no cron.
**Recovery playbook if it recurs:** `docker system prune -af` (keeps running-stack images + volumes); if orphaned
btrfs subvolumes persist, `apt-get install btrfs-progs`, stop docker, delete `/var/lib/docker/btrfs/subvolumes/*`
(safe when `docker images` is empty), then `rm -rf /var/lib/docker/{image,buildkit,btrfs,containers}` (KEEP
`volumes`+`network`), restart docker, `compose up -d --build`. The btrfs cleaner reclaims on the first commit
(starting docker triggers it). See [[redline-viewing-direction]] memory for the new redline-viewer roadmap input.

**Test vehicle on the dev stack:** the **Atlas** Commercial matter (`905720d1-5d17-43cd-a8f0-3a76d095de34`, owner
admin) seeded with a wiki + 2 wiki snapshots + 5 live facts + 1 superseded fact + 1 human-pinned correction.
Deep-link `/lq-ai?area=commercial&matter=905720d1-5d17-43cd-a8f0-3a76d095de34` → **Memory** tab.

**▶▶ PICK UP HERE — REDLINE WORD-DIFF SHIPPED; next slice = maintainer's call.** The redline-craft track's
renderer fix is done (ADR-F045): the tool keeps interiors bare via Adeu's native word-diff, the skill is
simplified, and the live C9 re-judge confirms surgical-pass 3/7→6/7 with the NDA mutualisation case (the prior
slices' headline weakness) RESOLVED. The MILESTONES § Backlog "C8/C9 redline-craft follow-ups" are now largely
**addressed**: the grant-clause wholesale-strike + the seam/duplication defect are both fixed by the renderer (no
separate worked-example or overlap-guard slice needed). **Remaining open commercial slices (maintainer picks):**
**C7** fan-out + **redline-download UI** (the most-requested — lets a lawyer download the redlined `.docx`); **C5**
negotiation rounds; **C6** controlling playbook skills. **Optional deeper verification** (not blocking): a
multi-rep × strong-judge eval to put a confidence interval on the 6/7 surgical-pass (n=1 today; the renderer's
interior-bare property is already unit-test-proven, so this only tightens the *model-behaviour* estimate). **Carried
cross-cutting:** marker-fence hardening (C3a nit); embedding/FTS search UI (gateway `/v1/embeddings` 501 until B6);
log pagination.

## Gotchas / durable traps (C8 + C4 + carried)

- **C3c-2 — the `web` container serves a PRE-BUILT bundle; rebuild it before any UI/Cypress verification**
  (`docker compose up -d --build web`) or you test stale code (a CLAUDE.md hard rule — bit the cockpit
  screenshot workflow). Headed Cypress needs `DISPLAY=:0` (`X0`/`X1` sockets present on this box).
- **C3c-2 — no `@testing-library/svelte` in `web/`.** Test Svelte component LOGIC by exporting pure functions
  from `<script module>` and unit-testing those (pattern: `MatterCard`/`AttachKBModal`); cover DOM + interaction
  via Cypress. Don't add the library (CLAUDE.md: justify every dep).
- **C3c-2 — cockpit Cypress nav:** deep-link `/lq-ai?area=<key>&matter=<id>` and wait for
  `[data-testid="lq-cockpit-conversation"]`. At narrow/stacked width a fresh deep-link (no `&thread=`) shows the
  thread LIST, not the panel where the matter tab strip lives — click `lq-cockpit-new-conversation` to enter the
  panel first, THEN the `lq-cockpit-matter-tab-{id}` tabs (incl. `…-memory`) are reachable.
- **C3c-2 — adding a cockpit tab must NOT remount the conversation pane.** Keep the conversation/register region
  MOUNTED behind `class:hidden={matterTab === '…'}` and render the new view as a SIBLING `{#if}`; moving
  `{@render conversationPane()}` to a new DOM position remounts `ConversationPanel` → drops the live SSE stream
  and resets the bound `runActive`. Also reset `matterTab` to a tab that's always present when the active tab can
  leave the derived strip (e.g. a Privacy matter widening past the split budget retires the `register` tab).
- **C3c-2 — any `{@html}` of model output needs `renderModelMarkdown` + an `eslint-disable-next-line
  svelte/no-at-html-tags` comment** (the shared sanitizer is DOMPurify media-forbid; raw `{@html}` fails lint
  and is an XSS sink). Every matter-memory body (`content_md`/`body_md`/`body_preview`) is untrusted model text.

- **F045 — the redline renderer uses Adeu's NATIVE word-diff applied via `engine.apply_edits`, NOT
  `process_batch`.** `redline_service._word_diff_edits` diffs `full` vs `full.replace(target,new)` with
  `adeu.diff.generate_edits_from_text` (sub-edits carry full-document `_match_start_index`), then
  `engine.apply_edits(subs)` applies them positionally. **Do NOT switch back to `process_batch`** — it runs
  `validate_edits`, which re-checks each sub-edit's `target_text` for uniqueness and REJECTS a short region
  ("the Customer" recurs) with `BatchValidationError: Ambiguous match`. `apply_edits` trusts the index and
  skips that check (the canonical `adeu.sanitize.core` pattern). The fragment-relative trap: diff the FULL doc
  text, never the bare clause, or `_match_start_index` is relative to the fragment and misplaces. Fallback to a
  wholesale `ModifyText` only when `full.count(target)!=1`. Proof scripts: `scratchpad/worddiff_design_probe2.py`.
- **F045 — a genuine rewrite (every word changed) correctly renders as ONE block; the renderer does not fake
  surgery.** So the surgical signal still depends on the model preserving unchanged wording (the skill teaches
  it) and the gate (D1–D5, minimal-diff) still guards genuine over-rewording. A carve-out APPEND now renders as
  a clean insertion via the word-diff (no more zero-width-insertion crash to dodge) — the skill no longer needs
  the "fold into the boundary" mechanic, though `_EDITOR_ERROR_MSG` remains as a defensive catch.
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

- **C8/C9 re-run — a bound skill's BODY reaches the model ONLY on-demand (ADR-F016 progressive disclosure).**
  deepagents' SkillsMiddleware auto-injects only the skill **index** (name + `description:`) into the system
  prompt; the full SKILL.md body is fetched by the model calling the builtin **`read_file`** on
  `/skills/<name>/SKILL.md`. So "skill loaded + bound" (the premise gate) ≠ "the worked examples are in context"
  — the model must choose to read them. So (1) make the `description:` itself carry the core directive (always
  present); (2) to confirm the body was consulted, look for `read_file` in the manifest `tools_called` (distinct
  from `read_document`, the matter-doc reader) and/or the redline reproducing the skill's worked examples.
- **C8/C9 re-run — redline craft at n=1 is NOISE; the `surgical` boolean is judge-borderline.** C9 is one run per
  (instrument, model); the surgical-pass *count* swings on borderline "is a bare-grant-clause wholesale rewrite
  surgical?" calls — even the *same* Claude panel split on it across two runs. Read deterministic signals
  (manifest `redlined`/`boilerplate_bare`) + direct text inspection as primary; treat verdict counts as
  qualitative. A real craft-rate change needs **multi-rep × strong-judge** → **don't ship a craft tweak you can't
  measure**. To compare two runs fairly, re-judge BOTH with the *identical* panel (removes judge drift).
- **C8/C9 re-run — a judge agent given a path to a MISSING `reconstruction.txt` (a no-redline run) will hunt and
  read a DIFFERENT run's file → a verdict for the wrong artifact.** Bit the v1 Meridian + pro DataBridge/Northwind
  cells. **Gate trust on file-existence**: a verdict is valid only if its `reconstruction.txt` exists on disk;
  otherwise use the manifest ground-truth (no-redline).

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
  columns on `matter_memory_entries`; `0068` is the store, `0069` the skill binding; **C3b-2 added NO
  migration** — it reuses `0070` + `context_md`). Re-check the head before writing in case anything lands first. Fresh-head check before any migration; rebuild api+arq-worker+
  ingest-worker after one; never host-side `alembic upgrade` on the dev DB; never `compose down -v`.
  (**C3c-1 added NO migration** — pure read + revert over existing rows/columns; head stays `0070`.)
- **C3b-1 — a Pydantic `datetime` field accepts a tz-NAIVE value from a bare ISO date** ("2026-01-01" parses
  with `tzinfo=None`). Comparing it against a tz-aware `DateTime(timezone=True)` column raises `TypeError`,
  which escapes a guarded tool as a CRASH (audited error + re-raised), not a reject-and-retry. Any datetime the
  model supplies must be normalised to UTC-aware at the schema boundary (now the shared `_utc_aware` helper in
  `schemas/matter_memory.py`, used by `RecordMatterFactInput` + the C3b-2 `ReplaceConsolidationOp`). Tests using
  only `+00:00` offsets mask it — add a bare-date case.
- **C3c-1 — a Pydantic `datetime` field reads a BARE NUMERIC string as a Unix timestamp, not a year.** `"2026"`
  becomes `1970-01-01`, `"1700000000"` becomes 2023 — silently, no reject. On a load-bearing arg (the
  `matter_facts_as_of` date) that is a confidently-wrong recall, not a crash, so `_utc_aware` (a `mode='after'`
  validator) can't catch it. Reject an all-digit string at the boundary with a `mode='before'` validator (the
  shared `_require_iso_date_string` in `schemas/matter_memory.py`, on `as_of` + both `valid_from`s). A `"2026-05"`/
  `"last Tuesday"` is already rejected by Pydantic; only the all-numeric case slips through. Add a `"2026"` test.
- **C3c-1 — `load_pinned_corrections` is the per-run prompt-INJECT slice (newest 30, capped), NOT the search/read
  corpus.** It exists to bound prompt size; reusing it for a read surface silently hides older live corrections.
  The read surface (search + the GET) uses the UNCAPPED `live_corrections(db, project_id)` (oldest-first rows) in
  `matter_fact_tools.py`. Keep the two distinct: capped-bodies-newest-first for injection, uncapped-rows-oldest
  for read.
- **C3b-2 — closing a bi-temporal window must respect the `invalid_at > valid_at` CHECK or the flush CRASHES.**
  Setting `invalid_at` to a time **at or before** a fact's `valid_at` (e.g. retiring a *future-dated* fact at
  `now`) violates `chk_matter_memory_entries_valid_window` → `IntegrityError` on flush → escapes the guarded
  tool as a crash, not a reject. The consolidation validation pass guards BOTH op kinds (`retire`: `now > valid_at`;
  `replace`: `new_valid_at > prior.valid_at`) BEFORE any write. Any future window-closing code must do the same
  pre-flush check. `record_matter_fact`'s supersede already enforces this for its one path; a *retire* (no
  replacement) was the new gap.
- **C3b-2 — a new `lq_ai_purpose` only takes effect after a GATEWAY RESTART** (`_KNOWN_PURPOSES` is a
  module-load frozenset in `gateway/app/api/inference.py`). An unknown purpose falls back to `chat` (the call
  still succeeds), so a live agent run works against an un-rebuilt gateway — only the routing-log tag is wrong
  until the gateway is rebuilt. Rebuild `gateway` when adding a purpose. **Egress-guard test pattern:** assert a
  module's only model access is the injected `GatewayClient` by AST-parsing its imports (forbid
  openai/anthropic/httpx/requests roots) — grepping the source text is fooled by a docstring that *names*
  `api.openai.com` (`test_module_has_no_direct_provider_egress`).
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
