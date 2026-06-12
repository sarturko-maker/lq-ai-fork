# F0-S9 model-qualification harness

Measures (model × harness-profile) pairs against the LIVE dev stack —
tool-call uptake, task-scoped fan-out compliance, negative-guard noise —
from settled `agent_run_steps` rows. Design: `docs/fork/research/f0-s9-eval-reuse.md`
§3; gate definition: ADR-F004. **Every cycle spends real provider tokens**;
nothing here runs in CI (`testpaths = ["tests"]`).

## One-time seed

```bash
PGPW=$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
docker run --rm --network lq-ai_default \
  -v $PWD/api:/work -w /work -e PYTHONPATH=/work \
  -e DATABASE_URL="postgresql+asyncpg://lq_ai:${PGPW}@postgres:5432/lq_ai" \
  --entrypoint python lq-ai-api:latest -m evals.seed_fixtures
```

Idempotent (uuid5 ids); re-run after editing `fixtures.py`.

## Run cycles

```bash
PGPW=$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
docker run --rm --network lq-ai_default \
  -v $PWD:/repo -w /repo/api -e PYTHONPATH=/repo/api \
  -e DATABASE_URL="postgresql+asyncpg://lq_ai:${PGPW}@postgres:5432/lq_ai" \
  -e LQAI_EVAL_USER_PASSWORD='<admin password>' \
  -e LQAI_EVAL_MODELS=smart -e LQAI_EVAL_N=5 \
  -e LQAI_EVAL_SCENARIOS=batch_fanout \
  -e LQAI_EVAL_OUT=/repo/docs/fork/evidence/f0-s9/results \
  -e LQAI_EVAL_GIT_SHA=$(git rev-parse --short HEAD) \
  --entrypoint bash lq-ai-api:latest \
  -c "pip install -q pytest pytest-asyncio && pytest evals/test_qualification.py -q -p no:cacheprovider"
```

Knobs: `LQAI_EVAL_MODELS` (csv of gateway aliases — a second model family
is one new gateway provider entry + alias away, keys live ONLY in the
gateway), `LQAI_EVAL_N`, `LQAI_EVAL_SCENARIOS` (csv of
`positive_grounding,batch_fanout,negative_control,mismatch`).

Cycles run sequentially (flood brake allows 3 concurrent; sequencing also
keeps the routing-log token window per cycle unambiguous — don't run other
agent traffic during a matrix run).

A cycle FAILS only on runner-hygiene violations (stranded run, completed
run with an empty answer). Metric outcomes are recorded data — thresholds
are set against the baseline, never a priori, never tighter than the CI
(±43pp at N=5, ±29pp at N=10 — quote them).

## Aggregate

```bash
python -m evals.report docs/fork/evidence/f0-s9/results > docs/fork/evidence/f0-s9/matrix.md
```

## Scorer unit tests (no stack, no tokens)

```bash
pytest evals/test_scoring_unit.py -q
```
