# C8 evidence — surgical-redline craft (ADR-F041)

C8 makes structure-preserving, multi-narrow-edit redlines the *reliable* default — via a curated
`surgical-redline` skill + a refreshed Commercial doctrine, a `preview_redline` self-review tool, and an
**eval** that measures the surgical-craft rate. (Craft is a prompt-quality property tuned by eval, not a
runtime gate; integrity stays with C4's D1–D6 gate; the human owns the accept.)

## What's here

- `eval/eval-report.json` — the aggregate run: per-scenario and overall **surgical-craft rate**
  (`surgical_pass / total`), plus a row per run (status, model turns, judge verdict, `surgical` flag,
  deterministic `boilerplate_bare` check).
- `eval/<scenario>-rep<N>-reconstruction.txt` — the produced redline as `[-struck-][+inserted+]` (judge the
  PRODUCED document, not the word count — the maintainer's requirement).
- `eval/<scenario>-rep<N>-verdict.md` — the craft-judge verdict (sharpened §5.1 rubric: surgical?
  boilerplate bare? right balance mechanism?).

## How it was produced

The model is given a plain redline **task** (not surgical-technique instructions) so the eval measures
whether the bound skill + doctrine actually drive the craft:

```
DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \
LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_REDLINE_EVAL_REPS=3 \
UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c8 \
pytest -m provider tests/agents/scenarios/test_commercial_redline_eval.py -s
```

Corpus: the vendor-favoured SaaS MSA (`securescan_msa`) + a vendor-favoured software licence
(`databridge_license`). Provider-marked → CI-skipped; run live to regenerate.

## Reading the result

A run counts as a surgical pass when the judge rates it STRONG/ADEQUATE **and** calls it surgical.

### Recorded figure (DeepSeek, 3 reps/scenario, tuned skill)

| scenario | surgical-craft pass | boilerplate-bare (deterministic) |
|---|---|---|
| `securescan_saas_msa` (in-distribution) | **2 / 3** | 2 / 3 |
| `databridge_licence` (out-of-distribution) | 0 / 3 | 2 / 2 redlined |
| **overall** | **2 / 6** | 4 / 5 redlined runs keep the key phrases bare |

**Honest read.** The mechanism works and the flagged **§8 indemnity is surgical in the passing runs** (the
`shall indemnify, defend and hold harmless` verb phrase stays bare; the scope is narrowed and the reciprocal
indemnity *inserted*) — a clear improvement over the C4 baseline that struck-and-retyped it. The skill keeps
the **key boilerplate bare in 4/5 redlined runs** (incl. the §9 cap stem). But the strict craft judge is
**not** yet "reliably surgical": the out-of-distribution licence still gets some clauses wholesale-rewritten
(judge says STRONG substance, not-surgical), and **1/6 runs produced no redline at all**. This is a
model-bound ceiling on DeepSeek, honestly measured — *not* a claim that surgical craft is solved.

### Limitations / next levers (the eval makes these cheap to re-measure)

- Out-of-distribution craft (non-MSA instruments) is weaker — broader worked examples or a stronger
  qualified model would lift it.
- ~1/6 runs fail to produce a redline (robustness gap — investigate step budget / editor-error recovery).
- Re-run this eval when a stronger model is qualified, or after further skill tuning, to track the rate.
