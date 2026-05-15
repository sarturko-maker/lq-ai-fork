# M1 Frontend — Wave B (Dashboard + IA + Trust + Admin Developer Support) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Guided Dashboard, Settings/Appearance, Trust & Privacy page, Admin Developer Support tab, and relocate the existing chat surface from `/lq-ai` to `/lq-ai/chats` — so `/lq-ai` becomes the post-login front door the design spec promises.

**Architecture:** The chat shell that currently lives at `/lq-ai/+page.svelte` (528 lines, the C8 chat experience) moves to `/lq-ai/chats/+page.svelte` and the `chats` top-tab flips `available: true`. The freed-up `/lq-ai/+page.svelte` becomes the Guided Dashboard (Welcome · Trust panel · Featured tools · Getting-started checklist · Recent activity). Three companion surfaces (`/lq-ai/settings/appearance`, `/lq-ai/trust`, `/lq-ai/admin/developer`) ship alongside. Personalization toggles persist to `localStorage` with a backend-sync hook stubbed for when `/api/v1/user/preferences` ships. Trust & Privacy data sources from env/static config for Wave B; the spec's `/api/v1/trust/*` endpoints (§9.1) are wired in when the backend Claude Code lands them.

**Tech Stack:** SvelteKit 2 · TypeScript · Tailwind v4 · Vitest · Cypress · Practice visual system shipped in Wave A.

