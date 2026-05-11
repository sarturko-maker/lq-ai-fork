# M1 Frontend — Wave B v2 (post-merge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Supersedes** [2026-05-11-m1-frontend-wave-b-dashboard-ia.md (v1)](2026-05-11-m1-frontend-wave-b-dashboard-ia.md). v1 was authored before pulling main into the branch and planned around backend routes that hadn't shipped yet. After the merge (commit `24c642c`), most of those routes are real — so v1's WAVE-B-FALLBACK pattern is gone, and two features (Enhance Prompt UX, Skill Detail "View source" tab) move forward from Wave D into Wave B.

**Goal:** Ship the Guided Dashboard, Settings/Appearance + Account, Trust & Privacy page, Admin Developer Support tab, and relocate the chat shell — wired to **real backend endpoints** that shipped on main between Wave A and now. Plus three features that became feasible because of those endpoints: Enhance Prompt inline UX, Skill Detail "View source" tab, and session-timeout warning chrome.

**Architecture:** `/lq-ai/+page.svelte` becomes the Guided Dashboard; the existing chat shell moves to `/lq-ai/chats/+page.svelte`. Preferences sync via `GET/PATCH /users/me/preferences` (localStorage cache for offline). Trust panel and chrome tier pill read `GET /inference/current-tier`. External-turns counter reads `GET /admin/usage`. Recent chats use `GET /chats/search`. Enhance Prompt uses `POST /enhance-prompt` with the diff-and-accept UX from spec §7.1. Skill Detail adds a "View source" tab backed by `GET /skills/{name}/contents`. Session-timeout warning watches user activity and refreshes the access token at the 25-minute mark of a 30-minute idle window (PRD §5.1 default). MFA enrollment surfaces in `/lq-ai/settings/account` using the existing `/auth/mfa/*` endpoints.

**Tech Stack:** SvelteKit 2 · TypeScript · Tailwind v4 · Vitest · Cypress · Practice visual system from Wave A · new API clients for the post-merge endpoints.

**Scope contract — what Wave B v2 does NOT do:**
- 3-pane Matter Workspace (Wave C — `matters` tab stays ComingSoonModal)
- Knowledge browser (Wave C — `knowledge` tab stays ComingSoonModal)
- Tier-floor refusal block as a persisted message (Wave D)
- Receipts mode (Wave D)
- Skill Creator three-mode wizard restructure (Wave D — current D8 single-form flow is fine; we add the "View source" tab on the detail page only)
- Skill Detail's `Try it` and `Versions` tabs (Wave D — "View source" ships here; the other two stay)
- Sandbox onboarding seeding (Wave E)
- Saved Prompts standalone surface (`saved-prompts` tab stays ComingSoonModal — the API exists but the dedicated surface is a smaller separate task)

