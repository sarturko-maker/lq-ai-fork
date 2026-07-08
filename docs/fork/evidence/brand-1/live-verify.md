# BRAND-1 live verification (ADR-F068)

2026-07-08, dev stack. Backend (1a) verified pre-merge with a 12/12 HTTP-surface probe (PR #233).
Web (1b) verified against the REBUILT web container (prebuilt-bundle rule) with real-browser Cypress
runs; all probe state (throwaway cypress admin, custom branding, ad-hoc spec, cypress artifacts)
removed afterwards — the dev stack is back to defaults.

## Default install — 3/3 shipped pins pass

`saas-rebrand-branding.cy.ts` (the rebrand pin spec) against the rebuilt bundle: 3 passing / 0
failing — the default install renders byte-identical chrome (login title + footer brand line,
cockpit wordmark lockup, per-page title suffixes). An initial 2/3 failure was the KNOWN
cypress-login trap (the spec's default smoke credentials don't match the seeded `admin@lq.ai`
password — API returned 401, proving the web login flow itself was untouched); re-run with a
throwaway admin via `CYPRESS_LQAI_ADMIN_*` env.

## Custom brand ("Acme Legal", purple accent) — 3/3 probe passes

Branding set via the API (admin PUT: name + full 7-token light/dark palette), then a lead-authored
probe spec (never committed):

| Check | Result |
|---|---|
| Pre-auth login: `h1` "Sign in to Acme Legal", `document.title` "Acme Legal", footer "**Acme Legal** — powered by LQ.AI Oscar Edition" + "Apache-2.0" | PASS |
| `#lq-branding` style tag present with BOTH scopes (`:root:root{…--brand:#7c3aed…}` + `:root.dark{…--brand:#a78bfa…}`) | PASS |
| **Warm-cache reload** (the cascade-blocker regression case): tag re-created by the PRE-PAINT path and `getComputedStyle(documentElement).getPropertyValue('--brand')` RESOLVES to `#7c3aed` — the doubled-specificity fix wins the cascade in a real browser | PASS |
| Post-auth cockpit header wordmark renders "Acme Legal" | PASS |

Screenshots: `brand1b-login-acme.png` (unauth branding — the purple initial tile + branded h1 +
"powered by" footer), `brand1b-cockpit-acme.png` (cockpit header wordmark).

Note (expected, recorded in ADR-F068): legacy `--lq-*` surfaces (e.g. the teal Sign-in button)
keep their own accent — the legacy token set is deliberately non-brandable and migrating away.
