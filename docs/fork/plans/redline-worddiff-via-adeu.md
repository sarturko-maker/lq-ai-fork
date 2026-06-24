# Plan — Surgical redline via Adeu's NATIVE word-diff (F041 craft track follow-up)

**Status: ✅ SHIPPED 2026-06-24** (branch `fork/redline-worddiff-adeu`, **ADR-F045**; memory
[[redline-worddiff-shipped]]). Outcome below matched the scope, with one design correction found during
implementation (see note). Governing: ADR-F045 (new) extends ADR-F041 (craft = prompt-quality lever) + ADR-F031
(the redline gate).

> **Implementation correction (recorded for the record).** The scope said "re-enable `generate_edits_from_text`
> in `_build_modifytexts` … route each `(target,new)` through it before `process_batch`." Reading Adeu's engine
> showed that is wrong: `process_batch` runs `validate_edits`, which rejects the resulting short sub-edits on
> uniqueness (`BatchValidationError: Ambiguous match`), and `generate_edits_from_text`'s `_match_start_index` is
> relative to its `original_text` arg. The correct, canonical pattern (from `adeu.sanitize.core`) is to diff the
> **full document text** vs the doc with the edit applied, and apply the sub-edits via **`engine.apply_edits`
> directly** (which trusts the positional index and skips uniqueness re-validation). The gate was left UNCHANGED
> (it already keys on the minimal token diff, renderer-agnostic). See ADR-F045 + `redline_service._word_diff_edits`.

## Why (the finding this is built on — proven empirically 2026-06-24)

The C8/C9 re-run showed the model still rip-and-replaces dense clauses (indemnity boilerplate swallowed, grant
clauses, NDA §9) and emits "seam" defects (`the Personal Data the Personal Data`). Root cause, then proven in
the dev image against `adeu==1.12.1`:

