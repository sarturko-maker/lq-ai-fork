# UX-B-2 — default practice-area behavior reports (ADR-F015)

Live MiniMax-M3 scenario runs for the four areas configured in this slice
(Disputes / M&A / Privacy / Employment), driven through the production agent
loop by the UX-B-1 harness (`api/tests/agents/scenarios/`). Commercial's
baseline lives in `../ux-b-1/`. Per ADR-F015 these are **observations**, not a
pass/fail gate: a shape-miss is a finding that calibrates the area profile, not
a test failure. Runs are **non-deterministic** (tier-4) — the numbers are a
snapshot, and the **final-answer excerpt in each report is the authoritative
record**, not the coarse `shape_matched` heuristic.

Reproduce (out-of-CI, live gateway):

```
docker run --rm --network host \
  -v "$PWD/api:/app" -v "$PWD/skills:/skills:ro" \
  -v "$PWD/docs/fork/evidence/ux-b-2:/evidence" \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e DATABASE_URL=postgresql+asyncpg://lq_ai:$POSTGRES_PASSWORD@localhost:5432/lq_ai \
  -e LQ_AI_GATEWAY_URL=http://localhost:8001 -e LQ_AI_GATEWAY_KEY=$LQ_AI_GATEWAY_KEY \
  -e UX_B2_EVIDENCE_DIR=/evidence -w /app lq-ai-api-dev \
  pytest -q -m provider tests/agents/scenarios/test_default_area_scenarios.py
```

## What the snapshot shows

All twelve scenarios across the four areas ran to `completed` — the rig and the
configured profiles drive the loop end-to-end with no stranded or `cap_exceeded`
runs. Across areas M3:

- **grounds + cites cleanly** on a direct fact (searches, often reads, then
  answers with the document name + page/section);
- **declines honestly** an action it has no tool for (issue/serve a claim, sign
  + wire funds, terminate + email) — it states its inability and the governance
  reasons rather than faking a confirmation;
- **clarifies** an ambiguous referent for three of the four areas instead of
  guessing — the calibrated profile sentence ("ask one brief clarifying
  question before guessing") is visibly echoed in the answers.

**Residual finding (calibration target, not a defect):** M3's tool-use
*efficiency* varies run to run — on some grounded fetches it issues a redundant
second `search_documents` (and a `read_document`) before answering, pushing the
step count past the soft bound. The answer is still correct and cited; the
finding is over-exploration, which a later slice can address with a "search
once, precisely" profile note or a tighter tool description. This matches the
UX-B-1 observation that M3's multi-step behaviour is inconsistent.

## Decisions recorded here

- **Tier floors stay NULL for every area.** MiniMax-M3 is the only S9-qualified
  model (tier 4); any area floor stronger than 4 would make every run under the
  area fail `tier_below_minimum`, and a floor of 4 is redundant. Operators set a
  floor via the admin PATCH once a stronger model is qualified (the 0054
  Commercial rationale).
- **No live subagents are seeded (agent_config stays `{}`).** The composition
  point renders area subagents **live**, and delegation is strictly harder than
  the multi-step chaining M3 is already inconsistent at. Per ADR-F015 nothing
  ships activated until a scenario report shows M3 handles it, and the UX-B
  decomposition sequences subagents to **UX-B-4** (after skills) with their own
  qualification. Privacy's forward-looking profile is prose only.
