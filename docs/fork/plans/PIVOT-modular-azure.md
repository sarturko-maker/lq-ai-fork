# PIVOT 2026-07-07 — modular agent builder + Azure Foundry + redline continuity

Maintainer direction (verbatim intent, 2026-07-07), decomposed into three workstreams. This document
is the breakdown; each workstream gets its own plan/ADRs before implementation. Status of each section
is marked. **Maintainer edits this file** to reorder/cut before anything is built.

The three pieces:

1. **MODULAR + agent builder** — inherited upstream modules (skills + skill builder, knowledge,
   playbooks) and fork-built modules (agentic tabular review, redlining, matter memory) must become
   truly SHARED modules, without losing the Deep Agents progress. Deep Agents ship with defaults, but
   a non-technical admin walks an **agent set-up wizard**: start from prebuilt profiles (Commercial,
   Privacy — imperfect, evolving), connect skills / knowledge / playbooks / tools, configure
   **sub-agents** without touching JSON, and configure **human-in-the-loop** (when the agent must stop
   and ask). "Deep Agents built from modules like lego. The trick is it needs to work."
2. **AZURE deployment** — deploy on Azure: initially a single VM sandbox, later enterprise
   (AKS etc.). Gateway grows three Azure AI Foundry model families (OpenAI/GPT, Anthropic Claude,
   Mistral) + investigate **Voyage embeddings** (available via Azure) for RAG. Additive, reversible,
   secret-free (public repo). Explicit two-phase gate: research report → maintainer approves → implement.
3. **REDLINE continuity (Commercial)** — on a follow-up instruction the agent redlines the ORIGINAL
   document instead of continuing from its own redlined output. Desired: default to the agent's own
   latest redlined version; start afresh only when the user explicitly asks.

Relationship to open threads: this ANSWERS task #472 (capability-sources scope — the maintainer chose
the full modular direction, not a single candidate) and absorbs task #473 / G13 (fresh-org curation
becomes part of the wizard). `docs/fork/plans/CAPABILITY-SOURCES-birdseye.md` is the substrate map for
workstream 1.

---

## Workstream R — redline continuity  *(smallest, live-blocking, do first)*

Status: **R-0 diagnosis DONE (2026-07-07, code trace).** Root cause, exactly:

- Every redline tool resolves its source by **exact case-insensitive filename**
  (`fetch_matter_docx`, `api/app/agents/tools.py:569`); the redlined output is saved under a
  DIFFERENT name (`contract (redlined).docx`, `commercial_tools.py:1078`), so naming "the document"
  always re-resolves the original. No lineage exists — `File` has `created_by_run_id` (run→file)
  but **no `parent_file_id`** (file→file); the source id survives only in an audit blob.
- The doctrine actively **reinforces** the bug: `apply_redline`'s docstring
  (`commercial_tools.py:147-152`) and `skills/surgical-redline/SKILL.md:146` both say each call
  "re-redlines the original afresh".
- The inventory shows the work product as `"(not ingested yet — status: ready)"`
  (`tools.py:684`) — it reads as a pending upload, not as "your current working version".
- WOPI/Collabora complicates "latest": first human save **mutates the redlined row's bytes in
  place** (flips `created_by_run_id`→NULL) and mints a `… (agent draft).docx` snapshot
  (`api/app/api/wopi.py:408-552`) — so name-resolution can silently return human-edited content
  and a third copy joins the inventory.

