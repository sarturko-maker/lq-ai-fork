# ADEU-2 — bump adeu 1.12.1 → 2.4.0 and converge on native surgical redlining

Status: DRAFT — maintainer edits before implementation. Task #524 (retargeted from 1.19.1).
Evidence: `docs/fork/evidence/adeu2-probe/` (live probe of 2.4.0 against the SecureScan MSA)
plus four independent source reviews of the 1.12.1→2.4.0 wheel diff (2026-08-15/16).

## Goal

One slice that (a) bumps the pin to 2.4.0, (b) **deletes our pinned word-diff shim** and
replaces it with Adeu-native application via a two-pass recipe (below), keeping redlines
surgical, and (c) fixes the negotiation-surface breaks — gated by the C9 surgical eval and a
new living-redline round-2 eval.

**Answer to "keep as much of Adeu as possible, yet surgical":** we keep MORE of Adeu than
today. All private-attribute coupling (`_match_start_index`, `_resolved_start_idx`,
`_active_mapper_ref`, `mapper._build_map`) is deleted; every call goes through public API
(`apply_edits`, `validate_edits`, `ModifyText`, comment-only edits). Surgical rendering comes
from Adeu's own word-diff fan-out, not our reimplementation of it.

## Why not the two obvious alternatives

- **Naive native** (pass `ModifyText(target, new, comment)` straight through): NOT surgical.
  v2 deliberately keeps commented edits atomic (`_single_commented_sub_edit` — one del+ins
  block, unchanged middle mutualised; upstream QA 2026-07-22 bug #1 rationale: rejecting one
  fragment of a commented change silently destroys the comment). Every real LQ.AI edit
  carries a rationale comment (D2 requires it), so this regresses to pre-F045 wholesale
  blocks. Probe scenario A.
- **Keep the shim, patch AP-05** (`sub._active_mapper_ref = engine.mapper`): works (probe C,
  escape hatch verified end-to-end by review), but keeps 60 lines of private-API coupling
  that broke once already, keeps the orphaned-comment hazard (our comment rides fragment 0
  only — exactly the defect upstream refuses to produce), keeps per-fragment instead of
  per-logical-edit counts, and keeps diffing a raw view that embeds CriticMarkup + comment
  bodies. Fallback position only if the eval fails the recipe.

## The design: two-pass native recipe (probe-proven: H1/H2/H4)

In `RedlineService` (shared by redline + negotiation counters), per batch of logical edits:

1. **Pass 1 — apply, uncommented:** one `engine.apply_edits([ModifyText(target_text=t_i,
   new_text=n_i)])` over all logical edits. Native resolution (raw view first, clean-view
   fallback; live-match filter excludes tracked-deleted text) + native word-diff fan-out →
   surgical regions (probe B). Batch index space == our logical-edit list (no flattening) →
   per-edit failure attribution is exact.
2. **Pass 2 — annotate, comment-only:** one `engine.apply_edits([ModifyText(target_text=n_i,
   new_text=n_i, comment=rationale_i)])` for every edit with a rationale. Comment-only edits
   are first-class in v2 (target == new → comment anchored over the range, zero tracked
   changes; probe H1). Result: ONE comment spanning the WHOLE logical edit (probe H2), which
   also survives round-2 anchoring where direct commented edits silently drop the comment
   (probe D vs H4), and removes our orphaned-comment hazard (reject one fragment in
   Collabora → comment survives, it anchors the range, not a change).
3. **dry_run (D6)** = per-edit `engine.validate_edits([edit], index_offset=i)` on a throwaway
   engine (public, confirmed non-mutating, per-edit actionable messages incl. strict-mode
   ambiguity with competing-match contexts) **then** the same two passes on the throwaway
   engine, requiring: all pass-1 applied, zero skipped, pass-2 comment count delta == number
   of rationales. Keep the throwaway full apply — validate alone misses the table-cell-count
   raise and multi-match structural checks, and `apply_edits` has NO internal rollback.
