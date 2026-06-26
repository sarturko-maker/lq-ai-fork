# Authorship Slice 2 — evidence (ADR-F048 addendum)

Roster-aware negotiation + richer authorship signals. Branch `fork/authorship-roster-slice2`.
Four items: C5a negotiation classification · `get_document_metadata` tool · `'other'` third-party side
(migration `0077`) · lazy operator auto-seed. No new HTTP route, no new dependency.

## Backend (dev image `lq-ai-api-dev`, throwaway test DBs)
- **Migration `0077` round-trip** (upgrade → downgrade → upgrade) on a throwaway pgvector container: the
  `matter_participants.side` CHECK goes `{ours, counterparty, unknown}` → `+ other` on upgrade, reverts on
  downgrade (deleting any `'other'` rows first), restores on re-upgrade. Verified via `pg_get_constraintdef`.
- **Full api suite: 2818 passed / 35 skipped / 0 failed** (+15 over Slice 1's 2803). **mypy clean (202
  files); ruff (CI-exact, repo-root config) clean.**
- New/extended tests:
  - `test_matter_roster.py`: `classify_author → 'other'`; `record_matter_participant(side='other')`;
    `ensure_operator_participant` seeds confirmed-`ours`, idempotent, name/email fallback, **does not
    resurrect a lawyer-retired operator** (the review should-fix).
  - `test_agent_tools.py`: `get_document_metadata` over email (`structured_content` headers) + docx
    (core-properties author), 404-conflation, matter-scope; the model-facing schema (3 tools); the
    guard receipt for all three tools.
  - `test_commercial_tools.py`: `_render_state_of_play` groups by side (ours / third party / counterparty)
    while keeping **every ref in the coverage list** (coverage parity); empty roster → all counterparty.
  - `test_review_edited_document.py`: the THIRD-PARTY bucket renders distinctly (not "ask").
  - `test_agent_composition.py`: a matter-bound run **seeds the operator** as confirmed-`ours` + injects it
    into the roster prompt block; idempotent across runs; the Slice-1 grant test updated for the seed.
  - `test_matter_roster_api.py`: the human surface accepts `side='other'`.

## Web
- `npm run check` **0 errors**; vitest **987 passed** (MemoryPanel helpers incl. `'other'` → "Third party"
  label + violet tone + submittable); prettier clean.

## Live (rebuilt dev stack — api+arq+web at mig `0077`, healthy)
- **Headed Cypress `authorship-roster.cy.ts` — 3/3 passed** (the add/edit/remove gestures, the new
  **third-party (other) side renders + the add-form offers it**, and the light/dark capture). Screenshots
  `f048-roster-{light,dark}.png` (the **Third party** violet badge on "Iron Mountain" beside the
  Counterparty amber badge on "Mark Counsel") + `f048-roster-form-{light,dark}.png`. (First run was flaky —
  the api was mid-rebuild concurrently; clean re-run on the stable stack was 3/3.)
- **Live DeepSeek scenario `test_matter_roster_slice2_scenario.py` — passed** (`live-matter-roster-slice2.json`):
  from a plain user statement, the real agent recorded **Northwind Trading Ltd → ours** and **Iron Mountain
  → other (Escrow agent)** via two `record_matter_participant` calls — and the **operator was auto-seeded**
  as a confirmed `'ours'` row (`UX-B Scenario User`, email alias) WITHOUT the agent recording it
  (`operator_seeded: true`, `third_party_recorded: true`). Proves the new side + the composition seed wiring
  end-to-end on the live gateway.

## Adversarial review (4-dimension × independent verify, 14 agents)
- **0 blockers; 1 should-fix (fixed); 8 nits (key ones folded).**
- **Should-fix (fixed):** `ensure_operator_participant` probed idempotency only against *active* rows, so a
  lawyer who soft-retired the auto-seeded operator would have it resurrected next run — a contract gap vs
  ADR-F042 B2 ("the human owns the tier"). **Fix:** the probe now matches **active OR retired** operator
  rows and respects a human removal; + a regression test (`…does_not_resurrect_a_retired_operator`).
- **Nits folded:** single-pass classification in `_render_state_of_play` (`_group_by_side` — was 3×
  redundant `classify_author` per item); stale docstrings (`build_matter_tools` "two tools" → the three-tool
  set; `classify_author` + `_classify_edits` now list `'other'`); a mirror-note on `_change_entry`. Remaining
  nits were cosmetic and left as-is.
