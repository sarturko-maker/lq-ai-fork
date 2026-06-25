# C7b evidence — drafter/reviewer fan-out roster + post-fan-out reconciliation (ADR-F034)

The deterministic mechanics are pinned in the CI suite (no provider needed):

- **Roster fan-out nesting** — `tests/agents/test_agent_composition.py::test_multi_subagent_fan_out_nests_every_delegate`
  drives the REAL deepagents loop with a scripted model: the lead delegates to `clause-drafter` **and**
  `clause-reviewer`, and each delegate's turn nests under its own `task` step via `parent_step_id`.
- **The reconciliation gate** — `tests/agents/test_position_reconciliation.py` (12 cases) pins
  `evaluate_position_consistency` (divergence without a resolution → reject; with a resolution → reconciled;
  duplicates collapse; normalization; collect-all-errors); `tests/agents/test_commercial_tools.py` pins the
  wired `reconcile_positions` tool (records one counts-only receipt + audit on success, **nothing** on an
  unresolved divergence, reject-and-guide on malformed input).
- **Migration `0073`** — `tests/test_practice_areas.py::test_commercial_roster_migration_is_idempotent`
  (reconciling swap of the verbatim 0057 config → roster; never-clobber operator edit; no duplicate binding) +
  the roster assertion (`[document-researcher, clause-drafter, clause-reviewer]`, every member's skills ⊆ area,
  no `model` key). Upgrade→downgrade→upgrade round-trip verified on a throwaway pgvector DB.

## Live (DeepSeek `deepseek`-flash, dev stack) — `fan-out-reconcile.json`

`tests/agents/scenarios/test_commercial_fan_out_scenario.py` (provider-marked, CI-skipped) drives the real
commercial agent on the Acme MSA across three material heads. Per ADR-F015 the assertions are RIG-only
(terminal status + a model turn); the fan-out / reconcile **shape** is the recorded finding below.

**Run 1 (max_steps=48):** **fan-out proven** — 3 `task` delegations, **31 steps nested** under them (the new
roster runs end-to-end with correct ancestry). The run hit `cap_exceeded` during drafting (each drafter
re-`search_documents`/`read_document`'d the matter), so it never reached `reconcile_positions`.

**Run 2 (max_steps=80, tightened prompt) — the full chain proven** (`fan-out-reconcile.json` holds this run):
- `task_delegations: 3`, `nested_under_task: 43` — the `clause-drafter` roster fans out, subagents run nested.
- `reconcile_positions_calls: 2` — the new tool fires live (a first call then a second — the gate's
  reject-and-retry loop working against the real model).
- `reconciliation_receipts: 1` — recorded to matter memory:
  *"Reconciled 3 drafted position(s) into 3 head(s) (0 divergence(s) resolved): Indemnity (missing — new
  clause), Limitation of Liability (§7), Term & Termination (§1)."* — **head names + counts only, no position
  text** (the audit row carries counts only).

**Honest finding (ADR-F015).** Both runs end `cap_exceeded`: deepseek-flash keeps exploring *after* it has
fanned out and reconciled (the same over-exploration trait recorded across prior commercial scenarios). The
**C7b behaviour — fan out the roster, reconcile the drafts into one position per head, record the receipt —
completes before the cap** (the reconcile + receipt land mid-run in run 2). The step-budget tuning / drafter
over-reading is a model-craft matter, not a C7b mechanism defect; the mechanism is deterministically pinned
above. A Claude-judged craft eval for the `deal-review` skill is deferred (no Anthropic key on the local
gateway — backlog, as for C5b-2).