4. **Error contract:** catch `BatchValidationError` explicitly at every Adeu call (v2's
   apply path CAN raise it: table-cell mismatch, paragraph-boundary spans). Surface
   `.errors` / `skipped_details` text in the TOOL RESULT to the model (Adeu's own posture:
   per-edit reports feed LLM contexts, capped at 500 chars); logs keep events + counts only
   (existing boundary). On any raise, discard the engine — never serialize a half-applied
   engine (apply_edits does not roll back; our fresh-engine-per-call + persist-only-on-success
   pattern is the safety net and stays).
5. **Post-apply recheck:** verify `edits_skipped == 0` and comment delta after the REAL
   apply too, not just after dry-run (today `_render_redline` trusts the dry-run).

Unchanged and load-bearing: `ensure_track_changes_recording()` (v2 still never sets
`w:trackChanges` — probe G); fresh engine per call; audit counts-only contract; D1/D2/D5
gates; author on engine construction.

## D4 gate text fix (pre-existing bug, must ride this slice)

`commercial_tools.py:438` counts target uniqueness against `normalized_content` /
`DocxReader` (python-docx `paragraph.text`) — which **structurally omits all `<w:ins>` /
`<w:del>` content and all table text**. Redlined working heads are never re-ingested, so on
every living-redline round 2, an edit targeting round-1-inserted text counts 0 occurrences
and D4 rejects it ("matches 0 spans") — today, on 1.12.1. Fix: D4's `document_text` for
redline calls becomes `adeu.extract_text_from_stream(data, clean_view=True,
include_appendix=False)` — the document as it currently stands (accept-all view), the same
space pass-2 targets and the agent's mental model live in. `DocxReader` stays for the ingest
/search pipeline (not this lane). `validate_edits` strict-ambiguity is the engine-side
backstop, which also closes the gap that negotiation counters have NO uniqueness gate today
(v2 `apply_edits` silently takes the first match on ambiguity — the ambiguity error lives in
`validate_edits` only).

## Negotiation adaptations (from the review)

- `negotiation_service.py:338`: `apply_review_actions` now returns
  `(applied, skipped, already_resolved)` — 2-unpack raises `ValueError`. Unpack 3; carry
  `already_resolved` into `Reconciliation` + audit details (review_applied will roughly
  halve for modify-pairs — semantics note for anyone reading historic audits).
- `negotiation_service.py:77/213`: v2 appends `" (pairs with Chg:N[, Chg:K...])"` after the
  author on `[Chg:N insert/delete]` meta lines; `_CHG_LINE` swallows it into
  `TrackedChange.author`. Strip via
  `re.sub(r"\s*\(pairs(?:\s+with)?\s+[^)]*\)\s*$", "", author)` + drift-guard test with a
  pairs-suffix fixture. (Likely the actual 1.19.x parser breaker.)
- Keep: replies-first/descending-id pre-ordering (still required — v2's internal sort only
  guarantees replies-first); `extract_comments_data` consumption (byte-identical);
  fresh-engine + discard-on-failure discipline (add a comment citing v2's
  `rollback_verified` BUG 2026-08-12 as the reason it must never change).
- Counters render through the same two-pass recipe (shared `RedlineService` primitive).
- Free hardening to note in the PR: v2 `escape_critic_tokens()` defangs comment text that
  fakes `Chg:`/`Com:` markers — closes a prompt-injection-shaped parser confusion.

## Mechanical

- Pin bump in **3 sites**: `api/Dockerfile`, `api/Dockerfile.dev`,
  `.github/workflows/ci.yml` (`--no-deps adeu==2.4.0`).
- Hand-pinned SDK deps (`api/pyproject.toml` ~L200): **add `regex>=2024.11.6`**
  (safe_regex ← mapper/engine/markup). `jinja2` NOT added (mcp_components only — forbidden
  path). Installed pydantic 2.13.4 / rapidfuzz 3.14.5 / python 3.12 already satisfy floors.
  SBOM note: +1 dep (`regex`, Apache-2.0 — confirm license file at bump time).
