# C9 — Claude-judged manual redline tests (5 agreements)

> **Status: implemented.** Maintainer-steered in-session (2026-06-22, after C8 merged).
> Memory: [[claude-judged-redline-tests-slice]]. Builds on C4 (ADR-F031/F035) and C8 (ADR-F041).
> **No new ADR** — C9 reuses the C4/C8 mechanism and adds a stronger *judge* + corpus breadth; the
> one code change (graceful `grep`/`glob` on the skills backend) is a robustness bugfix that *honours*
> ADR-F016's existing "steer to `read_file`" intent, not an architectural decision.

## The problem (from C8)

C8's surgical-craft eval used **DeepSeek as its own craft-judge** — a weak signal: the same model that
drafted the redline grades it. The maintainer's steer: use a **stronger judge**. *"Manual tests where you
[Claude] would be the judge. DeepSeek redlines, you judge whether the redlining is lawyer-like. You
instruct DeepSeek purposively and judge its result. You then make the docx files available for me to
review. Let's have 5 full agreements."*

## Decision (settled with the maintainer)

- **DeepSeek redlines, Claude judges.** The harness drives DeepSeek (the qualified live model) to redline
  five concise-but-complete vendor-favoured agreements under *purposive* instruction; **Claude (this agent,
  Opus-tier) then judges** each produced redline for lawyer-like craft. This harness deliberately does
  **not** call an automated craft judge — the judgement is Claude's, recorded as committed verdicts.
- **Five instruments span contract types** so the judgement is not MSA-bound: the two C8 instruments
  (SaaS MSA, software licence) + three new ones (a "mutual" NDA, a controller→processor DPA, a
  professional-services SOW).
- **The `.docx` files are the deliverable.** Every redlined `.docx` (+ the original, a readable
  `[-del-][+ins+]` reconstruction, and the accept-to-clean text) lands in `docs/fork/evidence/c9/<id>/`
  for the maintainer to open in Word.

## What C9 does NOT change

- C4's deterministic integrity gate (D1–D6), `apply_redline`/`preview_redline`, Adeu rendering, matter
  scope (ADR-F035), human-owns-accept — all untouched.
- No new runtime critic / gate (ADR-F041 stands). No migration (the `surgical-redline` skill is already
  bound from C8). No new dependency.

## Files

**Corpus (new instruments — single-source: uploaded `.docx` text == searchable `normalized_content`):**

*moderate (short-clause):*
- `api/tests/agents/scenarios/aegis_mutual_nda.py` — a "mutual" NDA drafted one-directionally for the
  Discloser (overbroad definition, no exclusions, perpetual term, return-on-demand, one-sided injunctive
  relief + indemnity).
- `api/tests/agents/scenarios/northwind_dpa.py` — a controller→processor DPA skewed to the Processor
  (own-policy processing, own-purpose/model-training use, unrestricted sub-processing, 30-day breach
  window, no audit, discretionary transfers, retention).
- `api/tests/agents/scenarios/meridian_services_sow.py` — a professional-services agreement skewed to the
  Supplier (deemed acceptance, uncapped T&M, deliverable IP to the Supplier, no conformance warranty, free
  personnel substitution, one-sided indemnity + cap + termination).

*complex (dense, multi-limb — added mid-slice on the maintainer's steer that the **real** test is surgical
craft on long clauses where most language must be LEFT ALONE, not short clauses that are trivially
replaceable):*
- `api/tests/agents/scenarios/helios_master_agreement.py` — a master SaaS+services agreement with a layered
  limitation-of-liability (cap + super-cap + existing carve-outs + time-bar), a multi-limb indemnity with
  procedure, a structured IP clause, and an express-warranty-plus-disclaimer — each built so the fix is a
  few narrow edits inside a big block.
- `api/tests/agents/scenarios/orion_dev_licence.py` — a software development & licence agreement (acceptance
  procedure, developed-IP/licence, support SLA with service credits, escrow, layered liability).

