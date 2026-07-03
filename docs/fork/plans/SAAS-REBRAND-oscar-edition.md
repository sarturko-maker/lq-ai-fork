# SAAS-rebrand — execute "LQ.AI Oscar Edition" branding

**Status:** implemented (branch `fork/saas-rebrand-oscar-edition`, task #455).
**Governing ADR:** [F058 — hosted-SaaS charter](../../adr/F058-hosted-saas-charter.md) (name decision
accepted 2026-07-02; this slice is the *execution*, recorded in F058's "Rebrand execution" addendum).
No new ADR — the slice makes no new architectural call.

## Context

ADR-F058 set the fork's product name to **"LQ.AI Oscar Edition"** (retaining the "LQ.AI" mark so
ADR-F001's rename obligation is met without appropriating a third party's identity; the "Oscar Edition"
suffix distinguishes the fork from upstream's own releases). Only the *execution* remained — apply the
name to user-facing surfaces. A four-lens branding audit (Opus subagents; result folded into the PR)
mapped the surface and, critically, the boundary a rename must never cross.

## Goals

- Apply "LQ.AI Oscar Edition" to the genuinely user-facing **product-name surfaces** in the live web
  client and the repo front door.
- Do it **surgically** — display strings only — so no identifier, wire contract, or provenance record
  is disturbed.

## Non-goals

- **Not** a global `LQ.AI` → `LQ.AI Oscar Edition` replace. The mark is retained; a bare `LQ.AI` in
  running prose / action phrases / developer-education headings stays as the short mark.
- **Not** a README body rewrite (upstream M1–M4 narrative + governance) — out of scope; only the H1,
  a fork-identity note, and the front-door framing change.
- **Not** the Microsoft Word add-in (deferred — see below).
- No code-namespace / CSS-token / env-var / package / image / testid / DB / observability rename.
- No edit to NOTICES.md or LICENSE (provenance; extend-never-edit; the rename adds no new entry).

## Changed surfaces (12 + fork note)

| # | File | Surface |
|---|---|---|
| 1 | `web/src/app.html` | SvelteKit shell `<title>` (app-wide fallback tab title) |
| 2 | `web/src/lib/lq-ai/cockpit/CockpitHeader.svelte` | app-wide brand wordmark (two-weight lockup: bold **LQ.AI** + muted "Oscar Edition") |
| 3 | `web/src/lib/lq-ai/components/DualBrandingFooter.svelte` | footer brand line (app-wide + pre-auth login) |
| 4–11 | 8 route `+page.svelte` | per-page `<title>` suffixes (playbooks, tabular ×3, autonomous session, playbook-execution, admin audit-log) |
| 12 | `README.md` | front-door H1 → "LQ.AI Oscar Edition" + a factual fork-identity note under the tagline |

## DECIDE calls (made on best judgment; documented for maintainer review)

- **Running-prose `LQ.AI`** → KEEP short mark (rename surfaces, not sentences).
- **Login heading "Sign in to LQ.AI"** → KEEP (clunky expanded; brand carried by the monogram + footer).
- **`/learn` headings + static playgrounds** → KEEP (developer/codebase-framed education, not the hero).
- **4× FastAPI `/docs` titles** (api, gateway, slack-bridge, teams-bridge) → KEEP (service descriptors on
  the retained mark).
- **PRD / architecture / CONTRIBUTING / db-schema titles** → KEEP (unmodified upstream docs; a title-only
  swap would make the doc internally inconsistent with its own body/governance).
- **`DevForkCallout` repo URL** (upstream `LegalQuants/lq-ai`) → KEEP for now; its linked PRD §10 /
  ADR-0009 are upstream documents, so repointing at the fork would break those specific links. **Flag for
  the maintainer:** repoint to the fork if we want developers to build on the fork's own frontend.
- **TOTP issuer `LQ.AI`** (authenticator-app label, api-side) → KEEP by the same "retained short mark"
  policy as the login heading; also has enrolled-user-consistency implications.

## Deferred (documented follow-ups)

- **Word add-in:** default display name (`api/app/api/word_addin.py` `DEFAULT_DISPLAY_NAME`) → the product
  name, **plus** tokenising two hardcoded manifest strings (`Open LQ.AI`) to `{{ DEPLOYMENT_DISPLAY_NAME }}`
  in **both** manifest copies (`api/app/data/word_addin_manifest.xml` and `word-addin/manifest.xml`). It is
  a genuine M365 end-user surface, but the add-in is non-live scaffold and admin-overridable, and the
  manifest change is a correctness fix that warrants its own M365-manifest-validation pass — not a
  display-string rename.
- **README body rewrite** (upstream M1–M4 narrative + Kevin-Keller/LegalQuants governance → the fork's
  Deep-Agents/modules story) is a larger content task.

## KEEP boundary (a global find/replace would break the app)

Code namespace `web/src/lib/lq-ai/**` + `$lib/lq-ai` imports (~140 sites); `--lq-*`/`.lq-*` CSS tokens;
`LQ_AI_*` / `PUBLIC_LQ_AI_*` env-var namespace (pydantic binds by field name); `lq-ai-*` package/image/
`data-testid` identifiers (~1,300 testids asserted 1:1 in Cypress); cross-service wire headers
(`X-LQ-AI-Gateway-Key`, `X-LQ-AI-Routed-*`); infra literals (`lq_ai` role/db, `lq-ai-files` bucket);
observability service names; and all upstream/provenance references (`LegalQuants/lq-ai`, open-webui,
NOTICES.md, LICENSE). `LegalQuants` is the provider/org name (not the product) and stays. **False positive:**
"Oscar" in `web/src/lib/lq-ai/components/ropa/*` comments refers to a competitor product, not "Oscar Edition".

## Verification

- `web`: `npm run check` (svelte-check) + `npm run test:frontend` (Vitest) — CI-parity; the CockpitHeader
  multi-line wordmark markup compiles.
- No `api`/`gateway` code touched → those CI jobs pass unchanged (README + `docs/adr` are doc-only).
- Grepped Cypress/Vitest for assertions on the changed strings: none (the one `cy.contains('Sign in to
  LQ.AI')` targets the deferred Word-add-in page, which is unchanged).
- Live UI screenshot of the rebranded header/footer before merge (prod build + preview — no dev-stack
  disruption; the dev stack rides the AIC migration chain).
- Merged under the full ADR-F005 gate (the NAME is maintainer-accepted in ADR-F058; execution is
  display-strings-only and trivially revertible). Two follow-ups flagged for the maintainer's taste,
  each a one-line change: the CockpitHeader "Oscar Edition" lockup styling, and the DevForkCallout
  repo-URL repoint question.