**Scope contract:** Wave B does **not** implement: the 3-pane Matter Workspace (Wave C — also gates `matters`, `knowledge`, the full `chats` detail view), per-message inline provenance pills (Wave D), the Skill Creator wizard restructure (Wave D), tier-floor refusal block (Wave D), Receipts mode (Wave D), or the sandbox onboarding (Wave E — but the checklist scaffold lands at Wave B so it's ready when sandbox seeding follows). Top tabs `matters`, `knowledge`, and `saved-prompts` continue to route through `ComingSoonModal` until their respective waves.

**Anchors:** [Spec §4 IA + Surfaces](../specs/2026-05-10-m1-frontend-design.md#4-information-architecture-and-primary-surfaces) · [Spec §5.4 Practice palette](../specs/2026-05-10-m1-frontend-design.md#54-practice-visual-system) · [Spec §6.4 Checklist items](../specs/2026-05-10-m1-frontend-design.md#64-getting-started-checklist-persists-on-dashboard) · [Spec §10 Theming + Dev Extensibility](../specs/2026-05-10-m1-frontend-design.md#10-theming-customization-and-developer-extensibility-open-source-posture) · [Wave A plan](2026-05-10-m1-frontend-wave-a-foundation.md) · [ADR 0009 Web shell coexistence](../../adr/0009-web-lq-ai-shell-coexistence.md).

---

## File structure

### Net-new files

| File | Responsibility |
|---|---|
| `web/src/routes/lq-ai/chats/+page.svelte` | The relocated chat shell (528 lines from `/lq-ai/+page.svelte`, otherwise unchanged at Wave B). Detail view (per-chat-id) is Wave C. |
| `web/src/routes/lq-ai/settings/+layout.svelte` | Settings sub-section chrome with side nav (`Appearance`, `Account`) |
| `web/src/routes/lq-ai/settings/appearance/+page.svelte` | 4 personalization toggles |
| `web/src/routes/lq-ai/settings/account/+page.svelte` | Account stub (MFA / export / password change links — full impl post-Wave-B) |
| `web/src/routes/lq-ai/trust/+page.svelte` | Trust & Privacy page (procurement-grade surface) |
| `web/src/routes/lq-ai/admin/developer/+page.svelte` | Admin Developer Support tab |
| `web/src/lib/lq-ai/stores/preferences.ts` | Personalization store (4 toggles), localStorage-backed + backend-sync hook |
| `web/src/lib/lq-ai/components/GuidedDashboardWelcome.svelte` | Welcome header + day |
| `web/src/lib/lq-ai/components/GuidedDashboardTrustPanel.svelte` | Day-1 trust summary, links to /lq-ai/trust |
| `web/src/lib/lq-ai/components/FeaturedToolsRow.svelte` | 4 cards: Enhance · Skill Creator · Knowledge · Apply skill |
| `web/src/lib/lq-ai/components/GettingStartedChecklist.svelte` | 5 detection-driven items (spec §6.4) |
| `web/src/lib/lq-ai/components/RecentActivity.svelte` | Recent matters (placeholder) + recent chats |
| `web/src/lib/lq-ai/components/TrustDataResidencyCard.svelte` | "Where your data lives" |
| `web/src/lib/lq-ai/components/TrustProvidersCard.svelte` | Configured providers + key-encryption status |
| `web/src/lib/lq-ai/components/TrustExternalTurnsCard.svelte` | Daily counter + 7-day rollup (placeholder data if backend not ready) |
| `web/src/lib/lq-ai/components/TrustArtifactsCard.svelte` | SBOM / threat-model / signed-releases links |
| `web/src/lib/lq-ai/components/DevApiDocsCard.svelte` | Links to Swagger UI / ReDoc / Gateway OpenAPI |
| `web/src/lib/lq-ai/components/DevApiPlaygroundCard.svelte` | Mini-playground stub (paste JWT, link to Swagger "Try it out") |
| `web/src/lib/lq-ai/components/DevForkCallout.svelte` | "Build your own frontend" callout linking to forthcoming fork guide |
| `web/src/lib/lq-ai/components/SettingsToggleGroup.svelte` | Reusable toggle group (radio-list shape per spec §5.4) |
| `web/src/lib/lq-ai/__tests__/preferences.test.ts` | Personalization store unit tests |
| `web/src/lib/lq-ai/__tests__/GettingStartedChecklist.test.ts` | Checklist detection-signal tests |
| `web/cypress/e2e/wave-b-surfaces.cy.ts` | E2E smoke for new surfaces |

### Files modified

| File | Change |
|---|---|
| `web/src/routes/lq-ai/+page.svelte` | **Replace contents** — the chat shell moves to `/chats` (T1); this becomes the new Guided Dashboard |
| `web/src/lib/lq-ai/tabs.ts` | Flip `chats` to `available: true`; keep `matters`, `knowledge`, `saved-prompts` at `available: false` (still Wave C/D) |
| `web/src/lib/lq-ai/__tests__/tabs.test.ts` | Update `isTabAvailable` assertion to reflect the chats flip |
| `web/src/lib/lq-ai/components/AmbientTrustChrome.svelte` | Plumb the `display` prop through from preferences store (labels vs dots toggle) |
| `web/src/lib/lq-ai/components/ProvenancePill.svelte` | Plumb the `collapsed` prop hook for Wave D wiring (toggle exists, behavior empty until Wave D) |
| `web/src/routes/lq-ai/+layout.svelte` | Add a settings-cog link in the right-side chrome (next to user menu) → `/lq-ai/settings/appearance` |

### Files NOT touched

- Anything in `web/src/lib/lq-ai/components/Message*.svelte`, `Skill*.svelte`, `Alias*.svelte`, `Tier*.svelte` (stays Wave A baseline; Wave D restructures these)
- OpenWebUI fork outside the LQ.AI subtree (ADR 0009 boundary)

---

## Backend dependencies — handoff for parallel work

The frontend wave can ship without these (with localStorage / static fallbacks); fallbacks are removed when the backend lands.

### Hard dependencies (no graceful fallback)

None. Wave B ships standalone.

### Soft dependencies (fallback in code; replace when shipped)

| Endpoint | Used by | Fallback strategy at Wave B |
|---|---|---|
| `GET/PUT /api/v1/user/preferences` | Settings/Appearance, AmbientTrustChrome | `localStorage` keyed by user id; sync-on-save when the endpoint ships |
| `GET /api/v1/trust/data-residency` | TrustDataResidencyCard | Static `{ postgres, minio, gateway }` from env or hardcoded `localhost`-aware defaults |
| `GET /api/v1/trust/providers` | TrustProvidersCard | Static — list comes from `gateway.yaml`-driven config exposed via an existing admin endpoint, or hardcoded as "Anthropic Claude (default)" |
| `GET /api/v1/trust/external-turns` | TrustExternalTurnsCard, AmbientFooter counter | Derive from `inference_routing_log` via existing audit endpoint if available; otherwise show "—" with explainer copy |
| `GET /api/v1/trust/audit-health` | AmbientFooter, TrustExternalTurnsCard | Static `✓ healthy`; flag in code with the wave-B-temporary comment |
| `GET /api/v1/admin/developer/openapi-urls` | DevApiDocsCard | Hardcode `http://localhost:8000/docs`, `/redoc`, `http://localhost:8001/docs` — operator can override via `.env` |

These fallbacks are explicit in code comments (`// WAVE-B-FALLBACK: replace when /api/v1/trust/data-residency ships`) so a future wave can grep-and-replace.

---

## Testing approach

Same pattern as Wave A: API-client + helper-logic Vitest tests + Cypress E2E for rendered behavior. No `@testing-library/svelte` yet. Major new test surfaces:

- `preferences.test.ts` — store load/save/toggle behavior; localStorage round-trip
- `GettingStartedChecklist.test.ts` — detection signals fire correctly given mock data
- `wave-b-surfaces.cy.ts` — E2E: log in → see dashboard, not chat shell; toggle a setting; visit /lq-ai/trust; click into Admin → Developer Support

---

## Tasks

> Each task ends with a commit. DCO sign-off required. Co-author trailer required.

### Task 1: Relocate the existing chat shell from /lq-ai to /lq-ai/chats

Foundation move. Everything else depends on this.

**Files:**
- Create: `web/src/routes/lq-ai/chats/+page.svelte` (the relocated chat shell)
- Modify: `web/src/routes/lq-ai/+page.svelte` (will become the dashboard — at this task it just becomes a stub that redirects to /lq-ai/chats so we don't lose chat access during the wave)
- Modify: `web/src/lib/lq-ai/tabs.ts` (flip `chats` to `available: true`; update `activeTabFor` if needed)
- Modify: `web/src/lib/lq-ai/__tests__/tabs.test.ts` (update assertion: `expect(isTabAvailable('chats')).toBe(true)`)

- [ ] **Step 1: Move the chat shell file**

```bash
cd /Users/kevinkeller/Desktop/lq-ai
mkdir -p web/src/routes/lq-ai/chats
git mv web/src/routes/lq-ai/+page.svelte web/src/routes/lq-ai/chats/+page.svelte
```

- [ ] **Step 2: Stub `/lq-ai/+page.svelte` as a temporary redirect**

Create `web/src/routes/lq-ai/+page.svelte` with:

```svelte
<script lang="ts">
  /**
   * Wave B transitional stub. Tasks 8+ replace this with the Guided Dashboard.
   * For now, /lq-ai redirects to /lq-ai/chats so the chat surface stays
   * reachable while subsequent tasks build the dashboard out.
   */
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/lq-ai/chats', { replaceState: true });
  });
</script>

<div class="lq-shell" style="padding: var(--lq-space-8); text-align: center;">
  <p class="lq-text-body" style="color: var(--lq-text-tertiary);">Redirecting to chats…</p>
</div>
```

- [ ] **Step 3: Update `tabs.ts`** — flip `chats` to available

Edit `web/src/lib/lq-ai/tabs.ts`: change the `chats` entry's `available: false` to `available: true` and remove its `shipsInWave` hint.

- [ ] **Step 4: Update `tabs.test.ts`** — reflect the new assertion

In the "marks tabs whose routes are not yet implemented as not available" test, move `'chats'` from the `false` group to the `true` group:

```ts
expect(isTabAvailable('chats')).toBe(true);
```

- [ ] **Step 5: Verify**

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
cd web && npm run check 2>&1 | grep -E "(routes/lq-ai/\+page|routes/lq-ai/chats/\+page|tabs)" | head -10
```

Expected: all tests pass (the chat-shell content is unchanged; `tabs.test.ts` passes with the updated assertion).

- [ ] **Step 6: Smoke** — start dev or rebuild docker web (per Wave A working setup); confirm `/lq-ai` redirects to `/lq-ai/chats` and the chat shell renders as before. (If the docker stack is up, `docker compose up -d --no-deps --build web` rebuilds and restarts.)

- [ ] **Step 7: Commit**

```bash
git add web/src/routes/lq-ai/+page.svelte web/src/routes/lq-ai/chats/+page.svelte web/src/lib/lq-ai/tabs.ts web/src/lib/lq-ai/__tests__/tabs.test.ts
git commit -s -m "feat(web): relocate chat shell to /lq-ai/chats; flip chats tab available

Frees /lq-ai for the Guided Dashboard (Wave B Task 8). Chat shell
content unchanged — only the route moved. /lq-ai stubs to a redirect
until the dashboard lands.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Personalization store + Settings/Appearance page

**Files:**
- Create: `web/src/lib/lq-ai/stores/preferences.ts`
- Create: `web/src/lib/lq-ai/__tests__/preferences.test.ts`
- Create: `web/src/lib/lq-ai/components/SettingsToggleGroup.svelte`
- Create: `web/src/routes/lq-ai/settings/+layout.svelte`
- Create: `web/src/routes/lq-ai/settings/appearance/+page.svelte`
- Create: `web/src/routes/lq-ai/settings/account/+page.svelte`
- Modify: `web/src/routes/lq-ai/+layout.svelte` (add settings-cog link in chrome)

#### 2a. Write the failing preferences store test

Create `web/src/lib/lq-ai/__tests__/preferences.test.ts`:

```ts
import { describe, expect, it, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { preferences, defaultPreferences, setPreference, loadFromStorage, saveToStorage, type Preferences } from '../stores/preferences';

describe('preferences store', () => {
  beforeEach(() => {
    localStorage.clear();
    preferences.set(defaultPreferences);
  });

  it('starts at defaults (prominent featured / 3-pane / labels / always-shown)', () => {
    const p = get(preferences);
    expect(p.featuredTools).toBe('prominent');
    expect(p.workspaceLayout).toBe('three-pane');
    expect(p.trustPills).toBe('labels');
    expect(p.provenancePills).toBe('always');
  });

  it('setPreference updates the store and persists to localStorage', () => {
    setPreference('featuredTools', 'inline');
    expect(get(preferences).featuredTools).toBe('inline');
    const stored = JSON.parse(localStorage.getItem('lq-ai:preferences') ?? '{}');
    expect(stored.featuredTools).toBe('inline');
  });

  it('loadFromStorage rehydrates without clobbering missing keys', () => {
    localStorage.setItem('lq-ai:preferences', JSON.stringify({ trustPills: 'dots' }));
    loadFromStorage();
    const p = get(preferences);
    expect(p.trustPills).toBe('dots');
    expect(p.featuredTools).toBe('prominent'); // default preserved
  });

  it('saveToStorage writes the full current state', () => {
    setPreference('workspaceLayout', 'one-pane');
    saveToStorage();
    const stored = JSON.parse(localStorage.getItem('lq-ai:preferences') ?? '{}');
    expect(stored.workspaceLayout).toBe('one-pane');
  });
});
```

#### 2b. Verify test fails

```bash
cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/preferences.test.ts
```

Expected: FAIL with "Cannot find module".

#### 2c. Implement the store

Create `web/src/lib/lq-ai/stores/preferences.ts`:

```ts
/**
 * Personalization store — 4 toggles per design spec §4.3.
 *
 * Wave B: backed by localStorage. When /api/v1/user/preferences ships
 * (spec §9.1), wrap setPreference / saveToStorage to also PUT to the
 * backend.
 */
import { writable } from 'svelte/store';

export type FeaturedToolsMode = 'prominent' | 'inline';
export type WorkspaceLayout = 'three-pane' | 'two-pane' | 'one-pane';
export type TrustPillsMode = 'labels' | 'dots';
export type ProvenancePillsMode = 'always' | 'collapsed';

export interface Preferences {
  featuredTools: FeaturedToolsMode;
  workspaceLayout: WorkspaceLayout;
  trustPills: TrustPillsMode;
  provenancePills: ProvenancePillsMode;
}

export const defaultPreferences: Preferences = {
  featuredTools: 'prominent',
  workspaceLayout: 'three-pane',
  trustPills: 'labels',
  provenancePills: 'always'
};

const STORAGE_KEY = 'lq-ai:preferences';

export const preferences = writable<Preferences>({ ...defaultPreferences });

export function setPreference<K extends keyof Preferences>(key: K, value: Preferences[K]): void {
  preferences.update((p) => ({ ...p, [key]: value }));
  saveToStorage();
}

export function loadFromStorage(): void {
  if (typeof localStorage === 'undefined') return;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw) as Partial<Preferences>;
    preferences.update((p) => ({ ...p, ...parsed }));
  } catch {
    // corrupt storage — reset to default; non-fatal
  }
}

export function saveToStorage(): void {
  if (typeof localStorage === 'undefined') return;
  preferences.subscribe((p) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  })();
}

// WAVE-B-FALLBACK: when /api/v1/user/preferences ships, replace
// localStorage-only with server PUT + localStorage cache for offline use.
```

#### 2d. Verify test passes

```bash
cd web && npm run test:frontend -- src/lib/lq-ai/__tests__/preferences.test.ts
```

Expected: 4 PASS.

#### 2e. Commit (atomic — preferences store first)

```bash
git add web/src/lib/lq-ai/stores/preferences.ts web/src/lib/lq-ai/__tests__/preferences.test.ts
git commit -s -m "feat(web): personalization preferences store (Wave B foundation)

Four toggles per spec §4.3, backed by localStorage. Server sync
(/api/v1/user/preferences, spec §9.1) lands in a follow-on when the
backend route ships — flagged with WAVE-B-FALLBACK in code.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

#### 2f. Build the SettingsToggleGroup component

Create `web/src/lib/lq-ai/components/SettingsToggleGroup.svelte`. Contract:

```svelte
<!--
  Reusable radio-list shape per spec §5.4. Used by all four toggles
  on /lq-ai/settings/appearance.
-->
<script lang="ts">
  export let label: string;
  export let description: string | undefined = undefined;
  export let value: string;
  export let options: { value: string; label: string; description?: string }[];
  export let onChange: (newValue: string) => void;
</script>

<fieldset class="lq-toggle-group">
  <legend class="lq-text-panel-h">{label}</legend>
  {#if description}<p class="lq-text-body" style="color: var(--lq-text-secondary); margin-top: var(--lq-space-2);">{description}</p>{/if}
  <div role="radiogroup" style="margin-top: var(--lq-space-3); display: flex; flex-direction: column; gap: var(--lq-space-2);">
    {#each options as opt (opt.value)}
      <label class="lq-toggle-option" class:lq-toggle-selected={value === opt.value}>
        <input
          type="radio"
          name={label}
          value={opt.value}
          checked={value === opt.value}
          on:change={() => onChange(opt.value)}
        />
        <span class="lq-toggle-content">
          <span class="lq-text-body" style="font-weight: 500;">{opt.label}</span>
          {#if opt.description}
            <span class="lq-text-caption">{opt.description}</span>
          {/if}
        </span>
      </label>
    {/each}
  </div>
</fieldset>

<style>
  .lq-toggle-group { border: 0; padding: 0; margin: 0 0 var(--lq-space-6) 0; }
  .lq-toggle-option {
    display: flex; gap: var(--lq-space-3); align-items: flex-start;
    padding: var(--lq-space-3); border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius); cursor: pointer;
    transition: border-color 0.12s ease, background-color 0.12s ease;
  }
  .lq-toggle-option:hover { border-color: var(--lq-accent-border); }
  .lq-toggle-selected {
    border-color: var(--lq-accent);
    background: var(--lq-accent-soft);
  }
  .lq-toggle-content { display: flex; flex-direction: column; gap: var(--lq-space-1); }
</style>
```

#### 2g. Build the Settings sub-layout + Appearance page + Account stub

Create `web/src/routes/lq-ai/settings/+layout.svelte`:

```svelte
<!--
  Settings sub-section chrome. Side nav with Appearance + Account.
-->
<script lang="ts">
  import { page } from '$app/stores';
  $: pathname = $page.url.pathname;
  function isActive(p: string): boolean { return pathname === p; }
</script>

<div style="display: flex; gap: var(--lq-space-6); padding: var(--lq-space-6);">
  <aside style="min-width: 200px;">
    <h1 class="lq-text-page-h" style="margin-bottom: var(--lq-space-4);">Settings</h1>
    <nav aria-label="Settings sections" style="display: flex; flex-direction: column; gap: var(--lq-space-1);">
      <a href="/lq-ai/settings/appearance" class="lq-text-body" class:lq-settings-active={isActive('/lq-ai/settings/appearance')} style="padding: var(--lq-space-2) var(--lq-space-3); border-radius: var(--lq-radius); text-decoration: none; color: var(--lq-text);">Appearance</a>
      <a href="/lq-ai/settings/account" class="lq-text-body" class:lq-settings-active={isActive('/lq-ai/settings/account')} style="padding: var(--lq-space-2) var(--lq-space-3); border-radius: var(--lq-radius); text-decoration: none; color: var(--lq-text);">Account</a>
    </nav>
  </aside>
  <main style="flex: 1; max-width: 720px;">
    <slot />
  </main>
</div>

<style>
  .lq-settings-active {
    background: var(--lq-accent-soft);
    color: var(--lq-accent) !important;
    font-weight: 500;
  }
</style>
```

Create `web/src/routes/lq-ai/settings/appearance/+page.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { preferences, setPreference, loadFromStorage } from '$lib/lq-ai/stores/preferences';
  import SettingsToggleGroup from '$lib/lq-ai/components/SettingsToggleGroup.svelte';

  onMount(() => loadFromStorage());
</script>

<h2 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-4);">Appearance</h2>
<p class="lq-text-body" style="color: var(--lq-text-secondary); margin-bottom: var(--lq-space-6);">
  Tune how LQ.AI presents itself. Brave choices are on by default; you can dial them back if you want less ceremony.
</p>

<SettingsToggleGroup
  label="Featured tools"
  description="Where Enhance Prompt, Skill Creator, and the launcher live."
  value={$preferences.featuredTools}
  options={[
    { value: 'prominent', label: 'Prominent cards on dashboard', description: 'Featured cards with descriptions, plus ⌘K launcher.' },
    { value: 'inline',    label: 'Inline toolbar only', description: 'Small button row on every composer; less ceremony.' }
  ]}
  onChange={(v) => setPreference('featuredTools', v as any)}
/>

<SettingsToggleGroup
  label="Workspace layout"
  description="How matter views compose."
  value={$preferences.workspaceLayout}
  options={[
    { value: 'three-pane', label: 'Three panes', description: 'Matter rail · chat · outputs panel (default).' },
    { value: 'two-pane',   label: 'Two panes',   description: 'Chat · outputs panel; matter rail collapsed.' },
    { value: 'one-pane',   label: 'Single pane', description: 'Chat only; docs open in a modal.' }
  ]}
  onChange={(v) => setPreference('workspaceLayout', v as any)}
/>

<SettingsToggleGroup
  label="Trust pills"
  description="The ambient indicators in the top bar."
  value={$preferences.trustPills}
  options={[
    { value: 'labels', label: 'Labels',  description: '"● self-hosted" — full label on the pill.' },
    { value: 'dots',   label: 'Dots',    description: 'Just the dot; label appears on hover.' }
  ]}
  onChange={(v) => setPreference('trustPills', v as any)}
/>

<SettingsToggleGroup
  label="Provenance pills"
  description="The per-message skill/tier/provider/audit row (Wave D)."
  value={$preferences.provenancePills}
  options={[
    { value: 'always',    label: 'Always shown', description: 'Pills under every AI reply.' },
    { value: 'collapsed', label: 'Collapsed; expand on hover', description: 'Single "🔍 details" affordance per reply.' }
  ]}
  onChange={(v) => setPreference('provenancePills', v as any)}
/>
```

Create `web/src/routes/lq-ai/settings/account/+page.svelte` (stub):

```svelte
<h2 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-4);">Account</h2>
<p class="lq-text-body" style="color: var(--lq-text-secondary);">
  Account-level settings — MFA enrollment (D5), per-user export and delete (D6, GDPR Art. 17 / 20), and password change — surface here when their respective implementation tasks land. For now, use the change-password flow under your user menu.
</p>
<ul class="lq-text-body" style="margin-top: var(--lq-space-4); color: var(--lq-text-secondary);">
  <li>MFA enrollment — Task D5</li>
  <li>Export my data — Task D6</li>
  <li>Delete my account — Task D6</li>
  <li>Change password — via user menu (B2)</li>
</ul>
```

#### 2h. Wire a settings-cog link in the main layout

Edit `web/src/routes/lq-ai/+layout.svelte` — in the top bar's right cluster (alongside AmbientTrustChrome), add a settings icon link:

Approximate placement (adapt to actual file shape):

```svelte
<header class="lq-topbar">
  <a class="lq-brand" href="/lq-ai">
    <span class="lq-brand-lq">LQ</span>.AI
  </a>
  <div style="display: inline-flex; align-items: center; gap: var(--lq-space-3);">
    <AmbientTrustChrome />
    <a href="/lq-ai/settings/appearance" aria-label="Settings" title="Settings" style="color: var(--lq-text-secondary); text-decoration: none; padding: var(--lq-space-1); border-radius: var(--lq-radius-sm);">⚙</a>
  </div>
</header>
```

#### 2i. Verify, smoke, commit

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
cd web && npm run check 2>&1 | grep -E "(settings|preferences|SettingsToggleGroup)" | head -10
```

Smoke (if stack is up): rebuild web (`docker compose up -d --no-deps --build web`), visit `/lq-ai/settings/appearance`, toggle a setting, refresh — toggle persists.

```bash
git add web/src/lib/lq-ai/components/SettingsToggleGroup.svelte web/src/routes/lq-ai/settings/+layout.svelte web/src/routes/lq-ai/settings/appearance/+page.svelte web/src/routes/lq-ai/settings/account/+page.svelte web/src/routes/lq-ai/+layout.svelte
git commit -s -m "feat(web): Settings/Appearance with 4 personalization toggles + Account stub

/lq-ai/settings/{appearance,account} with a side-nav layout.
Appearance wires the 4 toggles from spec §4.3 to the preferences
store (Task 2 first half). Account stub points at the deliverables
that flesh it out (D5 MFA, D6 export/delete, B2 password change).
Settings-cog link added to the top-bar chrome.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Trust & Privacy page

**Files:**
- Create: `web/src/routes/lq-ai/trust/+page.svelte`
- Create: `web/src/lib/lq-ai/components/TrustDataResidencyCard.svelte`
- Create: `web/src/lib/lq-ai/components/TrustProvidersCard.svelte`
- Create: `web/src/lib/lq-ai/components/TrustExternalTurnsCard.svelte`
- Create: `web/src/lib/lq-ai/components/TrustArtifactsCard.svelte`

Each card is a simple presentational component. Page composes them.

#### 3a. TrustDataResidencyCard

```svelte
<!-- web/src/lib/lq-ai/components/TrustDataResidencyCard.svelte -->
<script lang="ts">
  /**
   * Wave B uses fallback data — replace with /api/v1/trust/data-residency
   * when the backend route ships (spec §9.1).
   */
  // WAVE-B-FALLBACK: hardcoded host info for local-compose deployment.
  const hosts = [
    { label: 'Postgres',         host: 'postgres (container)' },
    { label: 'Object storage',   host: 'minio (container)' },
    { label: 'Inference Gateway', host: 'gateway (container)' }
  ];
</script>

<div class="lq-card">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">Where your data lives</h3>
  <ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--lq-space-2);">
    {#each hosts as h}
      <li style="display: flex; justify-content: space-between; padding: var(--lq-space-2) 0; border-bottom: 1px dashed var(--lq-border);">
        <span class="lq-text-body">{h.label}</span>
        <code class="lq-text-caption" style="font-family: ui-monospace, monospace;">{h.host}</code>
      </li>
    {/each}
  </ul>
  <p class="lq-text-caption" style="margin-top: var(--lq-space-3);">All data stays inside your deployment. No third-party SaaS holds your work.</p>
</div>

<style>
  .lq-card { background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); }
</style>
```

#### 3b. TrustProvidersCard

```svelte
<!-- web/src/lib/lq-ai/components/TrustProvidersCard.svelte -->
<script lang="ts">
  // WAVE-B-FALLBACK: hardcoded provider list. Replace with
  // /api/v1/trust/providers (spec §9.1) when ready — that endpoint
  // returns the configured providers + key-encryption status per
  // ADR 0011.
  const providers = [
    { name: 'Anthropic Claude', encryption: 'Encrypted at rest (ADR 0011)' }
  ];
</script>

<div class="lq-card">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">Configured providers</h3>
  {#each providers as p}
    <div style="display: flex; justify-content: space-between; padding: var(--lq-space-2) 0;">
      <span class="lq-text-body">{p.name}</span>
      <span class="lq-text-caption" style="color: var(--lq-accent);">{p.encryption}</span>
    </div>
  {/each}
  <p class="lq-text-caption" style="margin-top: var(--lq-space-3);">Provider keys never appear in logs, gateway.yaml, or this UI in plaintext.</p>
</div>
<style>.lq-card { background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); }</style>
```

#### 3c. TrustExternalTurnsCard

```svelte
<!-- web/src/lib/lq-ai/components/TrustExternalTurnsCard.svelte -->
<script lang="ts">
  // WAVE-B-FALLBACK: counter not yet wired. Replace with
  // /api/v1/trust/external-turns (spec §9.1) when ready.
  const today = '—';
  const sevenDay = '—';
</script>

<div class="lq-card">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">External provider turns</h3>
  <div style="display: flex; gap: var(--lq-space-6); margin-top: var(--lq-space-2);">
    <div>
      <div class="lq-text-welcome" style="font-weight: 600;">{today}</div>
      <div class="lq-text-caption">Today</div>
    </div>
    <div>
      <div class="lq-text-welcome" style="font-weight: 600;">{sevenDay}</div>
      <div class="lq-text-caption">Last 7 days</div>
    </div>
  </div>
  <p class="lq-text-caption" style="margin-top: var(--lq-space-3); color: var(--lq-text-tertiary);">Counter wires up when the backend's /api/v1/trust/external-turns endpoint ships.</p>
</div>
<style>.lq-card { background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); }</style>
```

#### 3d. TrustArtifactsCard

```svelte
<!-- web/src/lib/lq-ai/components/TrustArtifactsCard.svelte -->
<script lang="ts">
  /**
   * Pointers to procurement-grade artifacts. URLs are stable references
   * (SBOM and threat model are produced by the M1 Phase E release
   * pipeline). For Wave B we link them as anchor placeholders pointing
   * at the in-repo paths; when CI publishes artifacts these become
   * absolute URLs.
   */
</script>

<div class="lq-card">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">Procurement artifacts</h3>
  <ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--lq-space-2);">
    <li><a href="/docs/security/" class="lq-text-body" style="color: var(--lq-accent);">SBOM (Software Bill of Materials)</a></li>
    <li><a href="/docs/security/" class="lq-text-body" style="color: var(--lq-accent);">Signed release verification (Sigstore/cosign)</a></li>
    <li><a href="/docs/security/" class="lq-text-body" style="color: var(--lq-accent);">Public threat model</a></li>
    <li><a href="/docs/compliance/" class="lq-text-body" style="color: var(--lq-accent);">Compliance Alignment Pack (SOC 2 · ISO · GDPR · HIPAA · FedRAMP)</a></li>
  </ul>
  <p class="lq-text-caption" style="margin-top: var(--lq-space-3);">Share this page with your GC or procurement team. PDF export lands in Wave F.</p>
