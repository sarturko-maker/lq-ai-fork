# C4 evidence — Adeu surgical-redline tool (`apply_redline`, ADR-F031)

The maintainer's requirement for C4: **judge the produced `.docx`, not the word count**, and separate
*mechanism* quality (does the system render a good redline from good edits — model-free) from *model*
quality (did the model pick good edits). The artifacts here are organised that way.

## `golden/` — Layer 1+2, model-free (the SYSTEM, discounting model quality)

The committed golden-redline corpus (`api/tests/agents/scenarios/.../test_redline_corpus.py`) feeds
**hand-authored known-good surgical edits** through the real Adeu pipeline and asserts, against the produced
document: unchanged text stays bare (surgical *rendering*), and accept-to-clean yields the balanced clause.
Three clauses — vendor-favoured limitation of liability, one-sided indemnity, one-sided IP assignment.
`make_golden_evidence.py` dumps each scenario's redlined `.docx` + a readable `[-del-][+ins+]` reconstruction
here for inspection. *(Run via the dev image; see the script header.)*

## `live/` — Layer 3+4, DeepSeek (the MODEL on top of the system)

`scenario-saas-msa/SecureScan-MSA.docx` is the input: a realistic **vendor-favoured SaaS MSA** (one-sided
liability cap, indemnity, IP/data, warranty, auto-renewal). The live provider test
(`test_commercial_redline_scenario.py`) seeds it into a Commercial matter in object storage, has **DeepSeek**
read it and call `apply_redline`, then writes here:

- `SecureScan-MSA (redlined).docx` — the model's actual tracked-changes work product (open in Word).
- `redline-reconstruction.txt` — the same redline as readable `[-del-][+ins+]`.
- `accepted-clean.txt` — the clause text after accepting all changes.
- `judge-verdict.md` — an adversarial redline-quality critic scoring the §5.1 rubric (STRONG/ADEQUATE/WEAK
  + bullets). **A finding (ADR-F015), not a pass/fail gate** — substantive quality is human-owned.
- `redline-report.json` — the run receipt (tools called, steps, status, model).

## How to read the redline

`apply_redline` is the **system**; the surgical gate (D1–D6, model-free) only proves an edit is
narrow/well-formed/scoped — it cannot prove the redline is *good for the client*. So the golden corpus shows
what the system does with good edits; the live run shows what DeepSeek chose; the judge + the maintainer's own
read of the `.docx` are where substantive quality is assessed.
