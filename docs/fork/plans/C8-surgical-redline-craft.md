# C8 — Surgical-redline craft (prompt + self-review + eval)

> **Status: DRAFT for maintainer edit.** Explore → **this plan** → human edits → implement (CLAUDE.md
> § Iteration). Settled with the maintainer in-session (2026-06-22). Companion ADR: **F041** (proposed).
> Memory: [[surgical-redline-craft-slice]]. Builds on C4 (ADR-F031/F035).

## The problem (from the C4 live runs)

C4 shipped the redline *mechanism*: a deterministic integrity gate (D1–D6), Adeu native tracked-changes
rendering, matter-scoped persistence, the human owns the accept. What C4 **cannot** guarantee is redline
**craft** — that the agent makes *structure-preserving, sub-sentence, multi-narrow-edits-per-clause*
changes rather than striking a whole clause and retyping it.

Across C4's live DeepSeek runs the craft was **run-to-run variable**. The merged §8 evidence is actually
surgical (it keeps `The Customer shall indemnify, defend and hold harmless …` **bare**, narrows the scope,
and *inserts* the Vendor IP indemnity). But an **earlier** run struck the whole §8 clause and retyped it
`Customer → Vendor` — the rip-and-replace the maintainer flagged. **C8's job is variance reduction: make
the surgical shape the reliable default, and prove it with measurement** — not fix a one-off.

A structural gate can prove a redline is *well-formed*; it cannot prove it is *good* (architecture
§ "Tools & skills", Plane 2/3: *substance → human-owns + optional substantive review*). Craft is therefore
a **prompt-quality problem, validated by evaluation** — not a new runtime gate.

## Decision (settled — see ADR-F041)

Three levers, in order of weight:

1. **System prompt forces the shape** — a curated `surgical-redline` abstract-method skill (+ a tightened
   line in the Commercial `profile_md` doctrine) with **worked §8 before/after examples**: decompose a
   clause into narrow edits, swap the party, keep recognisable boilerplate (`shall indemnify, defend and
   hold harmless`) **bare**, *insert* additions — never strike-and-retype. **This is the primary lever.**
