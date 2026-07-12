# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

> ═══════════════════════════════════════════════════════════════════════════════════════════════════════
> **SESSION (2026-07-11/12, maintainer travelling — overnight run authorized "run until the morning"):**
> the maintainer's four-thread directive — ① workspace awareness (dup detection + per-doc summaries),
> ② agent-OFFERED adversarial review, ③ "can Agent vs Subagents run different models?", ④ task→model
> ROUTER (research only, reconsider the smart/fast/budget taxonomy, look at Harvey/Legora, OSS-safe).
> Maintainer decisions captured via AskUserQuestion (2026-07-11): review = **agent offers, human
> confirms** (HITL card); duplicates = agent-aware **+ UI badge**; summaries = written **when the agent
> reads** (no eager summarizer).
>
> **① WORKSPACE ✅ BUILT + COMMITTED (branch `fork/workspace-awareness`, ADR-F082, mig 0096) — PR next.**
> WS-1 backend: `files.summary/summary_updated_at/summary_run_id`; `record_document_summary` (guarded,
> area-agnostic, auto-write-then-correct); `duplicate_of_map` = exact-dup from `hash_sha256` computed in
> CODE (matter+owner scoped, soft-delete-safe, never agent-asserted — forgery-proof); inventory gains
> "— summary — (duplicate of X)". WS-2 prompt: 6th read-only tier "Documents in this matter" via
> `render_memory_tiers`→`TierMemoryMiddleware`, data-only fence, 30 lines/8000 chars, VISIBLE "+K more"
> tail. WS-3 surface: `MatterFileRead` + `summary`/`duplicate_of {id,filename}` (server-computed, no raw
> hash); Documents panel amber "duplicate of X" badge + muted summary subtitle (helpers test seam, no
> {@html}). **Verified:** doc-summary suite 15/15; impacted agents suites 143; matter-files/openapi/
> endpoints 11+1skip (contract pin bumped deliberately; fixture hashes made unique-by-default); mypy 242
> clean; web svelte-check 0 err, vitest 1372 (4 new). Full api suite running at handoff-write time.
> **TRAPS (new, on record):** `files.summary_run_id` FK needs a live `agent_runs` row (tests seed one);
> NEVER edit api/ (or add skills/) while a containerized pytest run is collecting off the live repo
> mount — raced twice → phantom fixture errors, clean re-run authoritative; the box OOM-kills a pytest
> container when vitest runs concurrently (suites run ALONE, including vs web builds).
>
> **② ADV (agent-offered adversarial review) ◀ IN FLIGHT (ADR-F084 drafted; task #511 reshaped).**
> Structure locked by research: HITL can only gate a TOP-LEVEL LEAD tool (subagents/`task` are
> un-gateable — `stamp_subagent_opt_out`, `capabilities.py:313`), so `adversarial_review` is a lead tool
> riding the REDLINING group's grant set (`COMMERCIAL_TOOL_NAMES` — no availability migration, auto
> HITL-eligible, auto admin-checklist), performing ONE purpose-specific gateway pass
> (`lq_ai_purpose="adversarial_review"`, `LQ_AI_ADVERSARIAL_REVIEW_MODEL` else `smart`,
> `anonymize=False`, max_tokens 4k, input cap 60k chars with HONEST truncation) validated against
> `schemas/adversarial_review.py` (25-finding cap; severity×{over_reach,under_protection,inconsistency,
> gap}); audit = counts only. **Written, PARKED in session scratchpad `adv-parked/` during the
> workspace full-suite run:** `app/agents/adversarial_review.py`, `app/schemas/adversarial_review.py`,
> mig `0097` (bind adversarial-review skill to commercial + users-gated Library adoption — the
> bound-but-not-adopted G13 class), `tests/agents/test_adversarial_review.py` (8 tests, stub gateway).
> Skill draft in scratchpad `adversarial-review-SKILL.md`. **REMAINING WIRING (after workspace PR):**
> restore parked files → add name to `COMMERCIAL_TOOL_NAMES` → append `build_adversarial_review_tools`
> in `_build_redlining` (capabilities.py) → move skill into `skills/adversarial-review/` →
> `profiles/commercial/profile.yaml` bindings.skills += → `RECOMMENDED_LIBRARY_SETS[commercial]` += →
> run parity oracle + profile suites + drift guards → seeded-defect eval (OOM-aware; defer-on-record
> path pre-approved) → own PR under the full gate. **Default OFF; whether the shipped profile turns the
> HITL toggle ON rides the maintainer's pending profile-HITL decision — do not pre-empt.**
>
> **③ MODEL QUESTION — ANSWERED (research, in `docs/fork/plans/ROUTER-model-selection.md`).** No —
> one gateway alias per run, every subagent inherits the parent model object; F010's model-key ban is
> deliberate (a string = gateway bypass). Differentiation IS possible: build a second gateway-bound
> `BaseChatModel` INSTANCE in composition (between `render_area_agent` and `build_deep_agent`,
> `composition.py:~1062→1172`) — the area-config JSON path is a DEAD END (`build_area_subagents`
> rejects extra keys). Verify deepagents 0.6.8 honours a per-spec instance before building.
>
> **④ ROUTER — RESEARCH DELIVERED (`docs/fork/plans/ROUTER-model-selection.md`; NOT built, per the
> maintainer).** Harvey (multi-provider portfolio, "Auto" routing, partner/associate per-STEP model
> choice, all-pass eval gates) + Legora (model-agnostic, no user picker) + the field (routing-collapse
> risk; learned routers opaque) ⇒ smart/fast/budget is the WRONG primary axis. Recommended: three
> orthogonal axes — capability-ROLE spine (`reasoning`/`balanced`/`bulk`, the only vocabulary agent
> code resolves) × operator-tunable TASK-CLASS aliases (nda-review, dd-fanout-lead/worker, redline,
> legal-research, judge — aliases-of-roles, gateway already supports alias→alias chains) × the
> EXISTING tier/security floor (never folded into capability). NDA→balanced; M&A fan-out = reasoning
> lead + bulk workers. Smallest build = CONFIG-ONLY gateway.yaml reframe. **The real prerequisite is
> EVAL** (Harvey/Legora both eval-gate model choice; use the in-repo CUAD/masked-judge harness).
> Future ADR-F083 reserved. Maintainer decisions before any build: taxonomy adoption / router seam /
> lead-worker split timing / default alias map.
>
> ◀ **PICK UP EXACTLY HERE:** workspace full api suite → PR `fork/workspace-awareness` → CI → fresh-
> context adversarial review (incl. security+simplification pass) → live verify on rebuilt api trio
> (mig 0096: rebuild api+arq+ingest together, `docker image prune -f`) → merge. Then ADV wiring per ②.
> Then HANDOFF/memory re-wrap. **DECISIONS STILL AWAITING THE MAINTAINER (unchanged, do not pre-empt):**
> (1) enterprise-vs-product call (CUSTODIAN #510–#514 gated); (2) shipped-profile HITL defaults
> (apply_redline AND now adversarial_review); (3) fate of the 5 untracked strays (4× scenario
> `test_*_live.py` + `sample-documents/`). GATED/deferred: CLEAN-3b #505; AZ-4 parked; AZ-6 keyless-MI
> branch still unpushed pending maintainer diff review; B-2c live masked-judge scenario (VM session).
>
> **MAINTAINER'S AZURE-VM LIVE-TEST SCRIPT (updated — pull main, rebuild per
> `docs/fork/runbooks/azure-vm-sandbox.md` + self-host traps: rebuild SERIAL with cache, never
> `--no-cache ×4` on the no-swap VM; stale web bundle hides features):**
> ① Fresh-org wizard (B-7 formal sign-off): empty Library → auto-launch → apply Commercial → agent
> redlines with zero manual curation (compare `docs/fork/evidence/b7-acceptance/`).
> ② F081 living redline: "redline it" → "further redline" → SAME document updates in place; Documents
> tab shows ONE "(redlined)" row; `start_fresh` branches a "(redlined v2)".
> ③ **WORKSPACE (new):** upload the same contract twice → Documents panel shows the amber
> "duplicate of …" badge; ask the agent about the matter's documents → it names the duplicate and
> works from one; after the agent reads a doc, its one-line summary appears under the filename.
> ④ **ADV (new, if merged by then):** on a high-stakes redline the agent OFFERS a hostile-reader pass;
> with the area's `adversarial_review` HITL toggle on, the "Waiting for your go-ahead" card appears;
> Approve runs it and findings come back severity-ordered.
> ⑤ HITL-3 UAT (on record): Commercial `hitl_policy` = apply_redline → confirm card → Approve.
> ⑥ B-4/PUBLISH UATs (on record). ⑦ Decide the profile-HITL defaults (apply_redline + adversarial_review).
> ⑧ AZ-6 keyless-MI: review + push the branch, runbook §4c smoke.
> ═══════════════════════════════════════════════════════════════════════════════════════════════════════