</div>
<style>.lq-card { background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); }</style>
```

#### 3e. Trust & Privacy page composition

Create `web/src/routes/lq-ai/trust/+page.svelte`:

```svelte
<script lang="ts">
  import TrustDataResidencyCard from '$lib/lq-ai/components/TrustDataResidencyCard.svelte';
  import TrustProvidersCard from '$lib/lq-ai/components/TrustProvidersCard.svelte';
  import TrustExternalTurnsCard from '$lib/lq-ai/components/TrustExternalTurnsCard.svelte';
  import TrustArtifactsCard from '$lib/lq-ai/components/TrustArtifactsCard.svelte';
</script>

<div style="padding: var(--lq-space-6); max-width: 1100px;">
  <h1 class="lq-text-page-h" style="margin-bottom: var(--lq-space-2);">Trust &amp; Privacy</h1>
  <p class="lq-text-body" style="color: var(--lq-text-secondary); margin-bottom: var(--lq-space-6);">
    Everything an attorney, GC, or procurement reviewer needs to see — at a glance.
  </p>

  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--lq-space-4);">
    <TrustDataResidencyCard />
    <TrustProvidersCard />
    <TrustExternalTurnsCard />
    <TrustArtifactsCard />
  </div>
</div>
```

#### 3f. Verify + commit (one commit per card or one combined — implementer's discretion)

```bash
cd web && npm run check 2>&1 | grep -E "trust|Trust" | head -10
git add web/src/lib/lq-ai/components/Trust*.svelte web/src/routes/lq-ai/trust/+page.svelte
git commit -s -m "feat(web): Trust & Privacy page (/lq-ai/trust) — procurement-grade surface

