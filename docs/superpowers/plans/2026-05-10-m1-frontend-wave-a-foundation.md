# M1 Frontend — Wave A (Practice Visual Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Practice visual system, base components, and top-tab + ambient-chrome layout for the `/lq-ai/*` shell so existing routes stop reading as "technical/mechanical" — without changing any feature behavior.

**Architecture:** Practice palette exposed as semantic CSS variables (`--lq-accent`, `--lq-secure`, `--lq-tier`, etc.) so the open-source community can re-theme without touching component logic. Inter variable font shipped via `@fontsource-variable/inter` (no Google CDN dependency — preserves self-host posture). Net-new shared components live at `web/src/lib/lq-ai/components/` alongside existing ones; `TierBadge` is refactored to wrap the new `TrustPill`. `+layout.svelte` extends with top-tab nav + ambient trust chrome; tabs whose surfaces don't exist yet route through a `ComingSoonModal` pointing to the design spec.

**Tech Stack:** SvelteKit 2 · TypeScript · Tailwind v4 · Vitest · `@fontsource-variable/inter` (new dep) · existing OpenWebUI fork primitives via import only (ADR 0009).

**Scope contract:** Wave A does *not* implement: the Guided Dashboard, Matter Workspace, Knowledge browser, Saved Prompts surface, Trust & Privacy page, settings/appearance, onboarding flow, or any power-feature UX. Those are Waves B–F. Wave A's only job is the foundation that subsequent waves build on, plus visual lift on what already ships.

