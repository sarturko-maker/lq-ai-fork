# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `adeu-2-bump` (PR pending — task #524). Base main `28499017`.
- Dev stack: all containers healthy on **adeu 2.4.0** (api + arq-worker + ingest-worker rebuilt +
  recreated; prod image is the stack tag; dangling layers pruned).
- The `web/src/lib/lq-ai/sse/*` changes on this branch are the **SSE stall-watchdog fix** from the
  demo incident (byte-level 45s watchdog → clean-EOF → reconcile+re-poll). Live in the rebuilt web
  container but **uncommitted** — split into its own PR (do not entangle with ADEU-2).

## Done (ADEU-2 — bump adeu 1.12.1 → 2.4.0, native two-pass surgical recipe)

- **ADR-F085** (supersedes F045): deleted the pinned word-diff shim entirely; `render_edits` =
  **annotate-first two-pass, one fresh engine per pass** (pass A comment-only on the D4-unique
  `target_text`; pass B uncommented apply on a fresh engine → native surgical fan-out inside the
  comment ranges). Bytes meaningful only when `outcome.clean`; `apply()` raises
  `RedlineRenderError` otherwise (Adeu 2.x `apply_edits` never rolls back). `validate_edits`
  per-edit pre-pass feeds actionable problems to the MODEL (tool result only; logs = counts).
- D4 gate text = Adeu clean view (`_redline_gate_text`) — fixes the pre-existing round-2 bug where
  DocxReader (blind to `w:ins`/`w:del`) counted 0 spans for targets inside round-1 insertions.
- Negotiation: `apply_review_actions` 3-tuple (+`review_already_resolved` in Reconciliation +
  audit), `_PAIRS_SUFFIX` strip (2.x `"(pairs with Chg:N)"` author corruption — the 1.19.x parser
  breaker), counters through `render_edits(validate=False)`, fresh-engine discipline documented.
- Pins ×3 → 2.4.0; hand-pin `regex>=2024.11.6` (NO jinja2 — mcp_components only). Import-guard
  unchanged.
- **Verification**: adapter fast-rig 26/26 on 2.4.0 (incl. living-redline round-2, region-level
  OOXML assertions); full api suite **3772 passed** (51 = 36 wizard container-layout + 15
  flaky-under-load, all proven green on targeted reruns); ruff CI-exact All-checks-passed (0.16.3);
  mypy clean (244 files); **C9 eval on the final build: STRONG / SURGICAL: yes** (matches the
  1.12.1 baseline; evidence `docs/fork/evidence/adeu2-recipe/final1/`). Interim samples (apply-first
  build): 2× STRONG with renderer verified surgical at reconstruction level (judge dinged model
  SCOPE — ADR-F041 craft territory), 1× deepseek thrash to step-cap. Probe evidence:
  `docs/fork/evidence/adeu2-probe/`.
- **Two hard-won substrate facts (in ADR-F085, do not relearn):** (1) an Adeu engine's mappers go
  STALE across sequential `apply_edits` calls (only `process_batch` refreshes) — a second call on
  the same engine silently mis-places edits; always fresh engine per call. (2) commented edits
  render ATOMIC natively; comment-only edits (`target == new_text`) are the public range-anchored
  annotation idiom; anchor comments on `target_text` (unique by D4), never on `new_text`
  (ambiguous in the updated doc).

## Next slice

1. Land the ADEU-2 PR (adversarial review findings → fix/defer, then merge under F005).
2. **SSE stall-watchdog PR** (small, web-only, tests already green 1376/1376 at fix time).
3. Then the roadmap: VM2-A (#525 — mostly absorbed by this slice's error clarity; re-scope it),
   PYMUPDF-SWAP (#530) research is drafted, or CUSTODIAN per the 2026-07-12 roadmap.

## Pick up exactly here

If the ADEU-2 PR is not yet merged: `git status` on `adeu-2-bump`, read the adversarial-review
findings in the PR/conversation, fix blockers, quote suite counts (above) in the PR body, merge
squash via `gh pr merge --repo sarturko-maker/lq-ai-fork`. If merged: split the SSE watchdog into
its own branch from the web/ changes and run the web gate (`CI=true npx vitest run`, svelte-check).

## Gotchas

- Backlogged from ADEU-2 (MILESTONES § Backlog candidates): `process_batch` consolidation (viable
  post-recipe), `reject_all_revisions` round-reject tool, upstream reports to Mikko (maintainer
  will contact — round-2 commented-insert comment drop; BatchValidationError index mis-attribution
  to 0), scenario-harness improvement: persist preview/tool rejection texts into evidence on
  `cap_exceeded` (run-2 forensics were blind).
- v2 fragments uncommented edits word-level → `read_state_of_play` enumerates MORE region-refs per
  logical counterparty edit (5 for the 3-edit fixture). Region-level enumeration is the contract;
  the coverage gate forces a decision per fragment.
- Containerized full-suite recipe: build `api/Dockerfile.dev` (context `api/`), tag `lq-ai-api`,
  `docker compose run --rm -v $PWD/api:/app api pytest -q` — wizard tests additionally need the
  whole repo (`-v $PWD:/repo -w /repo/api`) or they 127 on `/scripts` + `deploy/` templates.
  Rebuild the PROD api tag afterwards (the stack must not run the dev image).
- Host ruff: `pip install --user --break-system-packages ruff==0.16.3`, run with `--no-cache`
  (`.ruff_cache` is root-owned from container runs).