**Harness (new, provider-marked, CI-skipped):**
- `api/tests/agents/scenarios/test_commercial_redline_manual.py` — 5-instrument corpus + a *purposive*
  per-instrument prompt (names our side + the specific one-sided heads; leaves surgical *technique* to the
  bound skill). Runs DeepSeek once per instrument with the real skill registry active, captures the
  artifacts to `c9/<id>/`, merges a `manifest.json`. `LQ_AI_C9_ONLY=<id>[,<id>]` re-runs a single
  instrument without clobbering the others (DeepSeek is stochastic).

**Substrate robustness fix (the C9 unblocker):**
- `api/app/agents/skill_backend.py` — `RegistrySkillBackend.grep`/`glob` now return a graceful
  *unsupported* `GrepResult`/`GlobResult` (steer to `read_file`/`ls`) instead of inheriting the protocol
  default `raise NotImplementedError`. deepagents' `agrep`/`aglob` wrap the sync call in `to_thread` and do
  **not** catch a backend `NotImplementedError`, so the raise propagated out of the tools node and
  **failed the whole run** the moment a model reached for the builtin `grep`/`glob` (observed live: the NDA
  run crashed mid-redline). The fix removes that foot-gun for every area agent (Privacy too), without
  adding a search capability the curated-library design deliberately omits.
- `api/tests/agents/test_skill_backend.py` — locks the graceful error on the sync methods **and** the
  async wrappers the filesystem middleware actually invokes.

**Docs / evidence:**
- `docs/fork/evidence/c9/` — per-instrument `original-*.docx` + `* (redlined).docx` +
  `reconstruction.txt` + `accepted-clean.txt`; `manifest.json`; `verdicts/<id>.md` (Claude's verdicts);
  `SUMMARY.md` (Claude's cross-cutting finding); `README.md`.
- `docs/fork/HANDOFF.md` — pickup → next slice.

## Judging (Claude, the strong judge)

For each produced redline Claude reads the original + reconstruction + accepted-clean and grades, with
specific edit citations:
1. **Surgical craft** — narrow, structure-preserving edits with recognisable boilerplate left bare, or
   whole-clause rip-and-replace?
2. **Substance / balance** — did it fix the right one-sided heads with the right mechanism (mutualise,
   carve-outs from the cap, exclusions, audit right, transfer safeguards, IP assignment/licence-back)?
3. **Coherence** — do the edits read as a coherent clause; any broken anchors or over/under-protection?
4. **Completeness** — were the material one-sided heads worked through?
5. **Lawyer-likeness** — would a supervising commercial lawyer accept this as a competent first markup?

The deterministic `boilerplate_bare` flag (did the recognisable phrase survive *unchanged*?) is recorded
as a corroborating craft signal, not the judgement.

## Verification / DoD (ADR-F005)

- The grep/glob fix: ruff + mypy clean; `test_skill_backend.py` green (incl. the new graceful-search test).
- The new corpus + harness import, build, and run; touched-area regression suite green with counts quoted.
- Live evidence: redlined `.docx` produced and captured; Claude's per-instrument verdicts + an honest
  overall finding (`docs/fork/evidence/c9/SUMMARY.md`), with a **flash-vs-pro** control (`deepseek` vs
  `deepseek-pro`) for the cases craft fell short — the maintainer's "if it fails, re-run on DeepSeek Pro to
  rule out a model issue."
- Fresh-context adversarial + **security + simplification** review (synthetic contracts carry no real
  PII/secrets; evidence dir carries no secrets; the backend fix is read-only). HANDOFF updated.
- Squash-merge per ADR-F005.

## Outcome (recorded)

Flash surgical-craft pass **5/7** by the strong (Claude) judge — well above C8's self-judged 2/6. The
**complex** instruments scored *among the best on both models* (complexity is not the craft predictor); the
one consistent craft weakness is **pervasive mutualisation** (one-directional-throughout clauses → whole-
clause rewrite). The pro re-run shows the stronger tier does **not** reliably fix craft — it fixed the SOW
*robustness* (flash produced no redline) but did **worse** on the NDA (looped to `cap_exceeded`). So the
lever for the remaining weakness is **method** (a mutualisation worked-example in `surgical-redline` + a
redline step-budget tier), not the model. Full detail + the result matrix in `docs/fork/evidence/c9/SUMMARY.md`.
