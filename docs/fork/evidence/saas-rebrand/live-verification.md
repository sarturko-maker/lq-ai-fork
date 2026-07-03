# SAAS-rebrand — live verification (2026-07-03)

Dev `web` container rebuilt from `fork/saas-rebrand-oscar-edition`; full stack healthy
(api/gateway/postgres on the AIC-branch code — web bundle has no migration coupling).

## Cypress `saas-rebrand-branding.cy.ts` — 3/3 passing (live, real login)

| Test | Proves |
|---|---|
| pre-auth login page | shell `<title>` == "LQ.AI Oscar Edition" (served HTML also curl-verified); `DualBrandingFooter` shows "**LQ.AI Oscar Edition** — Open-Source Legal AI" |
| post-auth cockpit | header wordmark renders the "LQ.AI Oscar Edition" two-weight lockup (`rebrand-cockpit-header.png`) |
| representative page title | `/lq-ai/playbooks` title == "Playbooks · LQ.AI Oscar Edition" |

Login as a seeded `member@lq.ai` test user (created via the app's own `hash_password` in the
api container; the bootstrap admin's credentials were not touched).

## CI-parity local suite
- svelte-check: **0 errors** (1484 files)
- Vitest: **1051 passed** (99 files) — `CI=1 npx vitest run` (bare `vitest` is watch-mode locally)
- `vite build` (adapter-static): clean