## State

- Branch: `fork/workspace-awareness` (commit `16e68390`) — WORKSPACE slices WS-1/2/3, unpushed at
  write time; PR + gate next. `main` = `16c3df04` (the wrapped B-stack session, deployable).
- ADV artifacts parked in session scratchpad (`adv-parked/` + `adversarial-review-SKILL.md`) — restore
  after the workspace merge; wiring list in banner ②.
- Docs landed this session: ADR-F082 (workspace awareness), ADR-F084 (adversarial review, proposed),
  `docs/fork/plans/WORKSPACE-awareness.md`, `docs/fork/plans/ADV-hostile-reader.md` (untracked until
  the ADV PR), `docs/fork/plans/ROUTER-model-selection.md` (research brief, rides the workspace PR).
- Dev stack: healthy on pre-0096 images; **api+arq+ingest need a joint rebuild after the workspace
  merge (mig 0096)**, then `docker image prune -f`.

## Done (this session)

WORKSPACE WS-1/2/3 (built+verified, committed); ADV module/schema/mig/tests/ADR/skill (written, parked,
unwired); router research (Harvey/Legora/field survey → three-axis taxonomy recommendation, doc final);
model-per-subagent question answered in code terms; task #511 reshaped to the HITL-offer form; tasks
#517–#520 tracked (517/520 complete at write time).

