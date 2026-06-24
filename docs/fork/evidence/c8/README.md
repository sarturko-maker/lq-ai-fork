# C8 evidence — surgical-redline craft (ADR-F041)

> **⚠ v1 was CONFOUNDED — see `eval-v1-skill-absent/`.** The original C8 eval ran with the
> `surgical-redline` SKILL.md **silently absent from the registry** (an unquoted `": "` in its
> `description:` frontmatter made `yaml.safe_load` parse it as a mapping → the loader skipped it; fixed in
> C3a + guarded by `test_every_real_skill_loads_no_silent_drops`). So every figure below the line "Recorded
> figure" was produced **without the craft skill the eval was meant to measure**. It is preserved verbatim in
> `eval-v1-skill-absent/` and must NOT be read as the craft of the loaded skill. The corrected v2 run (skill
> loaded) lives in `eval/`; the v1→v2 delta is in `../c9/SUMMARY.md`.

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

### Recorded figure — v2 (skill LOADED), DeepSeek flash, 3 reps/scenario

| scenario | surgical-craft pass (self-judge) | boilerplate-bare (deterministic) |
|---|---|---|
| `securescan_saas_msa` | 0 / 3 *(2 ADEQUATE·not-surgical, 1 cap_exceeded/no-redline)* | 2 / 2 redlined |
| `databridge_licence` | 0 / 3 *(STRONG/ADEQUATE/WEAK substance, all not-surgical)* | 2 / 3 |
| **overall** | **0 / 6** *(was 2/6 in the confounded v1)* | 4 / 5 redlined runs keep the key phrases bare (v1 also 4/5) |

**Honest read — this is the WEAK self-judge; do not read 0/6 as a craft regression.** C8 uses DeepSeek to
judge DeepSeek with an all-or-nothing `surgical` boolean ("no if ANY material clause was struck wholesale"),
which is exactly why C9's **stronger Claude judge** exists. The v2 self-judge verdicts themselves describe
*mostly* surgical redlines — e.g. "*§8 indemnity is textbook surgical … shall indemnify, defend and hold
harmless left BARE … Elsewhere, changes are surgical: narrow insertions … standard boilerplate left intact*"
— tripped to `surgical=false` by one or two dense licence/data clauses rewritten wholesale. Deterministic
boilerplate-bare held at **4/6** (v1 was 4/5). **The authoritative craft read is the Claude-judged C9, not
this self-judged rate — see `../c9/SUMMARY.md`.**

### Limitations / next levers

- The DeepSeek self-judge under-credits surgical work and is unstable on the borderline `surgical` boolean —
  use it only as a relative, judge-held-constant signal; the absolute craft signal is C9 (Claude judge).
- The residual (dense single-party grant/data-licence clauses rewritten wholesale; occasional no-redline /
  cap_exceeded robustness) is characterised in `../c9/SUMMARY.md`; the model tier does NOT fix it (pro is worse).
- A proper craft-rate needs **multi-rep × strong-judge** — C8 is multi-rep but weak-judge, C9 is strong-judge
  but n=1. See the C9 SUMMARY follow-ups.
