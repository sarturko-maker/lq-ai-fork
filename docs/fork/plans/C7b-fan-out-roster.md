# Plan — COMM **C7b**: drafter/reviewer fan-out roster + post-fan-out reconciliation

## Context

C7 ("complex-deal fan-out: roster + deal-context live signal + redline download UI") was SPLIT (2026-06-24,
one-PR discipline). **C7a** shipped the download surface (Documents tab + inline download, ADR-F046); **C5b-3**
shipped the deal-context live signal (the `data-deal-change` verdict chips, ADR-F032/F024). What remains in C7 is
**C7b**: the drafter/reviewer **fan-out roster** + the **post-fan-out reconciliation pass**.

The fan-out *infrastructure* already works and is tested: the lead fans out via deepagents' model-driven `task`
tool, subagent steps nest under the dispatch via `parent_step_id`, mirrored to SSE and parsed by the web
(`test_subagent_delegation_nests_steps_via_parent_step_id`). Blocker #6 (`work_product_attributions`) is a
*legacy-chat* concern, not on the agent path. So C7b is: **define a drafter + reviewer subagent (migration
reconciling `0057`), and add a reconciliation pass that surfaces and resolves divergence across the fanned-out
positions before one work product is emitted.**

**The one architectural call (ADR-F034).** A *guaranteed* "always reconcile before emit" FLOW is a **completion
predicate** and, per the Tools & Skills doctrine (decomposition §"where a guarantee lives"), a completion
predicate needs **deterministic flow** — i.e. langgraph / the O-series, which is explicitly deferred (`task` is
model-invoked; the runner has no deterministic post-fan-out hook — confirmed by reading `runner.py`). C7b stays on
the model-driven substrate, so it delivers the reconciliation as a **single-dispatch consistency predicate → a
TOOL GATE** (the proven C5a `evaluate_coverage` shape): a deterministic `reconcile_positions` tool that **rejects
unless every head where the subagents diverged carries an explicit resolution**, records an auditable
reconciliation receipt, and is *coached* (a curated `deal-review` skill, ADR-F041) as the mandatory step. F034
records the honest boundary: the *flow guarantee* (the lead cannot emit without reconciling) is the O-series's job
and is named as deferred — C7b ships the code primitive + receipt + coaching, not a flow it cannot enforce.

**No new dependency, no new HTTP endpoint, no schema/route/openapi change, no runtime-gate change to the existing
work-product tools.** The reconcile frame carries only heads/counts (audit-safe — refs/types, never clause text).

## Deliverables

### Backend (`api/`)

