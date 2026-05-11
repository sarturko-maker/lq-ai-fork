# svelte-check Error Backlog

> **Purpose:** Inventory of pre-existing `svelte-check` errors captured at Wave A start so they can be triaged and cleaned up in a dedicated cycle. Referenced from the M1 frontend design spec §12 (open implementation questions).
>
> **Date captured:** 2026-05-10
> **Branch at capture:** `kk/main/Frontend_Design`
> **Log:** `/tmp/svelte-check-output.log` (ephemeral; re-run `cd web && npm run check 2>&1` to regenerate)

---

## Status

| Category | Count | Priority | Blocking Wave A? |
|---|---|---|---|
| **1 — Missing @types packages** (direct declaration errors) | 51 | Quick win | No |
| **2 — OpenWebUI fork legacy** (upstream errors) | 9,309 | Deferred until rebase | No |
| **3 — LQ.AI-specific errors** | 3 | Fix in next cleanup cycle | No |
| **Total** | **9,362** | — | — |

svelte-check summary line: `2678 FILES 9362 ERRORS 268 WARNINGS 380 FILES_WITH_PROBLEMS`

---

## Category 1 — Missing @types packages

### What it is

Several third-party packages used by OpenWebUI do not ship TypeScript declarations and do not have bundled types. svelte-check emits a "Could not find a declaration file" error for each import of these packages, then cascades through the file treating all calls into that package as `any`. These are pure dev-dependency gaps — no production code changes required.

### Packages missing declarations

| Package | Direct errors | Available fix |
|---|---|---|
| `file-saver` | 44 | `@types/file-saver` exists on npm |
| `uuid` | 36 | `@types/uuid` exists on npm |
| `sortablejs` | 10 | `@types/sortablejs` exists on npm |
| `turndown` | 2 | `@types/turndown` exists on npm |
| `sql.js` | 2 | `@types/sql.js` exists on npm |
| `leaflet` | 2 | `@types/leaflet` exists on npm |
| `katex/contrib/mhchem` | 2 | No separate @types; needs a local `declare module` stub |
| `@joplin/turndown-plugin-gfm` | 2 | No @types; needs a local `declare module` stub |
| `@sveltejs/svelte-virtual-list` | 1 | No @types; needs a local `declare module` stub |

### Suggested fix command (do not run during Wave A)

```bash
cd web
npm install --save-dev \
  @types/file-saver \
  @types/uuid \
  @types/sortablejs \
  @types/turndown \
  @types/sql.js \
  @types/leaflet
```

For the three packages without published @types, add a local declaration stub at `web/src/lib/types/third-party.d.ts`:

```ts
// Packages that ship no types and have no @types/* package
declare module 'katex/contrib/mhchem';
declare module '@joplin/turndown-plugin-gfm';
declare module '@sveltejs/svelte-virtual-list';
```

**Backend impact:** none. Frontend-only dev-dependency change.

**Estimated error reduction:** ~101 direct errors removed; cascade errors in files that import these packages will also collapse.

---

## Category 2 — OpenWebUI fork legacy

### What it is

The remaining ~9,309 errors are pre-existing in the upstream OpenWebUI codebase. They were present before the LQ.AI fork was created and will be addressed upstream or land via rebase. They are not introduced by LQ.AI code.

### Major error sub-patterns

**2a — i18n store type mismatch (3,531 errors, ~38% of total)**

The most common single error. OpenWebUI's i18n store is typed as `unknown` in the version we forked; Svelte 5 narrowed the type contract for `$store` syntax. Every component that uses `$i18n` emits this error.

Sample:
```
"src/lib/components/common/SensitiveInput.svelte" 22:51
"Cannot use 'i18n' as a store. 'i18n' needs to be an object with a
subscribe method on it."
```

**2b — Implicit any on untyped .js files (2,644 errors)**

OpenWebUI ships several editor-plugin integration files as plain JavaScript (not TypeScript). svelte-check's strict mode emits `implicitly has an 'any' type` for every parameter and variable in these files.

Sample:
```
"src/lib/components/common/RichTextInput/AutoCompletion.js" 62:7
"Variable 'debounceTimer' implicitly has type 'any' in some locations..."
"src/lib/components/common/RichTextInput/listDragHandlePlugin.js" 9:3
"Property 'itemTypeNames' does not exist on type '{}'."
```

**2c — Loose OpenWebUI interface shapes (1,134 errors)**

Many OpenWebUI components use `{}` or empty-object literals as type annotations for complex config objects (`Config`, `Settings`, `ModelMeta`). The real objects have more fields than the declared types, producing "Property 'X' does not exist on type '{}'" errors.

Sample:
```
"src/lib/components/chat/Chat.svelte" (297 errors — top-affected file)
"src/lib/components/admin/Users/Groups/Permissions.svelte" (279 errors)
```

**2d — Missing declaration file cascades (51 direct; see Category 1)**

As described in Category 1, these are attributable to missing @types packages and would drop after that fix.

### Not blocking Wave A