## Next slice

Finish the banner's PICK UP list: workspace PR→gate→merge, then ADV wiring→PR→gate→merge, then re-wrap
HANDOFF + memory. After that everything remaining is maintainer-gated (decisions list above).

## Gotchas (new this session — full history in memory topic files)

- **Mounted-repo test races:** a containerized pytest run reads the live mount at collection AND at
  app-boot (skills/, alembic/versions/) — do not edit api/, add migrations, or add skills mid-run.
  Phantom "fixture errored" storms = you raced it; re-run clean before diagnosing.
- **Box concurrency:** vitest (web) + pytest (api) together OOM-kill the pytest container silently
  (empty output, exit 0 through the pipeline). Suites run ALONE — including against web builds.
- **`files.summary_run_id`** FK requires a real run row (provenance, mirrors `created_by_run_id`).
- **Endpoint metadata-contract pin** (`test_matter_files_api`) exists to catch response-shape drift —
  bump it deliberately with each shape change; fixture hashes are now unique-by-default (the constant
  `"0"*64` made every file a byte-duplicate once dedup shipped).
- **New-shipped-skill checklist (post-B7a):** migration bind + users-gated Library adoption + profile
  manifest bindings + `RECOMMENDED_LIBRARY_SETS` move TOGETHER or the parity oracle fails.