1. **Our tool uses Adeu's WHOLESALE path.** `redline_service._build_modifytexts` builds ONE raw
   `ModifyText(target_text, new_text)` per model edit and calls `engine.process_batch`. Adeu then trims only the
   common **prefix/suffix** of target vs new — it does **NOT keep an unchanged INTERIOR bare**. Proven: a single
   edit "Upon any breach the Recipient shall indemnify the Discloser for all losses." → "…each party shall
   indemnify the other party…" renders as **ONE block** (`[-the Recipient shall indemnify the Discloser-][+each
   party shall indemnify the other party+]`), swallowing the unchanged "shall indemnify". That is exactly the
   eval's indemnity failure.
2. **Adeu 1.12.1 SHIPS a native word-level diff we are NOT using:** `adeu.diff.generate_edits_from_text(original,
   modified) -> list[ModifyText]`. Proven clean: a realistic indemnity clause decomposed into **3 minimal
   sub-edits** — `[-The Customer-][+Each party+] shall indemnify, defend and hold harmless the [-Vendor-][+other
   party+] and its affiliates against any and all claims arising from [-the Customer use of the Services-][+a
   party breach…+].` → verb phrase **BARE**, 3 regions, **no corruption**.
3. **We deliberately disabled it.** `redline_service.py` (~lines 11-21) notes `generate_edits_from_text` was
   rejected for "micro-anchor fuzzy-match corruption (`Vendor`→`Ven12or`)". That **did not reproduce on 1.12.1**
   — likely stale (older Adeu) or edge-case-specific (Adeu warns its diff engine can mid-word-split anchors
   containing `-`/`_`).

**So the fix is NOT to port the reference repo's custom word-diff** (github.com/sarturko-maker/Claude-Plugin-MCP,
`src/pipeline/{surgical_edit,word_diff}.py` — built against Adeu 0.7.0 alpha when this was missing). It is to
**re-enable Adeu's own `generate_edits_from_text`** in our tool, with a guarded fallback + a corpus corruption
re-check.

### Key nuance (must be in the skill)

Word-diff fixes **rendering** only when the model **preserves the unchanged wording** in `new_text`. If the
model genuinely *re-words* a clause (fresh paraphrase, every word different), `generate_edits_from_text` yields a
large diff → still a block (legitimately). So the simplified skill must teach **"return the clause with only the
necessary words changed; keep all other wording identical — the tool diffs it"**, NOT "anchor narrowly /
decompose / fold into the boundary" (the diff now handles anchoring).

## Implementation

1. **`api/app/agents/redline_service.py` — route through the native word-diff.**
   - In `_build_modifytexts` (feeds both `dry_run` and `apply`): for each `ProposedEdit(target_text, new_text,
     comment)`, expand via `adeu.diff.generate_edits_from_text(target_text, new_text)` into minimal sub-edits;
     pass the resulting `ModifyText` list to `process_batch`. (One edit → N sub-edits.)
   - **Comment/rationale:** attach the edit's rationale-comment to ONE representative sub-edit (e.g. the first),
     so the Word comment still lands once per logical edit (don't duplicate it N times).
   - **Guarded fallback:** if the word-diff path errors, yields zero sub-edits, or any sub-edit reports skipped /
     a reconstruction mismatch (`process_batch` `skipped_details`), fall back to the current single wholesale
     `ModifyText(target,new)` for that edit. Log which path each edit took.
   - Bytes out via the existing `_engine_bytes(engine)`.
2. **The D1-D5 gate (`api/app/schemas/commercial.py` `evaluate_gate` + validators).** Surgicality is now the
   renderer's job, so the **strike-ratio / one-contiguous-change pressure is redundant** — but the gate still
   usefully catches a model that *genuinely over-rewords* (large true diff) or strikes a whole clause. Decision
   to make in the slice: **relax** the surgical-anchor gate (don't penalise a coarse anchor that diffs cleanly)
   while **keeping** a guard on genuine over-rewording (true changed-token ratio after word-diff). Re-tune, don't
   delete blindly. The `changed_regions()` helper (defined, currently uncalled) becomes moot.
3. **Skill `skills/surgical-redline/SKILL.md` — simplify.** Drop the anchor-mechanics coaching (decompose into
   narrow edits / fold into boundary / one contiguous change per anchor / "split a long `[-…-]` block"). Replace
   with: return the clause with only the necessary words changed, **preserve all other wording verbatim**, keep
   recognisable boilerplate identical, and still preview. Keep the legal *what-to-change* doctrine (carve-outs,
   mutualise, deem-direct, cap mechanics). Re-run `test_every_real_skill_loads_no_silent_drops` after editing
   (frontmatter `": "` trap).
4. **Tests.** Deterministic unit test in `api/tests/agents/test_redline_service.py`: the indemnity clause →
   expect 3 regions, "shall indemnify, defend and hold harmless" bare, no letter-digit-letter corruption; plus a
   genuine-rewrite case (verify it still renders + the gate still flags over-rewording); plus the `-`/`_`
   punctuation edge case (fallback engages, no corruption). Update any redline-service tests asserting the old
   one-ModifyText-per-edit behaviour.

## Verify / retest (this is the deliverable; Claude is the judge)

- **Deterministic:** the unit tests above + `test_every_real_skill_loads_no_silent_drops` green; full api
  regression `-m 'not provider and not e2e'` (dev image, gateway key unset).
- **Live re-test on DeepSeek flash** (the whole point): re-run the C9 manual harness
  (`api/tests/agents/scenarios/test_commercial_redline_manual.py`, 7 instruments) with the new word-diff path +
  simplified skill → fresh `docs/fork/evidence/c9/` v3 dir (archive v2 first, mirror the v1 archive pattern).
- **Claude-judge** the artifacts with the SAME sharp panel + refuter — reuse the workflow at
  `scratchpad/c9-judge.js` (parameterised `{model, dir, only}`). Compare v3 (word-diff) vs v2 (current): do the
  indemnity/grant/NDA clauses now render **interior-bare**? Did the **seam defects** (duplicated text) disappear?
  Did surgical-pass rise? Keep the n=1 caveat; lean on deterministic + direct-text signals.
- **Conditional pro** only if flash still fails a case.
- ADR drafted; HANDOFF + memory updated; merge per ADR-F005.

## Artifacts to reuse (in scratchpad this session — re-create if gone after compaction)

- Empirical proof script: `scratchpad/adeu_native_worddiff_test.py` (run via dev image, `PYTHONPATH=/app`,
  mount `-v "$PWD/api:/app" -v "$SCRATCH:/scratch"`; `pip install diff-match-patch structlog` + `--no-deps
  adeu==1.12.1`).
- Judge workflow: `scratchpad/c9-judge.js`.
- Reference repo (user's, for the match-once-DOM-surgery pattern IF Adeu's native path corrupts on edge cases):
  `github.com/sarturko-maker/Claude-Plugin-MCP` → `src/pipeline/surgical_edit.py` + `word_diff.py`.
- Adeu facts: `adeu.diff` exposes `generate_edits_from_text`, `generate_edits_via_paragraph_alignment`,
  `trim_common_context`, `diff_match_patch`. `process_batch(changes, dry_run)` → dict
  (`edits_applied/edits_skipped/skipped_details/engine/...`). No `engine.document`; use `_engine_bytes(engine)`.

## Non-goals

- Porting the reference's custom word-diff layer (Adeu's native one suffices; only revisit if edge cases corrupt).
- Changing the model/provider (model-vs-method already settled: pro is worse). MCP / redline-viewer (separate).
