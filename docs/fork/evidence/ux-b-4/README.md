# UX-B-4 — live subagent (delegation) re-qualification (ADR-F015/F017)

Live MiniMax-M3 scenario runs for **Commercial with its `document-researcher`
subagent activated** (migration 0057), driven through the production agent loop
by the UX-B-1 harness with `run_scenario(..., skill_registry=…)` against a
**multi-document RFQ matter** (`subagent_fixtures.py`: RFQ instructions, two
vendor proposals, draft contract terms). The composition point builds the
read-only multi-source backend (ADR-F017): the lead agent sees Commercial's
bound subset at `/skills`, and the subagent — when delegated to — sees its own
(⊆ area) subset at `/skills/subagents/document-researcher`. Per ADR-F015 these
are **observations**, not a pass/fail gate.

Reproduce (out-of-CI, live gateway):

```
docker run --rm --network host \
  -v "$PWD/api:/app" -v "$PWD/skills:/skills:ro" \
  -v "$PWD/docs/fork/evidence/ux-b-4:/evidence" \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e DATABASE_URL=postgresql+asyncpg://lq_ai:$POSTGRES_PASSWORD@localhost:5432/lq_ai \
  -e LQ_AI_GATEWAY_URL=http://localhost:8001 -e LQ_AI_GATEWAY_KEY=$LQ_AI_GATEWAY_KEY \
  -e UX_B4_EVIDENCE_DIR=/evidence -w /app lq-ai-api-dev \
  pytest -q -m provider tests/agents/scenarios/test_subagent_scenarios.py -s
```

## What the snapshot shows

**The mechanism is proven — deterministically, in CI.** The scripted-model
integration test `test_subagent_delegation_nests_steps_via_parent_step_id`
(`tests/agents/test_agent_composition.py`) drives a real delegation through the
production composition point and asserts the settled `AgentRunStep` rows contain
a `task` tool-call with the subagent's steps **nested under it via
`parent_step_id`** (the F0-S7 ancestry). Delegation wiring works end-to-end; no
live model is needed to prove it.

**Finding (kept verbatim, NOT tuned green): MiniMax-M3 does not *elect* to
delegate at this matter size.** Both live scenarios ran to `completed`:

- **Single fact (`rfq_single_fact`) — direct answer, no delegation (correct).**
  "What is the submission deadline?" → `search_documents` → `read_document` →
  grounded, cited answer (`5:00pm on 30 September 2026`). **`task_calls=0`** — it
  rightly did NOT spawn a subagent for one fact. (Shape "miss" is only the soft
  step bound: 7 steps vs a bound of 6 — it read the doc to confirm rather than
  answering from the search snippet, the same benign over-step UX-B-1/2 saw.)
- **Cross-document review (`rfq_cross_document_review`) — handled in one context,
  no delegation.** "Review the RFQ across all the documents, compare the two
  vendors on price/SLA/liability, check against our draft terms, flag risks." →
  M3 issued `search_documents` then read **all four** documents itself
  (`read_document` ×4) and produced a structured, per-document comparison — 13
  steps, `completed`, **`task_calls=0`**. It kept the whole review in its own
  context rather than fanning out to the researcher.

## Reading the finding

This is the honest tier-4 result, and it is **reasonable**: four short
documents fit comfortably in one context, so reading them directly is a fine
strategy — delegation earns its keep on genuinely large matters (dozens of
documents, several independent threads of investigation), which this fixture
deliberately does not inflate to. Forcing delegation by sizing the matter
artificially huge, or by instructing "you must delegate," would be gaming the
qualification, so we did neither.

What UX-B-4 establishes:

- **Delegation is wired correctly and isolated** (ADR-F017): the subagent is
  built live from `agent_config`, inherits the gateway-bound model (no bypass,
  ADR-F010) and the guarded matter tools, and — when invoked — sees only its own
  skill source. Proven by the deterministic test + the multi-source backend unit
  tests.
- **M3 delegates on-demand, and at this matter size that demand is zero.**
  Whether a tier-4 model fans out on a truly large matter is an open calibration
  question for a later slice (options: a profile nudge that names the researcher
  for big matters, a larger fixture, or a stronger qualified model). The cockpit
  default is unchanged for simple matters — exactly the NDA-vs-RFQ posture the
  maintainer set.

## Decisions recorded here

- **Idiomatic per-subagent skill sources (ADR-F017).** Each subagent gets its own
  virtual source over the shared read-only backend — deepagents' documented,
  isolated per-subagent skill model — rather than inheriting the area set. Subset
  per agent, down to the subagent.
- **No scenario tuned to pass.** Both `task_calls=0` results are kept verbatim;
  the deterministic test is the mechanism gate, the live report is the behaviour
  record.
