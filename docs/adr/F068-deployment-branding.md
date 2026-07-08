# F068 — Deployment-level branding (white-labeling without code changes)

Status: proposed
Date: 2026-07-08
Deciders: maintainer + agent lead
Slice: BRAND-1a (backend + wizard); BRAND-1b (web) consumes this contract
Plan of record: the BRAND-1 scout report/plan (maintainer approved the shape 2026-07-07,
alongside the modular + Azure pivot, `docs/fork/plans/PIVOT-modular-azure.md`).

## Context

A client deploying LQ.AI Oscar Edition (self-host or hosted, ADR-F058) wants the product to carry
THEIR name, accent colour and logo — on the login page, the cockpit chrome, page titles and the
invite/reset email subjects — without forking the code or rebuilding images. Today the brand is
hardcoded (rebrand PR #214 surfaces) and the email subjects pin "LQ.AI"
(`api/app/lifecycle_email.py`). Hard lines set by the maintainer: the `NOTICES.md` +
`DualBrandingFooter` attribution stays; `lq-ai-*` / `--lq-*` / `LQ_AI_*` code identifiers never
rename; the Word add-in manifest stays deferred.

Option-A stack-per-tenant (ADR-F058) means one deployment IS one tenant, so branding is a
deployment-level concern. The login / accept-invite / reset-password pages are branded surfaces
consulted BEFORE authentication, so the read path must be unauthenticated.

## Considered Options

### Storage / scoping
1. **Deployment singleton row** (`deployment_branding`, the `organization_profile` mig-0010
   pattern: partial unique index on `((true))`, upsert endpoints).
2. Per-org branding rows — no org entity exists to scope by, and Option-A already equates
   deployment with tenant; pure speculative surface.
3. Env-only configuration (no table) — admins couldn't change branding at runtime; every tweak
   becomes an operator/deploy action, defeating "no code changes, no redeploys".

### Logo storage
1. **BYTEA in the singleton row, ≤512 KB, raster only.**
2. The `files` + S3 path — rejected: `files.router` is auth-gated and rows are user-owned, while
   the logo must be served on an UNAUTH path; that would put S3 credentials / signed URLs on an
   unauthenticated surface and misuse machinery sized for 100 MB documents.

### Logo format validation
1. **Magic-byte sniffing (PNG `\x89PNG\r\n\x1a\n` / JPEG `\xff\xd8\xff` / WEBP `RIFF....WEBP`),
   store + serve the SNIFFED type, never the client header.** SVG is rejected *by construction*
   (fails the sniff) — SVG can carry script and the logo is served unauth to every visitor.
2. Trust `upload.content_type` — rejected: attacker-controlled header (`files.py` trusts it for
   auth-gated user documents; an unauth-served deployment asset must not).
3. Decode-and-revalidate with pillow — rejected: new dependency (SBOM rule) and a
   decompression-bomb surface; sniff-without-decode has neither.

### Palette shape
1. **CLOSED per-theme allowlist** — themes `{light, dark}`, tokens `{brand, brand_foreground,
   ring, sidebar_ring, status_running, status_running_wash, chart_1}`, every value
   `^#[0-9a-fA-F]{6}$`; unknown theme/token/bad value → 422 naming the offender.
2. Free-form CSS-variable map — rejected: palette values are string-built into a `<style>` tag by
   the web client (BRAND-1b); an open set is a CSS-injection surface and would also let a tenant
   recolour `--primary`, which is ink (#111) BY DESIGN in the F013 language (pairing and WCAG
   audit break if it moves). The scarce-blue family above is the entire brandable set.

## Decision Outcome

One `deployment_branding` singleton (migration 0090): `product_name` varchar(80) NOT NULL default
`''` (empty = default brand), `palette` JSONB NOT NULL default `{}` (the validated allowlist
shape), `logo_bytes` BYTEA nullable + `logo_content_type` varchar(32) nullable (the sniffed type),
`updated_by` FK SET NULL, `updated_at` via the shared `set_updated_at()` trigger.

**Endpoints** (`api/app/api/branding.py`, router mounted unauth next to `bootstrap`):
- `GET /api/v1/branding` — unauth, public-by-design; `{product_name, palette, logo_version,
  updated_at}`; `logo_version` = an OPAQUE cache-buster when a logo is set, else null (the
  client's `?v=` query value). It derives from `updated_at` at MILLISECOND resolution — whole
  seconds would let two logo writes inside the same second share a version, leaving the
  immutable-cached (1y) old logo unbustable; clients must not parse it.
  `Cache-Control: public, max-age=300` bounds staleness; per-IP rate-limited
  (`enforce_branding`, the bootstrap-status precedent — shared bucket with the logo GET). An empty
  singleton returns 200 defaults, never 404.
- `GET /api/v1/branding/logo` — unauth; sniffed stored type, `Cache-Control: public,
  max-age=31536000, immutable` (safe because the URL is version-busted),
  `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`; 404 when unset.
- `PUT /api/v1/branding` / `POST /api/v1/branding/logo` / `DELETE /api/v1/branding/logo` —
  `AdminUser` at the handler level (the whole router is unauth-mounted, so every write carries the
  dependency explicitly — the `organization_profile` PUT pattern). `product_name` rejects
  control/format/line-separator characters (Unicode categories Cc/Cf/Zl/Zp — C0 AND C1 controls
  incl. CR/LF and DEL, U+2028/29, RTL overrides): the name lands in SMTP **subject headers**
  (`lifecycle_email.py`), so this is a header-injection boundary (the composer additionally
  strips the same character classes belt-and-braces). Audit rows carry counts/lengths/types
  only, never values. The validation rules (name cap, hex shape, control-char predicate, palette
  allowlist) are defined ONCE on `app/models/deployment_branding.py` and imported by the PUT
  boundary, the env seeder and the composer — the three surfaces cannot drift.

**Email parameterization:** `send_invite_email` / `send_password_reset_email` gain a
`product_name` kwarg (default `"LQ.AI"`); the two call sites resolve it via
`get_branding_name(db)`.

**First-boot seeding** (`ensure_first_run_branding`, called from the api lifespan): inserts ONLY
when the table is empty AND at least one of `BRAND_PRODUCT_NAME` / `BRAND_ACCENT_LIGHT` /
`BRAND_ACCENT_DARK` is set — an admin's in-app edits always win afterwards (the row's existence
blocks re-seeding). Invalid env values are warned about and skipped (degrade-not-crash), never
sanitized into something else. **Accent fan-out** (server-side, per theme):

- `brand = ring = sidebar_ring = status_running = chart_1 = accent`
- `brand_foreground` = `#ffffff` (light) / `#111111` (dark) — the shipped defaults' pairing
- `status_running_wash` = the accent blended into the theme canvas by pure channel math
  (8% accent over `#ffffff` on light; 16% accent over `#111111` on dark) — a quiet pill
  background in the accent's hue, approximating the shipped `#eef4ff` / `#14233a`.

**Wizard:** `scripts/setup-tenant.sh` accepts optional `BRAND_PRODUCT_NAME` /
`BRAND_ACCENT_LIGHT` / `BRAND_ACCENT_DARK` manifest keys and writes conditional `.env.prod` lines.
The product name deliberately does NOT pass the generic `check_value` charset (which bans spaces
and `#` because values land unquoted in a root-sourced env file); it gets its OWN fence
`^[A-Za-z0-9 ._-]{1,80}$` (no shell metacharacters) and its `.env.prod` line is emitted QUOTED;
the accents get `^#[0-9a-fA-F]{6}$` fences. The generic safe set is never widened. The **logo is
NOT wizard-seedable** — the manifest is flat KEY=VALUE with no binary channel; logo upload is an
admin-page action after first boot.

**Footer attribution (hard line, binding on BRAND-1b):** `DualBrandingFooter` keeps the
Apache-2.0 + LQ.AI attribution in every configuration. A custom product name renders as
**"NAME — powered by LQ.AI Oscar Edition"**; the default install keeps today's line verbatim.
`data-testid="lq-ai-dual-branding-footer"` and all `lq-ai-*` test ids never rename.

## Consequences

- **Good:** a tenant renames/recolours/logos the product at runtime — no code change, no rebuild
  (the web client re-reads the unauth GET each boot); the palette stays inside the audited design
  language; SVG/script logos are impossible by construction; the seed path lets the operator
  wizard pre-brand a stack while keeping the admin authoritative afterwards.
- **Bad / cost:** a migration (0090); one more unauth endpoint pair (bounded: per-IP rate limit,
  cacheable, fixed public fields, no user data, no version fingerprints); logo bytes ride the DB
  and its backups (≤512 KB, acceptable); the wash derivation is a fixed formula — a tenant wanting
  a precise wash sets `status_running_wash` explicitly via PUT.
- **Non-goals (recorded):** per-org branding rows; renaming code identifiers
  (`lq-ai-*` / `--lq-*` / `LQ_AI_*`), wire headers or test ids; the Word add-in manifest/display
  name (stays deferred); `--primary`/canvas theming (ink by design); the legacy `--lq-*` token set
  (`practice.css` — migrating away, keeps its own accent).
- BRAND-1b (web) builds on this contract: pre-paint cache + dual-scope `<style>` injection with
  client-side RE-validation of the same allowlist (localStorage is untrusted), wordmark/footer/
  login/title/favicon swaps, admin Branding page with contrast checks.