**Anchors:** [Spec §4 IA + Surfaces](../specs/2026-05-10-m1-frontend-design.md#4-information-architecture-and-primary-surfaces) · [Spec §5 Cross-cutting patterns](../specs/2026-05-10-m1-frontend-design.md#5-cross-cutting-patterns-and-the-practice-visual-system) · [Spec §7.1 Enhance Prompt UX](../specs/2026-05-10-m1-frontend-design.md#71-enhance-prompt) · [Spec §10 Dev extensibility](../specs/2026-05-10-m1-frontend-design.md#10-theming-customization-and-developer-extensibility-open-source-posture) · [PRD §5.1 Session lifecycle](../../PRD.md) · [Backend OpenAPI sketch](../../api/backend-openapi.yaml) · [Wave A plan](2026-05-10-m1-frontend-wave-a-foundation.md) · [Wave B v1 plan (superseded)](2026-05-11-m1-frontend-wave-b-dashboard-ia.md).

---

## Backend endpoints (real, shipped on main)

The plan wires to these existing endpoints. Implementer should reference `docs/api/backend-openapi.yaml` for exact request/response shapes during execution.

| Endpoint | Used by task |
|---|---|
| `GET /api/v1/users/me/preferences` | Task 2 |
| `PATCH /api/v1/users/me/preferences` | Task 2 |
| `POST /api/v1/enhance-prompt` | Task 6 |
| `PATCH /api/v1/enhance-prompt/{interaction_id}` | Task 6 (accept/reject signal) |
| `GET /api/v1/skills/{skill_name}/contents` | Task 7 |
| `GET /api/v1/skills/{skill_name}/inputs` | Task 7 |
| `GET /api/v1/chats/search` | Task 4 (recent chats), Task 1 (chats list FTS — optional polish) |
| `GET /api/v1/inference/current-tier` | Task 4 (dashboard tier label), Task 3b (chrome refinement) |
| `GET /api/v1/inference/tier-config` | Task 3 (Trust providers + tier rollup) |
| `GET /api/v1/admin/usage` | Task 3 (external-turns counter) |
| `GET /api/v1/admin/tier-policy` · `PATCH /api/v1/admin/tier-policy` | Existing Admin Models page; no new work |
| `PATCH /api/v1/admin/users/{user_id}/role` | Task 5 (role management surface) |
| `POST /auth/refresh` | Task 3b (session-timeout warning auto-refresh) |
| `POST /auth/mfa/setup` · `POST /auth/mfa/enable` · `POST /auth/mfa/disable` | Task 2b (MFA enrollment in Account settings) |
| `POST /users/me/export` · `GET /users/me/export/{job_id}` · `POST /users/me/delete` | Task 2b (account export/delete links) |
| `GET /metrics` (Prometheus) | Task 5 (linked from Developer Support card) |

## Backend endpoints (still fallback / static)

| Endpoint | Wave B v2 strategy |
|---|---|
| `/api/v1/trust/data-residency` | Static — read from compose-derived env (Postgres/MinIO/gateway hostnames). Task 3 card. |
| `/api/v1/trust/audit-health` | Static `✓ healthy` placeholder. Task 3 card. Flagged with `// V2-FALLBACK` comment. |
| `/api/v1/admin/developer/openapi-urls` | Hardcoded — `http://localhost:8000/docs`, `/redoc`, `http://localhost:8001/docs`. Task 5. |
| `/api/v1/matters` | Out of scope (Wave C). `matters` tab → ComingSoonModal. |
| `/api/v1/onboarding/*` | Out of scope (Wave E). Checklist uses derivable signals + localStorage flags. |

---

## File structure

### Net-new files

| File | Responsibility | Owning task |
|---|---|---|
| `web/src/lib/lq-ai/api/preferences.ts` | API client for `/users/me/preferences` | Task 2 |
| `web/src/lib/lq-ai/api/enhancePrompt.ts` | API client for `/enhance-prompt` + `/enhance-prompt/{id}` | Task 6 |
| `web/src/lib/lq-ai/api/inferenceTier.ts` | API client for `/inference/current-tier` + `/tier-config` | Task 4 / 3 |
| `web/src/lib/lq-ai/api/skillContents.ts` *(or extension of skills.ts)* | API for `/skills/{name}/contents` + `/inputs` | Task 7 |
| `web/src/lib/lq-ai/stores/preferences.ts` | Preferences store (server-synced, localStorage offline cache) | Task 2 |
| `web/src/lib/lq-ai/stores/sessionActivity.ts` | Idle-time tracking + token refresh trigger | Task 3b |
| `web/src/lib/lq-ai/components/SettingsToggleGroup.svelte` | Reusable radio-list shape | Task 2 |
| `web/src/lib/lq-ai/components/SessionTimeoutWarning.svelte` | Toast at 25min idle | Task 3b |
| `web/src/lib/lq-ai/components/MfaEnrollmentPanel.svelte` | MFA setup flow | Task 2b |
| `web/src/lib/lq-ai/components/AccountExportDeletePanel.svelte` | Per-user data export + delete | Task 2b |
| `web/src/lib/lq-ai/components/GuidedDashboardWelcome.svelte` | Greeting + day | Task 4 |
| `web/src/lib/lq-ai/components/GuidedDashboardTrustPanel.svelte` | Day-1 trust summary, links to /lq-ai/trust | Task 4 |
| `web/src/lib/lq-ai/components/FeaturedToolsRow.svelte` | 4 cards (Enhance · Skill Creator · Knowledge · Apply skill) | Task 4 |
| `web/src/lib/lq-ai/components/GettingStartedChecklist.svelte` | 5 detection-driven items | Task 4 |
| `web/src/lib/lq-ai/components/RecentActivity.svelte` | Recent chats (real); matters placeholder | Task 4 |
| `web/src/lib/lq-ai/components/TrustDataResidencyCard.svelte` | "Where your data lives" | Task 3 |
| `web/src/lib/lq-ai/components/TrustProvidersCard.svelte` | Configured providers (from `/inference/tier-config`) | Task 3 |
| `web/src/lib/lq-ai/components/TrustExternalTurnsCard.svelte` | Daily counter + 7-day from `/admin/usage` | Task 3 |
| `web/src/lib/lq-ai/components/TrustArtifactsCard.svelte` | SBOM / threat-model / signed-releases links | Task 3 |
| `web/src/lib/lq-ai/components/DevApiDocsCard.svelte` | Links to Swagger/ReDoc/Gateway + Prometheus | Task 5 |
| `web/src/lib/lq-ai/components/DevApiPlaygroundCard.svelte` | JWT-copy → Swagger Authorize CTA | Task 5 |
| `web/src/lib/lq-ai/components/DevRoleManagementCard.svelte` | Three-role admin: user role list + change | Task 5 |
| `web/src/lib/lq-ai/components/DevForkCallout.svelte` | "Build your own frontend" callout | Task 5 |
| `web/src/lib/lq-ai/components/EnhancePromptExpansion.svelte` | Original/Enhanced diff + Use/Edit/Keep | Task 6 |
| `web/src/lib/lq-ai/components/SkillDetailTabs.svelte` | Tab strip (Use it · View source · Try it · Versions) | Task 7 |
| `web/src/lib/lq-ai/components/SkillSourceView.svelte` | Renders SKILL.md raw markdown | Task 7 |
| `web/src/routes/lq-ai/chats/+page.svelte` | Relocated chat shell (528 lines from old /lq-ai/+page.svelte) | Task 1 |
| `web/src/routes/lq-ai/settings/+layout.svelte` | Side-nav chrome (Appearance · Account) | Task 2 |
| `web/src/routes/lq-ai/settings/appearance/+page.svelte` | 4 personalization toggles | Task 2 |
| `web/src/routes/lq-ai/settings/account/+page.svelte` | MFA + export/delete + password | Task 2b |
| `web/src/routes/lq-ai/trust/+page.svelte` | Trust & Privacy page | Task 3 |
| `web/src/routes/lq-ai/admin/developer/+page.svelte` | Admin Developer Support tab | Task 5 |
| `web/src/routes/lq-ai/admin/+layout.svelte` | Admin sub-nav strip | Task 5 |
| `web/src/routes/lq-ai/skills/[id]/+page.svelte` | Skill Detail view (currently only `/edit` exists) | Task 7 |
| `web/src/lib/lq-ai/__tests__/preferences.test.ts` | Preferences store unit tests | Task 2 |
| `web/src/lib/lq-ai/__tests__/sessionActivity.test.ts` | Activity-tracking store unit tests | Task 3b |
| `web/src/lib/lq-ai/__tests__/EnhancePromptExpansion.test.ts` | Helper tests for the diff component | Task 6 |
| `web/src/lib/lq-ai/__tests__/preferences-api.test.ts` | API-client tests | Task 2 |
| `web/src/lib/lq-ai/__tests__/enhancePrompt-api.test.ts` | API-client tests | Task 6 |
| `web/cypress/e2e/wave-b-surfaces.cy.ts` | E2E for new surfaces + Enhance flow | Task 8 |

### Modified files

| File | Change | Task |
|---|---|---|
| `web/src/routes/lq-ai/+page.svelte` | **Replace contents** — was the chat shell (moved in T1); becomes Guided Dashboard | Task 4 |
| `web/src/lib/lq-ai/types.ts` | Add `role: 'admin'\|'member'\|'viewer'` to User (per PRD §5.2 + migration 0017), plus `reasoning_visibility`, `session_absolute_expires_at`, `last_active_at` per migrations 0017/0018 | Task 2 (foundational) |
| `web/src/lib/lq-ai/tabs.ts` | Flip `chats` to `available: true`; refine admin gating to use `role === 'admin'` (keeps `is_admin` as fallback) | Task 1 + Task 5b |
| `web/src/lib/lq-ai/__tests__/tabs.test.ts` | Update assertions: chats `isTabAvailable === true`; three-role gating coverage | Task 1 / 5b |
| `web/src/lib/lq-ai/api/index.ts` | Export new `preferences`, `enhancePrompt`, `inferenceTier` clients | Task 2 / 6 / 4 |
| `web/src/lib/lq-ai/components/AmbientTrustChrome.svelte` | Plumb `display` from preferences store; add tier label from `/inference/current-tier` | Task 4 |
| `web/src/lib/lq-ai/components/AmbientFooter.svelte` | Plumb `display` + wire audit-health (still fallback) | Task 4 |
| `web/src/routes/lq-ai/+layout.svelte` | Add settings-cog link (right side, beside chrome); mount `SessionTimeoutWarning` | Task 2 / 3b |
| `web/src/lib/lq-ai/components/ChatSidebar.svelte` | Add chat-search input that uses `/chats/search` | Task 1 (optional polish) |

### Files NOT touched

- Anything outside `web/src/lib/lq-ai/**`, `web/src/routes/lq-ai/**`, `web/cypress/e2e/wave-b-*.cy.ts` (ADR 0009 boundary)
- The existing chat-shell internals (MessageList, MessageBubble, AttachedFilesPanel, SavedPromptsPanel, etc.) — Wave A polished those; Wave C restructures them
- `tabs.ts` for `matters` / `knowledge` / `saved-prompts` availability — stays `false` until C/D ship the surfaces

---

## Testing approach

Same pattern as Wave A: API-client + helper-logic Vitest tests + Cypress E2E. Vitest test counts grow from 100 (post-merge baseline) to ~115-120 by Wave B v2 end.

Major new test surfaces:
- Preferences store + API client (8-10 tests)
- Session activity tracker (4-5 tests)
- Enhance Prompt helper + API (5-6 tests)
- Tabs three-role gating (3 new assertions added to existing test file)
- Cypress: dashboard / chats relocation / settings / trust / developer / enhance prompt flow / session-timeout warning visible at the 25-min mark (mocked)

---

## Tasks

> Each task ends with one or more atomic commits. DCO sign-off (`-s`) and `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer required on every commit. Verify with `git log -1 --format=fuller`.

### Task 1: Relocate chat shell + flip chats tab available

**Files:**
- Create dir + move: `web/src/routes/lq-ai/chats/+page.svelte` (from `web/src/routes/lq-ai/+page.svelte`)
- Modify (replace): `web/src/routes/lq-ai/+page.svelte` (becomes a temporary redirect; Task 4 replaces with the dashboard)
- Modify: `web/src/lib/lq-ai/tabs.ts` (flip `chats.available` to `true`; remove its `shipsInWave`)
- Modify: `web/src/lib/lq-ai/__tests__/tabs.test.ts` (move `'chats'` from `isTabAvailable === false` group to the `true` group)

- [ ] **Step 1: Move the chat shell**

```bash
cd /Users/kevinkeller/Desktop/lq-ai
mkdir -p web/src/routes/lq-ai/chats
git mv web/src/routes/lq-ai/+page.svelte web/src/routes/lq-ai/chats/+page.svelte
```

- [ ] **Step 2: Stub the new /lq-ai/+page.svelte as a redirect**

```svelte
<script lang="ts">
  // Transitional — Task 4 replaces this with the Guided Dashboard.
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  onMount(() => goto('/lq-ai/chats', { replaceState: true }));
</script>
<div class="lq-shell" style="padding: var(--lq-space-8); text-align: center;">
  <p class="lq-text-body" style="color: var(--lq-text-tertiary);">Redirecting to chats…</p>
</div>
```

- [ ] **Step 3: Flip `chats` to available in `tabs.ts`** — change `available: false, shipsInWave: 'C'` → `available: true` (delete `shipsInWave` from that entry).

- [ ] **Step 4: Update `tabs.test.ts`** — in the "marks tabs whose routes are not yet implemented" test, move `'chats'` to the available-true assertion group.

- [ ] **Step 5: Verify + smoke**

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
cd web && npm run check 2>&1 | grep -E "(routes/lq-ai/(\+page|chats/\+page)|tabs)" | head -5
```

Smoke (stack running): `docker compose up -d --no-deps --build web`; hard-refresh `/lq-ai/login`; confirm post-login lands on `/lq-ai`, redirects to `/lq-ai/chats`, chat shell renders.

- [ ] **Step 6: Commit**

```bash
git add web/src/routes/lq-ai/+page.svelte web/src/routes/lq-ai/chats/+page.svelte web/src/lib/lq-ai/tabs.ts web/src/lib/lq-ai/__tests__/tabs.test.ts
git commit -s -m "feat(web): relocate chat shell to /lq-ai/chats; flip chats tab available

Frees /lq-ai for the Guided Dashboard (Task 4). Chat shell content
unchanged — only the route moved. /lq-ai stubs to a redirect until
the dashboard lands.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Personalization preferences (server-synced) + Settings/Appearance page

**Files:**
- Create: `web/src/lib/lq-ai/api/preferences.ts`
- Create: `web/src/lib/lq-ai/stores/preferences.ts`
- Create: `web/src/lib/lq-ai/components/SettingsToggleGroup.svelte`
- Create: `web/src/routes/lq-ai/settings/+layout.svelte`
- Create: `web/src/routes/lq-ai/settings/appearance/+page.svelte`
- Create: `web/src/lib/lq-ai/__tests__/preferences.test.ts`
- Create: `web/src/lib/lq-ai/__tests__/preferences-api.test.ts`
- Modify: `web/src/lib/lq-ai/api/index.ts` (export the new client)
- Modify: `web/src/lib/lq-ai/types.ts` (add `Preferences` shape; update `User` per migration 0017/0018 — at minimum add `role`)

#### 2.1 Update `types.ts`

Add to `web/src/lib/lq-ai/types.ts` (alongside existing `User`):

```ts
export type UserRole = 'admin' | 'member' | 'viewer';

// Augment User (verify field names against /users/me response — the
// backend's exact JSON shape is canonical; adapt if drift).
export interface User {
  id: string;
  email: string;
  display_name?: string | null;
  is_admin: boolean;             // legacy boolean; kept for back-compat
  role: UserRole;                 // NEW (migration 0017)
  mfa_enabled: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at?: string | null;
  reasoning_visibility?: 'hidden' | 'collapsed' | 'expanded';  // NEW (migration 0015)
}

export type FeaturedToolsMode = 'prominent' | 'inline';
export type WorkspaceLayout = 'three_pane' | 'two_pane' | 'one_pane';
export type TrustPillsMode = 'labels' | 'dots';
export type ProvenancePillsMode = 'always' | 'collapsed';

export interface Preferences {
  featured_tools: FeaturedToolsMode;
  workspace_layout: WorkspaceLayout;
  trust_pills: TrustPillsMode;
  provenance_pills: ProvenancePillsMode;
}
```

> If the backend's actual field names differ (camelCase vs snake_case), adjust to match. The implementer verifies via `curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/users/me/preferences` during this step.

#### 2.2 Write the failing API-client test

`web/src/lib/lq-ai/__tests__/preferences-api.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getPreferences, patchPreferences } from '../api/preferences';
import { setSession, clearSession } from '../auth/store';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