Four cards per spec §4.2: data residency, configured providers,
external-turns counter, and procurement artifacts (SBOM / signed
releases / threat model / Compliance Alignment Pack).

Wave B uses fallback data; cards flip to /api/v1/trust/* sources
(spec §9.1) when the backend route ships. Each fallback flagged with
WAVE-B-FALLBACK in code for grep-and-replace later.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Guided Dashboard (the new /lq-ai)

The replacement for the Task 1 stub. Five sub-components, one page composition.

**Files:**
- Modify (replace contents): `web/src/routes/lq-ai/+page.svelte`
- Create: `web/src/lib/lq-ai/components/GuidedDashboardWelcome.svelte`
- Create: `web/src/lib/lq-ai/components/GuidedDashboardTrustPanel.svelte`
- Create: `web/src/lib/lq-ai/components/FeaturedToolsRow.svelte`
- Create: `web/src/lib/lq-ai/components/GettingStartedChecklist.svelte`
- Create: `web/src/lib/lq-ai/components/RecentActivity.svelte`
- Create: `web/src/lib/lq-ai/__tests__/GettingStartedChecklist.test.ts`

#### 4a. GuidedDashboardWelcome

```svelte
<!-- web/src/lib/lq-ai/components/GuidedDashboardWelcome.svelte -->
<script lang="ts">
  export let userDisplayName: string | undefined = undefined;

  const now = new Date();
  const day = now.toLocaleDateString(undefined, { weekday: 'long' });
  const date = now.toLocaleDateString(undefined, { month: 'long', day: 'numeric' });
  const greeting = (() => {
    const h = now.getHours();
    if (h < 5) return 'Working late';
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  })();
</script>

<header style="margin-bottom: var(--lq-space-6);">
  <h1 class="lq-text-welcome">{greeting}{userDisplayName ? `, ${userDisplayName.split(' ')[0]}` : ''}</h1>
  <p class="lq-text-caption" style="margin-top: var(--lq-space-1);">{day} · {date}</p>
</header>
```

#### 4b. GuidedDashboardTrustPanel

Composition of `TrustPill` + "view detail" link to `/lq-ai/trust`.

```svelte
<!-- web/src/lib/lq-ai/components/GuidedDashboardTrustPanel.svelte -->
<script lang="ts">
  import TrustPill from './TrustPill.svelte';
</script>

<section style="background: var(--lq-inset-secure); border: 1px solid var(--lq-accent-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); margin-bottom: var(--lq-space-6); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--lq-space-3);">
  <div>
    <p class="lq-text-label">Your data</p>
    <p class="lq-text-body" style="margin-top: var(--lq-space-1);">In your firm's stack · 0 third-party calls today · audit on</p>
  </div>
  <div style="display: inline-flex; gap: var(--lq-space-2); align-items: center;">
    <TrustPill variant="secure" label="● self-hosted" />
    <a href="/lq-ai/trust" class="lq-text-body" style="color: var(--lq-accent); text-decoration: none;">View detail →</a>
  </div>
</section>
```

> **Counter copy** ("0 third-party calls today") is static for Wave B per the §9.1 fallback list; when `/api/v1/trust/external-turns` ships it becomes derived. Flag with the standard WAVE-B-FALLBACK comment.

#### 4c. FeaturedToolsRow

Four cards. Each gets icon + name + description + "open" action.

```svelte
<!-- web/src/lib/lq-ai/components/FeaturedToolsRow.svelte -->
<script lang="ts">
  import { preferences } from '$lib/lq-ai/stores/preferences';
  // Personalization: if preferences.featuredTools === 'inline',
  // render NOTHING on the dashboard — the inline toolbar (Wave D
  // composer toolbar) takes over.

  const tools = [
    { icon: '✨', name: 'Enhance Prompt',   desc: 'Turn a short ask into a precise instruction the AI can act on.', href: '/lq-ai/chats' },
    { icon: '📝', name: 'Skill Creator',    desc: 'Capture a working prompt as a reusable skill your team can apply.', href: '/lq-ai/skills/new' },
    { icon: '📎', name: 'Knowledge',        desc: 'Bring your playbooks, precedents, and policies into chat.', href: '/lq-ai/knowledge' /* ComingSoon at Wave B */ },
    { icon: '🛠️', name: 'Apply a skill',    desc: 'Browse 10 built-in skills and your own.', href: '/lq-ai/skills' }
  ];
