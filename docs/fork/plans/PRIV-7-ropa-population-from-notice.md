# PRIV-7 — ROPA population from a privacy notice (live DeepSeek validation + a `ropa-population` skill)

**Status:** DELIVERED (PR #111) — outcome in `docs/fork/evidence/priv-7/FINDINGS.md`. Phases A (baseline) +
B (skill) + C (escalation/comparison) all run. Two things diverged from the plan, both for the better:
(1) the comparison surfaced and **fixed a production blocker** — langgraph's default `recursion_limit=25` was
crashing skilled runs before `max_steps`; tied it to `max_steps` in `runner.py`. (2) The result exceeded the
target: flash + the skill + an adequate budget built a **fully-linked 9/9 register**, so pro/orchestrator-split
proved unnecessary to hit ~80% (kept as follow-ups). Skill bound **test-only** (maintainer's choice); shipping
its binding migration is a flagged follow-up. · **Branch:** `priv-7-ropa-population-from-notice`
**Milestone:** Oscar Edition / Agentic Modules → realizes MILESTONES § Backlog "ROPA onboarding flow".
**Linked ADRs:** ADR-F018 (module = typed domain + code-validated agent writes), ADR-F019 (relational,
deployment-global register), ADR-F015 (scenario-qualified Deep Agent — the evidence-report mechanism),
ADR-F016/F017 (skills activation / per-area skill subset). A new ADR is drafted **only if findings warrant
one** (see § ADR trigger).

## Context

The maintainer's onboarding vision (2026-06-19): *hand the Privacy agent a real company privacy notice +
answer a ~50-question intake → ~80% of the ROPA auto-populates.* This slice takes the **first, most-grounded
half** — **notice → ROPA** — and runs it **live** as a genuine end-to-end validation of everything PRIV-1…6c
built, against a **real reputable company's notice (Zendesk)**.

The write plumbing already exists: the Privacy Deep Agent has 14 guarded, code-validated ROPA tools
(`propose_processing_activity`/`_system`/`_vendor`/`_transfer`, `link_*`, `add_data_*_categories`, `list_*`),
and its area `profile_md` already tells it to *"map the processing … records of processing (ROPA) … ground
every claim in the programme's own documents and cite."* The open question is **calibration**: does a real
model, reading a real notice, actually drive those tools to a coherent, valid Article 30 register — and what
guidance does it need? The maintainer's direction: **try flash first, graduate to pro only if needed**, and
**write a `ropa-population` skill off the back of what the test reveals.**

Framing (maintainer): this is **one of a family** — later we populate/maintain records from *files,
interviews, client instructions, and analytics*, and a deep agent can fan out subagents (e.g.
*pro orchestrates / flash reads*). This slice is the first; the rest is banked (§ Non-goals / Follow-ups).

## Goals

1. A **provider-gated, self-skipping** live scenario (`@pytest.mark.provider`, like UX-B) that seeds a Privacy
   matter with **Zendesk's public privacy notice** (fetched + held **transiently** in the seeded DB — **not
   committed verbatim**) and drives the agent to build the Article 30 ROPA from it.
2. A **reusable register read-back + coverage scorer**: after the run, snapshot the produced register by
   `source_project_id` and score it against an Article 30(1) checklist (counts per entity; per-activity field
   coverage; invariant integrity). This is the *honest* measure of "how much of the ROPA got populated" — the
   `Receipt` alone only sees tool names + the final answer.
3. A **baseline live run on `deepseek-v4-flash`** (no ROPA-specific skill) → committed behavior + coverage
   report under `docs/fork/evidence/priv-7/` (source URL + retrieval date + a short excerpt + the produced
   register snapshot — **no verbatim notice text**).
4. **Author `skills/ropa-population/SKILL.md`** — the methodology the baseline shows the model is missing
   (identify activities; map lawful basis / Art 9; extract recipients, transfers + safeguards, retention,
   data-subject & data categories; the propose→link order; how to read tool rejections and re-propose). Bind
   it to the Privacy area.
5. A **second run on flash + the skill** → report; **compare** baseline vs skill-assisted coverage.
6. **Findings doc** with an honest verdict + a recommendation on (a) flash↔pro, (b) whether DeepSeek should be
   put forward for ADR-F015 scenario-qualification, (c) what the eventual onboarding flow needs
   (bulk-extract orchestration? the intake? the orchestrator/reader subagent split?).

## Non-goals (this slice) — banked as the family they belong to

- The **~50-question structured intake** (the onboarding flow's second half) — that's the assessment track
  **PRIV-A2 / ADR-F020**.
- **Populating records from files / interviews / client instructions / analytics** — the broader
  "populate-from-source" family; future slices reuse this slice's scorer + skill pattern.
- The **"pro orchestrates / flash reads" subagent split** — needs a Privacy subagent wired (today only
  Commercial has one, UX-B-4) **and** a per-subagent model override (subagents currently inherit the
  gateway-bound parent model, ADR-F010). Real future capability; out of scope here.
- A **web onboarding UI** (a guided bulk-extraction surface).
- **Officially marking DeepSeek "scenario-qualified"** — that's the maintainer's call per ADR-F015; this slice
  produces the evidence and a recommendation, not the ruling.

## Approach — phased, human-in-the-loop

The maintainer wants to steer the flash→pro→skill decisions, so I **execute incrementally and report between
phases** rather than running the whole arc blind.

- **Phase A — infra + baseline (this turn).** Build the notice loader, the scenario, the read-back scorer;
  run flash baseline; report coverage + the honest gaps. **Pause for the maintainer.**
- **Phase B — skill (after A's findings).** Author `ropa-population` SKILL.md targeting A's gaps; bind to
  Privacy (migration); re-run flash+skill; compare. **Pause.**
- **Phase C — escalation + close.** If flash+skill underperforms, run pro. Findings doc; ADR if warranted;
  HANDOFF + MILESTONES; adversarial + security + simplification review; PR.

## Files

**New**
- `docs/fork/plans/PRIV-7-ropa-population-from-notice.md` — this plan.
- `api/tests/agents/scenarios/ropa_eval.py` — `snapshot_register(factory, source_project_id)` +
  `score_coverage(snapshot)` (pure, reusable across the future populate-from-source family) + a notice loader
  `load_notice_document(path)` building a `FixtureDocument` from a local (gitignored) text file.
- `api/tests/agents/scenarios/test_ropa_population_scenario.py` — the provider-gated live scenario(s) +
  read-back + report writer. Self-skips without `LQ_AI_GATEWAY_KEY` (and without `LQ_AI_ROPA_NOTICE_PATH`).
- `skills/ropa-population/SKILL.md` — (Phase B) the methodology skill.
- `api/alembic/versions/00NN_bind_ropa_population_skill_privacy.py` — (Phase B) bind the skill to Privacy
  (idempotent, insert-only-when-absent; symmetric downgrade — the 0056 pattern).
- `docs/fork/evidence/priv-7/` — behavior + coverage reports (flash baseline, flash+skill, [pro]); the
  source URL + retrieval date + a short excerpt; the produced register snapshot. **No verbatim notice.**
- `docs/fork/evidence/priv-7/FINDINGS.md` — the honest verdict + recommendations.

**Edited**
- `.gitignore` — ignore the transient notice text (e.g. `api/tests/agents/scenarios/_local/`).
- `docs/fork/MILESTONES.md` — mark the slice; refine the "ROPA onboarding" backlog with what we learned.
- `docs/fork/HANDOFF.md` — written last.
- Possibly `skills/<...>`-adjacent + migration tests; the contract route tests are **not** touched (no new
  endpoint).

## Notice handling (Zendesk — testing-only, not committed)

1. Fetch Zendesk's public privacy notice (record the exact URL + retrieval date in the report).
2. Normalize to plain text; write to a **gitignored** local path (default
   `api/tests/agents/scenarios/_local/zendesk-privacy-notice.txt`); the scenario reads it via
   `LQ_AI_ROPA_NOTICE_PATH` (defaulting to that path). If the file is absent the test **skips** (so CI and a
   fresh checkout never depend on third-party text).
3. `load_notice_document` chunks it (paragraph/heading-aware) into a `FixtureDocument` so the agent's
   `search_documents`/`read_document` tools work exactly as in production.
4. The committed evidence carries **only** the URL, retrieval date, a short attributed excerpt for context,
   and the **produced** register snapshot — never the full notice. Treated as untrusted model input
   throughout (it already is — it's a document the agent reads; no skill/prompt injection trust).

## Read-back + scoring (the honest measure)

After `run_scenario`, open a session on `seeded.factory` and load the register filtered by
`source_project_id == seeded.project_id` (activities with systems/vendors/transfers/categories eager-loaded;
systems + vendors by `source_project_id`). Score:
- **Counts:** activities / systems / vendors / transfers / data-subject categories / data categories.
- **Per-activity Article 30(1) coverage:** purpose, lawful_basis, controller_role, retention, ≥1 system,
  ≥1 recipient, ≥1 data-subject category, ≥1 data category, special-category handling, ≥0 transfers
  (with safeguard where restricted).
- **Integrity:** every persisted row satisfies the invariants (it must — the write path enforces them; the
  interesting signal is how many proposals the model got *rejected* and whether it recovered — read from the
  run's audited tool dispatches / steps, counts only, never raw values).
- **Latency / steps / cost-cap:** did it complete, clarify, or hit the R4 cost cap / max_steps (a `cap_exceeded`
  on a broad build is itself a finding — it motivates chunking/orchestration in the onboarding flow).

**Dev-DB hygiene:** the register is deployment-global (rows stamped with `source_project_id`, ON DELETE SET
NULL). The test **explicitly deletes** the rows it created by `source_project_id` in teardown so the live run
does not pollute the dev register. (Run against the live dev stack so the gateway is reachable.)

## Verification / Definition of Done

- `ruff format && ruff check` + `mypy` clean (containerized api image); the new test files included.
- **Full** `pytest -q` green in CI — the new provider test **self-skips** without the key, so CI stays green
  and gains no flakiness; pure helpers (`score_coverage`, the notice chunker) get **deterministic unit tests**
  that DO run in CI.
- **Live evidence SHOWN, not asserted:** the flash baseline (and flash+skill) behavior + coverage reports
  committed under `docs/fork/evidence/priv-7/`, kept **verbatim — not tuned green** (ADR-F015 discipline).
- **Security + simplification pass (every slice):** no secrets in code/reports/fixtures (key presence checked
  by length only, never value); the notice text never committed; reports carry counts/IDs/labels, never raw
  provider keys; the audit contract holds; no gateway bypass (every call rides the gateway alias); ORM/
  parameterized only. Delete any dead scaffolding.
- Fresh-context adversarial review of the diff (Workflow, multi-lens → refute-by-default).
- HANDOFF updated last; ADR drafted if § ADR trigger fires.

## ADR trigger

Draft an ADR **only** if the findings produce a structural call, e.g.: putting DeepSeek forward for
ADR-F015 scenario-qualification; or deciding the onboarding flow needs a new capability (a bulk-extract
orchestration tool, or the orchestrator/reader subagent split). Otherwise this is an evidence + skill slice
under the accepted ADR-F018/F019/F015/F016/F017 — **no new ADR**.

## Risks

- **Broad multi-step ask → `cap_exceeded`.** UX-B found tier-4 models over-explore broad asks. A full-ROPA
  build is broad. Mitigations: generous `max_steps` + real `max_tokens` headroom (v4 are reasoning models);
  and the scenario may be run both as one broad ask **and** a staged ask ("first list the activities you can
  identify, then create each") — the delta is a finding about whether the onboarding flow needs staging.
- **Flash under-delivers.** Expected possible; the staged flash→pro plan handles it. Honest reporting either
  way — a partial/failed build is a valid, informative result, not something to hide.
- **Skill authored to game the test.** Guard: write the skill to encode *general* ROPA methodology, then
  judge it on Zendesk (the input) which the skill never mentions; ideally spot-check on a second notice.