beforeEach(() => {
  setSession({ access_token: 't', refresh_token: 'r', user: { id: '1', email: 'a@x', is_admin: false, role: 'member', mfa_enabled: false, must_change_password: false, created_at: '' } });
});
afterEach(() => {
  clearSession();
  global.fetch = realFetch;
  vi.restoreAllMocks();
});

describe('preferences API client', () => {
  it('GET /users/me/preferences returns the parsed Preferences', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(
      jsonResponse(200, { featured_tools: 'prominent', workspace_layout: 'three_pane', trust_pills: 'labels', provenance_pills: 'always' })
    );
    const p = await getPreferences();
    expect(p.featured_tools).toBe('prominent');
    expect(p.workspace_layout).toBe('three_pane');
  });

  it('PATCH /users/me/preferences sends only the diff', async () => {
    const spy = vi.fn().mockResolvedValueOnce(
      jsonResponse(200, { featured_tools: 'inline', workspace_layout: 'three_pane', trust_pills: 'labels', provenance_pills: 'always' })
    );
    global.fetch = spy;
    const p = await patchPreferences({ featured_tools: 'inline' });
    expect(p.featured_tools).toBe('inline');
    const [, opts] = spy.mock.calls[0];
    expect(opts.method).toBe('PATCH');
    expect(JSON.parse(opts.body as string)).toEqual({ featured_tools: 'inline' });
  });
});
```

#### 2.3 Implement the API client

`web/src/lib/lq-ai/api/preferences.ts`:

```ts
import { request } from './client';
import type { Preferences } from '../types';

export async function getPreferences(): Promise<Preferences> {
  return request<Preferences>('/users/me/preferences', { method: 'GET' });
}

export async function patchPreferences(patch: Partial<Preferences>): Promise<Preferences> {
  return request<Preferences>('/users/me/preferences', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  });
}
```

> If the existing `request` helper signature differs, adapt. Pattern matches `web/src/lib/lq-ai/api/savedPrompts.ts`.

Export from `api/index.ts`:

```ts
export * as preferencesApi from './preferences';
```

#### 2.4 Implement the store (server-synced with localStorage offline cache)

`web/src/lib/lq-ai/stores/preferences.ts`:

```ts
/**
 * Preferences store — server-synced via /users/me/preferences with
 * localStorage as an offline cache so the chrome doesn't flash defaults
 * on every page load.
 */