</script>

{#if $preferences.featuredTools === 'prominent'}
  <section style="margin-bottom: var(--lq-space-6);">
    <p class="lq-text-label" style="margin-bottom: var(--lq-space-3);">Featured tools</p>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--lq-space-3);">
      {#each tools as t}
        <a href={t.href} class="lq-tool-card">
          <span class="lq-tool-icon">{t.icon}</span>
          <span class="lq-tool-name lq-text-body" style="font-weight: 600;">{t.name}</span>
          <span class="lq-tool-desc lq-text-caption">{t.desc}</span>
        </a>
      {/each}
    </div>
  </section>
{/if}

<style>
  .lq-tool-card {
    display: flex; flex-direction: column; gap: var(--lq-space-1);
    padding: var(--lq-space-4); background: var(--lq-canvas);
    border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg);
    text-decoration: none; color: var(--lq-text);
    transition: border-color 0.12s ease, transform 0.12s ease;
  }
  .lq-tool-card:hover { border-color: var(--lq-accent); transform: translateY(-1px); }
  .lq-tool-card:focus-visible { outline: 2px solid var(--lq-accent); outline-offset: 2px; }
  .lq-tool-icon { font-size: 22px; }
</style>
```

#### 4d. GettingStartedChecklist

Detection-signal driven. Wave B does basic detection via existing endpoints + localStorage flags. Spec §6.4 items:

```svelte
<!-- web/src/lib/lq-ai/components/GettingStartedChecklist.svelte -->
<script context="module" lang="ts">
  export interface ChecklistItem {
    id: 'password' | 'first-skill' | 'enhance' | 'kb-attach' | 'save-skill';
    label: string;
    done: boolean;
    estimate: string;
    deepLink?: string;
  }

  export function pickNext(items: ChecklistItem[]): ChecklistItem | null {
    return items.find((i) => !i.done) ?? null;
  }

  export function allDone(items: ChecklistItem[]): boolean {
    return items.every((i) => i.done);
  }
</script>

