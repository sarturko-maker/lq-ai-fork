# F0-S6 provenance pass — Apache-2.0 relicensing record (ADR-F006)

ADR-F006 made the public Apache-2.0 claim for the standalone web app **conditional on a
per-file provenance pass** over the surviving lq-ai `.svelte` components. This is that record
(2026-06-11, executed before `web/LICENSE` was deleted in the husk-kill commit `8ec1fca`).

## Method

- **Per-file classification** of all 123 `.svelte` files under `web/src/{lib,routes}/lq-ai/`
  by 8 parallel review agents: each file read in full, then matched against the OpenWebUI
  husk (`web/src/lib/components/**` and all other non-lq-ai paths at `8ec1fca^`) by filename
  similarity and by grepping the file's most distinctive lines (multi-line markup, comment
  text, long class-string sequences, SVG path data) across the husk tree.
  Verdict scale: `clean` / `derived` (husk counterpart) / `external` (third-party source) /
  `suspicious` (escalate).
- **Import audit**: every import/require/dynamic-import in the 254 lq-ai source files
  resolved; zero imports escape the two lq-ai subtrees (only `$lib/lq-ai/*`, npm packages,
  and the SvelteKit builtins `$app/navigation`, `$app/stores`, `$app/environment`,
  `$env/dynamic/public`).
- **SVG icon escalation**: 5 files carrying heroicons-style inline SVGs
  (`AppliedSkillsChip`, `InfoTip`, `M2Citations`, `PlaybookDisclaimerBanner`,
  `agents/+page.svelte`) were checked conclusively against full clones of heroicons v1.0.6
  and v2 master plus GitHub-wide code search.

## Results

| Check | Result |
|---|---|
| Component classification | **123 / 123 `clean`** — zero derived, zero suspicious |
| Out-of-tree imports | **0** |
| SVG icons vs heroicons v1+v2 | **No matches.** 4 of 5 path strings are globally unique to upstream `LegalQuants/lq-ai` (Apache-2.0, inherited via the fork); the 5th (`PlaybookDisclaimerBanner` triangle) is de-minimis generic geometry found only in unrelated app repos, never an icon library. `agents/+page.svelte` contains no inline SVG at all. |
| SVG icons vs OpenWebUI husk | **No matches** anywhere under the husk tree. |

Consequently: **no heroicons attribution is required, no icon needs redrawing, and no
surviving file carries OpenWebUI provenance.** The Apache-2.0 condition in ADR-F006 is met.

## What was rewritten vs carried

- `src/app.html` — **rewritten from scratch** (ADR-F006 explicit condition) against a
  behavioral spec: FOUC-free `dark`/`light` class from `localStorage.theme` (default
  `system`, live `prefers-color-scheme` listener, meta theme-color update). The OpenWebUI
  splash screen, `loader.js`/`custom.css` hooks, `resizeIframe`, oled-dark variable
  overrides and `her` mode were dropped, not ported.
- `src/app.css`, `tailwind.config.js`, root layout/error/redirect, `Dockerfile`,
  `nginx.conf` — **written fresh** from behavioral specs.
- **Carried as constants** (uncopyrightable facts, recorded here for transparency): the
  12-step neutral gray ramp oklch values (incl. the non-standard `gray-850`/`gray-950`)
  from the pre-S6 `tailwind.css` `@theme` block — kept so the extraction is a visual no-op.
  The custom checkbox base style and scrollbar cosmetics were re-implemented fresh against
  their behavioral spec (appearance-none + inline SVG checkmark; slim neutral thumbs).
- **No OpenWebUI static assets** (logos, favicon, splash, fonts) were carried; the favicon
  is a new LQ.AI SVG; Inter ships from the `@fontsource-variable/inter` npm package
  (font files OFL-1.1, package MIT — recorded in NOTICES.md).