import { writable } from 'svelte/store';
import type { Preferences } from '../types';
import { getPreferences, patchPreferences } from '../api/preferences';

const STORAGE_KEY = 'lq-ai:preferences-cache';

export const defaultPreferences: Preferences = {
  featured_tools: 'prominent',
  workspace_layout: 'three_pane',
  trust_pills: 'labels',
  provenance_pills: 'always'
};

export const preferences = writable<Preferences>({ ...defaultPreferences });

export function readCache(): Preferences | null {
  if (typeof localStorage === 'undefined') return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try { return { ...defaultPreferences, ...JSON.parse(raw) }; } catch { return null; }
}

export function writeCache(p: Preferences): void {
  if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
}

/** Call once on auth-gate clear. Reads cache first for instant paint, then refreshes from server. */
export async function initPreferences(): Promise<void> {
  const cached = readCache();
  if (cached) preferences.set(cached);
  try {
    const fresh = await getPreferences();
    preferences.set(fresh);
    writeCache(fresh);
  } catch {
    // offline / unauthorized — keep cached or default
  }
}

/** Update a single preference: optimistic local update + server PATCH + cache write. */
export async function setPreference<K extends keyof Preferences>(key: K, value: Preferences[K]): Promise<void> {
  preferences.update((p) => {
    const next = { ...p, [key]: value };
    writeCache(next);
    return next;
  });
  try {
    const fresh = await patchPreferences({ [key]: value } as Partial<Preferences>);
    preferences.set(fresh);
    writeCache(fresh);
  } catch {
    // server-side rollback on failure — Wave F polish. Wave B v2 keeps optimistic state.
  }
}
```

#### 2.5 Store unit tests

`web/src/lib/lq-ai/__tests__/preferences.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { preferences, defaultPreferences, readCache, writeCache } from '../stores/preferences';