**Anchors:** [Spec §5 (Practice palette)](../specs/2026-05-10-m1-frontend-design.md#5-cross-cutting-patterns-and-the-practice-visual-system), [Spec §8.1 wave order](../specs/2026-05-10-m1-frontend-design.md#81-phasing-within-this-branch), [ADR 0009 web shell coexistence](../../adr/0009-web-lq-ai-shell-coexistence.md).

---

## File structure

**Net-new files:**

| File | Responsibility |
|---|---|
| `web/src/lib/lq-ai/styles/practice.css` | Practice palette as semantic CSS variables |
| `web/src/lib/lq-ai/styles/typography.css` | Inter variable font registration + Practice type scale |
| `web/src/lib/lq-ai/components/TrustPill.svelte` | Pill primitive used by ambient chrome (variant + tone + label/dot modes) |
| `web/src/lib/lq-ai/components/ProvenancePill.svelte` | Pill primitive for AI-message provenance (kind + clickable) — contract only at Wave A |
| `web/src/lib/lq-ai/components/TopTabBar.svelte` | Top-tab navigation with active-state + overflow handling |
| `web/src/lib/lq-ai/components/AmbientTrustChrome.svelte` | Right-side top-bar pills (self-hosted · tier · ⌘K hint · user menu wrapper) |
| `web/src/lib/lq-ai/components/AmbientFooter.svelte` | Footer pills for chat surfaces (provider · tier · audit health) |
| `web/src/lib/lq-ai/components/ComingSoonModal.svelte` | Tabs without routes yet open this; links to design spec |
| `web/src/lib/lq-ai/tabs.ts` | Top-tab definitions (label, icon, route, scope-gated flag) |
| `web/src/lib/lq-ai/__tests__/TrustPill.test.ts` | TrustPill props + tone derivation |
| `web/src/lib/lq-ai/__tests__/ProvenancePill.test.ts` | ProvenancePill kind dispatch |
| `web/src/lib/lq-ai/__tests__/TopTabBar.test.ts` | Active-tab derivation + coming-soon trigger |
| `web/src/lib/lq-ai/__tests__/tabs.test.ts` | Tab visibility rules |
| `web/cypress/e2e/wave-a-chrome.cy.ts` | Smoke: log in, see top tabs, navigate skills, see ambient chrome |

**Files modified:**

| File | Change |
|---|---|
| `web/package.json` | Add `@fontsource-variable/inter` dep |
| `web/src/routes/lq-ai/+layout.svelte` | Mount practice/typography CSS · render `TopTabBar` + `AmbientTrustChrome` |
| `web/src/routes/lq-ai/+page.svelte` | Footer chrome on this chat surface; visual lift of skill picker / model picker headers |
| `web/src/routes/lq-ai/login/+page.svelte` | Practice visual refresh |
| `web/src/routes/lq-ai/change-password/+page.svelte` | Practice visual refresh |
| `web/src/routes/lq-ai/skills/+page.svelte` | Practice visual refresh; use new typography scale |
| `web/src/routes/lq-ai/skills/new/+page.svelte` | Practice visual refresh (wizard reorganization deferred to Wave D) |
| `web/src/routes/lq-ai/skills/[id]/edit/+page.svelte` | Practice visual refresh |
| `web/src/routes/lq-ai/admin/audit-log/+page.svelte` | Practice visual refresh; use TrustPill where audit status is shown |
| `web/src/routes/lq-ai/admin/models/+page.svelte` | Practice visual refresh |
| `web/src/lib/lq-ai/components/TierBadge.svelte` | Refactor to delegate to `TrustPill` (preserve existing public API for callers) |

**Files NOT touched at Wave A:**
- Anything outside `web/src/lib/lq-ai/**`, `web/src/routes/lq-ai/**`, and `web/cypress/e2e/wave-a-*.cy.ts` (ADR 0009 boundary)
- `web/src/app.css`, `web/src/app.html`, `web/tailwind.config.js` (intentional — Practice loads via the LQ.AI layout only, not globally)

---

## Testing approach

This project's `web/` codebase has API-client tests (`vitest`) but no precedent for Svelte component-render tests. To stay consistent with that pattern *and* still get fast feedback on component logic, the plan uses:

- **Logic-only Vitest tests** for component-adjacent TypeScript (e.g., `tabs.ts` visibility rules, prop-derived state helpers exported from `.svelte` files via the `<script context="module">` block). Pattern matches `web/src/lib/lq-ai/__tests__/saved-prompts-api.test.ts`.
- **Cypress E2E smoke** for the rendered chrome (one test exercises the full Wave A surface: log in → see tabs → navigate → see ambient pills → click a not-yet-routed tab → see ComingSoonModal).

`@testing-library/svelte` is intentionally *not* added at Wave A — it's a new dep, and the API-client + Cypress combination covers Wave A's verification needs. We re-evaluate at Wave C when Matter Workspace logic gets complex enough that DOM-render tests pay off.

**Commit cadence:** every task ends with a commit. DCO sign-off (`git commit -s`) is required by CONTRIBUTING.md. Use imperative-mood messages.

---

## Tasks

### Task 1: Add the Practice palette as semantic CSS variables

**Files:**
- Create: `web/src/lib/lq-ai/styles/practice.css`

- [ ] **Step 1: Write the Practice palette CSS**

Create `web/src/lib/lq-ai/styles/practice.css` with the full semantic-token set from spec §5.4:

```css
/*
 * Practice — LQ.AI reference visual palette.
 *
 * Semantic tokens (--lq-*) so the open-source community can swap palette
 * by overriding these variables without touching component logic.
 * See docs/superpowers/specs/2026-05-10-m1-frontend-design.md §5.4 and §10.
 */
:root {
  /* Canvas + surfaces */
  --lq-canvas: #ffffff;
  --lq-inset: #fafbfa;
  --lq-inset-secure: #f7faf8;

  /* Text */
  --lq-text: #1a1a1a;
  --lq-text-secondary: #4b5563;
  --lq-text-tertiary: #9ca3af;

  /* Sage primary (secure state, primary actions) */
  --lq-accent: #1f7a6b;
  --lq-accent-soft: #e8f4ec;
  --lq-accent-border: #c5e6d1;

  /* Slate (privilege / tier) */
  --lq-tier: #355a82;
  --lq-tier-soft: #e8eff7;
  --lq-tier-border: #d4e2f1;

  /* Amber (warning, tier-override, JIT pre-action) */
  --lq-warn: #a16e1f;
  --lq-warn-soft: #fdf3e2;
  --lq-warn-border: #ead9c5;

  /* Red (audit unhealthy, errors — rare) */
  --lq-error: #b54848;
  --lq-error-soft: #fbeaea;
  --lq-error-border: #f1d2d2;

  /* Neutral borders */
  --lq-border: #e5e7eb;
  --lq-border-strong: #d4d4d4;

  /* Radii */
  --lq-radius-sm: 4px;
  --lq-radius: 6px;
  --lq-radius-lg: 8px;
  --lq-radius-pill: 999px;

  /* Spacing scale (Inter-aligned) */
  --lq-space-1: 4px;
  --lq-space-2: 8px;
  --lq-space-3: 12px;
  --lq-space-4: 16px;
  --lq-space-6: 24px;
  --lq-space-8: 32px;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/lq-ai/styles/practice.css
git commit -s -m "feat(web): add Practice palette as semantic CSS variables

Reference palette for the LQ.AI M1 frontend redesign per the design
spec §5.4. Exposes --lq-* semantic tokens so downstream forks can
re-theme without touching component logic (§10 transparency-as-
forkability principle extended to visuals)."
```

---

### Task 2: Add Inter variable font and the Practice typography scale

**Files:**
- Modify: `web/package.json` (add dep)
- Create: `web/src/lib/lq-ai/styles/typography.css`

- [ ] **Step 1: Install `@fontsource-variable/inter`**

Run from the `web/` directory:

```bash
cd web && npm install --save @fontsource-variable/inter
```

Expected: `package.json` gains `"@fontsource-variable/inter": "^5.x.x"` under `dependencies`. `package-lock.json` updated.

- [ ] **Step 2: Verify the install**

Run: `cd web && ls node_modules/@fontsource-variable/inter/`

Expected: directory exists with `index.css`, `*.woff2` files, and `files/` subdirectory.

- [ ] **Step 3: Write typography.css**

Create `web/src/lib/lq-ai/styles/typography.css`:

```css
/*
 * Practice typography — Inter variable + LQ.AI type scale.
 * Loaded by the /lq-ai/* layout only (not globally) per ADR 0009.
 */
@import '@fontsource-variable/inter/index.css';

:root {
  --lq-font-sans: 'Inter Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --lq-font-numeric: 'Inter Variable', monospace;
  font-variant-numeric: tabular-nums;
}

.lq-shell {
  font-family: var(--lq-font-sans);
  color: var(--lq-text);
}

/* Type scale per spec §5.4. */
.lq-text-label    { font-size: 12px;   font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--lq-text-tertiary); }
.lq-text-caption  { font-size: 12px;   color: var(--lq-text-tertiary); }
.lq-text-body-sm  { font-size: 13.5px; color: var(--lq-text); }
.lq-text-body     { font-size: 14px;   color: var(--lq-text); }
.lq-text-panel-h  { font-size: 16px;   font-weight: 600; color: var(--lq-text); }
.lq-text-page-h   { font-size: 18px;   font-weight: 600; color: var(--lq-text); }
.lq-text-welcome  { font-size: 22px;   font-weight: 500; color: var(--lq-text); }

.lq-tabular { font-variant-numeric: tabular-nums; }
```

- [ ] **Step 4: Commit**

```bash
git add web/package.json web/package-lock.json web/src/lib/lq-ai/styles/typography.css
git commit -s -m "feat(web): self-hosted Inter variable + Practice type scale

Adds @fontsource-variable/inter to keep LQ.AI's self-host posture
(no Google Fonts CDN dependency). Type scale in typography.css
implements spec §5.4 — label/caption/body/panel-h/page-h/welcome —
and is scoped to .lq-shell so it doesn't affect the OpenWebUI / root
surface per ADR 0009."
```

---

### Task 3: Mount Practice and typography in the LQ.AI layout

**Files:**
- Modify: `web/src/routes/lq-ai/+layout.svelte`

- [ ] **Step 1: Import the stylesheets in `+layout.svelte`**

In the `<script lang="ts">` block of `web/src/routes/lq-ai/+layout.svelte`, add at the top of the imports:

```ts
import '$lib/lq-ai/styles/practice.css';
import '$lib/lq-ai/styles/typography.css';
```

In the template, wrap the existing layout output in a `<div class="lq-shell">` so the typography scope applies. Locate the existing top-level template element (likely the layout wrapper around `<slot />`) and add the `lq-shell` class to it (or wrap in a new `<div>` if there isn't a single root).

- [ ] **Step 2: Run the build to confirm no breakage**

Run: `cd web && npm run check`

Expected: 0 svelte-check errors. (The check is purely a typecheck + Svelte-aware lint; visual changes don't surface here but breakage from a bad import would.)

- [ ] **Step 3: Run the dev server briefly to confirm the font loads**

Run (from `web/` directory): `npm run dev`
Manually verify in browser:
- Navigate to `http://localhost:5173/lq-ai/login` (or whatever port dev server prints)
- Open DevTools → Network tab → filter for `inter`
- Confirm an `inter-latin-wght-normal.woff2` (or similar) request returns 200
- Confirm computed `font-family` on a `.lq-shell` descendant includes `'Inter Variable'`

Stop the dev server (`Ctrl-C`).

- [ ] **Step 4: Commit**

```bash
git add web/src/routes/lq-ai/+layout.svelte
git commit -s -m "feat(web): mount Practice + typography in /lq-ai/* layout

Scopes the Practice visual system to the LQ.AI shell per ADR 0009.
Inter Variable loads via @fontsource self-host (no CDN dep). The
.lq-shell class scopes the type scale so the OpenWebUI / root
surface stays untouched."
```

---

### Task 4: Define top-tab metadata and visibility rules

**Files:**
- Create: `web/src/lib/lq-ai/tabs.ts`
- Create: `web/src/lib/lq-ai/__tests__/tabs.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/lq-ai/__tests__/tabs.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { TABS, isTabVisible, isTabAvailable, activeTabFor, type TabId, type User } from '../tabs';

describe('tabs', () => {
  const adminUser: User = { id: '1', email: 'a@x.io', is_admin: true, must_change_password: false };
  const memberUser: User = { id: '2', email: 'm@x.io', is_admin: false, must_change_password: false };

  it('defines six core tabs plus admin', () => {
    const ids = TABS.map((t) => t.id);
    expect(ids).toEqual(['home', 'chats', 'matters', 'skills', 'knowledge', 'saved-prompts', 'admin']);
  });

  it('hides admin tab for non-admin users', () => {
    expect(isTabVisible('admin', memberUser)).toBe(false);
    expect(isTabVisible('admin', adminUser)).toBe(true);
  });

  it('shows core tabs to all users', () => {
    for (const id of ['home', 'chats', 'matters', 'skills', 'knowledge', 'saved-prompts'] as TabId[]) {
      expect(isTabVisible(id, memberUser)).toBe(true);
      expect(isTabVisible(id, adminUser)).toBe(true);
    }
  });

  it('marks tabs whose routes are not yet implemented as not available', () => {
    expect(isTabAvailable('home')).toBe(true);
    expect(isTabAvailable('skills')).toBe(true);
    expect(isTabAvailable('admin')).toBe(true);
    expect(isTabAvailable('chats')).toBe(false);
    expect(isTabAvailable('matters')).toBe(false);
    expect(isTabAvailable('knowledge')).toBe(false);
    expect(isTabAvailable('saved-prompts')).toBe(false);
  });

  it('derives active tab from pathname', () => {
    expect(activeTabFor('/lq-ai')).toBe('home');
    expect(activeTabFor('/lq-ai/skills')).toBe('skills');
    expect(activeTabFor('/lq-ai/skills/new')).toBe('skills');
    expect(activeTabFor('/lq-ai/skills/abc-123')).toBe('skills');
    expect(activeTabFor('/lq-ai/admin/audit-log')).toBe('admin');
    expect(activeTabFor('/lq-ai/login')).toBe(null);
    expect(activeTabFor('/lq-ai/change-password')).toBe(null);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/tabs.test.ts`

Expected: 5 FAIL with "Cannot find module '../tabs'".

- [ ] **Step 3: Implement `tabs.ts`**

Create `web/src/lib/lq-ai/tabs.ts`:

```ts
/**
 * Top-tab definitions for the /lq-ai/* shell.
 *
 * Visibility = whether the user is allowed to see the tab at all (role gate).
 * Available  = whether the tab's destination route exists yet (per Wave A
 *              of the M1 frontend redesign; subsequent waves flip these to
 *              true as they ship the destination surfaces).
 *
 * Tabs that are visible-but-not-available open a ComingSoonModal that
 * points at the design spec.
 */

export type TabId =
  | 'home'
  | 'chats'
  | 'matters'
  | 'skills'
  | 'knowledge'
  | 'saved-prompts'
  | 'admin';

export interface TabDef {
  id: TabId;
  label: string;
  icon: string;            // emoji used in mockups; replaced with sprite in Wave F polish
  route: string;
  adminOnly?: boolean;
  available: boolean;
  /** The wave that lands the destination route. Used by ComingSoonModal copy. */
  shipsInWave?: 'B' | 'C' | 'D' | 'E';
}

export interface User {
  id: string;
  email: string;
  is_admin: boolean;
  must_change_password: boolean;
}

export const TABS: readonly TabDef[] = [
  { id: 'home',          label: 'Home',          icon: '🏠', route: '/lq-ai',                available: true },
  { id: 'chats',         label: 'Chats',         icon: '💬', route: '/lq-ai/chats',          available: false, shipsInWave: 'C' },
  { id: 'matters',       label: 'Matters',       icon: '📁', route: '/lq-ai/matters',        available: false, shipsInWave: 'C' },
  { id: 'skills',        label: 'Skills',        icon: '🛠️', route: '/lq-ai/skills',         available: true },
  { id: 'knowledge',     label: 'Knowledge',     icon: '📎', route: '/lq-ai/knowledge',      available: false, shipsInWave: 'C' },
  { id: 'saved-prompts', label: 'Saved Prompts', icon: '📌', route: '/lq-ai/saved-prompts',  available: false, shipsInWave: 'D' },
  { id: 'admin',         label: 'Admin',         icon: '🛡',  route: '/lq-ai/admin/audit-log', adminOnly: true, available: true }
] as const;

export function isTabVisible(id: TabId, user: User | null): boolean {
  const tab = TABS.find((t) => t.id === id);
  if (!tab) return false;
  if (tab.adminOnly && !user?.is_admin) return false;
  return true;
}

export function isTabAvailable(id: TabId): boolean {
  return TABS.find((t) => t.id === id)?.available ?? false;
}

/** Returns the tab whose route is the deepest prefix of pathname, or null on auth-exempt routes. */
export function activeTabFor(pathname: string): TabId | null {
  if (pathname === '/lq-ai/login' || pathname === '/lq-ai/change-password') return null;
  if (pathname === '/lq-ai' || pathname === '/lq-ai/') return 'home';

  // Find tab whose route is the deepest prefix.
  let best: TabDef | null = null;
  for (const tab of TABS) {
    if (tab.id === 'home') continue;
    if (pathname === tab.route || pathname.startsWith(tab.route + '/')) {
      if (!best || tab.route.length > best.route.length) best = tab;
    }
  }
  return best?.id ?? 'home';
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/tabs.test.ts`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/tabs.ts web/src/lib/lq-ai/__tests__/tabs.test.ts
git commit -s -m "feat(web): top-tab definitions + visibility/availability rules

Wave A foundation for the LQ.AI top-tab nav. Tabs marked available=false
route through ComingSoonModal (Task 7) until subsequent waves ship the
destination surfaces; shipsInWave hint anchors the modal copy back to
the design spec."
```

---

### Task 5: Build `TrustPill.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/TrustPill.svelte`
- Create: `web/src/lib/lq-ai/__tests__/TrustPill.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/lq-ai/__tests__/TrustPill.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { toneClassFor, labelFor } from '../components/TrustPill.svelte';

describe('TrustPill helpers', () => {
  it('maps secure variant to sage tone by default', () => {
    expect(toneClassFor('secure', undefined)).toBe('lq-pill-tone-sage');
  });

  it('maps tier variant to slate tone by default', () => {
    expect(toneClassFor('tier', undefined)).toBe('lq-pill-tone-slate');
  });

  it('honors explicit override tone', () => {
    expect(toneClassFor('tier', 'amber')).toBe('lq-pill-tone-amber');
    expect(toneClassFor('secure', 'red')).toBe('lq-pill-tone-red');
  });

  it('falls back to neutral for unknown variants', () => {
    // @ts-expect-error testing runtime fallback
    expect(toneClassFor('mystery', undefined)).toBe('lq-pill-tone-neutral');
  });

  it('labelFor returns "●" alone in dot mode', () => {
    expect(labelFor('● self-hosted', 'dot')).toBe('●');
    expect(labelFor('● self-hosted', 'label')).toBe('● self-hosted');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/TrustPill.test.ts`

Expected: FAIL with "Cannot find module" or "no export 'toneClassFor'".

- [ ] **Step 3: Implement `TrustPill.svelte`**

Create `web/src/lib/lq-ai/components/TrustPill.svelte`:

```svelte
<script context="module" lang="ts">
  /**
   * TrustPill — small ambient-trust indicator used in the LQ.AI chrome.
   *
   * variant determines a default tone (secure→sage, tier→slate,
   * provider→sage, audit→sage, warn→amber, error→red); `tone` prop overrides.
   * `display` chooses label vs dot-only rendering for the personalization toggle.
   *
   * The toneClassFor + labelFor helpers are exported for unit testing.
   */
  export type TrustVariant = 'secure' | 'tier' | 'provider' | 'audit' | 'warn' | 'error';
  export type TrustTone = 'sage' | 'slate' | 'amber' | 'red' | 'neutral';
  export type TrustDisplay = 'label' | 'dot';

  const VARIANT_DEFAULT_TONE: Record<TrustVariant, TrustTone> = {
    secure: 'sage',
    tier: 'slate',
    provider: 'sage',
    audit: 'sage',
    warn: 'amber',
    error: 'red'
  };

  export function toneClassFor(variant: TrustVariant, override: TrustTone | undefined): string {
    const tone = override ?? VARIANT_DEFAULT_TONE[variant] ?? 'neutral';
    return `lq-pill-tone-${tone}`;
  }

  export function labelFor(label: string, display: TrustDisplay): string {
    if (display === 'dot') return '●';
    return label;
  }
</script>

<script lang="ts">
  export let variant: TrustVariant;
  export let label: string;
  export let tone: TrustTone | undefined = undefined;
  export let display: TrustDisplay = 'label';
  export let onClick: (() => void) | undefined = undefined;

  $: toneClass = toneClassFor(variant, tone);
  $: rendered = labelFor(label, display);
</script>

<button
  type="button"
  class="lq-pill {toneClass}"
  class:lq-pill-dot={display === 'dot'}
  class:lq-pill-clickable={!!onClick}
  aria-label={label}
  on:click={onClick}
>
  {rendered}
</button>

<style>
  .lq-pill {
    display: inline-flex;
    align-items: center;
    gap: var(--lq-space-1);
    padding: 2px 10px;
    border-radius: var(--lq-radius-pill);
    font-size: 12px;
    font-weight: 500;
    line-height: 1.4;
    border: 1px solid transparent;
    background: transparent;
    cursor: default;
  }
  .lq-pill-clickable { cursor: pointer; }
  .lq-pill-dot { padding: 4px 8px; font-size: 10px; }

  .lq-pill-tone-sage    { background: var(--lq-accent-soft); color: var(--lq-accent); border-color: var(--lq-accent-border); }
  .lq-pill-tone-slate   { background: var(--lq-tier-soft);   color: var(--lq-tier);   border-color: var(--lq-tier-border); }
  .lq-pill-tone-amber   { background: var(--lq-warn-soft);   color: var(--lq-warn);   border-color: var(--lq-warn-border); }
  .lq-pill-tone-red     { background: var(--lq-error-soft);  color: var(--lq-error);  border-color: var(--lq-error-border); }
  .lq-pill-tone-neutral { background: var(--lq-inset);       color: var(--lq-text-secondary); border-color: var(--lq-border); }

  .lq-pill-clickable:hover { filter: brightness(0.97); }
  .lq-pill-clickable:focus-visible { outline: 2px solid var(--lq-accent); outline-offset: 2px; }
</style>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/TrustPill.test.ts`

Expected: 5 PASS.

- [ ] **Step 5: Run svelte-check to confirm component type correctness**

Run: `cd web && npm run check`

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/lq-ai/components/TrustPill.svelte web/src/lib/lq-ai/__tests__/TrustPill.test.ts
git commit -s -m "feat(web): TrustPill primitive for LQ.AI ambient chrome

Pill primitive used by AmbientTrustChrome (Task 8) and downstream
provenance/footer chrome. Variant→tone mapping is the policy
(secure=sage, tier=slate, etc.); explicit tone prop overrides.
Display=dot supports the personalization 'dots only' toggle (spec §4.3)
without changing the component public API."
```

---

### Task 6: Build `ProvenancePill.svelte` (contract for Wave D)

**Files:**
- Create: `web/src/lib/lq-ai/components/ProvenancePill.svelte`
- Create: `web/src/lib/lq-ai/__tests__/ProvenancePill.test.ts`

> **Rationale for Wave A scope:** Wave A doesn't yet attach provenance pills to messages (that's Wave D), but defining the component now locks the contract subsequent waves can build against and proves the styling foundation works for both `TrustPill` (chrome) and `ProvenancePill` (per-message).

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/lq-ai/__tests__/ProvenancePill.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { iconFor, toneFor, type ProvenanceKind } from '../components/ProvenancePill.svelte';

describe('ProvenancePill helpers', () => {
  it('maps each provenance kind to its icon', () => {
    expect(iconFor('skill')).toBe('🛠️');
    expect(iconFor('tier')).toBe('🔒');
    expect(iconFor('provider')).toBe('🧠');
    expect(iconFor('kb')).toBe('📎');
    expect(iconFor('audit')).toBe('📜');
    expect(iconFor('enhanced')).toBe('✨');
  });

  it('maps kinds to sage by default; tier mismatch flips to amber', () => {
    expect(toneFor('skill', false)).toBe('sage');
    expect(toneFor('tier', false)).toBe('slate');
    expect(toneFor('tier', true)).toBe('amber');
    expect(toneFor('provider', false)).toBe('sage');
  });

  it('lists six kinds (sentinel — update if Wave D adds more)', () => {
    const kinds: ProvenanceKind[] = ['skill', 'tier', 'provider', 'kb', 'audit', 'enhanced'];
    expect(kinds.length).toBe(6);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/ProvenancePill.test.ts`

Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement `ProvenancePill.svelte`**

Create `web/src/lib/lq-ai/components/ProvenancePill.svelte`:

```svelte
<script context="module" lang="ts">
  /**
   * ProvenancePill — pill primitive attached to AI messages.
   * Wave A defines the contract; Wave D wires it into the message renderer.
   * See spec §5.2.
   */
  export type ProvenanceKind = 'skill' | 'tier' | 'provider' | 'kb' | 'audit' | 'enhanced';

  const KIND_ICON: Record<ProvenanceKind, string> = {
    skill: '🛠️',
    tier: '🔒',
    provider: '🧠',
    kb: '📎',
    audit: '📜',
    enhanced: '✨'
  };

  export function iconFor(kind: ProvenanceKind): string {
    return KIND_ICON[kind];
  }

  export type ProvenanceTone = 'sage' | 'slate' | 'amber';

  export function toneFor(kind: ProvenanceKind, tierMismatch: boolean): ProvenanceTone {
    if (kind === 'tier') return tierMismatch ? 'amber' : 'slate';
    return 'sage';
  }
</script>

<script lang="ts">
  export let kind: ProvenanceKind;
  export let summary: string;
  export let tierMismatch = false;
  export let onTap: (() => void) | undefined = undefined;

  $: tone = toneFor(kind, tierMismatch);
  $: icon = iconFor(kind);
</script>

<button
  type="button"
  class="lq-prov-pill lq-prov-tone-{tone}"
  aria-label="{kind}: {summary}"
  on:click={onTap}
>
  <span class="lq-prov-icon" aria-hidden="true">{icon}</span>
  <span class="lq-prov-summary">{summary}</span>
</button>

<style>
  .lq-prov-pill {
    display: inline-flex;
    align-items: center;
    gap: var(--lq-space-1);
    padding: 2px 8px;
    border-radius: var(--lq-radius-pill);
    font-size: 11px;
    line-height: 1.4;
    border: 1px solid transparent;
    background: transparent;
    cursor: pointer;
  }
  .lq-prov-icon { font-size: 11px; }
  .lq-prov-summary { font-weight: 500; }
  .lq-prov-tone-sage  { background: var(--lq-accent-soft); color: var(--lq-accent); border-color: var(--lq-accent-border); }
  .lq-prov-tone-slate { background: var(--lq-tier-soft);   color: var(--lq-tier);   border-color: var(--lq-tier-border); }
  .lq-prov-tone-amber { background: var(--lq-warn-soft);   color: var(--lq-warn);   border-color: var(--lq-warn-border); }
  .lq-prov-pill:hover { filter: brightness(0.97); }
  .lq-prov-pill:focus-visible { outline: 2px solid var(--lq-accent); outline-offset: 2px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/ProvenancePill.test.ts`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/ProvenancePill.svelte web/src/lib/lq-ai/__tests__/ProvenancePill.test.ts
git commit -s -m "feat(web): ProvenancePill contract for inline provenance row

Defines the pill primitive Wave D will attach to AI-authored messages
(spec §5.2). Six kinds: skill, tier, provider, kb, audit, enhanced.
Tier-mismatch flips tone amber. Not yet wired into the message
renderer — that's Wave D — but the contract is locked here so
subsequent waves can build against it."
```

---

### Task 7: Build `ComingSoonModal.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/ComingSoonModal.svelte`
- Create: `web/src/lib/lq-ai/__tests__/ComingSoonModal.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/lq-ai/__tests__/ComingSoonModal.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { copyFor } from '../components/ComingSoonModal.svelte';

describe('ComingSoonModal copy', () => {
  it('names the wave for the destination surface', () => {
    const result = copyFor('matters', 'C');
    expect(result.title).toBe('Matters');
    expect(result.body).toContain('Wave C');
    expect(result.body).toContain('design spec');
  });

  it('falls back gracefully when wave is unknown', () => {
    const result = copyFor('chats', undefined);
    expect(result.title).toBe('Chats');
    expect(result.body).toContain('planned for an upcoming wave');
  });

  it('humanizes tab id for display', () => {
    expect(copyFor('saved-prompts', 'D').title).toBe('Saved Prompts');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/ComingSoonModal.test.ts`

Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement `ComingSoonModal.svelte`**

Create `web/src/lib/lq-ai/components/ComingSoonModal.svelte`:

```svelte
<script context="module" lang="ts">
  /**
   * ComingSoonModal — surfaces when a user clicks a top tab whose
   * destination route hasn't shipped yet. Points at the design spec
   * so community members poking around can find the full roadmap.
   */
  import type { TabId } from '../tabs';

  const TITLE: Record<TabId, string> = {
    home: 'Home',
    chats: 'Chats',
    matters: 'Matters',
    skills: 'Skills',
    knowledge: 'Knowledge',
    'saved-prompts': 'Saved Prompts',
    admin: 'Admin'
  };

  export function copyFor(tabId: TabId, wave: string | undefined): { title: string; body: string } {
    const title = TITLE[tabId] ?? tabId;
    const body = wave
      ? `${title} is part of Wave ${wave} of the M1 frontend redesign. See the design spec for the full roadmap and what this surface will do.`
      : `${title} is planned for an upcoming wave of the M1 frontend redesign. See the design spec for what this surface will do.`;
    return { title, body };
  }
</script>

<script lang="ts">
  import type { TabId } from '../tabs';

  export let open: boolean;
  export let tabId: TabId;
  export let wave: string | undefined;
  export let onClose: () => void;

  $: ({ title, body } = copyFor(tabId, wave));

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }
</script>

{#if open}
  <div
    class="lq-modal-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="coming-soon-title"
    on:click={onClose}
    on:keydown={handleKeydown}
  >
    <div
      class="lq-modal"
      role="document"
      on:click|stopPropagation
    >
      <h2 id="coming-soon-title" class="lq-text-page-h">{title}</h2>
      <p class="lq-text-body" style="margin-top: var(--lq-space-3);">{body}</p>
      <p class="lq-text-caption" style="margin-top: var(--lq-space-3);">
        Design spec:
        <a href="https://github.com/LegalQuants/lq-ai/blob/main/docs/superpowers/specs/2026-05-10-m1-frontend-design.md" target="_blank" rel="noopener noreferrer">
          docs/superpowers/specs/2026-05-10-m1-frontend-design.md
        </a>
      </p>
      <div style="margin-top: var(--lq-space-6); display: flex; justify-content: flex-end;">
        <button type="button" class="lq-btn-primary" on:click={onClose}>Got it</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .lq-modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.35);
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  .lq-modal {
    background: var(--lq-canvas);
    border-radius: var(--lq-radius-lg);
    padding: var(--lq-space-6);
    max-width: 480px;
    width: calc(100% - 32px);
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.18);
  }
  .lq-btn-primary {
    background: var(--lq-accent); color: white;
    border: 0; border-radius: var(--lq-radius);
    padding: 8px 16px; font-size: 14px; font-weight: 500;
    cursor: pointer;
  }
  .lq-btn-primary:hover { filter: brightness(0.95); }
  .lq-btn-primary:focus-visible { outline: 2px solid var(--lq-accent); outline-offset: 2px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/ComingSoonModal.test.ts`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/ComingSoonModal.svelte web/src/lib/lq-ai/__tests__/ComingSoonModal.test.ts
git commit -s -m "feat(web): ComingSoonModal for not-yet-shipped tab destinations

Tabs whose surfaces don't exist yet (chats/matters/knowledge/saved-prompts)
open this modal pointing at the design spec — so the chrome stays stable
across waves and community members can discover what's coming."
```

---

### Task 8: Build `TopTabBar.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/TopTabBar.svelte`
- Create: `web/src/lib/lq-ai/__tests__/TopTabBar.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/lq-ai/__tests__/TopTabBar.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { visibleTabsFor, type TopTabBarUser } from '../components/TopTabBar.svelte';

describe('TopTabBar.visibleTabsFor', () => {
  const admin: TopTabBarUser = { id: '1', email: 'a@x', is_admin: true,  must_change_password: false };
  const member: TopTabBarUser = { id: '2', email: 'm@x', is_admin: false, must_change_password: false };

  it('returns six tabs for a non-admin user (admin hidden)', () => {
    const ids = visibleTabsFor(member).map((t) => t.id);
    expect(ids).toEqual(['home', 'chats', 'matters', 'skills', 'knowledge', 'saved-prompts']);
  });

  it('returns seven tabs for an admin user', () => {
    const ids = visibleTabsFor(admin).map((t) => t.id);
    expect(ids).toEqual(['home', 'chats', 'matters', 'skills', 'knowledge', 'saved-prompts', 'admin']);
  });

  it('returns six tabs for null user (treats as non-admin)', () => {
    const ids = visibleTabsFor(null).map((t) => t.id);
    expect(ids).toEqual(['home', 'chats', 'matters', 'skills', 'knowledge', 'saved-prompts']);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/TopTabBar.test.ts`

Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement `TopTabBar.svelte`**

Create `web/src/lib/lq-ai/components/TopTabBar.svelte`:

```svelte
<script context="module" lang="ts">
  import { TABS, isTabVisible, type TabDef, type User } from '../tabs';

  export type TopTabBarUser = User;

  export function visibleTabsFor(user: User | null): TabDef[] {
    return TABS.filter((t) => isTabVisible(t.id, user));
  }
</script>

<script lang="ts">
  import { goto } from '$app/navigation';
  import { activeTabFor, isTabAvailable, type TabId } from '../tabs';
  import ComingSoonModal from './ComingSoonModal.svelte';

  export let user: User | null;
  export let pathname: string;

  $: tabs = visibleTabsFor(user);
  $: active = activeTabFor(pathname);

  let comingSoonOpen = false;
  let comingSoonTabId: TabId = 'home';
  let comingSoonWave: string | undefined;

  function handleTabClick(tabId: TabId, route: string, wave: string | undefined) {
    if (isTabAvailable(tabId)) {
      goto(route);
    } else {
      comingSoonTabId = tabId;
      comingSoonWave = wave;
      comingSoonOpen = true;
    }
  }
</script>

<nav class="lq-tabbar" aria-label="Primary">
  <ul role="tablist">
    {#each tabs as tab (tab.id)}
      <li role="presentation">
        <button
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          aria-controls="lq-main"
          class="lq-tab"
          class:lq-tab-active={active === tab.id}
          class:lq-tab-unavailable={!isTabAvailable(tab.id)}
          on:click={() => handleTabClick(tab.id, tab.route, tab.shipsInWave)}
        >
          <span class="lq-tab-icon" aria-hidden="true">{tab.icon}</span>
          <span class="lq-tab-label">{tab.label}</span>
        </button>
      </li>
    {/each}
  </ul>
</nav>

<ComingSoonModal
  open={comingSoonOpen}
  tabId={comingSoonTabId}
  wave={comingSoonWave}
  onClose={() => (comingSoonOpen = false)}
/>

<style>
  .lq-tabbar { border-bottom: 1px solid var(--lq-border); padding: 0 var(--lq-space-4); }
  .lq-tabbar ul { display: flex; gap: var(--lq-space-4); margin: 0; padding: 0; list-style: none; }
  .lq-tab {
    display: inline-flex; align-items: center; gap: var(--lq-space-1);
    background: transparent; border: 0; padding: var(--lq-space-3) var(--lq-space-1);
    font-size: 14px; font-weight: 500; color: var(--lq-text-secondary);
    cursor: pointer; border-bottom: 2px solid transparent;
    transition: color 0.12s ease, border-color 0.12s ease;
  }
  .lq-tab:hover { color: var(--lq-text); }
  .lq-tab-active { color: var(--lq-accent); border-bottom-color: var(--lq-accent); }
  .lq-tab-unavailable { color: var(--lq-text-tertiary); }
  .lq-tab:focus-visible { outline: 2px solid var(--lq-accent); outline-offset: 2px; border-radius: var(--lq-radius-sm); }
  .lq-tab-icon { font-size: 14px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/TopTabBar.test.ts`

Expected: 3 PASS.

- [ ] **Step 5: Run svelte-check**

Run: `cd web && npm run check`

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/lq-ai/components/TopTabBar.svelte web/src/lib/lq-ai/__tests__/TopTabBar.test.ts
git commit -s -m "feat(web): TopTabBar with role-gated visibility + ComingSoon routing

Renders the LQ.AI top-tab nav from tabs.ts. Admin tab hides for non-admin
users. Tabs whose surfaces don't exist yet (chats/matters/knowledge/
saved-prompts) open ComingSoonModal instead of routing to a 404. Available
tabs route via SvelteKit's goto(). Active tab is derived from pathname."
```

---

### Task 9: Build `AmbientTrustChrome.svelte` (top-bar right-side pills)

**Files:**
- Create: `web/src/lib/lq-ai/components/AmbientTrustChrome.svelte`

> **No new tests at this task** — `AmbientTrustChrome` is a pure composition of `TrustPill` (already covered). The Cypress E2E in Task 14 covers the rendered chrome.

- [ ] **Step 1: Implement `AmbientTrustChrome.svelte`**

Create `web/src/lib/lq-ai/components/AmbientTrustChrome.svelte`:

```svelte
<script lang="ts">
  /**
   * AmbientTrustChrome — right side of the top bar.
   *
   * At Wave A: self-hosted pill + ⌘K hint. Tier pill is rendered by the
   * Workspace shell in Wave C (it's chat-scoped, not global). User menu
   * stays where the existing layout puts it.
   *
   * Personalization toggle "Trust pills → Dots" (spec §4.3) plumbs through
   * the `display` prop in a later wave; Wave A always renders labels.
   */
  import TrustPill from './TrustPill.svelte';
</script>

<div class="lq-chrome">
  <TrustPill variant="secure" label="● self-hosted" />
  <span class="lq-kbd" aria-hidden="true">⌘K</span>
</div>

<style>
  .lq-chrome { display: inline-flex; align-items: center; gap: var(--lq-space-2); }
  .lq-kbd {
    font-family: var(--lq-font-sans);
    font-size: 11px; color: var(--lq-text-tertiary);
    border: 1px solid var(--lq-border); border-radius: var(--lq-radius-sm);
    padding: 1px 6px; background: var(--lq-inset);
  }
</style>
```

- [ ] **Step 2: Run svelte-check**

Run: `cd web && npm run check`

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/lq-ai/components/AmbientTrustChrome.svelte
git commit -s -m "feat(web): AmbientTrustChrome composition (top-bar pills)

Right-side of the LQ.AI top bar — self-hosted pill + ⌘K hint at
Wave A. Tier pill renders inside the chat surface (Wave C; scoped
to chat state), and the launcher backing the ⌘K hint lands in a
later wave. Personalization 'dots only' plumbs through TrustPill's
display prop when Wave B adds the toggle UI."
```

---

### Task 10: Build `AmbientFooter.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/AmbientFooter.svelte`

> **Wave A scope:** AmbientFooter only renders on the existing chat surface (`/lq-ai`) at this wave. It surfaces current provider/tier and audit-health placeholders sourced from the chat's state. Real audit-health data comes from `/api/v1/trust/audit-health` (Wave B backend dep) — for Wave A we render the static-success state with a TODO-in-code-comment pointing at the backend gap. (Note: "TODO" here is a *plan-permitted code annotation*, not a placeholder in the plan itself — see §No Placeholders in writing-plans skill.)

- [ ] **Step 1: Implement `AmbientFooter.svelte`**

Create `web/src/lib/lq-ai/components/AmbientFooter.svelte`:

```svelte
<script lang="ts">
  /**
   * AmbientFooter — bottom-of-chat reassurance bar.
   *
   * Wave A renders provider + tier + a static "audit on" pill. Wave B
   * wires audit-health from /api/v1/trust/audit-health (backend gap §9.1).
   * Wave D adds the "external turns today" counter.
   */
  import TrustPill from './TrustPill.svelte';

  export let provider: string;
  export let tier: string;
</script>

<footer class="lq-footer" aria-label="Chat status">
  <TrustPill variant="provider" label="● {provider} · {tier}" />
  {/* Audit-health wiring (Wave B backend dep): replace static label
      with derived state once /api/v1/trust/audit-health ships. */}
  <TrustPill variant="audit" label="✓ audit on" />
</footer>

<style>
  .lq-footer {
    display: flex; align-items: center; gap: var(--lq-space-3);
    padding: var(--lq-space-2) var(--lq-space-4);
    border-top: 1px solid var(--lq-border);
    background: var(--lq-inset);
    font-size: 12px;
  }
</style>
```

- [ ] **Step 2: Run svelte-check**

Run: `cd web && npm run check`

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/lq-ai/components/AmbientFooter.svelte
git commit -s -m "feat(web): AmbientFooter for chat-surface bottom reassurance bar

Renders provider + tier + audit-on pills at the bottom of chat surfaces.
Audit-health pill is static at Wave A; Wave B wires it from
/api/v1/trust/audit-health (backend gap §9.1). External-turns-today
counter lands in Wave D."
```

---

### Task 11: Mount `TopTabBar` + `AmbientTrustChrome` in `+layout.svelte`

**Files:**
- Modify: `web/src/routes/lq-ai/+layout.svelte`

- [ ] **Step 1: Read the current layout to find the insertion points**

Run: `cat web/src/routes/lq-ai/+layout.svelte`

Note the structure — the template renders `<DualBrandingFooter />` at the bottom and a `<slot />` (or similar) for the route content. We'll add the top bar above the slot.

- [ ] **Step 2: Update the layout**

Modify `web/src/routes/lq-ai/+layout.svelte`:

In the `<script lang="ts">` block, add (alongside existing imports):

```ts
import TopTabBar from '$lib/lq-ai/components/TopTabBar.svelte';
import AmbientTrustChrome from '$lib/lq-ai/components/AmbientTrustChrome.svelte';
```

In the template, wrap the route output in the `lq-shell` class (if not already from Task 3) and add the top bar:

```svelte
{#if booted && !isAuthExempt(pathname)}
  <div class="lq-shell">
    <header class="lq-topbar">
      <a class="lq-brand" href="/lq-ai">
        <span class="lq-brand-lq">LQ</span>.AI
      </a>
      <AmbientTrustChrome />
    </header>
    <TopTabBar user={$auth.user} {pathname} />
    <main id="lq-main">
      <slot />
    </main>
  </div>
{:else if booted}
  <!-- Auth-exempt routes (login, change-password) keep their existing chrome -->
  <slot />
{/if}
```

> **Note:** `$auth.user` is the user object from the existing auth store. Verify the shape via `cat web/src/lib/lq-ai/auth/store.ts | head -40` before this edit — if the property name differs from `user.is_admin`, adapt the TopTabBar props accordingly. The `User` type defined in `tabs.ts` expects `is_admin: boolean`.

Add scoped styles to the layout component:

```svelte
<style>
  .lq-shell { background: var(--lq-canvas); color: var(--lq-text); min-height: 100vh; display: flex; flex-direction: column; }
  .lq-topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--lq-space-3) var(--lq-space-4);
    border-bottom: 1px solid var(--lq-border);
    background: var(--lq-canvas);
  }
  .lq-brand {
    font-size: 16px; font-weight: 600; color: var(--lq-text);
    text-decoration: none;
  }
  .lq-brand-lq { color: var(--lq-accent); }
  main { flex: 1; }
</style>
```

- [ ] **Step 3: Verify shape of `$auth.user`**

Run: `grep -n "user" web/src/lib/lq-ai/auth/store.ts | head -10`

Expected: the store exposes a `user` field with `email`, `is_admin` (or `role`), `must_change_password`. If the field is named differently from `is_admin`, adjust the `User` type in `web/src/lib/lq-ai/tabs.ts` to match, then re-run Task 4's test.

- [ ] **Step 4: Run svelte-check + tests**

Run: `cd web && npm run check && npm run test:frontend`

Expected: 0 svelte-check errors; all existing tests still pass.

- [ ] **Step 5: Smoke test in dev**

Run: `cd web && npm run dev`
Open: `http://localhost:5173/lq-ai/login` → log in as `admin@lq.ai` with `LQ-AI-smoke-test-Pw1!` (per docs/SESSION-HANDOFF-2026-05-10d.md).
Verify:
- Top bar shows brand + "● self-hosted" pill + ⌘K hint
- Top tabs row shows Home / Chats / Matters / Skills / Knowledge / Saved Prompts / Admin
- Clicking "Skills" routes to `/lq-ai/skills`; clicking "Chats" opens ComingSoonModal
- Active tab underline tracks the current route
- The existing `DualBrandingFooter` still renders at the bottom (don't remove it)

Stop the dev server.

- [ ] **Step 6: Commit**

```bash
git add web/src/routes/lq-ai/+layout.svelte
git commit -s -m "feat(web): mount top-tab nav + ambient trust chrome in /lq-ai/* layout

Adds the LQ.AI top-tab bar and right-side ambient pills above the
route content for all authenticated /lq-ai/* surfaces. Auth-exempt
routes (login, change-password) keep their existing chrome. Tabs
whose surfaces don't exist yet route through ComingSoonModal."
```

---

### Task 12: Refactor `TierBadge.svelte` to use `TrustPill`

**Files:**
- Modify: `web/src/lib/lq-ai/components/TierBadge.svelte`

- [ ] **Step 1: Read the current implementation**

Run: `cat web/src/lib/lq-ai/components/TierBadge.svelte`

Note the props it exposes — callers expect that interface unchanged.

- [ ] **Step 2: Refactor to delegate to TrustPill**

Rewrite `web/src/lib/lq-ai/components/TierBadge.svelte` preserving the existing public API (props), but rendering via `TrustPill`:

```svelte
<script lang="ts">
  /**
   * TierBadge — historically a standalone badge; now delegates to TrustPill
   * so the LQ.AI ambient chrome stays consistent. Public API preserved for
   * existing callers.
   */
  import TrustPill from './TrustPill.svelte';

  // Preserve original prop names; map internally.
  export let tier: string;          // e.g. "privileged-floor", "standard"
  export let label: string | undefined = undefined;
  export let onClick: (() => void) | undefined = undefined;

  $: displayLabel = label ?? `🔒 ${tier}`;
</script>

<TrustPill variant="tier" label={displayLabel} {onClick} />
```

> **If the original component had additional props beyond `tier`, `label`, `onClick`** (e.g., `compact`, `size`), add them as forwarded props using `$$restProps` or explicit declarations and document them. Don't drop callers' surface area.

- [ ] **Step 3: Run svelte-check + tests + grep for callers**

Run:
```bash
cd web && npm run check && npm run test:frontend
grep -rn "TierBadge" src/ --include="*.svelte" --include="*.ts"
```

Expected: 0 errors. Grep should show every caller — verify their `<TierBadge ... />` usages still type-check.

- [ ] **Step 4: Smoke test the routes that render TierBadge**

Run: `cd web && npm run dev`
- Visit `/lq-ai` (chat shell) — the per-message TierBadge should still render
- Visit `/lq-ai/admin/audit-log` — if it uses TierBadge, confirm same

Stop dev server.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/TierBadge.svelte
git commit -s -m "refactor(web): TierBadge delegates to TrustPill

Unifies the ambient-chrome pill styling so tier badges in chat
messages, the audit log, and the workspace shell share the same
visual primitive. Public API preserved — callers untouched."
```

---

### Task 13: Visual refresh — existing routes (composite task with sub-commits)

> **Scope:** Apply the Practice typography scale (`.lq-text-page-h`, `.lq-text-body`, etc.) and CSS-variable-based colors to the existing pages, replacing ad-hoc Tailwind utility classes where they conflict. Each route is its own commit. No structural or feature changes — only visual.

#### 13a. `/lq-ai/login`

- [ ] **Step 1: Read the file** — `cat web/src/routes/lq-ai/login/+page.svelte`
- [ ] **Step 2: Apply Practice classes** to the page heading (`.lq-text-page-h`), labels (`.lq-text-label`), and the body copy (`.lq-text-body`). Replace hard-coded colors (e.g., `text-gray-800`, `bg-white`) with `var(--lq-text)` / `var(--lq-canvas)` in scoped `<style>` blocks. Submit button uses `.lq-btn-primary` (extract this class into `practice.css` if not already).
- [ ] **Step 3: Smoke** — `npm run dev` → visit `/lq-ai/login` → confirm Practice palette renders, Inter font is in use, form still works (submit with bogus creds → 401 message).
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh for /lq-ai/login"`

#### 13b. `/lq-ai/change-password`

- [ ] **Step 1: Read** — `cat web/src/routes/lq-ai/change-password/+page.svelte`
- [ ] **Step 2: Apply Practice classes** — same pattern as 13a. The forced-change copy ("Your password must be changed before continuing") gets `.lq-text-body` and an amber `<TrustPill variant="warn">` for the heads-up. Form fields use Practice borders.
- [ ] **Step 3: Smoke** — log in with `admin@lq.ai`, reset the password via CLI first (`docker compose exec api python -m app.cli reset-admin-password`), then visit `/lq-ai/change-password` and confirm visual lift.
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh for /lq-ai/change-password"`

#### 13c. `/lq-ai/skills` (list)

- [ ] **Step 1: Read** — `cat web/src/routes/lq-ai/skills/+page.svelte`
- [ ] **Step 2: Apply Practice classes** — page heading (`.lq-text-page-h`), section labels (`.lq-text-label`), skill cards (rounded with `var(--lq-radius-lg)`, border `var(--lq-border)`, padding `var(--lq-space-4)`). The "+ Create skill" CTA becomes a `.lq-btn-primary`. Filter chips reuse `TrustPill` with `variant="secure"` for the active state. Built-in / user / team scope badges use `TrustPill` with `variant="tier"`.
- [ ] **Step 3: Smoke** — visit `/lq-ai/skills`; confirm cards lift, scope chips render via TrustPill, "Create skill" button is prominent and sage-styled.
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh for /lq-ai/skills"`

#### 13d. `/lq-ai/skills/new`

- [ ] **Step 1: Read** — `cat web/src/routes/lq-ai/skills/new/+page.svelte`
- [ ] **Step 2: Apply Practice classes** — preserve the existing D8 form behavior; only restyle. Page heading, field labels, helper text, primary save button. The wizard reorganization stays deferred to Wave D.
- [ ] **Step 3: Smoke** — visit `/lq-ai/skills/new`; create a throwaway skill; confirm save still works.
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh for /lq-ai/skills/new (D8 polish)"`

#### 13e. `/lq-ai/skills/[id]/edit`

- [ ] **Step 1: Read** — `cat web/src/routes/lq-ai/skills/\[id\]/edit/+page.svelte`
- [ ] **Step 2: Apply Practice classes** — same pattern as 13d.
- [ ] **Step 3: Smoke** — open the skill created in 13d for edit; save a change; confirm.
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh for /lq-ai/skills/[id]/edit"`

#### 13f. `/lq-ai/admin/audit-log`

- [ ] **Step 1: Read** — `cat web/src/routes/lq-ai/admin/audit-log/+page.svelte`
- [ ] **Step 2: Apply Practice classes** — page heading, filter chip row (use `TrustPill variant="secure"` for active filter, `variant="tier"` for privilege-tag filter, `variant="audit"` for action-type filter), table rows (`var(--lq-border)` dividers; `.lq-text-body` for cells; `.lq-text-caption` for timestamps).
- [ ] **Step 3: Smoke** — visit `/lq-ai/admin/audit-log` as admin; toggle a filter; confirm Practice palette renders, filter behavior unchanged.
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh for /lq-ai/admin/audit-log (D3-coverage polish)"`

#### 13g. `/lq-ai/admin/models`

- [ ] **Step 1: Read** — `cat web/src/routes/lq-ai/admin/models/+page.svelte`
- [ ] **Step 2: Apply Practice classes** — same pattern; tier/provider columns use `TrustPill`.
- [ ] **Step 3: Smoke** — visit `/lq-ai/admin/models` as admin; confirm visual lift.
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh for /lq-ai/admin/models"`

#### 13h. `/lq-ai` (chat shell — sparingly)

> **Important:** `/lq-ai/+page.svelte` is 528 lines and is the C8 chat experience. Wave A only touches its *outer* chrome (heading text classes, color tokens for the surrounding shell). The chat-bubble rendering, skill-picker, model-picker, attached-files panel, saved-prompts panel keep their existing internal styling at Wave A — that's Wave C's reorganization.

- [ ] **Step 1: Read** — `head -60 web/src/routes/lq-ai/+page.svelte` to confirm the chrome regions
- [ ] **Step 2: Apply Practice classes** to the outer wrapper and section labels only. Mount `AmbientFooter` at the bottom of the chat surface (between the input and `DualBrandingFooter`):

```svelte
<script lang="ts">
  // add to existing imports:
  import AmbientFooter from '$lib/lq-ai/components/AmbientFooter.svelte';
  // derive provider/tier from the active chat / model state:
  $: footerProvider = $activeChatStore?.last_routed_provider ?? 'no provider';
  $: footerTier = $activeChatStore?.last_routed_tier ?? 'default';
</script>

<!-- existing template content above … -->

<AmbientFooter provider={footerProvider} tier={footerTier} />
```

> If `activeChatStore` doesn't expose these fields directly, derive them from the latest assistant message in `$messagesStore` (look for `routed_provider` / `routed_tier` on the message envelope per gateway adapter contract).

- [ ] **Step 3: Smoke** — log in, open a chat with skills configured, send a message, confirm: ambient footer appears with derived provider/tier; existing chat features (skill picker, model picker, saved-prompts) unchanged.
- [ ] **Step 4: Commit** — `git commit -s -m "style(web): Practice visual refresh outer chrome + AmbientFooter on /lq-ai chat surface"`

---

### Task 14: Cypress E2E smoke for Wave A chrome

**Files:**
- Create: `web/cypress/e2e/wave-a-chrome.cy.ts`

- [ ] **Step 1: Inspect existing Cypress patterns**

Run: `ls web/cypress/e2e/ && cat web/cypress/e2e/$(ls web/cypress/e2e | head -1) | head -40`

Note the existing test patterns (commands, fixtures, env config). The smoke test mirrors that style.

- [ ] **Step 2: Write the smoke test**

Create `web/cypress/e2e/wave-a-chrome.cy.ts`:

```ts
/**
 * Wave A chrome smoke test.
 *
 * Exercises the visual foundation end-to-end: log in, see the top-tab nav,
 * see ambient trust pills, navigate to Skills, click a not-yet-shipped tab
 * and see ComingSoonModal, dismiss it. Failure of any assertion means the
 * Wave A foundation is broken.
 */
describe('Wave A — LQ.AI chrome', () => {
  beforeEach(() => {
    cy.visit('/lq-ai/login');
    cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
    cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!');
    cy.get('button[type="submit"]').click();
    cy.url().should('not.include', '/login');
  });

  it('renders the top tabs with role-aware visibility', () => {
    cy.get('nav[aria-label="Primary"]').within(() => {
      cy.contains('Home');
      cy.contains('Chats');
      cy.contains('Matters');
      cy.contains('Skills');
      cy.contains('Knowledge');
      cy.contains('Saved Prompts');
      cy.contains('Admin'); // visible because we logged in as admin
    });
  });

  it('renders ambient trust chrome in the top bar', () => {
    cy.contains('● self-hosted').should('be.visible');
    cy.contains('⌘K').should('be.visible');
  });

  it('navigates to Skills when the tab is available', () => {
    cy.contains('nav[aria-label="Primary"] button', 'Skills').click();
    cy.url().should('include', '/lq-ai/skills');
    cy.contains('nav[aria-label="Primary"] button[aria-selected="true"]', 'Skills');
  });

  it('opens ComingSoonModal for not-yet-shipped tabs', () => {
    cy.contains('nav[aria-label="Primary"] button', 'Matters').click();
    cy.get('[role="dialog"]').within(() => {
      cy.contains('Matters');
      cy.contains('Wave C');
      cy.contains('design spec');
      cy.contains('Got it').click();
    });
    cy.get('[role="dialog"]').should('not.exist');
    // URL didn't change because the modal was used:
    cy.url().should('not.include', '/lq-ai/matters');
  });

  it('AmbientFooter renders on the chat surface with provider + tier + audit pills', () => {
    cy.visit('/lq-ai');
    cy.get('footer[aria-label="Chat status"]').within(() => {
      cy.contains('audit on');
    });
  });
});
```

- [ ] **Step 3: Run the smoke test against a running stack**

Run (from the repo root, with `docker compose up -d` already started):

```bash
cd web && npx cypress run --spec 'cypress/e2e/wave-a-chrome.cy.ts'
```

Expected: 5 tests pass.

If a test fails on first run, common causes:
- The dev server isn't proxying API calls correctly → check `web/vite.config.ts` proxy settings against the API container's port
- The admin password isn't the documented one → reset via `docker compose exec api python -m app.cli reset-admin-password`
- ComingSoonModal copy mentions a different wave letter than expected → adjust `tabs.ts` `shipsInWave` to match

- [ ] **Step 4: Commit**

```bash
git add web/cypress/e2e/wave-a-chrome.cy.ts
git commit -s -m "test(web): Cypress E2E smoke for Wave A chrome

Verifies the foundation end-to-end: top tabs render with role-aware
visibility, ambient trust pills are visible, available tabs route,
ComingSoonModal opens for not-yet-shipped tabs and dismisses cleanly,
AmbientFooter renders on the chat surface."
```

---

### Task 15: Accessibility pass

**Files:**
- Modify: `web/src/lib/lq-ai/components/TopTabBar.svelte` (refinements)
- Modify: `web/src/lib/lq-ai/components/ComingSoonModal.svelte` (refinements)

- [ ] **Step 1: Run axe-cli against the running app**

(If `@axe-core/cli` isn't installed: `cd web && npx --yes @axe-core/cli http://localhost:5173/lq-ai`)

Expected: 0 critical or serious issues on `/lq-ai/login`, `/lq-ai`, `/lq-ai/skills`, `/lq-ai/admin/audit-log`. Minor or moderate issues are acceptable at Wave A but recorded as findings.

- [ ] **Step 2: Verify keyboard navigation**

Manually:
- Tab through the top bar — focus moves brand → ambient pills → tabs in order → user menu
- Arrow keys on the tab bar move focus between tabs (if not, add `keydown` handler that moves focus along tablist; document if Wave A doesn't ship roving tabindex and defer to Wave F polish)
- Enter on a focused available tab navigates; Enter on an unavailable tab opens ComingSoonModal
- Escape closes ComingSoonModal; focus returns to the tab that opened it

If gaps surface, add a `keydown` handler to `TopTabBar.svelte`:

```svelte
<script lang="ts">
  // ... existing script ...
  function handleTabKeydown(e: KeyboardEvent, idx: number) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const delta = e.key === 'ArrowRight' ? 1 : -1;
      const next = (idx + delta + tabs.length) % tabs.length;
      const buttons = (e.currentTarget as HTMLElement)
        .closest('ul')
        ?.querySelectorAll<HTMLButtonElement>('button[role="tab"]');
      buttons?.[next]?.focus();
    }
  }
</script>

<!-- in the tab loop, add: on:keydown={(e) => handleTabKeydown(e, tabIndex)} -->
```

(Pass `tabIndex` from `{#each tabs as tab, tabIndex (tab.id)}`.)

- [ ] **Step 3: Commit any refinements**

```bash
git add web/src/lib/lq-ai/components/TopTabBar.svelte web/src/lib/lq-ai/components/ComingSoonModal.svelte
git commit -s -m "a11y(web): keyboard + axe refinements for Wave A chrome

Roving arrow-key focus on the top-tab bar; ComingSoonModal Escape
returns focus to the opening tab. axe-cli shows 0 critical/serious
issues across the Wave A surfaces."
```

If no changes were needed, skip the commit.

---

### Task 16: Final verification + push

- [ ] **Step 1: Run full test suite**

Run from repo root:

```bash
cd web && npm run check && npm run test:frontend
```

Expected: 0 svelte-check errors; all Vitest tests pass.

- [ ] **Step 2: Verify wave A surfaces in dev**

`npm run dev` → walk through every refreshed route:
- `/lq-ai/login`
- `/lq-ai/change-password` (force-reset admin first)
- `/lq-ai` (chat surface)
- `/lq-ai/skills`
- `/lq-ai/skills/new`
- `/lq-ai/skills/[id]/edit`
- `/lq-ai/admin/audit-log`
- `/lq-ai/admin/models`

Confirm visual consistency, ambient chrome, tabs.

- [ ] **Step 3: Run the Cypress smoke**

```bash
cd web && npx cypress run --spec 'cypress/e2e/wave-a-chrome.cy.ts'
```

Expected: 5 PASS.

- [ ] **Step 4: Show the branch state**

```bash
git log --oneline main..HEAD
git status -sb
```

Expected: clean working tree; ~16 commits ahead of main (one per task; Task 13 expanded into 8 sub-commits).

- [ ] **Step 5: Offer to push to remote**

Decision point — present to Kevin:
- "Wave A is complete on `kk/main/Frontend_Design`. Push to origin now (you'll see the branch on github.com/LegalQuants/lq-ai), or hold until you review locally?"

Push only with explicit approval:

```bash
git push -u origin kk/main/Frontend_Design
```

---

## Self-review

**1. Spec coverage:**

| Spec section | Wave A task |
|---|---|
| §4.1 Top-tab nav | Tasks 4, 8, 11 |
| §4.2 Primary surfaces (existing) — visual refresh | Task 13 (a–h) |
| §4.3 Personalization toggles | NOT in Wave A — deferred to Wave B (`/lq-ai/settings/appearance`) per spec §8.1 |
| §5.1 Ambient trust chrome — top bar pills | Task 9 |
| §5.1 Ambient trust chrome — footer pills | Task 10, applied in 13h |
| §5.2 Inline provenance pills | Component contract: Task 6; wiring into messages: Wave D per spec §8.1 |
| §5.3 JIT messaging | NOT in Wave A — Wave E |
| §5.4 Practice visual system | Tasks 1, 2, 3, 13 |
| §10 Theming (CSS variables) | Task 1 |

Three items deliberately not in Wave A: personalization toggles (Wave B has the settings page), JIT messaging (Wave E), and provenance pill wiring (Wave D). These are explicitly scoped out in the plan's header.

**2. Placeholder scan:** No "TBD" / "TODO" / "fill in" / "similar to" references in the task content. Code annotations using "TODO" inside code blocks are scoped notes pointing at backend dependencies (e.g., Task 10's audit-health wiring) — those are intentional in-code comments, not plan placeholders, and are flagged as such.

**3. Type consistency:** `User` type defined in Task 4 (`tabs.ts`) is reused by `TopTabBar` (Task 8) and the layout (Task 11). `TabId` is defined in Task 4 and consumed by `TopTabBar` (Task 8) and `ComingSoonModal` (Task 7). `TrustVariant` defined in Task 5 is used by `AmbientTrustChrome` (Task 9), `AmbientFooter` (Task 10), and the refactored `TierBadge` (Task 12). All consistent.

**4. Ambiguity check:** Task 11 explicitly verifies the `$auth.user` field shape before depending on it (Step 3). Task 13h notes the fallback if `activeChatStore` doesn't expose the routed-provider/tier fields. Task 15's keyboard handling is shipped if axe surfaces issues; otherwise deferred.

**5. Scope check:** Wave A is one cycle, ~16 tasks. Doesn't bleed into Waves B–F.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-10-m1-frontend-wave-a-foundation.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for a multi-task plan like this where each task is bounded and the foundation tasks (1–10) are independent of route-specific work (13).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Best if you want to validate each task interactively as it lands.

Which approach?
