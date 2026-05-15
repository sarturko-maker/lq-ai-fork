# M1 Frontend — Wave C (Matters skeleton) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Matters surface end-to-end — `/lq-ai/matters` list of matters and `/lq-ai/matters/[id]` 2-pane workspace (matter rail · embedded chat). Closes spec §4.2's Matters row and unblocks "in-house counsel works on Acme NDA inside a matter" as the canonical legal-workspace narrative.

**Architecture:** Per Kevin's 2026-05-12 architectural call: extract `<ChatPanel>` from `/lq-ai/chats/+page.svelte` (currently 590 lines of route-scoped code) into a reusable component. `/lq-ai/chats` becomes a thin wrapper around it; `/lq-ai/matters/[id]` mounts the same component on the right side of the matter rail. Naming: strings-only — UI says "Matter" / "Matters", code stays `Project` / `projectsApi`.

**Scope NOT in Wave C** (per architectural calls 2026-05-12):
- Outputs panel — moved to Wave D (no first-class draft/redline data model in M1; can render over `messages.applied_skills` later)
- Knowledge browser + KB-to-matter attach loop — moved to Wave D (will draw inspiration from OpenLoris GUD pattern)
- Saved Prompts dedicated surface — Wave D
- Sandbox onboarding (`matters.is_sandbox` column) — Wave E
- Receipts mode + Citation Engine UI — Wave D
- `matters` tab still uses ComingSoonModal *after* Wave C? NO — Wave C flips it to `available: true`

**Tech stack:** SvelteKit 2 · TypeScript · Tailwind v4 · Vitest · Cypress · Practice visual system from Wave A.