beforeEach(() => {
  localStorage.clear();
  preferences.set({ ...defaultPreferences });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('preferences store', () => {
  it('starts at defaults', () => {
    const p = get(preferences);
    expect(p.featured_tools).toBe('prominent');
    expect(p.workspace_layout).toBe('three_pane');
  });

  it('writeCache → readCache round-trips', () => {
    writeCache({ ...defaultPreferences, trust_pills: 'dots' });
    const c = readCache();
    expect(c?.trust_pills).toBe('dots');
  });

  it('readCache returns null on missing key', () => {
    expect(readCache()).toBeNull();
  });

  it('readCache merges missing keys with defaults', () => {
    localStorage.setItem('lq-ai:preferences-cache', JSON.stringify({ trust_pills: 'dots' }));
    const c = readCache();
    expect(c?.trust_pills).toBe('dots');
    expect(c?.featured_tools).toBe('prominent');
  });
});
```

#### 2.6 SettingsToggleGroup component

`web/src/lib/lq-ai/components/SettingsToggleGroup.svelte` — reusable radio-list. See v1's content (lines under "Build the SettingsToggleGroup component"); use it verbatim. (Self-contained, Practice-styled.)

#### 2.7 Settings sub-layout + Appearance page

`web/src/routes/lq-ai/settings/+layout.svelte` — see v1 plan section 2g; verbatim.

`web/src/routes/lq-ai/settings/appearance/+page.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { preferences, setPreference, initPreferences } from '$lib/lq-ai/stores/preferences';
  import SettingsToggleGroup from '$lib/lq-ai/components/SettingsToggleGroup.svelte';
  onMount(() => initPreferences());
</script>

<h2 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-4);">Appearance</h2>
<p class="lq-text-body" style="color: var(--lq-text-secondary); margin-bottom: var(--lq-space-6);">
  Tune how LQ.AI presents itself. Brave choices are on by default; you can dial them back if you want less ceremony.
</p>

<SettingsToggleGroup
  label="Featured tools"
  description="Where Enhance Prompt, Skill Creator, and the launcher live."
  value={$preferences.featured_tools}
  options={[
    { value: 'prominent', label: 'Prominent cards on dashboard', description: 'Featured cards with descriptions, plus ⌘K launcher.' },
    { value: 'inline',    label: 'Inline toolbar only', description: 'Small button row on every composer; less ceremony.' }
  ]}
  onChange={(v) => setPreference('featured_tools', v as any)}
/>

<SettingsToggleGroup
  label="Workspace layout"
  description="How matter views compose (Wave C)."
  value={$preferences.workspace_layout}
  options={[
    { value: 'three_pane', label: 'Three panes', description: 'Matter rail · chat · outputs panel (default).' },
    { value: 'two_pane',   label: 'Two panes',   description: 'Chat · outputs panel; matter rail collapsed.' },
    { value: 'one_pane',   label: 'Single pane', description: 'Chat only; docs open in a modal.' }
  ]}
  onChange={(v) => setPreference('workspace_layout', v as any)}
/>

<SettingsToggleGroup
  label="Trust pills"
  description="The ambient indicators in the top bar."
  value={$preferences.trust_pills}
  options={[
    { value: 'labels', label: 'Labels',  description: '"● self-hosted" — full label on the pill.' },
    { value: 'dots',   label: 'Dots',    description: 'Just the dot; label appears on hover.' }
  ]}
  onChange={(v) => setPreference('trust_pills', v as any)}
/>

<SettingsToggleGroup
  label="Provenance pills"
  description="The per-message skill/tier/provider/audit row (Wave D)."
  value={$preferences.provenance_pills}
  options={[
    { value: 'always',    label: 'Always shown', description: 'Pills under every AI reply.' },
    { value: 'collapsed', label: 'Collapsed; expand on hover', description: 'Single "🔍 details" affordance per reply.' }
  ]}
  onChange={(v) => setPreference('provenance_pills', v as any)}
/>
```

#### 2.8 Wire settings-cog in main layout

In `web/src/routes/lq-ai/+layout.svelte`, add a `⚙` link beside `AmbientTrustChrome`:

```svelte
<div style="display: inline-flex; align-items: center; gap: var(--lq-space-3);">
  <AmbientTrustChrome />
  <a href="/lq-ai/settings/appearance" aria-label="Settings" title="Settings" style="color: var(--lq-text-secondary); text-decoration: none; padding: var(--lq-space-1) var(--lq-space-2); border-radius: var(--lq-radius-sm);">⚙</a>
</div>
```

#### 2.9 Verify + commit

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
cd web && npm run check 2>&1 | grep -E "(preferences|settings|SettingsToggleGroup)" | head -10
```

Smoke (stack running): rebuild web, log in, visit `/lq-ai/settings/appearance`, toggle Featured tools → Inline, reload — toggle persists; check browser DevTools Network tab — `PATCH /users/me/preferences` request fires on toggle change.

Commit (one atomic — preferences foundation):

```bash
git add web/src/lib/lq-ai/api/preferences.ts web/src/lib/lq-ai/api/index.ts web/src/lib/lq-ai/stores/preferences.ts web/src/lib/lq-ai/types.ts web/src/lib/lq-ai/__tests__/preferences*.test.ts
git commit -s -m "feat(web): server-synced preferences store + API client

Wires the 4 personalization toggles (spec §4.3) to GET/PATCH
/users/me/preferences (shipped on main per migration 0015).
localStorage acts as offline cache. types.ts gains User.role
(migration 0017) and Preferences shape.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Commit (atomic — Settings/Appearance surface):

```bash
git add web/src/lib/lq-ai/components/SettingsToggleGroup.svelte web/src/routes/lq-ai/settings/+layout.svelte web/src/routes/lq-ai/settings/appearance/+page.svelte web/src/routes/lq-ai/+layout.svelte
git commit -s -m "feat(web): Settings/Appearance page wires real preferences API

/lq-ai/settings/appearance with the 4 toggles per spec §4.3; settings-
cog link added to top-bar chrome. Toggles round-trip through
PATCH /users/me/preferences and persist server-side; localStorage
cache for offline paint.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2b: Account settings (real MFA enrollment + export/delete + password)

**Files:**
- Create: `web/src/lib/lq-ai/components/MfaEnrollmentPanel.svelte`
- Create: `web/src/lib/lq-ai/components/AccountExportDeletePanel.svelte`
- Create: `web/src/routes/lq-ai/settings/account/+page.svelte`

Account page composes the three panels. Each panel wraps existing API calls.

#### 2b.1 MfaEnrollmentPanel

Calls `POST /auth/mfa/setup` (returns TOTP secret + QR data), shows QR + secret to user, accepts verification code, calls `POST /auth/mfa/enable`. Disable flow uses `POST /auth/mfa/disable`. Practice-styled. State: `idle | setting-up | verifying | enabled`.

For the QR rendering, use an inline SVG QR (write a tiny QR helper using an existing library if one is already in `web/package.json`, otherwise display the otpauth URL as text with a "Scan with your authenticator" caption — Wave F can polish the QR rendering).

If the deployment has `LQ_AI_MFA_MANDATORY=true`, show a banner indicating MFA is required. Read this from a config endpoint or the user response if one of those carries the flag.

#### 2b.2 AccountExportDeletePanel

Two buttons:
- **Export my data** — `POST /users/me/export` returns a `job_id`. Poll `GET /users/me/export/{job_id}` until complete; surface a download link.
- **Delete my account** — confirmation modal with typed-name verification → `POST /users/me/delete` (asynchronous; surfaces a cancel option via `POST /users/me/delete/cancel`).

Practice-styled. Destructive actions use the existing `lq-btn-danger` class from Wave A.

#### 2b.3 Account page

```svelte
<script lang="ts">
  import MfaEnrollmentPanel from '$lib/lq-ai/components/MfaEnrollmentPanel.svelte';
  import AccountExportDeletePanel from '$lib/lq-ai/components/AccountExportDeletePanel.svelte';
</script>

<h2 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-4);">Account</h2>
<p class="lq-text-body" style="color: var(--lq-text-secondary); margin-bottom: var(--lq-space-6);">
  Authentication, data export, and account closure.
</p>

<section style="margin-bottom: var(--lq-space-6);">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">Multi-factor authentication</h3>
  <MfaEnrollmentPanel />
</section>

<section style="margin-bottom: var(--lq-space-6);">
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">Change password</h3>
  <p class="lq-text-body" style="color: var(--lq-text-secondary);">
    Use the change-password flow under your user menu, or visit <a href="/lq-ai/change-password" style="color: var(--lq-accent);">/lq-ai/change-password</a> directly.
  </p>
</section>

<section>
  <h3 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-3);">Your data</h3>
  <AccountExportDeletePanel />
</section>
```

#### 2b.4 Commit

One atomic commit per panel + the page:

- Commit A: `MfaEnrollmentPanel.svelte`
- Commit B: `AccountExportDeletePanel.svelte`
- Commit C: `account/+page.svelte` composition

(Verify svelte-check + tests pass between each.)

Commit message pattern: `feat(web): account/<area> — <summary> (D5/D6 wiring)`.

---

### Task 3: Trust & Privacy page (wires real `/admin/usage` + `/inference/tier-config`)

**Files:** as listed in File structure (4 cards + page).

#### 3.1 Real-data cards

**TrustExternalTurnsCard** wires to `GET /admin/usage` (existing endpoint). Expected response shape per `/docs/api/backend-openapi.yaml`. Card displays:
- Today's count (filter the response to today)
- 7-day total

If the user lacks admin permission, the card shows a polite message: "External-turn counts visible to admins only — admins can <a>view here →</a>". (`/admin/usage` is admin-gated.)

**TrustProvidersCard** wires to `GET /inference/tier-config` (returns the configured tier policy, which contains provider list per tier). Render a flat list of unique providers with their encryption status (encrypted-at-rest per ADR 0011 ships with key derivation; display "Encrypted at rest" pill if `api_key_encrypted` is present, or "BYOK plaintext (legacy)" otherwise).

**TrustDataResidencyCard** — static, V2-FALLBACK. Hardcode the docker-compose hostnames.

**TrustArtifactsCard** — links to in-repo docs paths (already covered in v1).

#### 3.2 Page composition

`/lq-ai/trust/+page.svelte` — 2×2 grid as v1 spec'd.

#### 3.3 Commit

One commit per card (4 commits) + one for the page composition. Or grouped to 2 commits if it reads cleaner — implementer discretion. Aim for clear scope per commit.

---

### Task 3b: Session-timeout warning + activity tracker

**Files:**
- Create: `web/src/lib/lq-ai/stores/sessionActivity.ts`
- Create: `web/src/lib/lq-ai/components/SessionTimeoutWarning.svelte`
- Create: `web/src/lib/lq-ai/__tests__/sessionActivity.test.ts`
- Modify: `web/src/routes/lq-ai/+layout.svelte` (mount the warning component)

#### 3b.1 Activity tracker store

PRD §5.1 defaults: 8h absolute / 30m idle timeout. Backend's `/auth/refresh` (modified by migration 0018) checks `user_sessions.last_active_at` and refuses if idle > 30m. Frontend needs to:
- Track user activity (mousemove / keydown / click / scroll — debounced to once per minute)
- POST `/auth/refresh` on activity to bump `last_active_at`
- Show a warning at the 25-minute idle mark: "Session expires in 5 minutes. [Continue working]"
- If user clicks Continue → POST `/auth/refresh` immediately
- If 30 min elapses without activity → redirect to `/lq-ai/login`

`sessionActivity.ts`:

```ts
import { writable } from 'svelte/store';
import { authApi } from '$lib/lq-ai/api';

const IDLE_WARN_AT_MS = 25 * 60 * 1000;  // 25 minutes
const IDLE_LOGOUT_AT_MS = 30 * 60 * 1000;  // 30 minutes
const REFRESH_DEBOUNCE_MS = 60 * 1000;     // refresh at most once per minute

export const sessionActivity = writable({
  lastActivityMs: Date.now(),
  showWarning: false
});

let watchInterval: ReturnType<typeof setInterval> | null = null;
let lastRefreshMs = 0;

export function noteActivity(): void {
  const now = Date.now();
  sessionActivity.update((s) => ({ lastActivityMs: now, showWarning: false }));
  if (now - lastRefreshMs > REFRESH_DEBOUNCE_MS) {
    lastRefreshMs = now;
    authApi.refresh().catch(() => { /* silent */ });
  }
}

export function startTracker(onLogout: () => void): void {
  if (watchInterval) return;
  watchInterval = setInterval(() => {
    sessionActivity.update((s) => {
      const idleMs = Date.now() - s.lastActivityMs;
      if (idleMs >= IDLE_LOGOUT_AT_MS) {
        onLogout();
        return { ...s, showWarning: false };
      }
      return { ...s, showWarning: idleMs >= IDLE_WARN_AT_MS };
    });
  }, 30_000); // check twice per minute
}

export function stopTracker(): void {
  if (watchInterval) { clearInterval(watchInterval); watchInterval = null; }
}
```

#### 3b.2 Activity tracker test (helper-level)

```ts
import { describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { sessionActivity, noteActivity } from '../stores/sessionActivity';

vi.mock('../api/auth', () => ({ refresh: vi.fn().mockResolvedValue(undefined) }));

describe('sessionActivity', () => {
  it('noteActivity updates lastActivityMs and clears warning', () => {
    sessionActivity.set({ lastActivityMs: 0, showWarning: true });
    noteActivity();
    const s = get(sessionActivity);
    expect(s.lastActivityMs).toBeGreaterThan(0);
    expect(s.showWarning).toBe(false);
  });
});
```

#### 3b.3 SessionTimeoutWarning component

```svelte
<script lang="ts">
  import { sessionActivity, noteActivity } from '$lib/lq-ai/stores/sessionActivity';
</script>

{#if $sessionActivity.showWarning}
  <div role="alert" class="lq-toast" style="position: fixed; bottom: var(--lq-space-4); right: var(--lq-space-4); background: var(--lq-canvas); border: 1px solid var(--lq-warn-border); border-left: 3px solid var(--lq-warn); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); box-shadow: 0 8px 24px rgba(0,0,0,0.1); max-width: 360px; z-index: 60;">
    <p class="lq-text-body"><strong>Session expires in 5 minutes.</strong></p>
    <p class="lq-text-caption" style="margin-top: var(--lq-space-1);">You'll need to log in again if you stay idle.</p>
    <button type="button" on:click={noteActivity} class="lq-btn-primary" style="margin-top: var(--lq-space-3);">Continue working</button>
  </div>
{/if}
```

#### 3b.4 Mount in layout

In `web/src/routes/lq-ai/+layout.svelte`, inside the `lq-shell` wrapper but outside the auth-exempt block:

```svelte
<script>
  // existing imports
  import { onMount, onDestroy } from 'svelte';
  import { startTracker, stopTracker, noteActivity } from '$lib/lq-ai/stores/sessionActivity';
  import { goto } from '$app/navigation';
  import SessionTimeoutWarning from '$lib/lq-ai/components/SessionTimeoutWarning.svelte';

  onMount(() => {
    if (!isAuthExempt(pathname)) {
      startTracker(() => goto('/lq-ai/login?reason=idle-timeout'));
      const handler = () => noteActivity();
      ['mousedown', 'keydown', 'scroll', 'touchstart'].forEach((e) =>
        window.addEventListener(e, handler, { passive: true })
      );
      onDestroy(() => {
        stopTracker();
        ['mousedown', 'keydown', 'scroll', 'touchstart'].forEach((e) =>
          window.removeEventListener(e, handler)
        );
      });
    }
  });
</script>

<!-- in template, inside the .lq-shell, before DualBrandingFooter -->
<SessionTimeoutWarning />
```

#### 3b.5 Commit

One commit:

```bash
git add web/src/lib/lq-ai/stores/sessionActivity.ts web/src/lib/lq-ai/components/SessionTimeoutWarning.svelte web/src/lib/lq-ai/__tests__/sessionActivity.test.ts web/src/routes/lq-ai/+layout.svelte
git commit -s -m "feat(web): session-timeout warning + activity tracker (M-Sec.1 wiring)

Mounts a 25-minute idle warning + 30-minute auto-logout per PRD §5.1
defaults. Activity (mouse/key/scroll/touch) refreshes the access token
via /auth/refresh (debounced to once per minute). If idle for 30 min,
redirects to /lq-ai/login?reason=idle-timeout.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Guided Dashboard at /lq-ai (replaces Task 1 redirect)

**Files:** as listed in File structure (5 components + page replace).

#### 4.1 Welcome + Trust panel

Verbatim from v1 plan sections 4a + 4b — preserved here for self-contained reference. The trust panel reads tier from `GET /inference/current-tier` (new in v2):

```svelte
<!-- GuidedDashboardTrustPanel.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import TrustPill from './TrustPill.svelte';
  import { inferenceTierApi } from '$lib/lq-ai/api';
  let tierLabel = 'default';
  onMount(async () => {
    try {
      const t = await inferenceTierApi.getCurrentTier();
      tierLabel = t.tier ?? 'default';
    } catch { /* stay at default */ }
  });
</script>

<section style="background: var(--lq-inset-secure); border: 1px solid var(--lq-accent-border); border-radius: var(--lq-radius-lg); padding: var(--lq-space-4); margin-bottom: var(--lq-space-6); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--lq-space-3);">
  <div>
    <p class="lq-text-label">Your data</p>
    <p class="lq-text-body" style="margin-top: var(--lq-space-1);">In your firm's stack · audit on · tier: {tierLabel}</p>
  </div>
  <div style="display: inline-flex; gap: var(--lq-space-2); align-items: center;">
    <TrustPill variant="secure" label="● self-hosted" />
    <a href="/lq-ai/trust" class="lq-text-body" style="color: var(--lq-accent); text-decoration: none;">View detail →</a>
  </div>
</section>
```

#### 4.2 Featured tools row

Same as v1 section 4c, with the addition of an `inferenceTier` import if it's used in tile copy. Honors `$preferences.featured_tools === 'prominent'` toggle.

#### 4.3 Getting-started checklist (real signals)

In v1 the checklist mostly used localStorage flags. In v2 use real signals:

| Item | Signal source (post-merge) |
|---|---|
| Log in & rotate password | `user.must_change_password === false` |
| Run a skill on a document | `messagesApi.list(...)` filtered to messages where `skill_id` IS NOT NULL, with `limit=1`. If any exist → done. |
| Try Enhance Prompt | `GET /api/v1/users/me/enhance-prompt-history` if available, else localStorage flag set in Task 6 component on first use. (Endpoint shape: implementer verifies; if not yet exposed, use localStorage.) |
| Attach a knowledge base | `knowledgeBasesApi.list(...)` filtered to KBs the user has attached. If any → done. |
| Save a prompt as a skill | `userSkillsApi.listUserSkills('user')` — if `length > 0` → done. |

Implementer queries each endpoint on dashboard mount; updates `checklist` reactively when done.

#### 4.4 Recent Activity

Recent chats from `GET /api/v1/chats/search?q=&limit=5` (FTS endpoint accepts empty `q` to return most recent — verify in OpenAPI sketch). Render as a clickable list linking to `/lq-ai/chats?id={chatId}`.

Recent matters card stays a placeholder pointing at Wave C.

#### 4.5 Page composition

`web/src/routes/lq-ai/+page.svelte` — replace v1's redirect stub with the dashboard composition (5 components). See v1 plan section 4f for shape; adapt to call `initPreferences()` and the real signal-fetching functions.

#### 4.6 Commits

3-5 atomic commits across this task (one per component or grouped logically). Final commit replaces `/lq-ai/+page.svelte` with the composition.

---

### Task 5 + 5b: Admin Developer Support tab + three-role gating

**Files:** as listed.

#### 5a. Three-role gating in `tabs.ts`

Refine `isTabVisible('admin', user)`:

```ts
export function isTabVisible(id: TabId, user: User | null): boolean {
  const tab = TABS.find((t) => t.id === id);
  if (!tab) return false;
  if (tab.adminOnly) {
    // Three-role gate: 'admin' role OR legacy is_admin === true (back-compat)
    return user?.role === 'admin' || user?.is_admin === true;
  }
  return true;
}
```

Add corresponding tests to `tabs.test.ts`:

```ts
const viewerUser: User = { ...memberUser, role: 'viewer', is_admin: false };
const adminUserNoRole: User = { ...adminUser, role: 'admin' };

it('hides admin tab for viewer role', () => {
  expect(isTabVisible('admin', viewerUser)).toBe(false);
});
it('hides admin tab for member role', () => {
  expect(isTabVisible('admin', { ...memberUser, role: 'member' })).toBe(false);
});
it('shows admin tab for admin role even if is_admin flag is stale', () => {
  expect(isTabVisible('admin', { ...adminUserNoRole, is_admin: false })).toBe(true);
});
```

#### 5b. Admin Developer Support card-set

Four cards on the page:
- **DevApiDocsCard** — Swagger UI, ReDoc, Gateway docs, OpenAPI JSON
- **DevApiPlaygroundCard** — JWT copy
- **DevRoleManagementCard** — Lists users via `GET /admin/users` (existing endpoint per OpenAPI); each row has a role-select dropdown that calls `PATCH /admin/users/{user_id}/role`
- **DevForkCallout** — "Build your own frontend"

Page composition + admin sub-nav strip per v1 plan section 5d/5e.

#### 5c. /metrics link

Add a small "Observability" line to DevApiDocsCard pointing at `/metrics` (Prometheus) — note in caption that the deployment must expose the port to the operator (default: gateway port 8001, api port 8000).

#### 5d. Commits

Two commits:
- Commit A: `tabs.ts` + tabs.test.ts three-role refinement
- Commit B: Admin Developer Support tab + sub-nav + 4 cards

---

### Task 6: Enhance Prompt inline UX (✨ button on composer)

> Pulled forward from Wave D. Spec §7.1.

**Files:**
- Create: `web/src/lib/lq-ai/api/enhancePrompt.ts`
- Create: `web/src/lib/lq-ai/components/EnhancePromptExpansion.svelte`
- Create: `web/src/lib/lq-ai/__tests__/EnhancePromptExpansion.test.ts`
- Create: `web/src/lib/lq-ai/__tests__/enhancePrompt-api.test.ts`
- Modify: existing composer area in `web/src/routes/lq-ai/chats/+page.svelte` (the relocated chat shell from Task 1) — add the ✨ button

#### 6.1 API client

```ts
// web/src/lib/lq-ai/api/enhancePrompt.ts
import { request } from './client';

export interface EnhancePromptRequest {
  text: string;
  context?: { skill_name?: string; chat_id?: string };
}
export interface EnhancePromptResponse {
  interaction_id: string;
  enhanced_text: string;
  model_used: string;
}

export async function enhance(req: EnhancePromptRequest): Promise<EnhancePromptResponse> {
  return request('/enhance-prompt', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req)
  });
}

