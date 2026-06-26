# Authorship Slice 1 — evidence (ADR-F048)

Matter who-is-who roster + hand-back author resolution. Branch `fork/authorship-roster-slice1`.

## Backend (dev image `lq-ai-api-dev`, throwaway test DBs)
- **Migration `0076` round-trip** (upgrade → downgrade → upgrade) on a throwaway pgvector
  container: `matter_participants` created with all CHECKs (side/trust/length) + FKs (CASCADE) +
  index, dropped on downgrade, restored on re-upgrade.
- **Full api suite: 2800 passed / 34 skipped / 0 failed** (pre-review-fix run). Re-run after the
  adversarial-review fixes — see the PR for the final count.
- New `test_matter_roster.py` (grant/disjoint; pure `classify_author` agent/ours/counterparty/unknown;
  `record_matter_participant` insert + own-inference update + **human-confirmed-never-overridden**;
  reject invalid side; matter-gone; `clean_alias_list` clamp-vs-reject; **merge-over-cap clamps not
  crashes**; `format_roster_block`). New `test_matter_roster_api.py` (create `trust='confirmed'`+session
  author; cross-user 404; invalid side 422; partial PATCH re-confirms; aliases replace; **rename+aliases
  preserves the old name**; soft-retire→404; composite GET embeds roster; **audit IDs/side only**).
  Rewritten `test_review_edited_document.py` (roster bucketing; over-trust fix — empty roster → unknown,
  not ours; the three render buckets). Composition grant/inject/doctrine tests.
- **mypy clean (202 files); ruff (CI-exact, repo-root config) clean.**

## Web
- `npm run check` **0 errors**; vitest **987 passed** (+ roster helper tests: side label/tone, trust
  label, alias parse, submittable); prettier clean.

## Live (rebuilt dev stack — api+arq+web at mig `0076`, healthy)
- **Headed Cypress `authorship-roster.cy.ts` — 2/2 passed**, 4 screenshots
  (`f048-roster-{light,dark}.png`, `f048-roster-form-{light,dark}.png`): the **Participants** section
  renders (Mark Counsel · Counterparty badge · role/org · "writes as" aliases · Edit/Remove · "+ Add
  participant"); the add/edit form (Name / Side select / Role / Org / aliases) and the create→PATCH→retire
  round-trips fire against the real endpoints; light + dark verified clean.
- **Live DeepSeek agent scenario `test_matter_roster_scenario.py` — passed**
  (`live-matter-roster.json`): from a plain user statement ("we act for Northwind; the other side's
  counsel is Mark Counsel at Beta LLP, mcounsel@beta.example"), the real agent called
  `record_matter_participant` twice and wrote the roster correctly — **Northwind Trading Ltd → ours
  (Client)** and **Mark Counsel → counterparty (Beta LLP, alias mcounsel@beta.example)**, both
  `trust='inferred'` (tool-fixed agent provenance). Proves the agent-side who-is-who behavior end-to-end
  on the live gateway.

## Adversarial review (4 fresh-context reviewers × self-verify)
- **Security: SHIP** (0 blockers/should-fixes; 1 NIT = the prompt data-fence is the project-wide posture,
  documented in ADR-F048 §Consequences — no action).
- **Contract/docs: SHIP** (0 findings; path arithmetic 151→154 confirmed, meta-tests pass live, full
  type/ADR/migration parity).
- **Simplification: SHIP** (0 should-fixes; the `_aliases_excluding_name` "duplication" is justified
  agent/api separation — consolidation would couple the API on a private agent symbol; **NIT applied** =
  extract `_comment_lines` to match `_change_lines`).
- **Correctness: SHIP with 2 should-fixes (both fixed) + 1 nit (fixed):**
  - **SF1** — alias-merge past the 30-cap called `clean_alias_list` (which raises) outside the try/except →
    crashed the guarded tool / 500'd the PATCH. **Fix:** `clean_alias_list(..., clamp=True)` for the merge
    paths (a merge is internal upkeep, not a proposal to reject); + a clamp-not-crash test.
  - **SF2** — PATCH rename **+** aliases together: the `aliases` replace ran after the rename and clobbered
    the old-name preservation (the panel always sends both). **Fix:** apply the aliases block BEFORE the
    rename block; + a rename-preserves-old-name test.
  - **NIT** — `ParticipantRetireResponse` docstring claimed idempotent-instant; actual is 404-on-second
    (correct). **Fix:** docstring corrected.
