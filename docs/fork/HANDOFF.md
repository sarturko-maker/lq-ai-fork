# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (AE3 MERGED — next is AE4)

- **AE0 (#59) + AE1 (#60) + AE2 (#61) + AE3 (PR #62) MERGED** — AI Elements adoption on the chat
  surface (ADR-F011). The **AE-series** brings the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **VENDOR APPROACH CONFIRMED (AE0–AE3):** token system is **identical** to ours (shadcn-svelte +
  Tailwind v4) so remap ≈ identity. Still **zero new runtime deps** through AE3. **ADR-F011 option-2
  (hand-build on shadcn) used again in AE3:** the AE `sources` block sits on `collapsible` (not shipped)
  and `inline-citation` pulls `carousel`+`hover-card` — so `Sources` was hand-built on native `<details>`
  (like the AE2 reasoning ribbon) and only the **two** dependency-free `inline-citation` primitives
  (`-source`/`-quote`) were vendored. `sources/source.svelte` WAS vendored faithfully.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE3**.
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 811** (803 + 8 new `sources.test.ts`); **Cypress `ae3-sources-citations.cy.ts` 5/5** headed/
  live (lab funcional ×2 + live integration + 2 capture); **api pytest 2127 passed / 3 skipped** in a
  throwaway pgvector container (the lone `test_agent_runner` blip was a 20-min-concurrent-load flake —
  re-passed alone; unrelated to AE3). AE3 after-screenshots (lab Sources card + chat surface, light+dark,
  wide+narrow) in `docs/fork/evidence/ae3/`. Adversarial review (fresh-context agent): **SHIP** —
  0 blocker; the one should-fix (soft-deleted file names surfacing + a misleading CASCADE comment) and
  both nits FIXED before merge. Security pass CLEAN (source titles/quotes are escaped text bindings, no
  `{@html}`; backend leaks only the filename; authz unchanged — ownership enforced upstream of the join;
  no new deps; no secrets/stray files).

## Done (AE3, this slice)

- **Backend `get_citations`** (`api/app/api/chats.py`) — LEFT JOINs `files` to add `source_filename` to
  each citation row (the AE Sources card shows real document names, not opaque UUIDs) **without a second
  round-trip** — the lazy single-fetch contract holds. Join scoped to `File.deleted_at IS NULL` (mirrors
  the module's "deleted files invisible" posture); a suppressed/missing name degrades to an ordinal
  label. Test extended (happy path + soft-delete suppression).
- **`citations/format.ts`** — `previewQuote` extracted (was in `M2Citations.svelte`, now shared +
  re-exported for back-compat). **`citations/sources.ts`** — pure `buildMessageSources(citations)`:
  group by `source_file_id` (first-seen order), **most-cautionary** state rollup, distinct sorted pages,
  passage count, representative quote. Vitest `__tests__/sources.test.ts` (8).
- **Vendored `ai-elements/sources/`** — `source.svelte` (faithful; `href` made optional → non-navigating
  `<span>` for our internal docs, viewer is M2-D2), `sources.svelte` (**option-2** on `<details>` —
  trigger="Used N sources"+chevron, content snippet), `index.ts`. **Vendored `ai-elements/inline-citation/`**
  — only `-source` + `-quote` (the two dependency-free primitives used), `index.ts`.
- **NEW `MessageSources.svelte` (runes)** — composes Sources + the inline-citation identity with a 5-state
  verification marker (badge-check green/amber, circle-alert grey; AA in light+dark, matches M2Citations
  palette). Rendered in `MessageBubble` assistant footer **above** the M2Citations sidecar chips; renders
  nothing when the message cites no documents.
- **`_ae-lab`** — Sources demo (3 docs, mixed states). **NOTICES + `ai-elements/README.md`** updated.
  **`cypress/e2e/ae3-sources-citations.cy.ts`** (5).

## Next slice — pick up exactly here

1. **AE4 — Code Block** (plan §"AI Elements visual adoption" → AE4). **This is the one sanctioned new
   runtime dep: `shiki`** (justified in ADR-F011 — SBOM entry; tokenizes text, no eval/network). Vendor
   the AE **Code Block** (language header + copy button + Shiki highlight); hook it into
   `renderModelMarkdown`'s `<pre><code>` output — **highlight runs client-side on ALREADY-SANITIZED text**
   (no injection). **Inspect first** (proven pipeline): `curl https://svelte-ai-elements.vercel.app/r/code-block.json`
   — parse with python3 from the repo dir (NOT jq; mind `/tmp/types.py`). **Adversarial + security
   (extra pass — touches a new dep + a render sink):** confirm Shiki receives escaped text only; SBOM +
   ADR-F011 dep note + `NOTICES.md` row + `package.json`/lockfile surgical add (mirror the `runed` devDep
   precedent if it's build-time, but Shiki ships in the bundle → it's a true runtime dep); copy-button
   clipboard a11y; dark theme of the code surface reads AA. Full four-discipline gate + before/after
   screenshots (light+dark). Lab-based functional tests dodge the auth flakiness.
   Then **AE5 Prompt Input (≡ old R9 slot; also migrates ChatPanel's remaining `--lq-*` shell — see
   Carry-overs; responsive collapse REQUIRED in the narrow shot)** → **AE6 Tool+Task (≡ old R-CONV-2
   slot; responsive)** → AE7 Suggestions (the AE0 `Suggestion` chips are ready). **Backlog (from R6):**
   converge `ConversationPanel` + `SkillSourceView` onto `renderModelMarkdown` (do as part of AE6).
2. Other rollout slices (any order — the dark-mode bridge holds un-migrated surfaces):
   Foundation/rail R2–R5, Wave 1 R-CONV-1 (logic; R-CONV-2 → AE6), Wave 2
   R12/R13/R14a-b/R15/R15b-tab-pb/R16, Wave 3 R17a-b/R18/R19a-b/R20/R-CHROME, cleanup R-TYPO →
   R-BRIDGE → R-LAST. autonomous R21 = SKIP (deferred to F2/F3, stays on bridge).
3. **F1-S4** (subagent tree + SSE v3-projection adapter) / **F1-S5** (idempotency ledger +
   attribution fan-out) — `docs/fork/plans/F1-replan.md`. **Area skills/subagents ACTIVATION**
   (S9-gated) — wires `composition.py` to pass area skills/subagents + re-runs the S9 matrix.
   **Backlog:** scira-style minimalist interface pass AFTER the AE-series (MILESTONES § Backlog;
   **AGPL → reference-only**, study look/IA, never copy code — unlike the MIT AE port we vendor).

## Rollout progress

- **R-series:** Step 0 ✅ (#50) · R0 ✅ · R1a ✅ (#51) · R6 ✅ (#52) · R7 ✅ (#55) · responsive parity ✅
  (#53) · **R8 ✅ (#57)**. CI unblocked (repo public).
- **AE-series (ADR-F011):** plan+ADR ✅ (#58) · **AE0 ✅ (#59)** vendoring foundation · **AE1 ✅ (#60)**
  Conversation+Message+Response · **AE2 ✅ (#61)** Reasoning+Actions · **AE3 ✅ (PR #62)** Sources +
  Inline-Citation (Sources card + `source_filename` join). **Next AE4 (Code Block + `shiki`).**

## Carry-overs / review deferrals

- **AE2 — ChatPanel dark-mode shell gap (deferred to AE5 ≡ old R9):** in the wide layout the central
  chat *column* renders LIGHT in dark mode while the chrome is dark — ChatPanel shell still uses legacy
  `--lq-*` tokens. Pre-existing (AE1+AE2), NOT an AE3 regression (AE3 touched only the message footer +
  the new Sources card, both semantic-token). **AE5 migrates ChatPanel's `--lq-*` block.**
- **AE3 — no new carry-overs.** The fresh-context review's one should-fix (soft-deleted filenames
  surfacing + misleading CASCADE comment) and both nits (unused `isFallbackLabel`; over-vendored
  `inline-citation`/`-text`) were FIXED in-slice, not deferred.
- **AE1 nit (on record):** unused `debugInfo` getter in `stick-to-bottom-context.svelte.ts` — kept
  diffable vs MIT upstream.
- **AE0 nits (on record, byte-faithful to MIT upstream):** `loader-icon.svelte` redundant inline
  `style="color: currentcolor"`; shared static clipPath id across mounted Loaders (renders fine; scope
  with `$props.id()` if a future AE component needs per-instance clip geometry).
- **R8 deferred-on-record:** focus-on-open not asserted in Cypress (Xvfb programmatic focus); drawers not
  full focus-traps (ESC + scrim + `inert` cover practice).
- auth/refresh: per-user session cap + web gate timeout SHIPPED (#47). REMAINING: the
  **deterministic-HMAC index** (removes the global bcrypt scan + bad-token DoS; needs a migration +
  security review — Backlog). **AE3 re-confirmed:** under a LONG spec (7 min, many `cy.visit`) AND
  concurrent Docker load (the api suite running), page loads start timing out (elements "never found") —
  the documented degradation, NOT a code defect. Re-running the spec ALONE on a fresh/uncontended backend
  → **5/5**. More evidence for the HMAC index.
- F1-S3 deferrals: subagent-spec skill names bypass registry validation (validate on activation slice);
  `audit_log.practice_area_id` unindexed; area tier floor operator-set until a model > tier 4.
- ADR-0011 disclosure after F1-S5 attribution. Live SSE token deltas DEAD until a Redis pub/sub
  publisher lands (F1-S4). ADR-0011/F003 conversation memory + compaction → F2.

## Gotchas (carried + new)

- **NEW (AE3): run ruff from the REPO ROOT with the root `ruff.toml`, exactly as CI does.** CI runs
  `ruff check api scripts` + `ruff format --check api scripts` from the repo root. Running ruff from
  inside `api/` uses ruff's DEFAULT settings (the root `ruff.toml` excludes web/ and tunes line-length/
  rules) → spurious "would reformat" noise AND it MISSES rules like `UP017` (`datetime.UTC` over
  `timezone.utc`) — AE3's first CI run failed on exactly that. Correct repro:
  `docker run --rm -v $PWD:/repo -w /repo python:3.12-slim bash -c "pip install -q ruff; ruff check api
  scripts; ruff format --check api scripts"`. Under the root config everything (incl. your edits) is
  format-clean. `mypy app` (run from `api/`) still must pass separately.
- **NEW (AE3): running api pytest off the live dev DB.** The runtime image has NO test deps and the live
  postgres is off-limits. Recipe: throwaway `docker run -d --name <pg> --network lq-ai_default
  pgvector/pgvector:pg16` (+ `CREATE EXTENSION vector`); then
  `docker run --rm --network lq-ai_default -v $PWD/api:/app -v $PWD/skills:/skills:ro -e
  DATABASE_URL=postgresql+asyncpg://lq_ai:lq_ai@<pg>:5432/lq_ai -e LQ_AI_SKILLS_DIR=/skills --entrypoint
  bash lq-ai-api:latest -c "pip install -q -e .[dev]; python -m pytest -q …"`. **Mount `./skills`** or
  migration 0032 (seeds NDA playbook YAML) fails. conftest creates its own `lq_ai_test_*` DB per run.
- **NEW (AE3): the citations intercept glob.** The endpoint is `/chats/{id}/messages/{mid}/citations` —
  AE2's `**/api/v1/messages/*/citations` glob MISSED it (no `/chats/` segment). Use
  `**/api/v1/chats/*/messages/*/citations`.
- **NEW (AE3): option-2 again — Sources + inline-citation.** `sources` pulls `collapsible`;
  `inline-citation` pulls `carousel`+`hover-card`+16 files. Hand-build `Sources` on `<details>`; vendor
  only the dependency-free `inline-citation` primitives you actually use (AE0 "take only what you need").
  Inspect each registry item's `dependencies`/`registryDependencies` BEFORE deciding vendor vs hand-build.
- **(AE2): forward shadcn `Button onclick` through a RUNES wrapper, not the legacy parent** (legacy
  `on:click` on a runes component = silent no-op). `MessageActionsBar`/`MessageSources` are runes wrappers
  the legacy `MessageBubble` feeds plain props.
- **(AE2): lab-based functional Cypress dodges the auth-login flakiness.** `_ae-lab` is auth-gated but
  makes no API calls → deterministic interaction tests run there; use the live chat surface only for the
  integration check + before/after capture. Distinguish icons via lucide `svg.lucide-<name>`.
- **(AE1): the AE dark-capture recipe.** SHORT fixture · `localStorage.theme` BEFORE `cy.visit` · post-boot
  class pin · `cy.get('html').should('have.class', theme)` · 1px viewport nudge before `cy.screenshot`.
- **(AE1): wrapping a Svelte-4 component's content in runes children works** (legacy slots → `children`
  snippet). Alias the AE `Message` *component* vs our `Message` *type* (`Message as AeMessage`).
- **(AE0): the AE vendor pipeline** = shadcn-svelte registry JSON (`…/r/<c>.json`), NOT jsrepo. INSPECT
  before vendoring. Items can under-declare deps. Never adopt the `streamdown-svelte` `response` sink —
  keep `renderModelMarkdown`. **"dev-only route"** = unadvertised, auth-gated, leading-`_` (`_ae-lab`);
  the web container always serves a PROD build. Vendored AE source is eslint-exempt; kept prettier-formatted.
- web CI gates only `npm run check` + vitest (eslint/prettier NOT gated). `npx vitest run` (NOT
  `test:frontend` = watch). vitest env is `node` (no jsdom) — DOMPurify/sanitisation must be Cypress-tested.
  **headless cypress lies about dark theme — capture headed** (`DISPLAY=:0`); **rebuild the `web`
  container before screenshotting/Cypress-testing a UI change.** Cypress trashes `cypress/screenshots`
  at run START — copy before/after frames to `docs/fork/evidence/` immediately after each run.
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork` AND
  `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3 (run from repo dir,
  `/tmp/types.py` shadows stdlib `types`).
- migrations: NEVER host-side alembic against the live dev DB; api auto-migrates on boot; rebuild
  api+arq-worker+ingest-worker together + web. **NEVER `docker compose down -v`.**
- MiniMax-M3 is tier 4 (weak) — `default_tier_floor` < 4 makes every run 403. deepagents subagent `model`
  string = gateway-bypass (ADR-F010 guard at `build_deep_agent`). New API endpoints register in
  tests/test_openapi.py (count assert) — AE3 added NO endpoint (a field on an existing one).
