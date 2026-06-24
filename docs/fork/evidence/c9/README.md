# C9 evidence — Claude-judged manual redline tests

> **Current run = v3 (Adeu native word-diff render, ADR-F045).** `flash/`, `verdicts/` and `SUMMARY.md` hold
> the v3 result: the tool now keeps unchanged wording bare via Adeu's word-level diff, and the skill is
> simplified to "quote the clause, change only the necessary words." `SUMMARY.md` carries the v1→v2→v3 matrix.
> Earlier runs are preserved verbatim:
> - **`v2-wholesale-render/`** — skill loaded but the old wholesale prefix/suffix renderer (the swallow). v2's
>   own SUMMARY/verdicts are inside it.
> - **`v1-skill-absent/`** — the original CONFOUNDED run: the `surgical-redline` skill was **silently absent
>   from the registry** (frontmatter `": "` bug, fixed in C3a), so its "pervasive mutualisation is a *method*
>   weakness" headline was produced without the skill that teaches that move.

C9 upgrades C8's craft signal from **DeepSeek-judging-itself** to **Claude (Opus 4.8) judging DeepSeek**, over
a corpus that spans contract types **and** complexity, with the produced `.docx` surfaced for the maintainer
to open in Word. (Maintainer steer, 2026-06-22.) Plan: `docs/fork/plans/C9-claude-judged-redline-tests.md`.

## What's here

- **`SUMMARY.md`** — read this first: the result matrix + the cross-cutting finding (complexity is not the
  craft predictor; the weakness is pervasive mutualisation; the flash-vs-pro model-vs-method conclusion).
- **`verdicts/<id>.md`** — Claude's per-instrument verdict, with specific edit citations (flash + pro where
  both were run).
- **`flash/<id>/`** and **`pro/<id>/`** — per model, per instrument:
  - `original-<name>.docx` — the vendor's draft (the input).
  - `<name> (redlined).docx` — **the deliverable**: open in Word/LibreOffice for native tracked changes +
    margin comments (the rationale on each edit). This is what a partner reviews.
  - `reconstruction.txt` — plain-text `[-struck-][+inserted+]` view (read without Word).
  - `accepted-clean.txt` — the document with all changes accepted.
  - `manifest.json` — per-instrument status, model turns, tools called, and the deterministic
    `boilerplate_bare` flag (did the recognisable phrase survive *unchanged*).

## The corpus

**moderate (short-clause):** SecureScan SaaS MSA · DataBridge software licence · Aegis "mutual" NDA ·
Northwind DPA · Meridian professional-services SOW.
**complex (dense, multi-limb — the hard surgical test):** Helios master SaaS+services · Orion software
development + licence. The complex instruments are built so the *correct* redline is a few narrow edits
**inside** long clauses, and striking a whole clause would destroy good language (existing carve-outs, the
indemnification procedure, the SLA mechanics, the exclusion list).

All instruments are **synthetic** (fictional parties; no real data, PII or secrets).

## How it was produced

Provider-marked harness `api/tests/agents/scenarios/test_commercial_redline_manual.py`, run live on the dev
stack with the bound `surgical-redline` skill (v2.0.0) active and the word-diff renderer (ADR-F045). DeepSeek
is instructed *purposively* (named one-sided heads, surgical technique left to the skill); Claude then judges
the produced document.

```
# flash baseline (all 7 → c9/flash); pro re-run of the complex pair + flash failures (→ c9/pro)
LQ_AI_SCENARIO_MODEL=deepseek      UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c9/flash  pytest -m provider …
LQ_AI_SCENARIO_MODEL=deepseek-pro  UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c9/pro \
  LQ_AI_C9_ONLY=helios_master_agreement,orion_dev_licence,meridian_services_sow,aegis_mutual_nda  pytest -m provider …
```

`deepseek` = `deepseek-v4-flash`; `deepseek-pro` = `deepseek-v4-pro` (gateway aliases). Provider-marked →
CI-skipped; re-run live to regenerate. A subset re-run (`LQ_AI_C9_ONLY`) merges into the model's
`manifest.json` without clobbering the others.
