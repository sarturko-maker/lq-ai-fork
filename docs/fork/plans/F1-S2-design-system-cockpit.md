# F1-S2 — Design-system foundation + Cockpit v0 shell

Status: plan (2026-06-12). Slice 2 of the ratified F1 re-plan
(`docs/fork/plans/F1-replan.md` § F1-S2 + § Sequencing). Maintainer directives:
S2/S3 ordering delegated → **shell-first, seeded standard practice-area rows in
the same PR** (real config schema lands in S3); design rule (verbatim, governs
all UI work): **"don't use black background, needs to be clean and
professional, cutting edge design."**

Linked ADRs: F006 (stack + semantic intent tokens, accepted), F002 (practice
areas as backend entities; glass-cockpit rules), F004 (render-determinism;
declarative area shapes), F008 (thread identity drives the lists), 0011
(per-message routing disclosure must survive), F001/F005 (process). No new ADR
is minted: every structural call below implements an already-accepted ADR; the
one sequencing call (minimal table now, config vocabulary in S3) was expressly
delegated by the maintainer and is recorded here + HANDOFF.

## Goals

1. **Design-system foundation (ADR-F006).** Vendor shadcn-svelte components
   (CLI `init` + `add`, committed source — never run in CI), on the existing
   Tailwind v4 + Svelte 5 toolchain. One semantic-intent token layer in
   `app.css` (`:root` + `.dark` + `@theme inline`): warm low-chroma neutrals
   (Harvey hue-≈90 pattern), light-first canvas (no white-on-black anywhere;
   dark variant floors at L≥0.20 — never pure black), one restrained accent,
   status intent tokens (`running/completed/failed/cancelled` + wash variants)
   for run rollups, WCAG 4.5:1 text / 3:1 UI contrast in both modes.
2. **Cockpit v0 shell.** Login lands in the cockpit at `/lq-ai`. Left rail
   (paneforge): practice areas from **seeded DB rows** — configured areas
   enterable, unconfigured areas INERT cards (honest state; no composer, no
   matter creation under them) — plus a pinned **"Unfiled conversations"**
   bucket. Main pane: area list → matters under the entered area with
   **activity rollups from settled rows** (last run status + last activity +
   thread count), pick-or-create in place (S8 plumbing reused), resume into
   conversation (re-homed `ConversationPanel`, remount-per-thread contract
   preserved).
3. **Minimal `practice_areas` table + seed (ADR-F002: backend rows from day
   one; frontend-only grouping was rejected).** Columns only for what the
   shell renders: `id, key, name, unit_label, configured, position,
   created_at, updated_at`. Idempotent data migration seeds the standard
   areas (Commercial configured=true — it fronts the existing generic matter
   agent; Disputes, M&A, Privacy, Employment configured=false). S3 owns the
   real config vocabulary (area profile, bound skills/playbooks/MCPs, tier
   floor, `projects.practice_area_id`, admin API).
4. **Cockpit read API.** `GET /api/v1/practice-areas` (list, any active
   user); `GET /api/v1/agents/matters` (owner-scoped rollup: active projects
   LEFT JOIN their agent threads + latest-run status via the existing
   DISTINCT ON pattern at `api/app/api/agent_runs.py:754-760`, plus an
   `unfiled` summary block so the bucket never under-reports);
   `GET /api/v1/agents/threads` gains mutually-exclusive `project_id` /
   `unfiled` query filters (same path — no OpenAPI count change from this
   one). All cross-user access 404s.

## Non-goals (explicit, on record)

- **No restyle of legacy surfaces.** The 11 tool tabs, `--lq-*` tokens and
  ~12k lines of scoped CSS stay byte-identical (LEGACY bugfix-only). The
  cockpit and all new components use the new tokens exclusively; re-pointing
  `--lq-*` values is a later, deliberate slice. The known dark-mode
  brokenness of legacy surfaces is pre-existing and stays.
- **No `projects.practice_area_id`, no area↔skill bindings, no admin/config
  API, no per-area agents** — all S3. In v0 the matters list renders under
  Commercial (the only configured area) as presentation; **no area id is
  written to any stored row** (MILESTONES pre-F1 guard).
- **No RIGHT panel / capability rail rebuild** (S8), **no decision inbox**
  (S6), **no auto-titling/filing** (S8), **no Redis pub/sub live deltas**
  (carry-over; rollups poll settled rows per ADR-F004 anyway).
- **No new agent chrome** (reasoning ribbon / plan / tool cards re-skin) —
  the conversation surface mounts as-is; its redesign rides S4's SSE
  adapter slice on these tokens.