**Anchors:** [Spec §4.2 Primary surfaces](../specs/2026-05-10-m1-frontend-design.md#42-primary-surfaces) · [Spec §10 Dev extensibility](../specs/2026-05-10-m1-frontend-design.md#10-theming-customization-and-developer-extensibility-open-source-posture) · [PRD §3.11 Projects (M1)](../../PRD.md#311-projects-m1) · [Backend OpenAPI sketch](../../api/backend-openapi.yaml) · [Wave B v2 plan (predecessor)](2026-05-11-m1-frontend-wave-b-v2-post-merge.md).

---

## Backend endpoints (real, shipped on main)

| Endpoint | Used by task |
|---|---|
| `GET /api/v1/projects?archived=false` | T1 (Matters list), T8 (Dashboard recent matters) |
| `POST /api/v1/projects` | T7 (New Matter modal) |
| `GET /api/v1/projects/{id}` | T3 (Matter rail metadata) |
| `PATCH /api/v1/projects/{id}` | T4 (Matter rail inline rename, privileged toggle, tier-floor) |
| `DELETE /api/v1/projects/{id}` | T4 (Archive matter) |
| `POST /api/v1/projects/{id}/files` | T5 (Attach file to matter) |
| `DELETE /api/v1/projects/{id}/files/{file_id}` | T5 (Detach file) |
| `POST /api/v1/projects/{id}/skills` | T6 (Attach skill to matter) |
| `DELETE /api/v1/projects/{id}/skills/{skill_name}` | T6 (Detach skill) |
| `GET /api/v1/chats?project_id={id}` | T3 (Chat list for the matter in rail) |
| `POST /api/v1/chats` (with `project_id`) | T3 (New chat in matter) |

All confirmed live in `docs/api/backend-openapi.yaml`.

---

## File structure

### Net-new files

| File | Responsibility | Owning task |
|---|---|---|
| `web/src/lib/lq-ai/components/ChatPanel.svelte` | Extracted reusable chat composition (sidebar + message list + composer + AmbientFooter). Props: `projectIdFilter?: string`, `initialChatId?: string` | Task 0 (extraction) |
| `web/src/lib/lq-ai/components/MatterCard.svelte` | Single matter card for the list grid | Task 1 |
| `web/src/lib/lq-ai/components/MatterRail.svelte` | Left rail of matter workspace: metadata, file/skill attachments, chat list | Task 3 |
| `web/src/lib/lq-ai/components/MatterRailMetadata.svelte` | Editable rail section: name, description, privileged, tier floor | Task 4 |
| `web/src/lib/lq-ai/components/MatterRailAttachments.svelte` | File + skill attach/detach UI (drag-and-drop file picker + skill multi-select) | Task 5 / 6 |
| `web/src/lib/lq-ai/components/NewMatterModal.svelte` | "Create matter" modal (name + slug + description) | Task 7 |
| `web/src/routes/lq-ai/matters/+page.svelte` | Matter list (card grid) | Task 1 |
| `web/src/routes/lq-ai/matters/[id]/+page.svelte` | 2-pane workspace composition | Task 3 |
| `web/src/lib/lq-ai/__tests__/ChatPanel.test.ts` | Smoke test on the extracted component | Task 0 |
| `web/src/lib/lq-ai/__tests__/MatterCard.test.ts` | Card rendering test | Task 1 |
| `web/src/lib/lq-ai/__tests__/projects-attach-api.test.ts` | API client tests for attach/detach helpers | Task 5 |
| `web/cypress/e2e/wave-c-matters.cy.ts` | E2E for matters list → workspace → embedded chat | Task 9 |

### Modified files

| File | Change | Task |
|---|---|---|
| `web/src/lib/lq-ai/api/projects.ts` | Add `attachFile`, `detachFile`, `attachSkill`, `detachSkill` helpers | Task 5 / 6 |
| `web/src/routes/lq-ai/chats/+page.svelte` | Refactor to thin wrapper around `<ChatPanel>` (preserves behavior identically) | Task 0 |
| `web/src/lib/lq-ai/tabs.ts` | Flip `matters` to `available: true`, remove `shipsInWave: 'C'` | Task 8 |
| `web/src/lib/lq-ai/__tests__/tabs.test.ts` | Update `'matters'` assertion to `true` group | Task 8 |
| `web/src/lib/lq-ai/components/RecentActivity.svelte` | Wire matters card to real `projectsApi.listProjects({ limit: 5 })` | Task 8 |

### Files NOT touched

- Backend (`api/`) — Wave C is frontend only. All endpoints already shipped.
- `web/src/lib/lq-ai/components/ChatSidebar.svelte` and friends — they get composed inside `<ChatPanel>` unchanged.
- Wave A primitives (TrustPill, TopTabBar, ComingSoonModal) — used as-is.

---

## Testing approach

Vitest suite grows from 157 (post Wave B v2) to ~170-175 by Wave C end:
- ChatPanel smoke (3-4 tests after extraction — verify it mounts and accepts props)
- MatterCard render variants (2-3 tests)
- projects-attach-api (4 tests — attachFile/detachFile/attachSkill/detachSkill)
- tabs assertions (+1 — matters becomes available)
- Cypress (1 new file, 4-5 scenarios)

---

## Tasks

> Each task ends with one or more atomic commits. DCO sign-off (`-s`) and `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer required on every commit. **Conventional commit prefixes mandatory** (`feat(web):`, `refactor(web):`, `test(web):`).

---

### Task 0: Extract `<ChatPanel>` from /lq-ai/chats/+page.svelte

**Files:**
- Create: `web/src/lib/lq-ai/components/ChatPanel.svelte`
- Modify (rewrite): `web/src/routes/lq-ai/chats/+page.svelte`
- Create: `web/src/lib/lq-ai/__tests__/ChatPanel.test.ts`

**Approach:** the existing chat shell at `/lq-ai/chats/+page.svelte` (~600 lines) holds everything from data fetching to composer. Carve it into two layers:

1. `ChatPanel.svelte` (the carved-out component) — owns all chat composition: ChatSidebar, MessageList, SkillPicker, SavedPromptsPanel, ModelPicker, composer textarea + Send + ✨ EnhancePrompt button, AttachedFilesPanel, AmbientFooter, EnhancePromptExpansion. Receives `projectIdFilter?: string` and `initialChatId?: string` as props. Internally manages: `activeChat`, `messages`, `composerText`, `attachedSkillNames`, `skillInputs`, `availableModels`, `currentModelId`, the stream lifecycle, AmbientFooter provider/tier derivation.

2. `/lq-ai/chats/+page.svelte` (thin wrapper) — just mounts `<ChatPanel/>` with no props. Becomes ~10 lines.

**Critical:** behavior at `/lq-ai/chats` must be byte-identical after the extraction. Tests that exercise the chat shell (existing Vitest + Cypress) must keep passing without changes.

**Steps:**

- [ ] **Step 1:** Read all of `/lq-ai/chats/+page.svelte`. Identify the script-level state + functions + the template. Note: imports, `loadShell()`, `selectChat()`, `refreshProjectContext()`, `createNewChat()`, `selectProject()`, `toggleArchived()`, `attachSkill()`, `detachSkill()`, `updateSkillInputs()`, `uploadAttached()`, `detachFile()`, `sendMessage()`, `abortStream()`, `handleAppliedSkillClicked()`, reactive statements (`groups`, `filteredGroups`, `activeChat`, `messages`, `projectAttachedSkills`, `currentModelId`, `footerProvider`, `footerTier`).

- [ ] **Step 2:** Create `ChatPanel.svelte` carrying ALL the above. Add two new optional props at the top:
  ```ts
  export let projectIdFilter: string | undefined = undefined;
  export let initialChatId: string | undefined = undefined;
  ```
  - When `projectIdFilter` is set, `loadShell()` calls `chatsApi.listAllChats({ project_id: projectIdFilter })` instead of unfiltered list. (If the existing `listAllChats` doesn't accept `project_id`, add the param to the existing helper; small.)
  - When `initialChatId` is set, after `loadShell()` resolves, find the chat with that id in `chatsStore` and call `selectChat(chat)` automatically.
  - When `projectIdFilter` is set, hide the project filter in ChatSidebar (or pass a `hideProjectFilter` prop). The matter workspace's left rail already represents the project context; an in-sidebar project selector is redundant inside a matter.

- [ ] **Step 3:** Rewrite `/lq-ai/chats/+page.svelte` as a thin wrapper:
  ```svelte
  <script lang="ts">
    import ChatPanel from '$lib/lq-ai/components/ChatPanel.svelte';
    import { page } from '$app/stores';
    $: initialChatId = $page.url.searchParams.get('id') ?? undefined;
    $: projectIdFilter = $page.url.searchParams.get('project_id') ?? undefined;
  </script>

  <ChatPanel {projectIdFilter} {initialChatId} />
  ```
  This also adds deep-link support for `/lq-ai/chats?id={chatId}` and `/lq-ai/chats?project_id={id}` (used by the dashboard's RecentActivity and by matter navigation respectively).

- [ ] **Step 4:** Add `__tests__/ChatPanel.test.ts` (3-4 tests):
  - Mounts without crashing when no props provided (default behavior)
  - When `projectIdFilter='abc'` is provided, the project filter UI is hidden
  - When `initialChatId='xyz'` is provided, the component attempts to select that chat after load (mock chatsApi.listAllChats)
  - Smoke: composer text input + Send button render

- [ ] **Step 5:** Verify
  ```bash
  cd /Users/kevinkeller/Desktop/lq-ai/web && npm run test:frontend -- --run 2>&1 | tail -8
  cd /Users/kevinkeller/Desktop/lq-ai/web && npm run check 2>&1 | grep -E "(ChatPanel|routes/lq-ai/chats/\+page)" | head -10
  ```
  Expected: 157 + 3-4 new = 160-161 passing. Zero new svelte-check errors.

- [ ] **Step 6:** Smoke test in the browser (recommended): rebuild web, visit `/lq-ai/chats`, verify all chat flows still work — list chats, switch chat, send a message, attach skill, attach file.

- [ ] **Step 7:** Commit
  ```
  refactor(web): extract ChatPanel component for cross-surface reuse
  ```
  Carve the inner chat composition out of /lq-ai/chats/+page.svelte into a reusable `<ChatPanel projectIdFilter? initialChatId?/>` component. /lq-ai/chats becomes a thin route wrapper that mounts ChatPanel with URL params. Wave C task 3 will mount the same component inside /lq-ai/matters/[id]; no functional change to /lq-ai/chats. 3-4 new smoke tests pin the component contract; existing chat-shell tests pass unchanged.

---

### Task 1: Matters list at /lq-ai/matters

**Files:**
- Create: `web/src/routes/lq-ai/matters/+page.svelte`
- Create: `web/src/lib/lq-ai/components/MatterCard.svelte`
- Create: `web/src/lib/lq-ai/__tests__/MatterCard.test.ts`

**Page composition:** title "Matters" using `lq-text-page-h`. Top action row: "+ New matter" button (opens `NewMatterModal` from Task 7) + archived toggle. Card grid below: 1 column on narrow viewports, 2 on tablet, 3 on desktop. Each card uses `MatterCard`.

**MatterCard props:**
- `matter: Project`
- Renders: matter name (title), description excerpt (2 lines max), `privileged` badge if true, tier-floor badge if `minimum_inference_tier !== null` (TrustPill `tier` variant), file count + skill count, "Open" link to `/lq-ai/matters/{id}`.

**Empty state:** when `listProjects()` returns 0 (excluding archived), show: "You don't have any matters yet. [+ Start your first matter]" button. Practice-styled.

**Steps:**

- [ ] **Step 1:** Create `MatterCard.svelte` with the props + render shape above.
- [ ] **Step 2:** Create `MatterCard.test.ts` — 3 tests: renders matter name + description, shows privileged badge when applicable, shows tier badge when minimum_inference_tier is set.
- [ ] **Step 3:** Create `/lq-ai/matters/+page.svelte`. On mount, `await projectsApi.listProjects()`. Render grid of MatterCards.
- [ ] **Step 4:** Verify Vitest + svelte-check.
- [ ] **Step 5:** Commit `feat(web): /lq-ai/matters list surface`.

---

### Task 3: Matter workspace at /lq-ai/matters/[id] (2-pane composition)

**Files:**
- Create: `web/src/routes/lq-ai/matters/[id]/+page.svelte`
- Create: `web/src/lib/lq-ai/components/MatterRail.svelte`

**Page composition:** 2-pane layout — `MatterRail` on the left (fixed ~320px width), `ChatPanel` on the right (`flex: 1`).

`/lq-ai/matters/[id]/+page.svelte` body:
```svelte
<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { projectsApi } from '$lib/lq-ai/api';
  import type { Project } from '$lib/lq-ai/types';
  import MatterRail from '$lib/lq-ai/components/MatterRail.svelte';
  import ChatPanel from '$lib/lq-ai/components/ChatPanel.svelte';

  let matter: Project | null = null;
  let error: string | null = null;
  let activeChatId: string | undefined = undefined;

  $: matterId = $page.params.id;

  onMount(async () => {
    if (!matterId) return;
    try {
      matter = await projectsApi.getProject(matterId);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load matter';
    }
  });
</script>

{#if error}
  <p class="lq-text-body" style="padding: var(--lq-space-6); color: var(--lq-error);">{error}</p>
{:else if matter}
  <div class="matter-workspace">
    <MatterRail
      {matter}
      onSelectChat={(chatId) => (activeChatId = chatId)}
      onMatterUpdate={(next) => (matter = next)}
    />
    <ChatPanel
      projectIdFilter={matter.id}
      initialChatId={activeChatId}
    />
  </div>
{:else}
  <p class="lq-text-body" style="padding: var(--lq-space-6);">Loading matter…</p>
{/if}

<style>
  .matter-workspace { display: flex; height: 100%; }
</style>
```

**MatterRail composition:** vertical stack with sections (Practice-styled cards or sectioned panels):
1. Matter header — name, "Edit" button to open inline edit, archive action
2. Description (multi-line text)
3. Privileged + tier-floor badges + TrustPill summary
4. "Files" section — list of attached files; "+ Attach file" button (Task 5)
5. "Skills" section — list of attached skill names; "+ Attach skill" button (Task 6)
6. "Chats" section — list of chats in this matter (via `chatsApi.listAllChats({ project_id: matter.id })`); each row links to the embedded ChatPanel via `onSelectChat(chatId)`. "+ New chat" button creates a chat with `project_id` prefilled.

Steps to build MatterRail are bundled with Task 4/5/6 below; this task is the workspace skeleton.

- [ ] **Step 1:** Create `MatterRail.svelte` with placeholder sections (Tasks 4/5/6 fill them in).
- [ ] **Step 2:** Create `/lq-ai/matters/[id]/+page.svelte` per the body above.
- [ ] **Step 3:** Verify Vitest + svelte-check. Smoke: visit `/lq-ai/matters/{some-id}` — rail renders, ChatPanel renders, chat list works.
- [ ] **Step 4:** Commit `feat(web): /lq-ai/matters/[id] 2-pane workspace skeleton`.

---

### Task 4: Matter rail metadata (name / description / privileged / tier-floor inline edits)

**Files:**
- Create: `web/src/lib/lq-ai/components/MatterRailMetadata.svelte`
- Modify: `web/src/lib/lq-ai/components/MatterRail.svelte` (mounts MatterRailMetadata)

**MatterRailMetadata** — Props: `matter: Project`, `onUpdate(next: Project)`. Renders the matter's name (inline-editable on click), description (textarea on edit), privileged toggle, tier-floor select. Each edit PATCHes `/projects/{id}` and propagates the response back via `onUpdate`.

Archive button at bottom: confirms via inline confirm-modal, then PATCHes `archived: true` → navigates to `/lq-ai/matters`.

- [ ] **Step 1:** Build `MatterRailMetadata.svelte` with the inline-edit pattern.
- [ ] **Step 2:** Wire archive flow.
- [ ] **Step 3:** Verify + commit `feat(web): matter rail metadata inline-edits + archive`.

---

### Task 5: Matter rail file attach/detach

**Files:**
- Create: `web/src/lib/lq-ai/components/MatterRailFiles.svelte` (or extend MatterRailAttachments — implementer's call)
- Modify: `web/src/lib/lq-ai/api/projects.ts` (add `attachFile`, `detachFile`)
- Create: `web/src/lib/lq-ai/__tests__/projects-attach-api.test.ts`
- Modify: `web/src/lib/lq-ai/components/MatterRail.svelte` (mounts MatterRailFiles)

**projects.ts additions:**
```ts
export async function attachFile(projectId: string, fileId: string): Promise<Project> {
  return apiRequest<Project>(`/projects/${encodeURIComponent(projectId)}/files`, {
    method: 'POST',
    body: { file_id: fileId }
  });
}

export async function detachFile(projectId: string, fileId: string): Promise<Project> {
  return apiRequest<Project>(
    `/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}`,
    { method: 'DELETE' }
  );
}
```

**MatterRailFiles** renders the matter's `attached_file_ids` as a list (with file metadata fetched via `filesApi.getFile`). "+ Attach file" button opens a file picker (reuse existing FilePicker pattern from chat shell if present, or use a small inline list of the user's files with a multi-select chip). Each row has a "detach" affordance.

- [ ] **Step 1:** Add API helpers + 2 tests (attach/detach happy path).
- [ ] **Step 2:** Build MatterRailFiles component.
- [ ] **Step 3:** Mount in MatterRail.
- [ ] **Step 4:** Commit `feat(web): matter rail file attachments`.

---

### Task 6: Matter rail skill attach/detach

**Files:**
- Create: `web/src/lib/lq-ai/components/MatterRailSkills.svelte`
- Modify: `web/src/lib/lq-ai/api/projects.ts` (add `attachSkill`, `detachSkill`)
- Extend: `web/src/lib/lq-ai/__tests__/projects-attach-api.test.ts` (add 2 tests for skills)
- Modify: `web/src/lib/lq-ai/components/MatterRail.svelte` (mounts MatterRailSkills)

Same shape as Task 5, but for skills. `attached_skill_names` is a string[]; render each as a TrustPill (variant `audit` or `skill` — implementer's pick). Attach affordance: typeahead over `skillsApi.listSkills()` filtered to skills not already attached.

- [ ] **Step 1:** Add API helpers + 2 tests.
- [ ] **Step 2:** Build MatterRailSkills.
- [ ] **Step 3:** Mount in MatterRail.
- [ ] **Step 4:** Commit `feat(web): matter rail skill attachments`.

---

### Task 7: New Matter modal

**Files:**
- Create: `web/src/lib/lq-ai/components/NewMatterModal.svelte`
- Modify: `web/src/routes/lq-ai/matters/+page.svelte` (mounts modal)

Practice-styled modal (overlay pattern from ComingSoonModal). Fields:
- Matter name (required)
- Description (optional, multi-line)
- Privileged checkbox (default off)
- Tier-floor select (default empty; required if privileged is checked, per backend CHECK constraint)

Submit calls `projectsApi.createProject(...)`; on success, navigates to `/lq-ai/matters/{newId}`.

- [ ] **Step 1:** Build modal component.
- [ ] **Step 2:** Wire from matters list page's "+ New matter" button.
- [ ] **Step 3:** Commit `feat(web): NewMatterModal — create matter with privileged + tier-floor`.

---

### Task 8: Flip matters tab + wire dashboard RecentActivity

**Files:**
- Modify: `web/src/lib/lq-ai/tabs.ts` (flip `matters` to `available: true`; remove `shipsInWave: 'C'`)
- Modify: `web/src/lib/lq-ai/__tests__/tabs.test.ts` (move `'matters'` to `true` assertion group)
- Modify: `web/src/lib/lq-ai/components/RecentActivity.svelte` (wire matters card to `projectsApi.listProjects({ limit: 5 })` and surface recent matters with links to `/lq-ai/matters/{id}`)

Mirror of T1's tab flip from Wave B v2. The dashboard's RecentActivity currently has a "Recent matters — Wave C" placeholder; replace with live data.

- [ ] **Step 1:** Flip tabs.ts.
- [ ] **Step 2:** Update tabs.test.ts.
- [ ] **Step 3:** Update RecentActivity.
- [ ] **Step 4:** Commit `feat(web): flip matters tab available + wire dashboard recent matters`.

---

### Task 9: Cypress E2E for Wave C surfaces

**File:** `web/cypress/e2e/wave-c-matters.cy.ts`

5 scenarios:
1. Click Matters tab → routes to `/lq-ai/matters` (not ComingSoonModal)
2. Empty state if no matters; "+ Start your first matter" CTA opens NewMatterModal
3. Create a matter via the modal → redirected to `/lq-ai/matters/{id}` workspace
4. Matter workspace renders matter rail on left + ChatPanel on right; chat list in rail is filtered to the matter
5. Create a chat in the matter; send a message; chat persists; matter rail chat list updates

- [ ] **Step 1:** Write the file.
- [ ] **Step 2:** Commit `test(web): Cypress E2E smoke for Wave C matters surfaces`.

---

### Task 10: Final verification + push

- [ ] `cd web && npm run test:frontend -- --run` — expect ~175 passing
- [ ] `cd web && npm run check 2>&1 | grep -E "(Matter|matters|ChatPanel)" | head -20` — zero new errors in Wave C files
- [ ] Stack smoke (with `docker compose up -d --no-deps --build web`):
  1. Log in → land on Guided Dashboard
  2. Dashboard RecentActivity shows real matters (or empty state)
  3. Click Matters tab → `/lq-ai/matters` list renders
  4. Click "+ New matter" → modal opens, fields work, submit creates matter
  5. Land on `/lq-ai/matters/{id}` workspace — rail + embedded chat
  6. Rename matter inline — persists across reload
  7. Toggle privileged — tier-floor select becomes required
  8. Attach a file to the matter — appears in rail; chat shell sees it as project file
  9. Attach a skill — appears in rail; chat composer sees it as project-attached skill
  10. Create a chat inside the matter — appears in rail chat list; ChatPanel auto-loads it
  11. Send a message — streams, persists, applied_skills surfaces
  12. Click another chat in rail — switches; previous chat's state preserved
  13. Visit `/lq-ai/chats` — still works identically (existing chat shell behavior preserved)
- [ ] Push: `git push origin kk/main/Frontend_Design`

---

## Self-review

**1. Spec coverage:**

| Spec section | Wave C task |
|---|---|
| §4.1 Top-tab nav (matters available) | T8 |
| §4.2 Matters list (`/lq-ai/matters`) | T1 |
| §4.2 Matter workspace 2-pane (rail · chat) | T3 |
| §4.2 Matters tab routing | T8 |
| Outputs panel (§4.2 row mentions it) | **Deferred to Wave D** per architectural call 2026-05-12 |
| KB attach to matter (§4.2 row mentions it) | **Deferred to Wave D** per architectural call 2026-05-12 |

**2. Placeholder scan:** zero `V2-FALLBACK` annotations in Wave C — the wave wires real backend everywhere.

**3. Type consistency:** Reuses `Project`, `Chat`, `Skill`, `FileMeta` types from `types.ts`. No new types needed (Wave C ships entirely on existing contracts).

**4. Scope:** ~10 commits (Task 0 + 7 + Task 10 push; some tasks split into 2 commits). Doesn't bleed into Wave D/E/F.

**5. Backend dependency match:** Every endpoint referenced (11 endpoints, all shipped on main).

---

## Open implementation questions (resolve during execution)

1. **ChatPanel project filter behavior** — when `projectIdFilter` is set, does `chatsApi.listAllChats` already accept a `project_id` param? If yes, use it. If no, add `project_id` to the helper or filter client-side. Decide at Task 0.2.
2. **File picker UI in MatterRailFiles** — there's no shared FilePicker component yet. Either reuse the chat shell's AttachedFilesPanel pattern (with adaptations) or build a minimal "select from your files" affordance. Decide at Task 5.2.
3. **Skill typeahead in MatterRailSkills** — same as above; might reuse the SkillPicker pattern from the chat shell, possibly with a smaller form factor.
4. **Matter list pagination** — `listProjects()` doesn't paginate by default. For Wave C, list all matters (M1 deployments likely have < 100 matters per user). Wave F can add cursor pagination if needed.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-05-12-m1-frontend-wave-c-matters.md`. Execute subagent-driven (Kevin's standing preference). All Wave A patterns + Wave B v2 patterns (commit message conventions, DCO sign-off, push-every-commit, atomic commits) apply unchanged.
