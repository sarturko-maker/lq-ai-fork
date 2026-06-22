# ADR-F041 — Surgical-redline craft: prompt-forced shape + self-review tool + eval, not a runtime gate

- Status: proposed
- Date: 2026-06-22
- Deciders: Arturs (maintainer)
- Relates: extends ADR-F031 (Adeu redline tool + the D1–D6 integrity gate), ADR-F028 (Commercial method
  doctrine in `profile_md`), ADR-F018 (code-validated writes — deterministic, never LLM verdicts),
  ADR-F005 (agent-merged DoD). Memory: [[surgical-redline-craft-slice]].

## Context

ADR-F031 shipped the redline **mechanism**: the model proposes narrow `ModifyText` edits, a deterministic
**integrity gate** (D1–D6) validates them (unique anchor, supplied replacement, in-scope, mandatory
dry-run), **Adeu renders** native tracked changes, the document is matter-scoped, and the **human owns the
accept**. The integrity gate proves a redline is *well-formed*. It cannot prove it is *good craft*.

C4's live DeepSeek runs showed redline **craft** is run-to-run **variable**: sometimes the agent makes
structure-preserving, sub-sentence, multi-narrow-edit changes (the merged §8 keeps `shall indemnify,
defend and hold harmless` bare and *inserts* the Vendor indemnity); sometimes it strikes a whole clause and
retypes it (the rip-and-replace the maintainer flagged). The architecture's own rule (Tools & skills,
Plane 2/3) is that **substance/craft is human-owned plus *optional* substantive review — never claimed by a
structural gate**. So the open question is: how do we make surgical craft *reliable*?

Two facts bound the answer. **Adeu already renders each edit surgically** (prefix/suffix trim) — surgical
*rendering* is settled and not ours to rebuild. And the run-to-run variation is in **how the model proposes
the edits** — a prompt-quality problem, not an integrity problem.

## Considered Options

1. **Deterministic single-region gate (D7).** Add a code rule rejecting a `ModifyText` whose minimal diff
   spans >1 change separated by unchanged text (§6.1 option 2, deferred at C4), forcing decomposition.
   *Rejected:* re-derives in code what Adeu already renders; needs threshold calibration; produces false
   positives (it would reject the §9 edit from the "STRONG" run); papers over a weak prompt.
2. **Mandatory per-run LLM critic (guaranteed inspection flow).** Every redline is inspected by a (stronger)
   model before persist; a non-surgical verdict loops back. *Rejected:* reliable but **too slow** — an extra
   inference round-trip taxes every production redline; and an LLM verdict gating a write diverges from the
   ADR-F018 deterministic-integrity doctrine.
3. **Prompt forces the shape + a self-review tool + an eval that measures the craft rate (chosen).** A
   curated `surgical-redline` skill (+ tightened `profile_md`) with worked before/after examples is the
   primary lever; the agent can call a read-only `preview_redline` to see its rendered tracked changes and
   self-correct before committing; and an eval harness runs many vendor scenarios × repetitions, scores the
   produced `.docx` for craft with the redline-quality judge, and reports the **surgical-craft rate**, which
   tunes the prompt until redlines are reliably surgical.

## Decision Outcome

**Chosen: option 3.** Redline **craft is a prompt-quality property, tuned and proven by evaluation** — not
enforced by a runtime gate. C8 ships: (a) the `surgical-redline` curated abstract-method skill + a tightened
Commercial doctrine line (the shape-forcing prompt); (b) `preview_redline` — a read-only self-review tool
that reuses the C4 dry-run + reconstruction and **persists nothing** (the agent's own next reasoning step
inspects — no extra model call); (c) an eval harness + expandable scenario corpus that measures the
surgical-craft **rate and variance** and drives prompt tuning.

**Unchanged:** C4's deterministic integrity gate (D1–D6) and `apply_redline` write path; Adeu rendering;
matter-scope (ADR-F035); the human owns the accept. The skill is a **curated abstract-method skill** (bound +
named in the doctrine) — the code-gated *controlling*-skill machinery (instrument classifier, non-shadowable
namespace, apply-receipt) remains C6/F038. Craft scoring is an **eval-time** substantive review (the
architecture's sanctioned optional review), not a runtime gate.

## Consequences

- **Good:** no per-run latency tax; integrity stays deterministic (no LLM in the write-gate; ADR-F018
  intact); craft reliability is *measured*, not asserted (the maintainer's "judge the produced `.docx`"
  steer); the eval corpus + judge are reusable for every future prompt/model change; `preview_redline` lets
  the model see and fix its tracked changes without persisting junk Files.
- **Cost:** craft quality is model-dependent — it is *raised and stabilised* by prompt tuning against the
  qualified model and backstopped by human-owns-accept, not proven correct for all models; the eval is
  provider-marked (live gateway), so it is a calibration/evidence tool, not a CI gate; the curated skill body
  is unreviewed natural language that steers judgment → it gets an adversarial-review pass like code
  (ADR-F005 / skill-governance).
- **Follow-ups:** if eval shows the prompt alone cannot reach the target rate for a given model, an
  *optional* substantive-review step (option 2, framed as review-not-gate) can be added later without
  reopening this decision; the full controlling-skill enforcement is C6/F038.