export async function recordOutcome(interactionId: string, outcome: 'used' | 'edited' | 'rejected'): Promise<void> {
  await request(`/enhance-prompt/${interactionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ outcome })
  });
}
```

Verify exact response shape vs the backend's actual schema during implementation.

#### 6.2 EnhancePromptExpansion component

Renders Original (dimmed) + Enhanced cards with three actions: `[Use enhanced]` · `[Edit enhanced]` · `[Keep original]`. State machine:

```ts
type ExpansionState =
  | { kind: 'closed' }
  | { kind: 'loading'; original: string }
  | { kind: 'shown'; original: string; enhanced: string; interactionId: string; modelUsed: string }
  | { kind: 'error'; original: string; message: string };
```

Props:
- `originalText: string` (the composer content)
- `onUseEnhanced: (enhanced: string, interactionId: string) => void` — parent updates composer + records `outcome=used`
- `onEditEnhanced: (enhanced: string, interactionId: string) => void` — parent loads enhanced into composer for editing + records `outcome=edited`
- `onKeepOriginal: (interactionId: string | null) => void` — parent dismisses + records `outcome=rejected` if interactionId

#### 6.3 Composer integration

In the relocated chat shell at `web/src/routes/lq-ai/chats/+page.svelte`, add a ✨ button beside the existing Send button. On click, opens `EnhancePromptExpansion` inline. Wire the three action handlers to update the composer state.

#### 6.4 Localstorage flag

When the user uses/edits/keeps an enhancement at least once, set `localStorage.setItem('lq-ai:onboarded:enhance', 'true')` so the dashboard checklist item flips done.

#### 6.5 Commits

Two commits:
- API client + tests
- Component + composer integration

---

### Task 7: Skill Detail "View source" tab

> Pulled forward from Wave D. Spec §4.2 (Skill detail) and §7.2 (skill creator).

**Files:**
- Create: `web/src/routes/lq-ai/skills/[id]/+page.svelte` (NEW — currently only `[id]/edit` exists)
- Create: `web/src/lib/lq-ai/components/SkillDetailTabs.svelte`
- Create: `web/src/lib/lq-ai/components/SkillSourceView.svelte`
- (Optional) Create: `web/src/lib/lq-ai/api/skillContents.ts` OR extend `web/src/lib/lq-ai/api/skills.ts`

The detail page has 4 tabs in the design spec (Use it · View source · Try it · Versions). Wave B v2 ships **Use it** and **View source** only; Try it and Versions stay deferred to Wave D.

#### 7.1 SkillDetailTabs component

Tab strip with two tabs at Wave B v2:

```svelte
<script lang="ts">
  export let activeTab: 'use' | 'source' = 'use';
  export let onTabChange: (tab: 'use' | 'source') => void;
</script>

<nav role="tablist" class="lq-skill-tabs">
  <button role="tab" aria-selected={activeTab === 'use'} class:active={activeTab === 'use'} on:click={() => onTabChange('use')}>Use it</button>
  <button role="tab" aria-selected={activeTab === 'source'} class:active={activeTab === 'source'} on:click={() => onTabChange('source')}>View source</button>
  <button role="tab" aria-disabled="true" disabled title="Wave D">Try it</button>
  <button role="tab" aria-disabled="true" disabled title="Wave D">Versions</button>
</nav>

<style>
  .lq-skill-tabs { display: flex; gap: var(--lq-space-4); border-bottom: 1px solid var(--lq-border); padding: 0 var(--lq-space-4); }
  .lq-skill-tabs button { background: transparent; border: 0; padding: var(--lq-space-3) var(--lq-space-1); color: var(--lq-text-secondary); cursor: pointer; border-bottom: 2px solid transparent; font-size: 14px; font-weight: 500; }
  .lq-skill-tabs button.active { color: var(--lq-accent); border-bottom-color: var(--lq-accent); }
  .lq-skill-tabs button[disabled] { color: var(--lq-text-tertiary); cursor: not-allowed; }
</style>
```

#### 7.2 SkillSourceView component

Fetches `GET /skills/{name}/contents` and renders the SKILL.md as raw markdown in a `<pre>` with syntax highlighting if a markdown component is already imported in the codebase (check `web/src/lib/components/` for existing markdown renderers; reuse). If none, render as a plain `<pre>` with monospace.

Includes a "Copy raw" button and a "Frontmatter inputs" sub-section that lists the skill's input fields from `GET /skills/{name}/inputs`.

#### 7.3 Skill detail page composition

```svelte
<!-- web/src/routes/lq-ai/skills/[id]/+page.svelte -->
<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { userSkillsApi } from '$lib/lq-ai/api';
  import SkillDetailTabs from '$lib/lq-ai/components/SkillDetailTabs.svelte';
  import SkillSourceView from '$lib/lq-ai/components/SkillSourceView.svelte';

  let activeTab: 'use' | 'source' = 'use';
  let skill: any = null;

  $: skillId = $page.params.id;

  onMount(async () => {
    if (!skillId) return;
    skill = await userSkillsApi.getUserSkill(skillId).catch(() => null);
  });
</script>

<div style="padding: var(--lq-space-6); max-width: 1100px;">
  {#if skill}
    <header style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--lq-space-4);">
      <div>
        <h1 class="lq-text-page-h">{skill.display_name}</h1>
        <p class="lq-text-caption" style="color: var(--lq-text-tertiary); margin-top: var(--lq-space-1);">{skill.slug} · v{skill.version}</p>
      </div>
      <a href={`/lq-ai/skills/${skill.id}/edit`} class="lq-btn-primary">Edit</a>
    </header>

    <SkillDetailTabs {activeTab} onTabChange={(t) => (activeTab = t)} />

    <div style="margin-top: var(--lq-space-4);">
      {#if activeTab === 'use'}
        <article class="lq-text-body" style="white-space: pre-wrap;">
          {skill.description ?? '(no description)'}
        </article>
      {:else if activeTab === 'source'}
        <SkillSourceView slug={skill.slug} />
      {/if}
    </div>
  {:else}
    <p class="lq-text-body" style="color: var(--lq-text-secondary);">Loading skill…</p>
  {/if}
</div>
```

#### 7.4 Commits

Two commits: component pair (`SkillDetailTabs` + `SkillSourceView`), then page composition.

---

### Task 8: Cypress E2E for Wave B v2 surfaces

**File:** `web/cypress/e2e/wave-b-surfaces.cy.ts`

Five-to-seven tests covering:
1. Post-login lands on Guided Dashboard (not chat shell)
2. Chats tab routes to `/lq-ai/chats` (not ComingSoonModal)
3. Settings/Appearance toggle persists across reload (via real backend)
4. `/lq-ai/trust` renders all four cards
5. Admin/Developer Support renders with API doc links + JWT copy
6. ✨ Enhance Prompt button on composer shows Original/Enhanced cards
7. Skill detail shows two-tab View it / View source flow

Body shape: v1 plan section 6, expanded with tests 6 + 7.

#### Commit

```bash
git add web/cypress/e2e/wave-b-surfaces.cy.ts
git commit -s -m "test(web): Cypress E2E smoke for Wave B v2 surfaces

Seven tests covering the new surfaces: dashboard, relocated chats,
appearance-toggle persistence (server-synced), trust page, developer
support tab, Enhance Prompt flow, and skill detail tabs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Final verification + push

- [ ] `cd web && npm run test:frontend -- --run` — expect all tests pass (~115+)
- [ ] `cd web && npm run check 2>&1 | grep -E "(<wave-b-v2-files>)" | head -30` — expect 0 new errors
- [ ] Stack smoke (with `docker compose up -d --no-deps --build web`):
  1. Log in → land on Guided Dashboard
  2. Chats tab → chat shell renders, history loads
  3. Skills tab → skills list with team chips + Practice styling
  4. Settings cog → Appearance: toggle Featured tools → Inline, refresh, persists
  5. Settings → Account: MFA panel renders; export/delete buttons visible
  6. /lq-ai/trust: 4 cards render, external-turns counter populated (admin)
  7. Admin → Developer Support: Swagger link works; Copy token works; role-list visible
  8. Click Matters tab → ComingSoonModal (Wave C)
  9. ✨ button on composer (in /lq-ai/chats): types a prompt, clicks ✨, sees Original/Enhanced expansion
  10. /lq-ai/skills/{id} → tabs render; View source loads SKILL.md
  11. Idle 25 minutes → SessionTimeoutWarning appears (or test with a temporary 1-minute threshold)
- [ ] Push: `git push origin kk/main/Frontend_Design`

---

## Self-review

**1. Spec coverage:**

| Spec section | Wave B v2 task |
|---|---|
| §4.1 Top-tab nav (chats available) | T1 |
| §4.2 Home (Guided Dashboard) | T4 |
| §4.2 Chats (relocated) | T1 |
| §4.2 Skill detail (Use it / View source tabs) | T7 |
| §4.2 Trust & Privacy | T3 |
| §4.2 Admin (extensions: Developer Support, sub-nav, role management) | T5 |
| §4.2 Settings (Appearance, Account) | T2, T2b |
| §4.3 Personalization toggles (server-synced) | T2 |
| §5.1 Ambient chrome (tier label real) | T4 |
| §5.3 JIT (session-timeout warning is a mid-action/post-action variant) | T3b |
| §6.4 Getting-started checklist (real detection signals) | T4 |
| §7.1 Enhance Prompt UX | T6 |
| §10.4 Developer Support tab content | T5 |

**2. Placeholder scan:** Code annotations labeled `V2-FALLBACK` are intentional and mark the remaining 4 places where Wave B v2 still uses static data (trust/data-residency, trust/audit-health, admin/developer/openapi-urls hardcoded, matters API). Not plan placeholders.

**3. Type consistency:** `User` shape (with `role`), `Preferences`, `EnhancePromptResponse`, `ChecklistItem` (from v1), `TabId`, `TrustVariant` all coherent across tasks. Implementer verifies the actual backend shapes (especially `User.role` values and `Preferences` key casing) at the start of Task 2.

**4. Scope:** ~11 logical tasks, ~22-25 atomic commits expected. Doesn't bleed into Wave C/D/E.

**5. Backend dependency match:** Every endpoint referenced (~14 endpoints across tasks) maps to an OpenAPI path in `docs/api/backend-openapi.yaml` confirmed during the audit.

---

## Open implementation questions (resolve during execution)

1. **`User.role` field on `/users/me`** — **RESOLVED 2026-05-11.** Backend exposes `role` per migration 0017; OpenAPI sketch confirms enum `[admin, member, viewer]` (NOT `team_admin` — the earlier plan draft drifted from PRD §5.2). Frontend uses backend's enum verbatim; admin tab gates on `role === 'admin'` with `is_admin` as fallback for legacy callers. See spec §4.1.1 for the role enum contract.
2. **`Preferences` JSON casing** — confirm snake_case vs camelCase by curling `/users/me/preferences`. Adjust `Preferences` type to match. Decide at Task 2.1.
3. **`chats/search` empty-query semantics** — does `GET /chats/search?q=&limit=5` return most-recent, or does it require a query string? If it requires a query, fall back to `GET /chats?limit=5` for the dashboard "Recent chats" card.
4. **`/admin/users` listing shape** — for the role-management card in Task 5, what's the response shape? Adjust the card accordingly.
5. **Enhance Prompt body shape** — confirm `{text, context}` vs `{prompt, context}` etc. Adjust API client at Task 6.1.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-11-m1-frontend-wave-b-v2-post-merge.md`. v1 superseded.

Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review on the higher-judgment tasks (T2, T4, T6), fast iteration. Same rhythm as Wave A.

**2. Inline Execution** — batch through tasks in this session with checkpoints.

Which approach?