- Delete: `word_diff_edits` + pinning, the wholesale-fallback branch, `_engine_bytes`'s dead
  fallback attr loop (keep the `save_to_stream`/BytesIO branch). Update module docstrings
  ("verified live on adeu==2.4.0"), rebuild api + arq-worker + ingest-worker,
  `docker image prune -f`.
- ADR: new F-series ADR "Adeu-native two-pass surgical application (apply-then-annotate)",
  superseding **F045**; seam comments at RedlineService + the D4 gate-text change (touches
  the F066/F081 living-redline contract). Import-guard (no `adeu.server` /
  `adeu.mcp_components`) unchanged and re-verified.

## Verification (gate, in order)

1. Unit: port probe assertions into pytest with a small fixture docx — pass-1 fan-out region
   counts (OOXML-level), pass-2 comment spans + count delta, comment-only no-op regions,
   round-2 resolution over inserted text, round-2 refusal on deleted text, D4-on-inserted
   text passes with the new gate text, `BatchValidationError` surfaced not swallowed,
   pairs-suffix author strip, 3-tuple unpack.
2. Import-guard + full api containerized suite (counts quoted in PR).
3. **C9 Claude-judged surgical eval** on 2.4.0 ≥ the 1.12.1 baseline (scenario run 2026-08-15:
   STRONG / SURGICAL=yes, 12 edits / 34 regions — itself a single sample). This is the
   accept/reject gate for the recipe; if it fails, fall back to shim+AP-05-patch (documented
   above) and record why.
   **RESULT (2026-08-16): PASSED on the final annotate-first build — STRONG / SURGICAL: yes**
   (`docs/fork/evidence/adeu2-recipe/final1/`). Full disclosure: 3 earlier samples on the
   interim apply-first build were 2× STRONG/SURGICAL-no (reconstructions show the renderer
   surgical; the judge dinged the MODEL's rewrite scope — ADR-F041 craft territory) and 1×
   `cap_exceeded` preview loop (cause not fully attributable — the harness records no
   tool-result text; backlogged). The live gate signal is noisier than the single-sample
   baseline suggested; ADR-F085 § Decision carries the run-by-run record.
4. **New living-redline round-2 eval case**: redline → counterparty round → second redline
   targeting both untouched AND round-1-inserted text; assert surgical + comments attached +
   no mis-anchor. (C9 never covered round 2 — that's where both old paths fail silently.)
5. Live demo-rig run on the dev stack (SecureScan pack), evidence in PR. Full ADR-F005 gate.

## Non-goals / backlog

- `process_batch` migration (transactional all-or-nothing + failed indices). Newly viable
  AFTER the recipe (its per-edit uniqueness re-validation matches D4 once we stop flattening
  sub-edits) — its own future slice.
- Exposing `match_mode`/`regex` to the model (D4 subsumes strict; keep dormant).
- `reject_all_revisions` tool ("reject entire counterparty round") — new in v2, unused.
- Upstream reports to Adeu (comment drop on round-2 commented inserts = probe D; Raise-A
  index mis-attribution to 0) — maintainer's call on outreach.
- VM2-A remainder (configurable comment author) — error-clarity half largely falls out of
  this slice's validate_edits/tool-result surfacing.

## Risks

- **Pass-2 target = n_i not unique / typography-normalized** → comment skipped or lands on
  first occurrence (v2 apply is silent-first on ambiguity). Mitigated by validate_edits in
  dry-run (strict ambiguity error) + comment-count recheck; on failure the tool reports
  per-edit so the model rephrases. Eval decides severity.
- **≥40-char full rewrites with <0.35 word-similarity** collapse to one block in pass 1
  (upstream diff guard). Acceptable: a genuine rewrite IS a block; judge tolerates it.
- **Multi-paragraph commented edits**: pass-2 comment-only across `\n\n` uses
  `_attach_comment_spanning` via the COMMENT_ONLY path — reviewed but not probed
  multi-paragraph. In the unit matrix; fallback = comment on first paragraph's span.
- Region counts rise for lawyers (4 small vs 1 big) — that IS the feature; Collabora renders
  tracked regions natively (F047).
