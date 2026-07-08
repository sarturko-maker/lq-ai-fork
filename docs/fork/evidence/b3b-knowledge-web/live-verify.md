# B-3b live UI verification — knowledge web surfaces (ADR-F067 D1)

**Date:** 2026-07-08 · **Branch:** `b3b-knowledge-web` (`b749d145`) · **Stack:** dev
`docker compose` (web rebuilt from this branch; api unchanged — the slice is web-only) ·
**Runner:** Cypress 13 headless (Electron), temporary spec `web/cypress/e2e/b3b-probe.cy.ts`
(deleted after the run, B-2b precedent).

**Probe user:** `b3b-probe-admin@example.com` (admin). Credentials rode
`CYPRESS_B3B_PROBE_PASSWORD`; never in the spec or logs.

**Result: 7/7 passing** on the final evidence run. Full loop: create a knowledge
collection (API) → adopt it in the **Store** UI → see it on the **admin Library** →
bind it on the **area page** → member **Library** where-used line names the area →
**matter Capabilities** tab lists it (toggle ON by default) → un-adopt degrades the
binding (G13 amber chip) → UI **remove modal** carries the honest fail-closed copy.

## Step-by-step outcomes

| # | Surface | Outcome |
|---|---|---|
| 1 | `/lq-ai/admin/store` | PASS — new **Knowledge** section lists the collection with name + description; **Add to Library** → card flips to `In Library ✓`. → `01-store-knowledge-section-adopted.png` |
| 2 | `/lq-ai/admin/library` | PASS — Knowledge card renders (label + "Not attached to any practice area."). → `02-admin-library-knowledge-card.png` |
| 3 | `/lq-ai/admin/areas/b3b-probe-area` | PASS — new **Knowledge collections** bind card: attach `<select>` → Attach → bound row with name + Detach. → `03-area-knowledge-bound.png` |
| 4 | `/lq-ai/library` (member view) | PASS — knowledge card shows **"Attached to: B3b Probe Area"** (where-used map now covers `bound_knowledge_bases`). → `04-member-library-where-used.png` |
| 5 | Cockpit → matter → **Capabilities** tab | PASS — Knowledge section lists the collection as a toggleable row (default ON; server-driven section shipped in B-3, panel types/caption made knowledge-aware here). → `05-matter-capabilities-knowledge-toggle.png` |
| 6 | Un-adopt (API `DELETE /admin/library/knowledge/{id}`) → area page | PASS — G13 degraded chip on the bound row: *"Not in your Library — the agent will not receive this. Adopt in Store"* (fail-closed truth: composition drops the collection). Re-adopt clears it. → `06-area-degraded-chip.png` |
| 7 | Admin Library → Remove (D-F confirm) | PASS — modal shows where-used ("Attached to: B3b Probe Area") + the generic warning verified truthful for knowledge: *"The B3b Probe Area agent will lose this — it stays attached but stops resolving until you add it back."* Confirm → card leaves the Library. → `07-remove-confirm-modal.png` |

## Teardown

Spec `after` hook (API: detach → project → area → library entry → collection), then SQL
hard sweep of the probe admin and every row it owned (knowledge_bases 4, projects 4 —
archived leftovers across spec iterations — audit_log 48, users 1). Residual queries
returned **zero** for users / knowledge_bases / projects with the probe markers;
`practice_areas` and `org_library_entries` were already clean from the API teardown.

## Gate summary (same tree, commit `b749d145`)

- `npm run check`: **1534 files, 0 errors** (5 pre-existing warnings, none in touched files).
- `CI=true npm run test:frontend`: **112 files / 1265 tests, all passing**.
- Zero `api/` changes — no api suite or migration concerns; the five route drift guards
  are untouched by construction.

## Rig notes (reused from B-2b, one addition)

- Seed `lq_ai_auth` localStorage with `refresh_token: null` (activity tracker otherwise
  rotates the token and kills the session snapshot).
- App-shell `<main>` no-ops `scrollIntoView` — assign `scrollTop` directly before shots.
- NEW: the matter Capabilities tab lives in the cockpit at
  `/lq-ai?area={key}&matter={project_id}` (testid `lq-cockpit-matter-tab-capabilities`);
  the `/lq-ai/matters/{id}` route is the legacy attach page and has no tab strip.
