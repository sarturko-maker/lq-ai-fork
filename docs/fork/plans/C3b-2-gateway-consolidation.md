# C3b-2 — gateway-routed matter-memory consolidation/Lint pass (the ADR-F010 egress slice)

**Status:** APPROVED scope (maintainer answered the 3 load-bearing questions, 2026-06-23). Builds on **C3b-1**
([[matter-facts-c3b1-shipped]], PR #134), **C3a** (PR #133), **ADR-F042** (auto-write-then-correct), and the
gateway-egress precedents. Supersedes the §C3b-2 *outline* in `C3b-typed-facts-consolidation.md`.
**Depends:** C3b-1 ✓, C3a ✓, ADR-F042 ✓. **Drafts ADR-F043.** **No migration** (reuses the `0070` typed-fact
columns + `projects.context_md`).

## Maintainer decisions (the three that shaped the slice)

1. **Scope = facts + wiki rewrite.** The pass consolidates the typed fact ledger **and** rewrites the prose
   one-pager from the consolidated state, in the one tool (the original outline, chosen over facts-only).
2. **Mutation = supersede-only.** The pass may only **close a fact's window** (`invalid_at` [+ `superseded_by`])
   — dedup, resolve a contradiction by superseding the weaker, age out the stale. A *corrected* statement is a
   **new superseding fact** (REPLACE), never an in-place `body_md` edit. Full bi-temporal history is preserved
   (the "what did we believe at signing" guarantee stays intact).
3. **Cost = match the existing R4-no-op posture + gateway audit.** R4 stays a documented no-op (as for *every*
   agent tool today; per-run $ budgets are F1's job). The call is bounded **structurally**: exactly **one**
   gateway call per invocation + a hard `max_tokens` cap; the spend is recorded in the gateway routing-log
   under the **new `lq_ai_purpose`** (auditable). **No bespoke per-tool fact-count ceiling / invocation cap**
   (the rejected option) — a pathological input fails gracefully at the gateway as a reject-and-retry.

## Goal

A matter agent can, in one tool call, **consolidate the matter's memory**: the tool loads the matter's live
fact set **whole** (no embeddings — gateway `/v1/embeddings` is 501 until B6) + the wiki + the pinned
corrections, routes a **mem0-style extract→judge + Karpathy/OpenClaw Lint** pass through the **Inference
Gateway** (every model call through the gateway — the ADR-F010 egress obligation lands here), then **supersedes**
the stale/contradicted/duplicate facts and **rewrites the wiki**. **Pinned corrections stay immutable to the
loop** (structural, not prose). End to end, all areas. First matter-memory code that calls a model.

## The consolidation loop (one guarded tool call)

`consolidate_matter_memory()` → `guarded_dispatch("consolidate_matter_memory", op, ctx)`; inside `op(db)`:

1. **Load (read substrate, C3b-1/C3a):** `live_facts(db, project_id)` (the `kind='fact'`, `invalid_at IS NULL`
   set), `project.context_md` (the wiki), `load_pinned_corrections(db, project_id)`. **Early-out:** 0 live
   facts ⇒ return "no facts to consolidate" with **no gateway call** (a free lower bound on egress).
2. **Prompt:** render the facts (id · type · statement · source · valid_at), the current wiki, and the pinned
   corrections as **read-only ground truth ("never contradict or supersede these")**. Ask for: per changed
   fact a `retire`/`replace` op + the **full rewritten wiki** + `lint_notes`. JSON-only output contract.
3. **One gateway call:** `GatewayClient.chat_completion(ChatCompletionRequest(model=<alias>, messages=[…],
   max_tokens=_CONSOLIDATION_MAX_TOKENS, anonymize=False, lq_ai_purpose="consolidate_matter_memory"))`.
   `anonymize=False` mirrors `playbooks/easy/extractor.py` — the consolidation must judge the **real** fact
   text (equivalence/contradiction over masked text is impossible); the gateway is still the sole egress.
   Any gateway exception ⇒ a **reject-and-retry string** (never a crash — the C3b-1 tz-naive lesson +
   `autonomous/guard.py` catch-and-return precedent), **no writes**.
4. **Parse + validate (untrusted model output):** lenient JSON extract (mirror extractor's fence-strip) →
   `ConsolidationResult` Pydantic (`extra='forbid'`, reject-not-truncate). Then a **pure validation pass, no
   mutation:** every op `fact_id`/`supersedes` id must be a **live `kind='fact'` row of THIS matter** (rejects
   a hallucinated id, a correction id, another matter's id, an already-superseded id); **no id may appear in
   two ops** (no double-supersede); a `replace`'s `valid_from` (UTC-normalised; defaults to *now*) must be
   `>` each superseded fact's `valid_at` (temporal coherence — same rule as `_record_matter_fact`); `new_wiki`
   must pass `UpdateMatterMemoryInput` (non-blank, ≤16 KiB). **Any failure ⇒ reject string, zero writes.**
5. **Apply (all-or-nothing in the guarded session, only after validation passes):**
   - `retire`: `prior.invalid_at = now`, `prior.superseded_by = None` (window closed, no replacement).
   - `replace`: insert the new `kind='fact'` row (`author='agent'`, `trust='normal'`, `fact_type`,
     `source_citation`, `valid_at`), flush for its id, then set each superseded prior's `invalid_at` +
     `superseded_by = new.id`. (Reuses the exact C3b-1 supersede mechanic; never deletes.)
   - **Wiki:** if `new_wiki.strip()` differs from the current, snapshot the prior + rewrite `context_md`
     (reuse the C3a snapshot+rewrite path — extract a shared `snapshot_and_rewrite_wiki(...)` helper in
     `matter_memory_tools.py` so C3a and C3b-2 single-source it; DRY over an 8-line copy).
6. **Receipt (model-visible) + audit (guard envelope):** return a counts summary + `lint_notes`
   ("retired 2, merged 3→1, wiki rewritten (1,180 chars). Notes: …"). The guard auto-audit records
   `tool`/`outcome`/`result_chars` only — **never a body** (audit contract).

## Structural guarantees (carry over; the isolated egress review's core)

- **Pinned corrections immutable:** the loop's input passes corrections as *read-only ground truth*; the apply
  step writes/closes only `kind='fact'` rows (the live-fact-id validation in step 4 makes a correction id
  unreachable). No-fabrication (no agent path mints `human-pinned`) + no-overwrite both hold structurally.
- **Confinement:** own disjoint grant `MATTER_CONSOLIDATION_TOOL_NAMES = {consolidate_matter_memory}` — disjoint
  from `MATTER_MEMORY_TOOL_NAMES` / `MATTER_FACT_TOOL_NAMES` and the ROPA/assessment/commercial domain grants.
- **Egress (ADR-F010):** the tool's ONLY model access is the injected `GatewayClient`; no provider SDK import,
  no `api.openai.com`. Asserted by a unit test (the stub gateway sees exactly one call, the right purpose) +
  a static egress-guard test on the module source.
- **Bounded:** one gateway call/invocation + `max_tokens` cap; the agent's ADR-F026 step/time budget bounds how
  often it can be invoked. Spend audited at the gateway under the new purpose. (Per-run $ budget = F1.)

## Build

1. **Gateway purpose** — add `"consolidate_matter_memory"` to `_KNOWN_PURPOSES`
   (`gateway/app/api/inference.py`); document it in the `lq_ai_purpose` docstring
   (`gateway/app/providers/openai_schema.py`); extend the purpose-propagation test
   (`gateway/tests/test_inference_b4.py` parametrize). **Gateway restart needed** (frozenset at module load)
   — covered by the dev rebuild.
2. **Schemas** (`api/app/schemas/matter_memory.py`) — `ConsolidationOpType(StrEnum)` (`retire`/`replace`),
   the tagged-union op models (`RetireOp`, `ReplaceOp` — `ReplaceOp.valid_from` reuses the `_valid_from_utc`
   UTC-normaliser), `ConsolidationResult` (`operations` [bounded length], `new_wiki` [≤`MATTER_WIKI_MAX_CHARS`],
   `lint_notes` [bounded]); `extra='forbid'` throughout; bounded `reason`/`lint_notes` lengths.
3. **Consolidation module** (`api/app/agents/matter_consolidation.py`, NEW) —
   `MATTER_CONSOLIDATION_TOOL_NAMES`, `build_matter_consolidation_tools(session_factory, *, run_id, binding,
   gateway_factory=get_gateway_client, model_alias=_CONSOLIDATION_MODEL_ALIAS)`, the guarded
   `consolidate_matter_memory()` tool, `_consolidate_matter_memory(db, binding, *, run_id, gateway, model_alias)`
   (load → prompt → one gateway call → parse → validate → apply), a `_format_facts_for_prompt(...)` renderer,
   `_parse_consolidation_result(...)` (lenient JSON), the system/user prompt constants, and `_rejection_text`.
   Imports the gateway via a `gateway_factory` (DI seam; tests inject a fake).
4. **Wiki helper** (`api/app/agents/matter_memory_tools.py`) — extract
   `snapshot_and_rewrite_wiki(db, project, *, run_id, user_id, new_content)` from `_update_matter_memory`;
   both C3a and the consolidation apply call it (single-source the snapshot+rewrite).
5. **Composition** (`api/app/agents/composition.py`) — grant `build_matter_consolidation_tools(...)` for
   **every** matter-bound run (the `if binding is not None:` block), beside the matter-memory + matter-fact
   grants; default `gateway_factory=get_gateway_client`.
6. **Skill** (`skills/matter-memory/SKILL.md`) — a short *consolidation* section (when to call
   `consolidate_matter_memory`: the ledger has grown / facts duplicate or contradict / before handing off;
   it supersedes stale facts + rewrites the wiki; it never touches a lawyer's correction). **No unquoted
   `": "`** in the description (the trap; CI guard `test_every_real_skill_loads_no_silent_drops`).
7. **ADR-F043** (`docs/adr/F043-matter-memory-consolidation-egress.md`) — the egress + the new purpose + the
   model-calling agent tool + the 3 decisions (skeleton below).

## Verify (4-discipline DoD)

- `ruff format && ruff check` (CI ruff), `mypy app`, full `pytest` (dev-image recipe; counts quoted).
  Gateway: `cd gateway && pytest` (mypy `--strict`).
- **Unit tests** (`api/tests/agents/test_matter_consolidation.py`, NEW — `_StubGateway` pattern from
  `test_easy_playbook_extractor.py`, `commit_factory` from the scenario conftest):
  - grant set + disjointness (vs memory/fact/domain grants);
  - happy path: scripted ops JSON ⇒ a `retire` closes a fact's window (`invalid_at` set, `superseded_by` NULL),
    a `replace` inserts a new live fact + closes+links the priors, the wiki is snapshotted + rewritten;
  - the stub gateway saw **exactly one** call with `lq_ai_purpose=="consolidate_matter_memory"`,
    `anonymize is False`, `max_tokens==_CONSOLIDATION_MAX_TOKENS` (**egress + purpose assertion**);
  - **0 live facts ⇒ no gateway call** (stub call-count 0) + a benign receipt;
  - reject-not-write: an op naming a **correction** id / a non-live id / a cross-matter id ⇒ reject, zero
    writes; a `fact_id` in two ops ⇒ reject; `new_wiki` blank/over-budget ⇒ reject; malformed JSON ⇒ reject;
    `replace.valid_from` ≤ prior `valid_at` ⇒ reject; **a pinned correction is untouched in every reject path**;
  - gateway raises ⇒ reject string (not a crash), zero writes;
  - guard audit row carries no body (counts/outcome only);
  - **static egress guard:** the module source contains no direct-provider sink (`openai`/`anthropic`/
    `api.openai.com`) — the only egress is the injected gateway.
  - `test_agent_composition.py`: the consolidation tool is granted to a matter-bound run (Commercial **and**
    Privacy); grant-set disjoint.
- **Gateway:** `test_inference_b4.py` recognises the new purpose (propagates, not `chat`-fallback).
- **Live (DeepSeek)** (`api/tests/agents/scenarios/test_matter_consolidation_scenario.py`, provider-marked):
  seed a matter with a few **duplicate/contradictory** facts (via `record_matter_fact`), prompt the agent to
  consolidate; hard-assert `receipt.status=="completed"`, `"consolidate_matter_memory" in receipt.tools_called`,
  the call routed through the gateway under the purpose, the loop didn't crash, and the live fact set was
  reconciled (≥1 supersede OR a justified all-NOOP) + a `wiki_snapshot` exists if the wiki changed. The model's
  specific judgement is a **finding, not a gate** (ADR-F015). Evidence → `docs/fork/evidence/c3b2/`.
- **No migration** (head stays `0070`); still rebuild api+arq-worker+ingest-worker + **gateway** (new purpose).
- Fresh-context **adversarial + security + simplification** review (injection: facts/wiki/corrections are
  untrusted model input; the loop cannot mint a pin or touch a correction; egress only via the gateway; audit
  counts/IDs only; reject-don't-truncate; all-or-nothing apply; confinement). HANDOFF + memory.

## ADR-F043 skeleton (MADR-minimal — draft in the PR, maintainer accepts)

- **Title:** F043 — Matter-memory consolidation as a gateway-routed, supersede-only agent tool
- **Status:** proposed · **Date:** 2026-06-23 · **Deciders:** maintainer + agent · **Relates:** F042, F010, F018, F026
- **Context:** C3b-1 gives the agent a manual supersede; an automated consolidation/Lint keeps the ledger + wiki
  honest. It is the first matter-memory code to call a model ⇒ the ADR-F010 egress obligation + a cost posture
  must be decided. mem0's ADD/UPDATE/DELETE/NOOP + Karpathy/OpenClaw Lint over a small whole fact set (no
  embeddings until B6).
- **Considered options:** (1) in-run guarded tool [chosen — no post-run hook exists; an agent tool needs a live
  run] vs background cron [deferred — backlog]; (2) facts-only vs **facts + wiki** [chosen]; (3) **supersede-only**
  [chosen] vs in-place fact UPDATE [rejected — loses bi-temporal history]; (4) **R4-no-op + gateway-routing-log
  audit + structural bound** [chosen] vs a bespoke per-tool cost guard [rejected — F1 owns per-run budgets].
- **Decision outcome:** the four chosen options; the egress lands here (every model call via `GatewayClient`
  under `lq_ai_purpose="consolidate_matter_memory"`; no direct provider); pinned corrections immutable to the
  loop (structural); all-or-nothing apply (validate-then-write); `anonymize=False` (judge real text; gateway is
  still sole egress).
- **Consequences:** + ledger/wiki stay self-consistent automatically; + history preserved (supersede-only);
  + egress + audit honoured. − the in-tool token spend is invisible to R4 until F1 (mitigated: one bounded call,
  audited at the gateway); − a new gateway purpose needs a gateway restart to register; − background-cron
  autonomy + structured Citation-Engine refs + embedding retrieval remain deferred (C3c / backlog).

## Non-goals (→ C3c / backlog)
Background-cron / scheduled consolidation (in-run tool only). In-place fact edits (supersede-only). Embedding /
vector retrieval (whole-set load; gateway embeddings 501 until B6). Structured Citation-Engine refs (prose
source only). The agent-facing read tools / REST / cockpit memory panel + undo endpoint (C3c). A per-run $ budget
(F1). A new fact_type beyond the C3b-1 enum.
