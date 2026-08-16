# ADR-F085 — Adeu-native two-pass redline rendering (annotate-then-apply)

- Status: proposed
- Date: 2026-08-16
- Deciders: Arturs (maintainer)
- Supersedes: ADR-F045 (word-diff shim). Relates: ADR-F031 (Adeu SDK-only + D1–D6 gate), ADR-F041
  (craft = prompt lever + eval), ADR-F081 (living redline — the case that forced this), ADR-F047
  (Collabora review UI — where fragment-level accept/reject actually happens), ADR-F005 (gate).
  Evidence: `docs/fork/evidence/adeu2-probe/` (live 2.4.0 probe) + four independent source reviews
  of the 1.12.1→2.4.0 wheel diff; plan `docs/fork/plans/ADEU-2-BUMP-plan.md`.

## Context

ADR-F045 made the TOOL responsible for surgical rendering: our `word_diff_edits` diffed the full
document text against itself-with-one-edit-applied via `adeu.diff.generate_edits_from_text`, pinned
each sub-edit's private `_match_start_index`/`_resolved_start_idx` offsets, and rode the rationale
comment on the first fragment only. That was correct on `adeu==1.12.1`, whose native apply rendered
every edit as one atomic block.

Adeu ≥1.19 ("More surgical redlines", prompted by our own feedback) absorbed word-level surgical
application into the engine — but gated it: an UNCOMMENTED `ModifyText` fans out into minimal
regions; a COMMENTED one is deliberately kept atomic (upstream QA 2026-07-22: rejecting one fragment
of a commented change silently destroys the comment). Every LQ.AI edit carries a rationale comment
(D2 mandates it), so naive native application would regress every clause to a wholesale block.

Meanwhile the shim broke on 2.x in a worse way (upstream AP-05): caller-pinned offsets are now
interpreted as CLEAN-view positions while we computed them from the raw view — on any document that
already carries tracked changes (every living-redline round 2, ADR-F081) the probe showed an edit
silently landing in a WRONG CLAUSE with `applied=1, skipped=0`. The shim also reproduced exactly the
orphaned-comment hazard upstream refuses to emit, and 2.4.0's default raw view embeds comment bodies
in the text the shim diffed against.

Probe facts (2.4.0, real MSA): commented native apply = 1 atomic block (not surgical); uncommented =
4 minimal regions (surgical); comment-only edits (`target_text == new_text` + comment) are
first-class — comment anchors over the range, zero tracked changes; a round-2 commented insert near
round-1 regions silently DROPS its comment, but the same annotation via a comment-only second pass
attaches.

## Considered Options

1. **Naive native** — pass `ModifyText(target, new, comment)` straight through. Simplest; not
   surgical for commented edits (all of ours) — regresses to pre-F045 blocks.
2. **Keep the shim, patch AP-05** — set `_active_mapper_ref = engine.mapper` (verified honored
   end-to-end). Works, but keeps ~60 lines coupled to unversioned private attributes that broke
   once across 391 commits, keeps the orphaned-comment hazard, keeps per-fragment (not per-edit)
   counts, and keeps diffing a raw view that now contains comment bodies.
3. **Two-pass native recipe (chosen)** — pass 1: one `apply_edits` batch of UNCOMMENTED edits
   (native surgical fan-out; batch index space 1:1 with the model's edit list); pass 2: one batch of
   comment-only edits (`ModifyText(new_text, new_text, comment=rationale)`) anchoring ONE comment
   across each whole logical edit. Public API only; probe-proven surgical + commented on pristine
   docs AND on living-redline rounds.
4. **`process_batch` migration** — transactional all-or-nothing with failed indices. Viable only
   after the recipe (it re-validates logical-edit uniqueness, which D4 already guarantees); a
   bigger rewrite. Deferred to its own slice, not rejected.

## Decision Outcome

Option 3, plus the supporting contract changes the reviews showed to be load-bearing:

- **One fresh engine per pass, serialising between them.** An Adeu engine caches its document
  mappers and only `process_batch` refreshes them between sequential `apply_edits` calls; a second
  call on the same engine resolves against pre-mutation offsets and silently mis-places edits
  (verified live: empty deletions + insertions landing before untouched text). Within one call the
  engine pre-resolves every edit against the initial state by design, so each pass is one call on a
  virgin engine, serialising between — one extra serialize+parse buys structural immunity to the
  whole staleness class.
- **Annotate FIRST, then apply.** Pass A anchors each rationale as a comment-only edit on
  `target_text` — the D4-unique anchor, so comment ambiguity is impossible by construction; the
  range then encloses the tracked regions pass B writes inside it (accept-all leaves the comment on
  the new wording; rejecting the edit leaves the rationale on the restored text). The apply-first
  alternative (comment-only on `new_text` after the apply) was implemented and rejected: a short or
  repeated `new_text` is ambiguous in the updated document, so the comment skips with a rejection
  the model cannot fix by rephrasing — and over nested round-2 regions it also failed to resolve.
  NOTE: an annotate-first attempt on a SHARED engine failed spectacularly (empty deletions,
  mis-placed insertions) — that was the mapper-staleness bug above, not the ordering; the two must
  not be conflated again.

- `render_edits(engine, edits, validate=...)` is the single shared renderer (C4 redline service and
  C5a negotiation counters). `validate=True` (redline path) runs Adeu's public, read-only
  `validate_edits` per edit first — all-or-nothing batch rejection with per-edit actionable
  messages, closing 2.x `apply_edits`' silent-first-match on ambiguity. Negotiation counters pass
  `validate=False` (countering deliberately edits the counterparty's pending insertions, which
  validate flags as foreign-author overlap); that path keeps its tool-layer D4/D5 gate on
  `clean_text_full` plus reconciliation.
- `BatchValidationError` is caught at every Adeu call and folded into per-edit `problems`;
  2.x `apply_edits` never rolls back, so `RedlineService.apply` serialises bytes ONLY from a fully
  clean render and raises `RedlineRenderError` otherwise — a half-applied engine is discarded,
  never persisted. Problems (which may quote clause text) go to the TOOL RESULT for the model;
  logs keep counts/events only.
- The D4 uniqueness gate's document text moves from `normalized_content`/DocxReader (python-docx
  `paragraph.text` — structurally blind to `w:ins`/`w:del`, so round-2 targets inside round-1
  insertions counted 0 and were falsely rejected) to Adeu's CLEAN view
  (`extract_text_from_stream(clean_view=True, include_appendix=False)`) — the same space the engine
  resolves in and the agent reasons about. DocxReader remains a last-resort fallback.