2. **A self-review tool the agent can call** — `preview_redline(document_name, edits)`: runs the same
   integrity gate + Adeu dry-run + reconstruction and returns the rendered `[-del-][+ins+]` view,
   **persisting nothing**. The skill instructs: *draft edits → preview → inspect for surgical craft →
   revise → `apply_redline` once*. This is option **(B)** — a self-review primitive, not a forced per-run
   critic. No extra LLM call (the agent's own next reasoning step inspects).
3. **An eval harness that measures the surgical-craft rate** — runs many vendor-favoured scenarios ×
   repetitions, scores each produced `.docx` for surgical craft with the redline-quality judge, and reports
   the **rate + variance**. This is the loop that *tunes the prompt* until redlines are reliably surgical,
   and the evidence that C8 worked.

### Explicitly rejected (and why)

- **(A) Mandatory per-run LLM critic.** Reliable but **too slow** — it taxes every production redline with
  an extra inference round-trip. The maintainer's call: we don't pay per-run latency to fix a prompt
  problem.
- **Deterministic single-region gate (D7).** Over-engineering: **Adeu already renders surgically**
  (settled), so a code rule re-deriving "is this surgical" only papers over a weak prompt — at the cost of
  threshold calibration and false positives (it would even reject the §9 edit from the "STRONG" run).
- **An LLM verdict in the *integrity* gate.** Every agent-tool write-gate in the codebase is deterministic
  code (ADR-F018: "code validates, never LLM verdicts"); C8 does not change that. Integrity stays
  deterministic; craft is tuned by eval; the human owns the accept.

## Goals

- The Commercial agent **reliably** produces structure-preserving, multi-narrow-edit redlines on
  one-sided clauses — measured as a **surgical-craft rate** across repeated live runs, materially higher
  and **lower-variance** than the C4 baseline.
- A reusable, expandable **eval harness + scenario corpus** that scores produced redlines for craft (not
  word-count), so future prompt/model changes are measured the same way.
- A `preview_redline` self-review primitive the agent uses to see and correct its tracked changes before
  committing.

## Non-goals

- No change to C4's integrity gate (D1–D6), `apply_redline` write path, Adeu rendering, or matter-scope.
- No runtime critic / D7 / LLM-in-the-write-gate.
- No controlling-skill code machinery (instrument classifier, non-shadowable namespace, apply-receipt) —
  that is **C6 / F038**. The C8 skill is a **curated abstract-method skill** (bound + named in the
  doctrine), available with today's wiring.
- No negotiation rounds (C5), deal-context memory (C3), or fan-out (C7).

## Files (anticipated)

**Skill + doctrine (data):**
- `skills/surgical-redline/SKILL.md` (new) — abstract-method craft skill; worked §8 (and §9) before/after.
- `api/alembic/versions/0067_commercial_surgical_redline_skill.py` (new, **fresh head off 0066**) —
  idempotent, never-clobber (0056/0066 precedent): add `surgical-redline` to `_DEFAULT_BINDINGS["commercial"]`
  **and** tighten the redline line in the Commercial `profile_md` (guarded `WHERE profile_md = :old`).

**Self-review tool (code):**
- `api/app/agents/commercial_tools.py` — add `preview_redline` guarded tool (reuses `service.dry_run` +
  `reconstruct_redline_text`, runs `evaluate_gate`, persists nothing); add to `COMMERCIAL_TOOL_NAMES`.
- `api/app/agents/composition.py` — no change if the grant set is read from `COMMERCIAL_TOOL_NAMES`
  (verify; the Commercial branch already grants the whole frozenset).

**Eval + tests:**
- `api/tests/agents/scenarios/securescan_msa.py` — extend with per-clause **surgical-shape expectations**.
- `api/tests/agents/scenarios/<2-3 more vendor scenarios>.py` (new) — corpus breadth.
- `api/tests/agents/scenarios/test_commercial_redline_eval.py` (new, provider-marked) — runs each scenario
  K times, judges surgical craft (sharpened rubric), writes per-run reconstructions + an **aggregate
  surgical-craft-rate report** to the evidence dir.
- `api/tests/agents/test_commercial_tools.py` / `test_redline_corpus.py` — `preview_redline` happy-path +
  render-and-read golden (the §8 decomposition keeps `shall indemnify, defend and hold harmless` bare).
- **Fix the C4 live-scenario `_seeded` no-op cleanup leak** (carried from C4) in
  `test_commercial_redline_scenario.py`.

**Docs:**
- `docs/adr/F041-surgical-redline-craft.md` (new, proposed).
- `docs/fork/research/commercial-lawyer-method.md` — note the craft-via-prompt+eval decision (§5/§6 cross-ref).
- `docs/fork/evidence/c8/` — eval report + per-run reconstructions + the human `.docx` artifacts.
- `docs/fork/HANDOFF.md` — pickup → next slice.

## The skill (sketch — maintainer to steer the doctrine)

`surgical-redline` SKILL.md teaches **one discrete change = one narrow edit**, with the §8 worked example:

> **Anti-pattern (rip-and-replace):** strike the whole clause and retype it.
> `[-The Customer shall indemnify, defend and hold harmless the Vendor … Customer Data.-]`
> `[+The Vendor shall indemnify … third-party IP …+]`
>
> **Surgical (decompose; keep boilerplate bare):**
> - swap the party: `The [-Customer-][+Vendor+] shall indemnify, defend and hold harmless the
>   [-Vendor-][+Customer+] …` — the verb phrase stays **bare**;
> - narrow the scope: one edit on the trigger words;
> - **insert** the third-party-IP indemnity as an addition after the existing clause.

Plus: reward keeping recognisable boilerplate bare; rationale on every substantive edit; use
`preview_redline` to inspect before `apply_redline`.

## The eval (the maintainer's "run enough tests to get to surgical")

- **Corpus:** the SaaS MSA + 2–3 more vendor-favoured contracts, each a single-source module
  (`CLAUSES`, `build_docx()`, `normalized_text()`, **+ per-clause `surgical_expectations`**: which boilerplate
  must stay bare, which party-swap/insert is expected).
- **Runner (provider-marked, DeepSeek):** for each scenario, run the live agent **K times** (variance is the
  point), capture the redline, reconstruct it, judge craft.
- **Judge (sharpened):** the redline-quality judge scores **craft** explicitly — structure-preserving?
  boilerplate bare? multiple narrow edits (not one block)? no rip-and-replace? → STRONG/WEAK + per-criterion.
- **Report:** `surgical-craft rate = surgical_runs / total_runs` per scenario + aggregate, written to
  `docs/fork/evidence/c8/`. The C4 baseline is the comparison.
- **Tuning loop:** run → refine skill/doctrine → re-run, until the rate is acceptably high and stable.
  (Judging across many runs can fan out via a Workflow; the agent-run itself drives the live gateway.)

## Verification / DoD (ADR-F005)

- Layer-1/2 golden tests for `preview_redline` (render-and-read; §8 decomposition; boilerplate bare) pass in CI.
- Eval shows a materially higher, lower-variance surgical-craft rate vs the C4 baseline (evidence committed).
- ruff + mypy clean; full api suite green with counts quoted; fresh head 0067 verified on a throwaway pgvector.
- Live DeepSeek evidence: the §8-class clause redlined surgically (multi narrow edits, boilerplate bare)
  reliably across runs; judge STRONG.
- Fresh-context adversarial + **security + simplification** review (skill body is curated model-input — review
  it like code; no secrets/PII in evidence; the live-test leak fixed). HANDOFF updated. Squash-merge.

## Open questions for the maintainer

1. **Slice size.** Skill + preview tool + multi-scenario eval + tuning may exceed one ≤2–3-day PR. Keep as
   one C8, or split **C8a** (skill + `preview_redline` + golden tests) from **C8b** (eval harness + tuning)?
   *(Recommendation: one slice; the eval is how we tune the skill, so they're coupled — but split if it grows.)*
2. **Tool name** — `preview_redline` vs `review_redline`. *(Recommendation: `preview_redline`.)*
3. **Acceptable surgical-craft rate** to call C8 done (e.g. ≥X/Y runs STRONG with no rip-and-replace), and
   **how many scenarios × repetitions** the eval should cover.
4. **Stronger-model inspection at eval time.** Should the judge run on a stronger tier than the drafter
   (gateway alias), to make the craft scoring more discriminating?