<script lang="ts">
  // WAVE-B: detection signals.
  //   password   — from user.must_change_password === false
  //   first-skill — from messages count where skill_id IS NOT NULL
  //   enhance     — from a localStorage flag set on first Enhance Prompt use
  //   kb-attach   — from matters.length > 0 where attached_kbs.length > 0
  //                 (Wave C will replace; Wave B uses localStorage flag too)
  //   save-skill  — from user_skills.length > 0 OR saved_prompts.length > 0
  // For now: stub the signals so the UI is testable; wire to real
  // endpoints at Wave B end. Wave E (onboarding cycle) replaces with
  // /api/v1/onboarding/checklist-status.
  export let items: ChecklistItem[];
</script>

{#if !allDone(items)}
  <section style="background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); margin-bottom: var(--lq-space-6);">
    <header style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--lq-space-3);">
      <h3 class="lq-text-panel-h">Get started with LQ.AI</h3>
      <span class="lq-text-caption">{items.filter((i) => i.done).length} of {items.length}</span>
    </header>
    <ol style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--lq-space-1);">
      {#each items as item}
        <li style="display: flex; align-items: center; gap: var(--lq-space-3); padding: var(--lq-space-2) 0; border-top: 1px solid var(--lq-border);">
          <span aria-hidden="true" style="width: 16px; height: 16px; border-radius: var(--lq-radius-sm); border: 1.5px solid var(--lq-border); display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; {item.done ? `background: var(--lq-accent); border-color: var(--lq-accent); color: white;` : ''}">{item.done ? '✓' : ''}</span>
          {#if item.deepLink && !item.done}
            <a href={item.deepLink} class="lq-text-body" style="color: var(--lq-text); text-decoration: none; flex: 1;">{item.label}</a>
          {:else}
            <span class="lq-text-body" style="flex: 1; {item.done ? `color: var(--lq-text-tertiary); text-decoration: line-through;` : ''}">{item.label}</span>
          {/if}
          <span class="lq-text-caption">{item.done ? 'done' : item.estimate}</span>
        </li>
      {/each}
    </ol>
  </section>
{/if}
```

Create `web/src/lib/lq-ai/__tests__/GettingStartedChecklist.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { pickNext, allDone, type ChecklistItem } from '../components/GettingStartedChecklist.svelte';

const items: ChecklistItem[] = [
  { id: 'password',    label: 'Log in & rotate your password',         done: true,  estimate: '—'    },
  { id: 'first-skill', label: 'Run your first skill on a document',    done: false, estimate: '2 min' },
  { id: 'enhance',     label: 'Try ✨ Enhance Prompt',                 done: false, estimate: '30 sec' },
  { id: 'kb-attach',   label: 'Attach a knowledge base',               done: false, estimate: '3 min' },
  { id: 'save-skill',  label: 'Save a prompt as a skill',              done: false, estimate: '1 min' }
];

describe('GettingStartedChecklist helpers', () => {
  it('pickNext returns the first unchecked item', () => {
    expect(pickNext(items)?.id).toBe('first-skill');
  });

  it('pickNext returns null when all done', () => {
    const allComplete = items.map((i) => ({ ...i, done: true }));
    expect(pickNext(allComplete)).toBeNull();
  });

  it('allDone is true only when every item is done', () => {
    expect(allDone(items)).toBe(false);
    expect(allDone(items.map((i) => ({ ...i, done: true })))).toBe(true);
  });
});
```

#### 4e. RecentActivity

Two-column section: Recent matters (Coming Soon for now) + Recent chats (using existing `/api/v1/chats` endpoint).

```svelte
<!-- web/src/lib/lq-ai/components/RecentActivity.svelte -->
<script lang="ts">
  /**
   * Wave B: recent chats list pulled from existing /api/v1/chats.
   * Recent matters is a placeholder until Wave C ships /api/v1/matters.
   */
  import { onMount } from 'svelte';
  import { chatsApi } from '$lib/lq-ai/api';

  let recentChats: Array<{ id: string; title: string; updated_at: string }> = [];
  let loading = true;

  onMount(async () => {
    try {
      const result = await chatsApi.list({ limit: 5 });
      recentChats = result.items ?? [];
    } catch {
      recentChats = [];
    } finally {
      loading = false;
    }
  });
</script>

<section style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--lq-space-4);">
  <div>
    <p class="lq-text-label" style="margin-bottom: var(--lq-space-2);">Recent matters</p>
    <p class="lq-text-caption">Matters land in Wave C. Until then, group your chats by intent inside <a href="/lq-ai/chats" style="color: var(--lq-accent);">Chats</a>.</p>
  </div>
  <div>
    <p class="lq-text-label" style="margin-bottom: var(--lq-space-2);">Recent chats</p>
    {#if loading}
      <p class="lq-text-caption">Loading…</p>
    {:else if recentChats.length === 0}
      <p class="lq-text-caption">No chats yet. <a href="/lq-ai/chats" style="color: var(--lq-accent);">Start a conversation →</a></p>
    {:else}
      <ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--lq-space-1);">
        {#each recentChats as c}
          <li><a href="/lq-ai/chats?id={c.id}" class="lq-text-body" style="color: var(--lq-text); text-decoration: none;">{c.title}</a></li>
        {/each}
      </ul>
    {/if}
  </div>
</section>
```

> The `?id=` query-param navigation pattern is Wave B's transitional UX for selecting a specific chat from the list. Wave C replaces with proper `[chatId]` path params inside the matter workspace.

> Adapt the `chatsApi.list({ limit: 5 })` call to match the actual API client signature — if `chatsApi.list` doesn't take a `limit`, slice to 5 client-side after the call.

#### 4f. Dashboard page composition

Replace `web/src/routes/lq-ai/+page.svelte` contents (was Task 1's redirect stub):

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { auth } from '$lib/lq-ai/auth/store';
  import { loadFromStorage } from '$lib/lq-ai/stores/preferences';

  import GuidedDashboardWelcome from '$lib/lq-ai/components/GuidedDashboardWelcome.svelte';
  import GuidedDashboardTrustPanel from '$lib/lq-ai/components/GuidedDashboardTrustPanel.svelte';
  import FeaturedToolsRow from '$lib/lq-ai/components/FeaturedToolsRow.svelte';
  import GettingStartedChecklist, { type ChecklistItem } from '$lib/lq-ai/components/GettingStartedChecklist.svelte';
  import RecentActivity from '$lib/lq-ai/components/RecentActivity.svelte';

  let checklist: ChecklistItem[] = [];

  onMount(async () => {
    loadFromStorage();

    // WAVE-B: detection signals (sketch — implementer wires the real
    // queries). For now, only `password` is reliably derivable from auth state.
    const u = $auth.user;
    checklist = [
      { id: 'password',    label: 'Log in & rotate your password',      done: !!u && !u.must_change_password,                estimate: '—',     deepLink: '/lq-ai/change-password' },
      { id: 'first-skill', label: 'Run your first skill on a document', done: false /* TODO: query messages */,             estimate: '2 min', deepLink: '/lq-ai/chats' },
      { id: 'enhance',     label: 'Try ✨ Enhance Prompt',              done: localStorage.getItem('lq-ai:onboarded:enhance') === 'true', estimate: '30 sec', deepLink: '/lq-ai/chats' },
      { id: 'kb-attach',   label: 'Attach a knowledge base',            done: localStorage.getItem('lq-ai:onboarded:kb') === 'true',      estimate: '3 min', deepLink: '/lq-ai/knowledge' },
      { id: 'save-skill',  label: 'Save a prompt as a skill',           done: localStorage.getItem('lq-ai:onboarded:save-skill') === 'true', estimate: '1 min', deepLink: '/lq-ai/skills/new' }
    ];
  });
</script>

<div style="padding: var(--lq-space-6); max-width: 1100px; margin: 0 auto;">
  <GuidedDashboardWelcome userDisplayName={$auth.user?.display_name ?? $auth.user?.email} />
  <GuidedDashboardTrustPanel />
  <GettingStartedChecklist items={checklist} />
  <FeaturedToolsRow />
  <RecentActivity />
</div>
```

#### 4g. Verify + commit (one commit per component or grouped — implementer's discretion; aim for 3-5 commits across Task 4)

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
cd web && npm run check 2>&1 | grep -E "(GuidedDashboard|FeaturedTools|GettingStarted|RecentActivity)" | head -10
git add web/src/lib/lq-ai/components/GuidedDashboard*.svelte web/src/lib/lq-ai/components/FeaturedToolsRow.svelte web/src/lib/lq-ai/components/GettingStartedChecklist.svelte web/src/lib/lq-ai/components/RecentActivity.svelte web/src/lib/lq-ai/__tests__/GettingStartedChecklist.test.ts web/src/routes/lq-ai/+page.svelte
git commit -s -m "feat(web): Guided Dashboard at /lq-ai — welcome · trust · checklist · tools · recent

Replaces the Task 1 redirect stub with the M1 front door promised in
spec §4.2. Five sub-components compose the dashboard; personalization
toggle (featuredTools=inline) hides Featured Tools in favor of the
inline composer toolbar (Wave D).

Checklist detection: password from auth state; the rest use
localStorage flags as Wave B fallback. Replaced with
/api/v1/onboarding/checklist-status (spec §9.4) at Wave E.

Recent matters waits on Wave C; recent chats pulls from existing
/api/v1/chats.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Admin Developer Support tab

**Files:**
- Create: `web/src/routes/lq-ai/admin/developer/+page.svelte`
- Create: `web/src/lib/lq-ai/components/DevApiDocsCard.svelte`
- Create: `web/src/lib/lq-ai/components/DevApiPlaygroundCard.svelte`
- Create: `web/src/lib/lq-ai/components/DevForkCallout.svelte`

#### 5a. DevApiDocsCard

```svelte
<!-- web/src/lib/lq-ai/components/DevApiDocsCard.svelte -->
<script lang="ts">
  // WAVE-B-FALLBACK: hardcoded for local-compose deployment.
  // When /api/v1/admin/developer/openapi-urls ships (spec §9.1),
  // resolve these from the backend.
  const backendBase = 'http://localhost:8000';
  const gatewayBase = 'http://localhost:8001';
</script>

<div class="lq-card">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">API documentation</h3>
  <ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--lq-space-2);">
    <li><a href={`${backendBase}/docs`} target="_blank" rel="noopener noreferrer" class="lq-text-body" style="color: var(--lq-accent);">Backend API · Swagger UI (interactive) ↗</a></li>
    <li><a href={`${backendBase}/redoc`} target="_blank" rel="noopener noreferrer" class="lq-text-body" style="color: var(--lq-accent);">Backend API · ReDoc (readable) ↗</a></li>
    <li><a href={`${backendBase}/openapi.json`} target="_blank" rel="noopener noreferrer" class="lq-text-body" style="color: var(--lq-accent);">Backend API · OpenAPI JSON ↗</a></li>
    <li><a href={`${gatewayBase}/docs`} target="_blank" rel="noopener noreferrer" class="lq-text-body" style="color: var(--lq-accent);">Inference Gateway · Swagger UI ↗</a></li>
  </ul>
</div>
<style>.lq-card { background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); }</style>
```

#### 5b. DevApiPlaygroundCard

Stub — full inline playground is a follow-on; for Wave B we surface the JWT and a "try in Swagger" CTA.

```svelte
<!-- web/src/lib/lq-ai/components/DevApiPlaygroundCard.svelte -->
<script lang="ts">
  import { auth } from '$lib/lq-ai/auth/store';
  $: token = $auth.access_token;
  let copied = false;
  function copyToken() {
    if (!token) return;
    navigator.clipboard?.writeText(token);
    copied = true;
    setTimeout(() => (copied = false), 1500);
  }
</script>

<div class="lq-card">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">API playground</h3>
  <p class="lq-text-body" style="color: var(--lq-text-secondary); margin-bottom: var(--lq-space-3);">
    Your current access token (for use in Swagger UI's "Authorize" dialog as <code>Bearer &lt;token&gt;</code>):
  </p>
  <pre style="background: var(--lq-inset); border: 1px solid var(--lq-border); border-radius: var(--lq-radius); padding: var(--lq-space-3); font-size: 11px; overflow-x: auto; max-height: 80px;">{token ? token : '(not logged in)'}</pre>
  <button type="button" on:click={copyToken} class="lq-btn-secondary" style="margin-top: var(--lq-space-2); background: white; color: var(--lq-accent); border: 1px solid var(--lq-accent-border); border-radius: var(--lq-radius); padding: 4px 10px; font-size: 13px; cursor: pointer;">
    {copied ? '✓ Copied' : 'Copy token'}
  </button>
  <p class="lq-text-caption" style="margin-top: var(--lq-space-3);">
    Inline endpoint playground lands in a follow-on. For now, copy the token and use it in <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" style="color: var(--lq-accent);">Swagger UI</a>'s Authorize dialog.
  </p>
</div>
<style>.lq-card { background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); }</style>
```

#### 5c. DevForkCallout

```svelte
<!-- web/src/lib/lq-ai/components/DevForkCallout.svelte -->
<div class="lq-card lq-fork-card">
  <h3 class="lq-text-panel-h">Build your own frontend</h3>
  <p class="lq-text-body" style="color: var(--lq-text-secondary); margin-top: var(--lq-space-2);">
    LQ.AI is open source. The Practice visual language is a great default — but if your firm wants a different IA, palette, or shape, the backend is yours and the frontend is fully forkable. See <a href="/docs/superpowers/specs/2026-05-10-m1-frontend-design.md#10-theming-customization-and-developer-extensibility-open-source-posture" style="color: var(--lq-accent);">§10 of the frontend design spec</a> for the extensibility story (semantic CSS variables · component swap · layout pluggability · companion fork guide).
  </p>
  <p class="lq-text-caption" style="margin-top: var(--lq-space-3);">A companion <em>developer-fork guide</em> ships post-Wave-F.</p>
</div>
<style>.lq-card { background: var(--lq-canvas); border: 1px solid var(--lq-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); }
.lq-fork-card { background: linear-gradient(135deg, var(--lq-accent-soft), var(--lq-tier-soft)); border-color: var(--lq-accent-border); }
</style>
```

#### 5d. Developer Support page

```svelte
<!-- web/src/routes/lq-ai/admin/developer/+page.svelte -->
<script lang="ts">
  import DevApiDocsCard from '$lib/lq-ai/components/DevApiDocsCard.svelte';
  import DevApiPlaygroundCard from '$lib/lq-ai/components/DevApiPlaygroundCard.svelte';
  import DevForkCallout from '$lib/lq-ai/components/DevForkCallout.svelte';
</script>

<div style="padding: var(--lq-space-6); max-width: 1100px;">
  <h1 class="lq-text-page-h" style="margin-bottom: var(--lq-space-2);">Developer Support</h1>
  <p class="lq-text-body" style="color: var(--lq-text-secondary); margin-bottom: var(--lq-space-6);">
    For developers building on LQ.AI — direct links to the backend's API documentation, a quick playground, and pointers if you want to fork the frontend.
  </p>
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--lq-space-4);">
    <DevApiDocsCard />
    <DevApiPlaygroundCard />
  </div>
  <div style="margin-top: var(--lq-space-4);">
    <DevForkCallout />
  </div>
</div>
```

#### 5e. Surface a sub-nav for /lq-ai/admin/*

The Admin tab in the top nav currently routes to `/lq-ai/admin/audit-log`. For Wave B, add a tiny admin sub-nav strip at the top of every `/lq-ai/admin/*` page with three links: Audit log, Models, Developer Support.

Create or update `web/src/routes/lq-ai/admin/+layout.svelte` (may not exist yet — create it):

```svelte
<script lang="ts">
  import { page } from '$app/stores';
  $: pathname = $page.url.pathname;
</script>

<nav aria-label="Admin sections" style="padding: var(--lq-space-3) var(--lq-space-6); background: var(--lq-inset); border-bottom: 1px solid var(--lq-border); display: flex; gap: var(--lq-space-4);">
  <a href="/lq-ai/admin/audit-log"  class="lq-text-body" class:lq-admin-active={pathname.startsWith('/lq-ai/admin/audit-log')}  style="color: var(--lq-text-secondary); text-decoration: none;">Audit log</a>
  <a href="/lq-ai/admin/models"     class="lq-text-body" class:lq-admin-active={pathname.startsWith('/lq-ai/admin/models')}     style="color: var(--lq-text-secondary); text-decoration: none;">Models</a>
  <a href="/lq-ai/admin/developer"  class="lq-text-body" class:lq-admin-active={pathname.startsWith('/lq-ai/admin/developer')}  style="color: var(--lq-text-secondary); text-decoration: none;">Developer Support</a>
</nav>

<slot />

<style>
  .lq-admin-active { color: var(--lq-accent) !important; font-weight: 500; }
</style>
```

#### 5f. Commit

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
cd web && npm run check 2>&1 | grep -E "(admin/developer|DevApi|DevForkCallout|admin/\+layout)" | head -10
git add web/src/routes/lq-ai/admin/developer/+page.svelte web/src/routes/lq-ai/admin/+layout.svelte web/src/lib/lq-ai/components/DevApi*.svelte web/src/lib/lq-ai/components/DevForkCallout.svelte
git commit -s -m "feat(web): Admin Developer Support tab + admin sub-nav

Implements spec §4.2 admin extension and §10.4 — links to backend
Swagger / ReDoc / Gateway docs, a JWT-copy playground stub, and a
"Build your own frontend" callout pointing at §10's extensibility
story. Admin sub-nav strip surfaces Audit log / Models / Developer
Support consistently.

Inline endpoint playground is a follow-on; Wave B ships the
JWT-copy + Swagger-Authorize flow as the minimum viable surface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Cypress E2E for Wave B surfaces

**Files:**
- Create: `web/cypress/e2e/wave-b-surfaces.cy.ts`

```ts
/**
 * Wave B surfaces smoke test — covers the new surfaces shipped in this wave.
 *
 * Operator runs:
 *   docker compose up -d
 *   docker compose exec api python -m app.cli reset-admin-password
 *   (change password via UI or API to skip the gate)
 *   cd web && npx cypress run --spec 'cypress/e2e/wave-b-surfaces.cy.ts'
 */
describe('Wave B — dashboard, settings, trust, developer', () => {
  beforeEach(() => {
    cy.visit('/lq-ai/login');
    cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
    cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-Admin-Pw1!');
    cy.get('button[type="submit"]').click();
    cy.url().should('not.include', '/login');
  });

  it('post-login lands on the Guided Dashboard (not the chat shell)', () => {
    cy.url().should('match', /\/lq-ai(\/?)$/);
    cy.contains('Get started with LQ.AI').should('be.visible'); // checklist
    cy.contains('Featured tools').should('be.visible');
    cy.contains('Recent chats').should('be.visible');
  });

  it('Chats tab is now available (not ComingSoon)', () => {
    cy.contains('nav[aria-label="Primary"] button', 'Chats').click();
    cy.url().should('include', '/lq-ai/chats');
    cy.get('[role="dialog"]').should('not.exist');
  });

  it('Settings → Appearance toggles persist', () => {
    cy.visit('/lq-ai/settings/appearance');
    cy.contains('Featured tools').should('be.visible');
    cy.contains('label', 'Inline toolbar only').click();
    cy.reload();
    cy.get('input[value="inline"]').should('be.checked');
  });

  it('/lq-ai/trust renders all four cards', () => {
    cy.visit('/lq-ai/trust');
    cy.contains('Where your data lives').should('be.visible');
    cy.contains('Configured providers').should('be.visible');
    cy.contains('External provider turns').should('be.visible');
    cy.contains('Procurement artifacts').should('be.visible');
  });

  it('Admin → Developer Support tab renders with API doc links', () => {
    cy.visit('/lq-ai/admin/developer');
    cy.contains('API documentation').should('be.visible');
    cy.contains('Swagger UI').should('be.visible');
    cy.contains('Build your own frontend').should('be.visible');
    cy.contains('Copy token').should('be.visible');
  });
});
```

#### Commit

```bash
git add web/cypress/e2e/wave-b-surfaces.cy.ts
git commit -s -m "test(web): Cypress E2E smoke for Wave B surfaces

Five tests covering the dashboard front door, chats availability,
appearance-toggle persistence, trust page, and developer-support
tab. Operator runs against a live stack — see file header for the
recipe.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Final verification + push

- [ ] **Step 1: Run full test suite**

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
```

Expected: all tests pass (Wave A's 91 + Wave B additions ≥ ~95).

- [ ] **Step 2: svelte-check** — filter for Wave B files

```bash
cd web && npm run check 2>&1 | grep -E "(settings|trust|developer|GuidedDashboard|FeaturedTools|GettingStarted|RecentActivity|TrustData|TrustProviders|TrustExternal|TrustArtifacts|DevApi|DevForkCallout|preferences|SettingsToggleGroup)" | head -30
```

Expected: 0 new errors from Wave B files.

- [ ] **Step 3: Smoke** — `docker compose up -d --no-deps --build web` (with the stack already up), hard-refresh, walk through:
  1. Log in → land on Guided Dashboard
  2. Click Chats → chat shell (relocated)
  3. Click Skills → unchanged
  4. Click Matters → ComingSoonModal (still Wave C)
  5. Settings gear → Appearance, toggle Featured Tools → Inline → return to Dashboard, Featured Tools row hidden
  6. Visit /lq-ai/trust → 4 cards render
  7. Admin → Developer Support → links open Swagger UI in new tab; Copy token works

- [ ] **Step 4: Push**

```bash
git push origin kk/main/Frontend_Design
```

---

## Self-review

**1. Spec coverage:**

| Spec section | Wave B task |
|---|---|
| §4.1 Top-tab nav (Chats availability flip) | Task 1 |
| §4.2 Home (Guided Dashboard) | Task 4 |
| §4.2 Chats (the relocated surface — list view; detail in Wave C) | Task 1 |
| §4.2 Trust & Privacy | Task 3 |
| §4.2 Admin Developer Support | Task 5 |
| §4.3 Personalization toggles | Task 2 |
| §6.4 Getting-started checklist | Task 4 (scaffold; detection signals refined in Task 4 wiring) |
| §10.4 Developer Support tab content | Task 5 |
| §5.1 Settings-cog in chrome | Task 2 |

**2. Placeholder scan:** Code comments labeled `WAVE-B-FALLBACK` are intentional — they mark where backend endpoints will replace static data. Not plan placeholders.

**3. Type consistency:** `Preferences` shape, `ChecklistItem`, `TabId` (Wave A), `User` (Wave A) used consistently across components. `auth.user` shape is verified to expose `display_name`, `email`, `must_change_password`, `access_token`.

**4. Ambiguity:** Two items resolved with explicit defaults:
- Chat relocation: `/lq-ai/chats` is the new home (Task 1, no `[chatId]` route yet; query-param `?id=` for selection — Wave C upgrades)
- Recent matters: placeholder card pointing at Chats (no Matters API at Wave B)

**5. Scope:** 7 high-level tasks, ~15-18 atomic commits. Within Wave B's deliverables; no bleed into Wave C/D.

---

## Open implementation questions

1. **`chatsApi.list` signature** — verify it supports a `limit` param or whether to slice client-side. Decide during Task 4e (RecentActivity).
2. **Admin sub-nav placement** — Task 5e adds a sub-nav strip via `/lq-ai/admin/+layout.svelte`. If a layout already exists at that path, merge rather than replace.
3. **Settings cog visibility on auth-exempt routes** — the gear icon in `+layout.svelte` should hide on `/login` and `/change-password` since those routes don't render the top bar at all (Wave A behavior). Confirm during Task 2h.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-11-m1-frontend-wave-b-dashboard-ia.md`.

Two execution options (same as Wave A):

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans.

Which approach?