- Negotiation adapter: `apply_review_actions` 3-tuple (`already_resolved` carried into
  `Reconciliation` + audit), the 2.x `" (pairs with Chg:N)"` author-suffix stripped from meta-line
  parsing, fresh-engine + discard-on-failure discipline kept (documented against upstream's
  `rollback_verified` bug class).
- Pin `adeu==2.4.0` (3 sites, `--no-deps`); hand-pin `regex>=2024.11.6` (SDK path); `jinja2`
  deliberately NOT added (mcp_components only). `ensure_track_changes_recording` stays (2.4.0 still
  never sets `w:trackChanges`).

Acceptance gate: probe-derived unit tests (region counts, comment spans, round-2 resolution and
refusals) + the C9 Claude-judged surgical eval at or above the 1.12.1 baseline + a live run. If the
eval rejects the recipe, fall back to option 2 and record why here.

**Gate result (2026-08-16, full disclosure — evidence `docs/fork/evidence/adeu2-recipe/`).** Four
live samples. Final annotate-first build: **STRONG / SURGICAL: yes** (`final1/` — baseline parity;
the 1.12.1 baseline was itself a single sample). Interim apply-first build: two completed runs
judged STRONG / SURGICAL: no — but reconstruction-level inspection of both flagged clauses (§5 IP,
§6 Customer Data) shows unchanged wording BARE and narrow regions where the edit was narrow; the
"no" verdicts key on the MODEL choosing to rewrite clause tails wholesale (rendered faithfully as
one block per the Consequences stance below) — a craft/prompt lever (ADR-F041), not a renderer
property, and single-sample judge variance the pre-bump baseline never measured. One interim run
hit the step cap in a preview loop (~30 `preview_redline` calls, no apply) — deepseek's known
thrash mode, though the apply-first build's model-unfixable comment-ambiguity rejection is a
plausible contributor and is eliminated by the shipped annotate-first ordering; the scenario
harness records no tool-result text on `cap_exceeded`, so the loop's cause is not fully
attributable (backlog: persist rejection texts in evidence).

## Consequences

- All coupling to Adeu private attributes is gone; upstream's ongoing QA hardening accrues to us.
- Comments now span whole logical edits: rejecting one word-region in Collabora leaves the rationale
  intact (fixes our pre-existing orphaned-comment hazard, independent of the bump).
- Counts are per LOGICAL edit (native aggregation), so failure attribution maps 1:1 to the model's
  edit list — most of VM2-A's error-clarity ask lands here.
- Ambiguous anchors are now rejected with competing-context messages instead of silently editing
  the first occurrence (behavior change; D4 forbade them anyway).
- A genuine full rewrite still renders as one block (upstream's <0.35 similarity collapse) — the
  craft gate/judge, not the renderer, polices over-rewording (unchanged from F045's stance).
- Pass 2 targets the edit's `new_text` in the clean view; a non-unique or typography-normalised
  `new_text` skips the comment and rejects the batch with a message — the eval watches whether this
  bites in practice.
- `review_applied` in negotiation audits roughly halves for modify-pairs (second id counts
  `already_resolved`) — a semantics note for historical comparisons, nothing gates on it.
- `process_batch` consolidation and a "reject entire counterparty round" tool
  (`reject_all_revisions`, new in 2.x) are unlocked as future slices.