- **No eslint 9 / flat-config migration** (vendored-dir ignore instead);
  **no serif/mono font deps** (Inter-only; optional polish later); **no
  `/lq-ai/agents` removal** — the F0 preview tab stays functional (keeps
  f0-s3/s4/s5/s7 Cypress regression value) until the cockpit fully
  supersedes it.

## Design direction (within the verbatim rule)

Light-first professional canvas at the Harvey/Legora bar: warm near-white
canvas (≈ oklch(0.985 0.003 90)), white cards, hairline low-contrast borders,
slightly tinted rail; ink ≈ oklch(0.26) — never #000 text; ONE deep
indigo-blue accent (≈ oklch(0.47 0.15 262)) used only for primary action,
focus ring, active nav, running pulse; status pills are soft pastel washes
with 600-weight text + small dot (pulsing for running), never saturated
chips. Type: Inter Variable, 13–14px UI body, weights 400/500/600 only,
−0.01em tracking, tabular-nums on counts. Density: 8px grid, 36px list rows,
6/8/10px radii, shadows only on hover. Dark variant: cool charcoal canvas
≈ oklch(0.21 0.006 262) (≈ #17191E — explicitly not black), same accent hue
raised for contrast. Micro-interactions: 120–160ms ease-out, skeleton rows
not spinners, empty states = one headline + one muted line + one primary
action.

## Files

API (`api/`):
- `alembic/versions/0053_practice_areas.py` — table + idempotent standard-rows
  seed (0033 data-migration precedent; checks-before-insert).
- `app/models/practice_area.py` (new), registered in models `__init__`.
- `app/schemas/practice_areas.py` (new: `PracticeAreaRead`),
  `app/schemas/agent_runs.py` (+`MatterActivityRead`, `UnfiledSummary`,
  threads-filter plumbing).
- `app/api/practice_areas.py` (new router: GET list),
  `app/api/agent_runs.py` (+`GET /agents/matters`, threads query filters),
  `app/api/__init__.py` (mount).
- Tests: `tests/test_practice_areas.py` (seed idempotency incl.
  double-upgrade, list endpoint, authz), `tests/agents/test_matter_activity.py`
  (rollup correctness: latest-run DISTINCT ON per project, thread_count,
  unfiled summary, cross-user 404, archived exclusion), threads-filter tests,
  `tests/test_openapi.py` (EXPECTED_PATHS + count 124→126),
  `tests/test_endpoints.py` (IMPLEMENTED_ROUTES + 2).

Web (`web/`):
- `package.json`/lockfile — vendored-stack devDeps (shadcn-svelte 1.3.0,
  bits-ui 2.18.1, paneforge 1.0.2, @lucide/svelte pinned 1.17.0,
  tailwind-variants/-merge, tw-animate-css, clsx); `components.json`;
  `src/lib/utils.ts`; `src/lib/components/ui/{button,badge,input,textarea,
  dialog,dropdown-menu,tooltip,separator,skeleton,scroll-area,resizable}/`
  (vendored, lint/format-ignored).
- `src/app.css` — hand-merged token layer (`:root`/`.dark`/`@theme inline`,
  `@custom-variant dark`, tw-animate + shadcn-svelte/tailwind.css imports);
  existing gray ramp + `@config` bridge retained. `src/app.html` —
  theme-color metas → new canvas values.
- Routes: `src/routes/lq-ai/+layout.svelte` slims to gate-only (auth,
  must-change-password, idle, booted); legacy chrome (header, TopTabBar,
  `#lq-main`, footer) moves to a `(tools)/+layout.svelte` route group
  wrapping every existing tool route (URLs unchanged — groups don't affect
  paths); login/change-password keep current rendering. Cockpit replaces
  `src/routes/lq-ai/+page.svelte`; old guided-dashboard components + their
  tests are deleted (retired per MILESTONES).
- Cockpit components under `src/lib/lq-ai/cockpit/`: shell (paneforge
  panes), area rail (+ inert-card state), matters list + status pills,
  unfiled bucket, pick-or-create dialog (reuses `validateNewMatter` +
  POST /projects), conversation host ({#key} remount, `?area=&matter=&thread=`
  URL state), header (brand, AmbientTrustChrome + SessionTimeoutWarning
  re-homed, Tools menu → legacy routes incl. admin/autonomous gating, theme
  toggle writing `localStorage.theme`, logout).
- `src/lib/lq-ai/api/practiceAreas.ts` (new), `api/agents.ts` (+matters
  rollup, +thread filters), types.
- Tests: cockpit helper/unit tests (URL-state codec, area state mapping,
  rollup presentation, theme toggle contract); update `wave-b-surfaces`
  Cypress landing assertions; new `f1-s2-cockpit.cy.ts` (login→cockpit, area
  list, inert card not enterable, matter create, resume thread); delete
  retired dashboard tests; `.eslintignore`/`.prettierignore` +
  `src/lib/components/ui/**`.

Docs: `NOTICES.md` (new rows: vendored shadcn-svelte source + full dep/license
delta — 19 packages, MIT/ISC/Apache-2.0, runed+svelte-toolbelt cite shipped
LICENSE files), `docs/db-schema.md` (practice_areas), `UPSTREAM.md` untouched,
`docs/fork/HANDOFF.md` (end of slice).

## Dependency justification (SBOM, CLAUDE.md rule)

ADR-F006 (accepted) names the stack; this slice instantiates it. bits-ui
(headless a11y primitives), paneforge (resizable panes — cockpit's core
layout), shadcn-svelte (token/theme CSS + vendoring CLI; becomes a build-time
dep via its tailwind.css), @lucide/svelte (stroke icons, ISC, pinned),
tailwind-variants/tailwind-merge/clsx (component variant plumbing),
tw-animate-css (data-state animations). All MIT except noted; full transitive
list in NOTICES.md. Components are vendored source committed to the repo —
no registry/network access at build or CI time.

## Verification (ADR-F005 gate)

- Containerized: api pytest (throwaway pgvector, alembic head incl. 0053 —
  HANDOFF recipe), gateway untouched, web `npm run check` +
  `npx vitest run` — counts quoted in the PR.
- Migration verified on a throwaway container, never host-side; rebuild
  api + arq-worker + ingest-worker together; rebuild `web` (pre-built
  bundle).
- Live on the dev stack, screenshots in `docs/fork/evidence/f1-s2/`:
  login → cockpit (light + dark — no black backgrounds anywhere); area list
  with Commercial enterable + 4 inert cards; matters under Commercial with
  correct rollups vs DB; unfiled bucket matches
  `agent_threads.project_id IS NULL` count; create matter in place → run a
  real prompt → resume the thread from the cockpit after reload; legacy tabs
  still reachable via Tools menu and fully functional; `/lq-ai/agents`
  unchanged.
- Fresh-context adversarial review (multi-dimension + verify pass) — design
  rule compliance ("no black background…") is an explicit review dimension
  alongside security (authz 404s, no SQL strings, no key leakage) and
  ADR-conformance (F002 inert cards, F004 settled-rows rollups, 0011 tier
  disclosure untouched on the agent surface).
- HANDOFF.md rewritten; squash-merge to `sarturko-maker/lq-ai-fork`.

## Deviations (recorded at gate time, 2026-06-12)

- **Filter semantics beat the plan's "all cross-user access 404s" line**: the
  threads `project_id` filter returns an EMPTY 200 page for a foreign id —
  a filter that 404'd would *confirm* foreign ids exist (the stricter
  reading of the no-existence-leak rule). The rollup endpoint takes no id,
  so no cross-user 404 case exists for it. Tests pin the empty-page
  contract.
- **Seed idempotency is tested as a seed re-run** (`_seed()` against a
  seeded DB), not a literal double `upgrade()` (which would fail on
  `create_table` — the 0033 precedent behaves the same).
- **Cockpit helper tests** cover the URL codec, `timeAgo`, and the theme
  cycle; "area state mapping / rollup presentation" live in markup and are
  covered by the f1-s2 Cypress spec instead.
- **Wider Cypress touch-set than planned**: the cockpit landing removed the
  tab bar from `/lq-ai`, so f0-s3/s4/s5/s7 entry navigation, wave-a (2
  point-in-time-stale tests retired), wave-c test 1, and m4's gating visit
  were updated alongside the planned wave-b edits.
- **Two found-live fixes rode along** (evidence doc § found-and-fixed):
  the auth refresh event-loop freeze (legacy bugfix + double-spend
  liveness re-check under lock) and the dark-token lightness bump.
- **Adversarial-review fixes added** the `threadcreated` URL-sync contract
  to ConversationPanel/cockpit, a sign-out control + Trust menu entry in
  the cockpit header, the truncation row on the conversation list, and
  retired the orphaned "Featured tools" settings toggle (its dashboard
  consumer was deleted by this slice).
