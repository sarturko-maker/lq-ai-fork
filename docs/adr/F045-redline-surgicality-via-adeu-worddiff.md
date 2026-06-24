# ADR-F045 — Surgical redlines are produced by the tool (Adeu native word-diff), not the model

- Status: proposed
- Date: 2026-06-24
- Deciders: Arturs (maintainer)
- Relates: extends ADR-F041 (surgical-redline craft = prompt lever + eval — and **corrects a factual
  premise of it**, see Context), ADR-F031 (Adeu redline tool + the D1–D6 integrity gate), ADR-F018
  (code-validated writes — deterministic, never LLM verdicts), ADR-F035 (matter-scoped records), ADR-F005
  (agent-merged DoD). Memory: [[redline-worddiff-next-slice]], [[claude-judged-redline-tests-slice]],
  [[surgical-redline-craft-slice]].

## Context

ADR-F041 made redline **craft** a prompt-quality property: a `surgical-redline` skill coaches the model to
**decompose** a one-sided clause into several narrow edits and keep boilerplate bare, proven by an eval. It
rested on the stated premise that *"Adeu already renders each edit surgically (prefix/suffix trim) — surgical
rendering is settled and not ours to rebuild."*

The C8/C9 redline-eval **re-run** (with the skill correctly loaded — it had been silently dropped by a
frontmatter bug through the original C8/C9) confirmed the residual weakness is real: on dense clauses
(indemnity, grant/data-licence, NDA §9) the model still strikes-and-retypes wholesale, and "seam" defects
(duplicated inserted text) appear. Root-causing it in the dev image against `adeu==1.12.1` falsified the F041
premise:

1. Our adapter sent **one raw `ModifyText(target_text, new_text)` per logical edit** and called
   `engine.process_batch`. Adeu's resolver for such an edit trims only the **common prefix/suffix** — it does
   **not** keep an unchanged **interior** bare. A whole-clause mutualisation therefore renders as one
   struck-and-retyped block that **swallows** the unchanged interior (e.g. "shall indemnify, defend and hold
   harmless"). That is precisely the eval's failure — and it is a *rendering* limit of the path we used, not
   only a model-craft limit.
2. Adeu 1.12.1 **ships a native word-level diff we were not using**: `adeu.diff.generate_edits_from_text`.
   Proven: a realistic indemnity clause decomposes into minimal sub-edits with the verb phrase left bare and
   no corruption.
3. The C-R0 reason we *disabled* `generate_edits_from_text` ("micro-anchor fuzzy-match corruption", e.g.
   `Vendor` → `Ven12or`) **does not reproduce** on the pin: the native diff anchors **positionally**
   (`_match_start_index` in full-document coordinates), not by fuzzy micro-match.

So surgical rendering was **not** settled, and the user's design steer ("the model does not need to know
Adeu, but it must return amendments such that Adeu applies them surgically") is achievable by the tool.

## Considered Options

1. **Keep F041 as-is — coach the model harder to decompose.** *Rejected:* the re-run shows the model
   (flash *and* a stronger pro tier) does not reliably decompose dense clauses; it offloads mechanical
   surgery onto the model when a deterministic renderer can do it; and decomposed micro-anchors collide with
   the gate's D4 unique-anchor rule.
2. **Port the reference repo's custom word-diff layer** (`Claude-Plugin-MCP/src/pipeline/word_diff.py`).
   *Rejected:* that layer existed only because it ran against Adeu **0.7.0 alpha**, which lacked the feature;
   Adeu 1.12.1's native `generate_edits_from_text` suffices, and porting adds an unjustified SBOM/maintenance
   surface.
3. **Re-enable Adeu's native word-diff inside the tool (chosen).** For each logical edit, diff the **full
   document text** against the document with that one edit applied (`full.replace(target, new)`), via
   `generate_edits_from_text`, and apply the positioned sub-edits with `engine.apply_edits(...)` **directly**.
   Simplify the skill to "return the clause with only the necessary words changed; keep the rest verbatim — the
   tool diffs it."

## Decision Outcome

**Chosen: option 3 — the TOOL makes the redline surgical; the model's job is to preserve unchanged wording.**

- **Renderer (`app.agents.redline_service`).** Each `(target_text, new_text)` is expanded by
  `adeu.diff.generate_edits_from_text(full, full.replace(target_text, new_text))` into minimal `ModifyText`
  sub-edits carrying full-document `_match_start_index` offsets; the rationale rides as the Word comment on
  the first sub-edit. Sub-edits are applied with **`apply_edits`, not `process_batch`** — `process_batch`
  re-validates each sub-edit's `target_text` for uniqueness and would reject a short region ("the Customer"
  recurs); `apply_edits` trusts the positional index. This is the canonical pattern in `adeu.sanitize.core`.
- **Fallback.** When `target_text` is **not** uniquely locatable in the engine's text (a rare
  whitespace-normalisation mismatch — D4 already requires uniqueness in the document text), that edit falls
  back to a single wholesale `ModifyText` resolved heuristically — no worse than the prior behaviour. Counted
  and logged (counts only, no clause text).
- **Skill (`skills/surgical-redline`, v2).** Drops the anchor-mechanics/decompose/"split the block"/"fold
  into the boundary" coaching; teaches: quote the unique clause as `target_text`; in `new_text` change only
  the necessary words and copy all other wording verbatim; preview; keep the legal *what-to-change* doctrine
  (mutualise, carve-outs, deem-direct, cap mechanics).

**Unchanged.** The D1–D5 surgical gate keys on the **minimal token diff** of `(target, new)`, which is
renderer-agnostic, so it still correctly guards **genuine over-rewording** (a true rewrite where every word
differs renders — correctly — as one block and is flagged by D1) without penalising a coarse anchor that
diffs cleanly. **No gate-threshold change this slice**: the thresholds already operate on the minimal diff,
and `n=1` live evidence cannot verify a calibration change ("if you can't verify it, don't ship it"). Adeu
remains SDK-only/zero-egress (ADR-F031), the document stays matter-scoped (ADR-F035), and the **human owns
the accept**.

## Consequences

- **Good:** the C8/C9 swallow is fixed deterministically — surgical rendering no longer depends on the model
  decomposing; recognisable boilerplate stays bare; "seam"/duplicate-text defects from overlapping coarse
  anchors disappear (one clean diff per clause); the model's prompt simplifies to a single preserve-the-wording
  rule; we use Adeu's **own** facility (no custom diff layer to own).
- **Cost / risk:** applying via `apply_edits` **bypasses Adeu's `validate_edits` uniqueness re-check** — we
  rely instead on the gate's D4 (unique anchor in the document text) **plus** the renderer's `full.count==1`
  guard and the wholesale fallback; a genuine full rewrite still renders as a block (correct — the gate, not
  the renderer, guards it); word-diff fixes *rendering* only when the model preserves unchanged wording, so
  the skill must (and now does) teach that, and the gate still catches the model that genuinely re-words.
- **Follow-ups:** re-tune D1–D5 thresholds **with** a multi-rep × strong-judge eval if the live re-test shows
  systematic friction (e.g. the clause-straddle rejection when a model quotes a two-sentence span);
  craft-quality remains model-dependent and backstopped by human-owns-accept (the F041 stance is otherwise
  intact). This decision **supersedes the F041 premise** that surgical rendering was settled in Adeu's
  prefix/suffix path; it does **not** reopen F041's "craft is tuned by eval, not a runtime gate" stance.