- R-1 (the fix, one PR): **lineage + working-version resolution + honest doctrine.**
  (i) migration: `File.parent_file_id` (nullable FK, SET NULL), set on redline/response outputs and
  on WOPI snapshots; (ii) working-version resolver: `apply_redline`/`preview_redline` grow
  `start_fresh: bool = False` — default follows the lineage chain from the named doc to the newest
  working leaf (WOPI *snapshots excluded* — they are history for diffing; the in-place-edited live
  row, by `coalesce(updated_at, created_at)`, is the continuation point), `start_fresh=True` uses
  the named row exactly; `respond_to_counterparty`/`extract_counterparty_position` keep exact-name
  semantics (their subject is the counterparty's named doc); (iii) inventory renders provenance
  ("agent work product — redline of contract.docx") instead of "not ingested yet"; (iv) fix the
  docstring + SKILL.md line + one doctrine sentence (continue from your own latest redline unless
  told to start afresh); (v) deterministic tests incl. the WOPI-mutated case; live verify on the
  Test 1 matter.

## Workstream AZ — Azure Foundry  *(research now; implement after maintainer approves Phase 1)*

- AZ-R (Phase 1): **DONE 2026-07-07 — full report: `docs/fork/plans/AZURE-FOUNDRY-phase1.md`**
  (verdict table, confirmed endpoints/auth/scopes/regions, repo inspection, coupling flags, cited
  Microsoft Learn / Anthropic pages). Headline verdicts: Azure OpenAI **CONFIG-ONLY** (the
  `azure_openai` adapter already exists end-to-end); Claude-on-Foundry **CONFIG-ONLY for chat, CODE
  for agent use** (the Anthropic adapter is still text-only — fork blocker #2 becomes the one real
  gateway slice); Mistral **CONFIG-ONLY** (Foundry now serves non-OpenAI models over the OpenAI-
  compatible routes we already speak; the /models Model Inference route is legacy — its SDK retires
  2026-08-26); Voyage **real but awkward** (law-2 = ~$5+/hr GPU managed app; serverless catalog =
  general-purpose voyage-4 with Voyage-native schema) — split + partly defer.
- AZ-1: Azure OpenAI provider — config + env + aliases + rates; smoke test. First to enable. One PR.
- AZ-2a: Claude-on-Foundry chat — config entry + env plumb (works today, text). One PR.
- AZ-2b: Anthropic adapter tool-calling (request tools/tool_use/tool_result + streaming deltas) —
  unlocks Claude as an AGENT model, Foundry and direct; respx tests, mypy --strict. One PR.
- AZ-3: Mistral-Large-3 — config-only via the azure_openai-type route on the services.ai host (only
  Large-3 gets an agent alias; medium-3-5/Codestral lack tool-calling on Azure). One PR.
- AZ-4 — **PARKED (maintainer, 2026-07-07: budget-constrained — ship what works; inference-on-Foundry
  readiness outranks embeddings).** The local Door-A embedder is $0, private, and proven — it IS the
  shipping answer. AZ-4a shrinks to a comment-only `embedding`-alias example inside the AZ-CONFIG PR;
  AZ-4b (Voyage — maintainer sighted voyage-4 / voyage-4-lite / rerank-2.5 LIVE in the Foundry catalog
  2026-07-07, which confirms the previously-UNCONFIRMED reranker) revisits ONLY if real-matter
  tabular/retrieval quality shows the embedder is the bottleneck — the CUAD eval harness is ready for
  that head-to-head. Ties into F056.
- AZ-5: VM sandbox deploy runbook (compose on an Azure VM; secrets via env; gateway-config named-
  volume seeding; per-provider synthetic smoke tests). Builds on ADR-F058 delivery modes.
- AZ-6 (later): enterprise posture — AKS, Entra ID keyless (configurable audience — scope strings per
  route recorded in the report), per-client isolation. Not planned yet.
- Region note: one Foundry resource in **Sweden Central (or East US2)** satisfies all three families —
  Claude's region restriction is the binding constraint.

Constraints carried from the maintainer's brief: public repo — no secrets/endpoints/resource names in
commits; everything additive (non-Azure providers keep working with AZURE_* unset); each provider
independently enableable; full diff + git status shown before any push; smoke tests synthetic-only.

## Workstream B — modular structure + agent builder  *(the big one; plan after R + AZ-R)*

Substrate facts (from CAPABILITY-SOURCES-birdseye.md): capabilities reach a Deep Agent only via
Store → org Library (adopt) → area binding → `build_area_inventory` (fail-closed chokepoint). Upstream
authoring surfaces (user skills + builder, playbooks + easy builder, knowledge collections) are
ORPHANED from Deep Agents. F065 D7 deliberately deferred org-authored content (prompt-injection
surface) and reserved an `org` namespace tier.

Draft slice ladder (to be re-planned as its own milestone doc after maintainer edits):

- B-0: **ADR — the module model.** One vocabulary: a "module" = skill | knowledge collection |
  playbook | tool group | sub-agent profile. Defines how org-authored content enters the Library
  (reopens F065 D7 with the injection harness it demanded), and what an "agent profile" is
  (practice_areas already carries the config vocabulary from F1-S3).
- B-1: House Brief admin page (birdseye candidate A — cheap, already re-prioritised as G9; feeds
  "who the agent acts for").
- B-2: org-authored skills → agent path (candidate C): author in the existing builder → propose to
  Library (`org` namespace) → harness (review gate + provenance label + injection guard) → adoptable →
  bindable. The riskiest slice — needs the D7 harness ADR.
- B-3: knowledge → Deep Agent (candidate E): a knowledge-collection search tool group, so admin-uploaded
  KBs become a bindable module.
- B-4: playbooks → Deep Agent (candidate D): today only bound POSITIONS inject (read-only Practice
  Playbook tier); decide whether org-authored playbooks join the Library the same way.
- B-5: sub-agent configuration: surface the fan-out roster (drafter/reviewer, ADR-F034) as
  admin-configurable per area — names, instructions, tool subsets — no JSON.
- B-6: human-in-the-loop policy: when the agent must stop and ask (deepagents/langgraph interrupts;
  needs a research spike — this is new substrate, not config).
- B-7: **the wizard**: a guided flow stitching B-1..B-6 — pick a starting profile (Commercial /
  Privacy / blank) → House Brief → adopt modules → bind → sub-agents → HITL policy → test run.
  ONBOARD-1 (template catalog) and ONBOARD-2 (admin wizard) fold into this.

Non-goals for B until stated otherwise: no marketplace/multi-org sharing; Practice Knowledge tier
(ADR-F050 prize) stays future; legacy executors stay frozen (the wizard configures Deep Agents only).

## Sequencing recommendation

1. **R-1** (redline fix) — small, unblocks live Commercial demos.
2. **AZ-R report → maintainer approval → AZ-1..AZ-3** (each config-mostly, independent PRs), then AZ-5
   VM runbook. AZ-4 (Voyage) after the embeddings findings are in.
3. **B-0 ADR + milestone re-plan** in parallel with AZ implementation; then the B ladder.

Backlog notes absorbed: SETUP-6 guides stay on hold; T5, F056 fold into AZ-4/B as noted.
