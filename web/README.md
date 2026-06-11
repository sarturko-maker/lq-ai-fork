# LQ.AI web shell

Standalone SvelteKit single-page app for the LQ.AI client (Apache-2.0 — see the repo-root
`LICENSE`). Until F0-S6 this directory was a fork of OpenWebUI v0.9.2 hosting the shell at
`/lq-ai`; the husk (including its Python backend and the OpenWebUI license §4 branding
obligation) was removed per ADR-F006 — see `NOTICES.md` at the repo root. Builds from pre-S6
commits remain bound by the OpenWebUI license recorded in git history.

## Commands

```bash
npm ci                            # node >=20 <=22
npm run dev                       # vite dev server
npm run check                     # svelte-kit sync + svelte-check (CI gate, 0 errors)
npm run test:frontend -- --run    # vitest unit suite (CI gate)
npm run build                     # static bundle into build/
npm run cy:open                   # Cypress (live-verification specs, needs the dev stack)
```

## Configuration

`PUBLIC_LQ_AI_API_BASE_URL` — baked into the bundle at build time (default `/api/v1`,
same-origin behind a reverse proxy). Local Compose dev sets it to
`http://localhost:8000/api/v1` via the repo-root `.env`; it must be the URL as the **browser**
sees it.

## Serving contract

The container (see `Dockerfile` + `nginx.conf`) listens on **:8080**, serves **GET /health**,
and falls back to `index.html` for client-side routes. `static/word-addin/` is populated by
the repo-root `word-addin/` build (`cd word-addin && npm run build`) and served at
`/word-addin/`; `static/learn/playgrounds/` ships the Learn tab's interactive diagrams.