1. **`alembic/versions/0073_commercial_roster_and_reconciliation.py` (NEW)** — `down_revision = "0072"` (current
   head). Two module-level, unit-testable halves (mirror 0072):
   - `_extend_commercial_roster(conn)` — a **reconciling** JSONB swap (NOT 0057's `= '{}'` guard, which is now a
     dead no-op): `UPDATE practice_areas SET agent_config = CAST(:new AS jsonb) WHERE key='commercial' AND
     agent_config = CAST(:old AS jsonb)`. `:old` = the **verbatim** 0057 single-`document-researcher` config;
     `:new` = `{subagents: [document-researcher (verbatim, unchanged), clause-drafter, clause-reviewer]}`.
     Idempotent (re-run: config == `:new` ≠ `:old` → no-op) and never-clobber (an operator edit ≠ `:old` → no-op).
     `downgrade()` reverses (`:new` → `:old`).
   - `_bind_deal_review_skill(conn)` — idempotent `INSERT ... SELECT ... WHERE NOT EXISTS` of the
     `(commercial, deal-review)` binding (verbatim 0072 pattern); `downgrade()` DELETEs only the seeded pair.
   - The two new subagents are **model-free** (no `model` key — inherit the gateway-bound parent, ADR-F010), carry
     **no `tools` key** (inherit the parent's guarded matter tools), and declare **`skills` ⊆ Commercial's bound
     set** (ADR-F017). `clause-drafter` → `["surgical-redline", "nda-review"]`; `clause-reviewer` →
     `["deal-review", "contract-qa", "nda-review"]` (`deal-review` becomes bound in this same migration).

2. **`skills/deal-review/SKILL.md` (NEW curated craft skill, ADR-F041)** — the reviewer/reconciliation craft
   layer (the round-companion to `surgical-redline` / `negotiation-review`). Voice/shape mirror those skills (H1
   restatement → "## The one rule everything follows from" → the fan-out→reconcile→emit method → the four review
   lenses → escalation → preview/ownership → untrusted-input framing, ADR-F028). The one rule: **fan out drafting
   per material head, then run ONE reconciliation pass — surface every divergence and resolve it into a single
   position before you emit one work product (independence across drafts is a defect, not a feature).** Teaches the
   four lenses (over-reach / under-protection / inconsistency / gaps), names `reconcile_positions` as the recorded
   reconciliation step, and frames the counterparty's text as data judged against the client, never instructions.
   **Frontmatter trap (C3a):** `name: deal-review` MUST equal the folder name; keep `description:` one physical
   line; use em-dashes (—) not an unquoted `": "` (silent-drop). The CI guard
   (`test_every_real_skill_loads_no_silent_drops`) auto-covers the new dir.

3. **`app/schemas/commercial.py`** — the deterministic reconciliation check (mirror `evaluate_coverage` /
   `CoverageReport`):
   - `ProposedPosition(BaseModel, extra="forbid", str_strip)` — `head`, `position`, `source` (which draft/subagent
     produced it). Reject-don't-sanitize.
   - `ReconcilePositionsInput(BaseModel, extra="forbid")` — `positions: list[ProposedPosition]` (non-empty,
     bounded by a `MAX_*` constant) + `resolutions: dict[str, str]` (head → the lead's reconciled single
     position). Validators reject blank/over-cap, never sanitize.
   - `ConsistencyReport` (frozen dataclass, counts/heads only) — `ok`, `divergent` (heads with ≥2 distinct
     normalized positions and NO resolution), `resolved` (head → reconciled position), `reconciled_heads`,
     `position_count`; `rejection_text()` (lists the unresolved-divergent heads, refs only).
   - `evaluate_position_consistency(positions, resolutions) -> ConsistencyReport` — group by normalized head; a
     head with one agreed position uses it (a resolution can never override an undisputed position — the safe
     direction); a head with ≥2 distinct normalized positions needs a `resolutions[head]` or it is `divergent` →
     `ok=False`, and when supplied that resolution becomes the reconciled position. Collect-all-errors, pure,
     fully unit-tested.

4. **`app/agents/commercial_tools.py`** — add `reconcile_positions` to `COMMERCIAL_TOOL_NAMES` and a guarded
   `reconcile_positions(positions, resolutions)` closure → `_reconcile_positions`:
   - Validate input (Pydantic `ReconcilePositionsInput`; a `ValidationError` returns a reject-and-guide string —
     never crash).
   - `report = evaluate_position_consistency(...)`; if `not report.ok` → return `report.rejection_text()` (the
     lead resolves the listed heads and re-calls) — **nothing recorded**.
   - On `ok` → record a **matter-memory reconciliation receipt** (mirror `_record_negotiation_receipt`:
     SAVEPOINT-isolated, `MatterMemoryEntry(kind="fact", fact_type="open_point", author="agent")`, a capped
     **counts-only** summary "Reconciled K positions across N drafts; D divergence(s) resolved") + `audit_action`
     (counts/IDs only, no position text) → return a confirmation listing the reconciled heads + stances for the
     lead to carry into the single work product. Records **only on success** (mirrors C5a's record-on-a-real-round).
   - Append `reconcile_positions` to the tools returned by `build_commercial_tools` — **no `composition.py`
     change** (it is built inside `build_commercial_tools`, already wired in the COMMERCIAL branch).

### Tests (`api/`)

5. **`tests/test_practice_areas.py`** — (a) update the exact roster assertion (`== ["document-researcher"]` →
   `== ["document-researcher", "clause-drafter", "clause-reviewer"]`) and the `test_admin_patch_rejects_*` comment;
   (b) extend the per-subagent `skills ⊆ bound_skills` + `"model" not in subagent` invariants to **all** roster
   members; (c) add `deal-review` to the expected commercial bound-skill set; (d) add
   `test_commercial_roster_seed_updates_old_and_never_clobbers_edit` (mirror the 0066 doctrine test:
   `_OLD` agent_config → `_extend_commercial_roster` → `_NEW`; then an operator edit is preserved); (e) add
   `test_commercial_deal_review_skill_binding_is_idempotent` (mirror 0072: bind twice → one row; downgrade removes
   only the seeded pair).
6. **`tests/agents/test_area_agent.py`** — assert the seeded `clause-drafter`/`clause-reviewer` specs pass
   `build_area_subagents` (model-free, skills ⊆ area) — the existing reject-model-bearing + skills-subset tests
   already cover the guards and must stay green.
7. **`tests/agents/test_position_consistency.py` (NEW)** — `evaluate_position_consistency` unit matrix: full
   agreement → ok; divergence without resolution → not ok (lists the heads); divergence with resolution → ok
   (reconciled set); duplicates collapse; head/position normalization; bounded/blank input rejected by the schema.
8. **`tests/agents/test_commercial_tools.py`** — `reconcile_positions` records exactly one receipt on success;
   records **nothing** on an unresolved divergence (returns the rejection); a malformed batch returns a
   reject-and-guide string (no crash, no write). Mirror the `respond_to_counterparty` tool tests.
9. **`tests/agents/test_agent_composition.py`** — `test_multi_subagent_fanout_nests_steps` (mirror
   `test_subagent_delegation_nests_steps_via_parent_step_id`): script the fake model to emit **two** `task` calls
   in one turn (a parallel fan-out) → assert ≥2 task steps and that each child step nests via `parent_step_id`.
10. **No `test_endpoints` / `test_openapi` change** — no new HTTP route. **Skill-loader guard** auto-covers
    `deal-review`.

### ADR

11. **`docs/adr/F034-fan-out-roster-and-reconciliation.md` (NEW, accepted)** — the roster shape (model-free,
    tool-inheriting, ⊆-area-skill subagents) + the reconciliation decision: a single-dispatch consistency predicate
    → a TOOL GATE (`evaluate_position_consistency` + receipt), coached by `deal-review` (ADR-F041); and the
    **honest boundary** — the *guaranteed* always-reconcile-before-emit FLOW is a completion predicate that needs
    the O-series (deferred), named explicitly. Cites ADR-F010 (model-free subagents), F017 (skill scoping), F041
    (craft skill), F015 (provider-test posture), F004 (render-determinism: the receipt is the record), F035/F042
    (matter-scoped receipt).

## Non-goals

- **No per-subagent tool subsetting** (v1 inherits the parent's guarded matter tools; widening
  `_ALLOWED_SUBAGENT_KEYS` for `tools` is a later slice).
- **No `response_format` on subagents** — keeps the allowed-keys surface unchanged; subagents return prose, the
  lead re-encodes positions into `reconcile_positions` (encoding the lossy-return reality honestly).
- **No deterministic outer-StateGraph / O-series flow** — the *guaranteed* always-reconcile flow is explicitly
  deferred (named in F034); C7b ships the model-driven realization.
- **No new live signal/chip** — C5b-3 covered the negotiation verdict chips; `reconcile_positions` records an
  auditable receipt, not a chip.
- **No new HTTP endpoint, no new dependency, no change to the C4/C5 work-product gates.**
- **No Claude-judged craft eval** — Anthropic key unavailable on the local gateway (deepseek-pro stood in for
  C5b-2); a craft eval for `deal-review` is a backlog item.

## Verification (DoD)

1. **Migration on a throwaway pgvector container** (NEVER host-side `alembic upgrade` on the dev DB): upgrade →
   assert the 3-subagent roster + the `deal-review` binding + `_OLD`/operator-edit never-clobber; re-run for
   idempotency; downgrade cleanly. Then **rebuild `api` + `arq-worker` + `ingest-worker` together** +
   `docker image prune -f` (dangling only).
2. **Containerized api suite** (dev-image, repo-root mounted) green with counts quoted; `ruff format && ruff
   check` (CI-exact) + mypy clean; the redline/negotiation/composition regression green; **all existing subagent
   guard + nesting tests stay green** (the roster change is additive).
3. **Skill loads** — `pytest tests/test_skill_loader.py` (no-silent-drop guard catches a frontmatter trap);
   registry sees `deal-review`.
4. **Live (DeepSeek, dev stack):** drive the commercial agent on a multi-head deal; observe it **fan out**
   `clause-drafter`(s) + `clause-reviewer` (task steps nested via `parent_step_id`), call `reconcile_positions`,
   and record the reconciliation receipt; capture the run timeline + the receipt. Evidence →
   `docs/fork/evidence/c7b/`. Halt-mid-fan-out: the cancellation guarantee is already covered at the API +
   worker seams (`test_agent_lifecycle_api`/`test_agent_run_worker`); add a deterministic in-fan-out cancellation
   assertion only if cheap, else note the existing coverage (no in-fan-out skeleton exists today).
5. Fresh-context adversarial + **security + simplification** pass on the diff (every slice). Update
   `docs/fork/HANDOFF.md` + a memory note. Squash-merge under the ADR-F005 gate.

## Recommended order

migration (+ verbatim 0057 `_OLD`, new roster `_NEW`, deal-review bind) → `deal-review` SKILL.md →
`evaluate_position_consistency` + schemas → `reconcile_positions` tool + receipt → backend tests → ADR-F034 →
migration round-trip + rebuild → live fan-out + evidence → review/merge.
