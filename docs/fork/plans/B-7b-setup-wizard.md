# Plan — B-7b: guided admin setup wizard (web over the profiles apply endpoint)

**Status:** DRAFT — awaiting maintainer sign-off on the forking UX decisions (§7) before build.
**Depends on:** B-7a ✅ merged (PR #262, `c8fcd9ba`) — `GET /api/v1/profiles`, `GET /api/v1/profiles/{name}`,
`POST /api/v1/profiles/{name}/apply` are shipped, tested, live.
**Links:** ADR-F067 (module model; B-7a addendum), ADR-F065 (org-library adoption), ADR-F064 (operator
fence), ADR-F013 (design tokens), ADR-F011/F012 (design language). Absorbs ONBOARD-1/2 + G13/#473.

## Context

B-7a made the backend real: a shipped profile (`commercial`/`privacy`/`blank`) can be materialised onto a
real org in one atomic, idempotent transaction that **create/patches the practice area, adopts the matching
`org_library_entries`, and binds skills+tool groups** — reproducing the seeded config AND adopting the
Library so the agent isn't bare. B-7b is the guided web flow a non-technical tenant-admin walks to drive it,
turning a fresh org into "an agent that actually works" without hand-curating the Library.

**Why it matters (G13/#473):** a fresh org's Library is empty (`0088_org_library_entries.py` seeds only if
users exist at migrate-time; the operator is minted *after* migrations), so `build_area_inventory`
(`api/app/agents/capabilities.py:651`, adopted set at `:712`) intersects bindings ∩ adopted(Library) ∩
registry to **nothing** and the agent silently improvises. The wizard's adopt step (driven by apply) is the
fix — and it must be **unskippable**.

The whole slice is **almost entirely web work**: the three endpoints already exist and are tested. The only
possible backend touch is a small read for "is this org already set up?" (§4 — recommend reusing existing
reads, no new endpoint).

## Goals

1. One guided admin page `/lq-ai/admin/setup` that walks: **pick profile → House Brief → review
   bindings/roster/HITL → adopt (unskippable) → apply → receipt → try it now**, driving the shipped
   profiles endpoints.
2. A typed web API client `web/src/lib/lq-ai/api/profiles.ts` (the one real client gap) mirroring the B-7a
   wire shapes.
3. A reusable, token-driven step primitive (`StepRail`) built on F013 tokens (no legacy `--lq-*`).
4. The G13 kill is visible end-to-end: after the wizard, a member runs the Commercial agent and it redlines
   with **no manual Library curation** (the acceptance walk).

## Non-goals (from ADR-F067 D6 + the module milestone)

- No marketplace / cross-org sharing; no Practice Knowledge (F050 future); legacy executors stay FROZEN; no
  MCP wiring; no remote lq-skills sync.
- No new profiles beyond `commercial`/`privacy`/`blank`; `RECOMMENDED_LIBRARY_SETS` kept, not folded.
- **No playbook/knowledge curation in the guided flow** (apply covers skills+tools only; both reference DB
  ids, not static keys). Curation/removal of adopted capabilities stays on the always-available Store/Library
  admin pages — the wizard is **additive** (apply never prunes; a deselect can't be expressed through it).
- No DB migration (unless the maintainer later wants a durable "wizard-completed" flag — recommend deriving
  completion from `PracticeArea.configured` + non-empty Library instead).

## The journey → wizard steps

The apply is one atomic transaction, so steps 1–5 are a **build-up UI**; the single mutation fires at Apply.

| # | Step | Backend call | Reuses (real paths) |
|---|------|--------------|---------------------|
| 0 | Entry / first-run detect | `bootstrapApi.getBootstrapStatus()` + `practiceAreasApi.listPracticeAreas()` (`.configured`) | `web/.../api/bootstrap.ts`, `api/practiceAreas.ts` |
| 1 | Pick a profile | `GET /api/v1/profiles` → `ProfileListResponse` | `Card`/`CardGrid`, new `profiles.ts` |
| 2 | Name the area (**blank only**) | client-side; branch on `kind` | `FormControl` + shadcn `Input` |
| 3 | Review doctrine + bindings + roster + HITL | `GET /api/v1/profiles/{name}` → `ProfileDetail` | area `[key]` section-card composition; B-5 roster helpers |
| 4 | House Brief | `organizationProfileApi` GET/PUT | embed the B-1 form (`admin/house-brief/+page.svelte`) |
| 5 | Adopt modules (**unskippable**) — shows what Apply will adopt + Recommended-for rail | preview via `getDeploymentCapabilities` (`GET /admin/capabilities`); apply performs it | `store/page-helpers.ts` `buildRecommendedRails`/`missingEntries`; `library/page-helpers.ts` `provenanceBadge` |
| 6 | **Apply** (the one mutation) | `POST /api/v1/profiles/{name}/apply` → `ProfileApplyResult` | `ModalShell` confirm, new `profiles.ts` |
| 7 | Receipt | render `ProfileApplyResult` | `Alert(info)`, `StatusDot` |
| 8 | Try it now (CTA into a scratch matter) | normal agent-run path (no special pipeline) | existing run surface |

*Invite-a-member* is part of the maintainer's **acceptance walk**, reachable via the existing
`admin/users` invite flow linked from the receipt — not a modelled wizard step (default; see §7-Q3).

## New / edited web files

**New**
- `web/src/routes/lq-ai/(app)/admin/setup/+page.svelte` — the flow. Copy the per-page admin guard verbatim
  from `admin/store/+page.svelte` (`onMount`: `!$auth.user`→`/lq-ai/login`; then role check → `/lq-ai`),
  **branching on `role` not just `is_admin`** so the operator is redirected out (mirror the server fence).
  Wrap in `PageShell size="wide"` + `SectionHeader size="page"`.
- `web/src/routes/lq-ai/(app)/admin/setup/page-helpers.ts` + `__tests__/*.test.ts` — pure step/validation
  logic: per-step `canProceed()`, `buildApplyBody(kind,…)` (omit target_key/name/unit_label for `area`;
  require all three for `blank`), localStorage draft `lq-ai:wizard-draft:setup`. (Repo convention: thin
  `.svelte`, tested helpers — mirrors `SkillWizard`'s `<script module>` exports.)
- `web/src/lib/lq-ai/api/profiles.ts` — `listProfiles()`, `getProfile(name)`, `applyProfile(name, body)` over
  `apiRequest` (`api/client.ts` gives auth header, `/api/v1` base, 401-refresh, typed errors). Types mirror
  `api/app/schemas/profiles.py`. Export from the `api/index.ts` barrel.
- `web/src/lib/lq-ai/components/primitives/StepRail.svelte` — token-driven step indicator on F013 tokens
  (`--brand` active, `--border`/`--muted` pending); `StatusDot` tones for completed/running/idle. **Do NOT**
  reuse `SkillWizardSection.svelte` (legacy `--lq-*` + teal `#1f7a6b`). Collapses to a compact top indicator
  under ~880px.

**Edited**
- `web/src/routes/lq-ai/(app)/admin/+layout.svelte` — add "Setup" to the hardcoded `navLinks` (active match
  is `pathname.startsWith`).

**Reused (import individually — house primitives have no barrel):** `PageShell`, `SectionHeader`, `Card`,
`CardGrid`, `Stack`, `Inline`, `FormControl`, `Alert`, `ModalShell`, `StatusDot`; shadcn
`Button`/`Input`/`Textarea`/`Badge`; `describeMutationError` (`admin/page-helpers.ts`); Store/Library/area
`page-helpers.ts`. SkillWizard is reused for its **logic pattern only** (canSave / draft autosave /
buildPayload), never its styling.

## Backend gaps

Endpoints are shipped + tested. Concrete gaps:
- **"Already set up?" read** — reuse `bootstrapApi.getBootstrapStatus()` + `PracticeArea.configured`; no new
  endpoint. A durable "wizard-completed" flag is deferrable (derive from `configured` + non-empty Library).
- **Adoption-state preview** — reuse `getDeploymentCapabilities` (`GET /admin/capabilities`: `in_library`,
  `recommended_for`, provenance) + `GET /api/v1/library`. No new endpoint.
- **Apply is additive + skills/tools only** — keep the guided flow additive; leave removal + playbook/knowledge
  to Store/Library pages.

## Risks / traps (from the surface map)

- **Operator fence must be mirrored client-side.** Apply 403s the operator (`tenant_admin_visibility`); but
  `is_admin` admits the operator elsewhere, so a naive `is_admin` guard walks them into a 403. Branch on
  `role === 'operator'`.
- **G13 caveat is the whole point** — the adopt step must be unskippable, and completing the wizard must leave
  the area's bindings **actually adopted** (verified by the live test-run producing a non-empty inventory).
- **Apply asymmetry** — re-apply overwrites manifest scalars but only ADDS bindings/adoptions (never prunes);
  a deselect can't go through apply. Additive-only flow.
- **Blank re-apply is a hard 409** (only creates) — surface "key already in use" on the naming step.
- **Two failure shapes on the body:** `kind` mismatch (sending identity for `area`, or omitting it for
  `blank`) → 422; skill drift → 422; tool-group drift → 404. Branch on `kind` client-side to avoid the shape
  422; surface drift as "this profile references a capability that's no longer available."
- **Profiles are shipped-static (loaded once at boot)** — no runtime catalog refresh; don't build a reload
  affordance.
- **"Nothing new" is success, not error** — on re-apply `adopted`/`bindings_written` can be all-zero via
  `on_conflict_do_nothing`; key success copy off `area_created` + HTTP 200, not the counts. `changed_fields`
  is `[]` on a fresh create even though everything was set.
- **Design tokens** — F013 semantic tokens only (ink `#111`, scarce `--brand` blue, charcoal-not-black dark
  floor); no legacy `--lq-*`. Responsive collapse + `motionMs()`; tokenized scrims, never black.
- **SPA, no route guards/load functions** (`+layout.js` `ssr=false`) — self-guard in `onMount`; the server
  `AdminUser` dep is the real enforcement.

## Verification / DoD (ADR-F005 gate)

- **Web unit:** `setup/page-helpers.ts` vitest — per-step gates, `buildApplyBody` area-vs-blank shape, draft
  autosave, receipt copy keyed off `area_created`. `npm run check` (svelte-check) + `npm run test:frontend`.
- **Cypress full-journey (the acceptance walk):** reset a fresh org (ONBOARD-0/STORE-3 method) → wizard picks
  Commercial → House Brief → adopt (unskippable) → apply → receipt → **invite a member → member runs the
  Commercial agent and it redlines** — screenshot evidence per step under
  `docs/fork/evidence/b7b-setup-wizard/`.
- **Live:** rebuild the prebuilt `web` bundle before UI verification (the container serves a built bundle).
- **Fresh-context adversarial review incl. mandatory security + simplification pass:** operator fence mirrored
  client-side; the only untrusted input is the blank-apply `target_key`/`name`/`unit_label` (validated at the
  boundary + server-side); no secrets/stray files; no legacy-token bleed; dead-code/dup sweep.
- **ADR-F067 B-7b addendum** (wizard shape decisions), HANDOFF + memory updated. Merge under the full
  ADR-F005 gate (`--repo sarturko-maker/lq-ai-fork`; branch + PR; `Co-Authored-By: Claude Opus 4.8`).

## §7 — Decisions (maintainer-ratified 2026-07-11)

- **Q1 First-run behavior → AUTO-LAUNCH, SKIPPABLE.** Auto-open on first admin login when no area is
  `configured`, with a "Skip for now" escape; always reachable from the admin nav afterward. The *adopt step
  within a chosen profile* stays unskippable per G13 (separate from gating the whole wizard).
- **Q2 Flow shape → MULTI-STEP (back/next).** True multi-step with a `StepRail` + gated Next; build the new
  `StepRail` primitive on F013 tokens.
- **Q3 Where the guided flow ends → RECEIPT + "Try it now".** End at the receipt with a CTA into a scratch
  matter; invite-a-member via the existing `admin/users` flow linked from the receipt (not a modelled step).
- **Q4 Diff-preview before Apply → YES.** A "here's exactly what Apply will create/adopt/bind" review screen
  (ADR-F067 B-7a addendum item 5 earmarked the preview for B-7b), since re-apply authoritatively overwrites
  scalars.
- **Q5 Capability curation scope → PROFILE DEFAULT + RECOMMENDED, ADDITIVE.** Adopt the profile's set plus
  optional Recommended-for extras; no deselect in the wizard; removal/curation stays on Store/Library (matches
  apply's additive-only semantics — one clean transaction).