These errors are inherited from upstream. Fixing them requires either waiting for OpenWebUI to address them (resolved via future rebase) or doing a targeted typing pass across ~380 affected files. Neither is appropriate during Wave A. Mark as deferred.

---

## Category 3 — LQ.AI-specific errors

Three errors in files under `web/src/lib/lq-ai/` and `web/src/routes/lq-ai/`. All are small, targeted fixes.

### 3a — Missing env var declaration

**File:** `web/src/lib/lq-ai/api/client.ts:49`
**Error:** `Module '"$env/static/public"' has no exported member 'PUBLIC_LQ_AI_API_BASE_URL'.`

**Root cause:** `PUBLIC_LQ_AI_API_BASE_URL` is declared in `.env.example` but no `.env` file exists in the working tree. SvelteKit's `$env/static/public` module only exposes variables that are present at build time. Without a `.env` file, the variable is invisible to the type system.

**Fix location:** Frontend dev workflow, not backend.

**Suggested fix:**
```bash
# For local development — copy .env.example to .env
cp web/.env.example web/.env
```

Alternatively, add a `web/src/app.d.ts` augmentation for `$env/static/public` so the type is declared even when `.env` is absent. This is the more robust solution for CI environments.

**Backend impact:** None — this is a local dev environment setup gap, not a backend type-shape mismatch.

---

### 3b — Union type narrowing false positive

**File:** `web/src/routes/lq-ai/admin/models/+page.svelte:236`
**Error:** `This comparison appears to be unintentional because the types 'Alias' and 'string' have no overlap.`

**Root cause:** `editing` is typed as `Alias | null | 'new'`. The template guard `{:else if editing && editing !== 'new'}` is logically correct — after passing the `{#if editing === 'new'}` branch, TypeScript should narrow `editing` to `Alias | null`. However, the second `editing !== 'new'` check inside the `onSubmit` callback lambda confuses the TypeScript checker because it sees `editing: Alias` (already narrowed by the `:else if`) and flags comparing an `Alias` to the string literal `'new'` as a no-overlap error.

**Fix location:** Frontend code only — type annotation or cast.

**Suggested fix options:**
1. Add a type guard helper: `function isAlias(e: Alias | null | 'new'): e is Alias { return e !== null && e !== 'new'; }`
2. Use a type assertion inside the lambda: `onSubmit={(p) => editing && (editing as Alias | null) && handleUpdate(editing as Alias, p)}`

**Backend impact:** None. The runtime behavior is correct; this is a TypeScript static-analysis false positive caused by union narrowing across callback scope.

---

### 3c — Page param possibly undefined

**File:** `web/src/routes/lq-ai/skills/[id]/edit/+page.svelte:47`
**Error:** `Argument of type 'string | undefined' is not assignable to parameter of type 'string'. Type 'undefined' is not assignable to type 'string'.`

**Root cause:** `$page.params.id` is typed as `string | undefined` by SvelteKit's generated types. `userSkillsApi.getUserSkill(skillId)` expects `string`. The reactive assignment `$: skillId = $page.params.id` does not narrow to `string`.

**Fix location:** Frontend code only.

**Suggested fix:**
```ts
// Narrow before use, or assert — the route is only reachable with a valid id segment
$: skillId = $page.params.id ?? '';
// Or in the load function body:
if (!skillId) { loadError = 'No skill ID in URL'; return; }
```

**Backend impact:** None. `getUserSkill` signature on the backend is correct — the error is purely a TypeScript narrowing issue on the frontend route param.

---

## Recommended remediation order

1. **Quick win — install missing @types packages** (Category 1)
   - Install 6 `@types/*` packages + 3 local `declare module` stubs.
   - Drops ~51 direct errors; collapses associated cascade errors.
   - No backend involvement, no risk to production.
   - Estimated effort: 30 minutes.

2. **Fix LQ.AI-specific errors** (Category 3)
   - Three isolated items; each is a frontend-only fix.
   - 3a needs a `.env` setup or a `app.d.ts` augmentation — the augmentation approach is more robust.
   - 3b and 3c are narrowing fixes in two route files.
   - Estimated effort: 1–2 hours.

3. **Defer OpenWebUI legacy** (Category 2)
   - Do not attempt to fix during Wave A.
   - Will partially resolve via a future upstream rebase.
   - Remaining items (i18n, untyped .js files) should be addressed in a dedicated typing pass after Wave A is complete and the OpenWebUI rebase has landed.
   - Estimated effort when scheduled: 2–3 sessions (large surface, mostly mechanical).

---

## Tracking

This backlog is referenced from the M1 frontend design spec at `docs/superpowers/specs/2026-05-10-m1-frontend-design.md` §12 (open implementation questions). The actual cleanup is post-Wave-F polish or its own separate cycle. Category 1 and Category 3 fixes should land before or alongside the first Wave F polish pass. Category 2 is blocked on the OpenWebUI rebase milestone.

No Wave A deliverable is blocked by any item in this backlog.
