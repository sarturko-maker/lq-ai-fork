# Wave D.2 — Skill Creator (Design)

| | |
|---|---|
| **Status** | DRAFT — awaiting Kevin's review |
| **Authored** | 2026-05-13 |
| **Branch** | `kk/main/Frontend_Design` |
| **Working dir** | `/Users/kevinkeller/Desktop/lq-ai` |
| **Anchors** | [M1 Frontend Design §7.2](./2026-05-10-m1-frontend-design.md#72-skill-creator-three-modes), [PRD §1.3 Transparency](../../PRD.md), [PRD §7.1 Skills as work product](../../PRD.md), [ADR 0007 Skill prompt assembly](../../adr/0007-skill-prompt-assembly.md) (pending Q1 amendment), [ADR 0012 DB-backed user skills](../../adr/0012-db-backed-user-skills.md), [Session handoff 2026-05-12](../../SESSION-HANDOFF-2026-05-12-pre-d2.md), [claude-for-legal Q1 decision](../../research/2026-05-12-claude-for-legal-review.md#9-decisions) |
| **Scope** | Wave D.2: the last M1 frontend item before v0.1.0 tag. Ships the three skill-creation modes (capture-from-chat · from-scratch wizard · fork), skill detail tabs (Use / Source / Try-it / Versions), the per-user try-it sandbox matter scope, and the composer slash-invocation surface that implements the Q1 dual-invocation decision. |

---

## 1. Problem framing

The M1 backend treats user skills as first-class content (ADR 0012, the `user_skills` table, the resolver order user > team > built-in). The frontend at the end of Wave D.1 surfaces them as a *list* and an *edit form*, but doesn't yet make authoring an everyday gesture. The closed competitors (gc.ai, Spellbook, Legora) lean hard on "your firm's knowledge, captured" — that's the muscle Wave D.2 builds.

Three creation gestures land in this wave:

1. **Capture from chat.** An in-house lawyer has a productive turn with the model; they should be one click from saving it as a personal skill.
2. **Build from scratch.** A four-section wizard at `/lq-ai/skills/new` for users who know the skill they want to author and don't have it yet.
3. **Fork existing.** Any built-in or team skill can be cloned into the user's personal scope and customized — making LQ.AI's open skill library a starting point, not a final answer.

A try-it sandbox lets users validate skills before committing them. A slash-invocation surface in the composer (`/skill-name`) lands the Q1 decision — dual invocation alongside the existing attach-on-chat trigger model. A Versions tab on detail pages exposes the audit history.

This is the last M1 frontend wave. After it, M1 ships as v0.1.0.

## 2. Goals and non-goals

**Goals:**

1. Three creation modes converging on one wizard + one storage layer (`user_skills`).
2. Authoring becomes everyday, not ceremonial — capture is one click from any AI turn.
3. The slash surface lands the Q1 decision without a parser overhaul (bare `/slug` only).
4. The try-it sandbox is a first-class matter (so Wave E onboarding reuses the same column).
5. The Versions tab makes edit history visible without a snapshot table.
6. Every Cypress test gets live-executed before D.2 closes — per the dry-run-value lesson from the 2026-05-12 session (`feedback_dry_run_value` in agent memory).

**Non-goals (deferred to v1.1+ or other waves):**

- Full slash grammar `/slug arg=value` with frontmatter `inputs:` schema — DE-222 candidate.
- Diff view in the Versions tab — DE-223 candidate.
- Conversational `skill-creator` SKILL integration in the capture flow — DE-224 candidate.
- Cross-device draft sync — localStorage-only at M1.
- Wave E onboarding UX (Acme NDA pre-load + guided walkthrough) — reuses our `is_sandbox` column but ships separately.
- ADR 0007 amendment formalizing the dual-invocation model — separate planning task.

## 3. Decisions captured during brainstorm

Nine architectural decisions resolved with Kevin via `AskUserQuestion` (2026-05-13 session). Recorded here so the plan and implementation don't re-litigate them.

| # | Decision | Resolution |
|---|----------|------------|
| D1 | Slicing | **One wave** (atomic D.2, no D.2.1/D.2.2 split) |
| D2 | Slash-invocation depth | **Composer popover** with fuzzy match (Slack/Discord pattern). No arg grammar. |
| D3 | Capture trigger | **Inline on every AI message**, user-toggleable to overflow menu (`⋯`) per the §3 personalization throughline |
| D4 | Sandbox schema | **`projects.is_sandbox BOOLEAN NOT NULL DEFAULT FALSE`** — Wave E reuses |
| D5 | Capture flow | **Thin modal** — name + description + slug + body, save → done. Wizard accessible via "Edit in wizard" handoff. |
| D6 | Wizard layout | **Single-page sections** (all 4 sections visible, scroll down) |
| D7 | Versions tab depth | **Audit-log view** — timestamp + actor + version label. No snapshots, no diffs. |
| D8 | Fork flow | **Frontend pre-populate** — `/lq-ai/skills/new?fork=<slug>` reads source via `GET /skills/{slug}` and seeds the wizard. Save = `POST /user-skills` with `forked_from` set. |
| D9 | Slash composer state | **Separate-row pill** in the existing attached-context row (matches KB-attach visual per §7.3) |

## 4. Architecture

Wave D.2 = "Skills become first-class user work product." Three creation modes converge on the same storage (`user_skills`) and the same wizard component (`/lq-ai/skills/new`), with different entry-state.

```
                       ┌─────────────────────────────────────┐
   Chat AI message ─→  │ Mode A · Thin capture modal         │ ─┐
                       └─────────────────────────────────────┘  │
                                                                ├──→  POST /user-skills
       /lq-ai/skills    ┌─────────────────────────────────────┐ │     (creates row in
       "+ New skill" ─→ │ Mode B · 4-section wizard           │ ├──→  user_skills table)
                       └─────────────────────────────────────┘  │
                                                                │
       /lq-ai/skills/X   ┌────────────────────────────────────┐ │
       "🔱 Fork" ─────→  │ Mode C · Wizard pre-populated      │ ┘
       /skills/new?fork=X│        (frontend pre-fetch from X) │
                        └────────────────────────────────────┘

   Detail tabs (/skills/X): Use it · View source · [NEW] Try it · [NEW] Versions
                                                       │             │
                                                       ↓             ↓
                                                 Sandbox matter   audit_log
                                                 (is_sandbox=t)   filtered view

   Composer (every matter):
   ┌──────────────────────────────────┐
   │ [skill-pill] [📎kb-pill]         │   ← attached-context row
   │ [textarea]                       │
   └──────────────────────────────────┘
       ↑ type "/" → popover from GET /skills/autocomplete?q=
```

**Three architectural beats:**

1. **Three modes, one wizard.** Capture-modal (Mode A) is a stripped-down form (4 fields). Blank wizard (Mode B) is the full single-page layout. Fork-prepopulated wizard (Mode C) is Mode B with fields hydrated from `GET /skills/{slug}`. All three save via `POST /user-skills`.

2. **Sandbox = first-class matter.** `projects.is_sandbox` is the new column. The sandbox is auto-created lazy-per-user via `POST /projects/sandbox/ensure` on first try-it click. The same per-user sandbox backs both the wizard's section-4 Try-it pane and the detail-page Try-it tab. Default filters hide sandbox matters from the matters list; `?include_sandbox=true` reveals them.

3. **Slash = parallel to KB-attach.** Slash invocation is a third way to attach context (alongside `📎 KB attach` and the skill picker). It uses the existing attached-context row in the composer, surfaces in receipts/audit as `source: "slash"`, and is fed by `GET /skills/autocomplete?q=` filtered by the existing user > team > built-in resolver.

## 5. Components

Grouped by layer. ★ = net-new, ⟳ = modified, · = reused as-is.

### Frontend (Svelte, `web/src/lib/lq-ai/`)

**Wizard core (Modes B + C):**

- ★ `components/SkillWizard.svelte` — single-page-sections layout with 4 sections + Advanced toggle (jurisdiction, version, tags, scope). Save / Save-draft (localStorage) / Discard footer.
- ★ `components/SkillWizardSection.svelte` — section block with title + helper text + slot. Used 4× in `SkillWizard`.
- ★ `components/SkillTryItPane.svelte` — embedded sandbox chat. Used in wizard section 4 AND detail-page Try-it tab.
- ⟳ `routes/lq-ai/skills/new/+page.svelte` — shrinks to a thin wrapper around `SkillWizard`. Reads `?fork=`, `?capture=`, `?draft=` query params for seeding.

**Capture-from-chat (Mode A):**

- ★ `components/CaptureSkillModal.svelte` — 4-field modal pre-populated from the AI message. Save → `POST /user-skills`. "Edit in wizard" → localStorage stash + navigate to `/skills/new?capture=<key>`.
- ★ `components/MessageOverflowMenu.svelte` — `⋯` menu hosting demoted "Capture as skill" when toggled off-inline.
- ⟳ `components/ChatMessage.svelte` (or equivalent) — adds inline `📝 Capture as skill` button next to thumbs-up/down + overflow trigger.
- ★ `lib/preferences/capture-affordance.ts` — preference store + Settings entry: "Show 'Capture as skill' inline on AI messages." Default on.

**Fork (Mode C):**

- ⟳ `routes/lq-ai/skills/[id]/+page.svelte` — add `🔱 Fork as my own` action alongside existing Edit.

**Detail tabs:**

- ⟳ `components/SkillDetailTabs.svelte` — extends from 2 tabs (use, source) to 4 (use, source, try-it, versions).
- ★ `components/SkillTryItTab.svelte` — wraps `SkillTryItPane` with the saved skill id.
- ★ `components/SkillVersionsTab.svelte` — table of audit-log entries (timestamp · actor · action · version).

**Slash invocation:**

- ★ `components/SlashPopover.svelte` — autocomplete popover anchored to composer. Triggered on bare `/` at column 0 (or after `\n`). Arrow + Enter to pick, Esc to dismiss. Fed by `GET /skills/autocomplete?q=`.
- ★ `components/AttachedSkillPill.svelte` — green pill in the existing attached-context row. Removable.
- ⟳ `components/ChatComposer.svelte` — text-watcher detects bare `/` at line start → toggles `SlashPopover`. On pick: strips slash token, adds `AttachedSkillPill`.
- ⟳ `api/skills.ts` — adds `autocomplete(q: string)` client method.

**Reused as-is:** `SkillSourceView`, `TrustPill`, `ProvenancePill`, base chat panel components, the existing skill picker.

### Backend (`api/app/`)

**New endpoints:**

- ★ `GET /api/v1/skills/autocomplete?q=&limit=` — fuzzy match against `slash_alias` / `slug` / `title`, resolver-aware (user > team > built-in), shadowed built-ins excluded. Empty `q` returns top-N recently-attached by user. Limit default 10, max 25.
- ★ `POST /api/v1/projects/sandbox/ensure` — idempotent find-or-create the caller's sandbox matter (`slug="__sandbox__"`, `is_sandbox=true`, `privileged=false`, `minimum_inference_tier=null`).

**Modified endpoints:**

- ⟳ `POST /api/v1/user-skills` — accepts new fields: `slash_alias`, `forked_from`, `source_message_id`. 422 on alias regex fail or unique-per-owner-active collision.
- ⟳ `PATCH /api/v1/user-skills/{id}` — accepts `slash_alias` (others write-once).
- ⟳ `GET /api/v1/skills/{slug}` — response includes `slash_alias` and `forked_from` when set.
- ⟳ `GET /api/v1/projects` — default filter `is_sandbox=false`. New params: `?include_sandbox=true`, `?only_sandbox=true`.
- ⟳ `GET /api/v1/audit-log` — if not already supported, add `target_type` + `target_id` query params for the Versions tab.

**Not touched:** the existing `POST /api/v1/skills/{slug}/fork` endpoint stays for non-web clients but isn't on the Mode C path.

### Schema (Alembic)

- ★ `0022_add_projects_is_sandbox.py` — `ALTER TABLE projects ADD COLUMN is_sandbox BOOLEAN NOT NULL DEFAULT FALSE` + partial index `WHERE is_sandbox = false` for fast default queries.
- ★ `0023_add_user_skills_slash_alias_and_forked_from.py` — single migration adding both columns to `user_skills`: `slash_alias TEXT NULL` with `CHECK (slash_alias IS NULL OR slash_alias ~ '^/[a-z0-9-]{1,32}$')` + unique-per-owner-active partial index, plus `forked_from TEXT NULL` (documentary; no FK since skills are filesystem-canonical).
- ⟳ `models/user_skill.py` — add `slash_alias`, `forked_from` fields.
- ⟳ `models/project.py` — add `is_sandbox` field.

## 6. Data flow walkthroughs

Six end-to-end traces. Each shows user gesture → component → API call → DB side effect → UI result.

### Mode A — Capture from chat

```
1. AI message renders → ChatMessage shows [👍][👎][📝 Capture][⋯]
2. User clicks [📝 Capture]
   → CaptureSkillModal opens, pre-populated:
       name        ← derived from first heading or first sentence
       description ← second line / leading paragraph
       slug        ← kebab-case(name), strip-to-ASCII, fallback to "captured-skill-<short-id>"
       body        ← AI message markdown verbatim
3. User edits, clicks Save
   → POST /api/v1/user-skills { slug, display_name, description, body,
                                source_message_id, version: "1.0.0", scope: "user" }
   → 201 Created
4. Modal closes, toast "Saved as a personal skill"
   Alt: "Edit in wizard" → localStorage stash + navigate /skills/new?capture=<key>
```

### Mode B — From scratch

```
1. /lq-ai/skills → "+ New skill" → /lq-ai/skills/new
2. SkillWizard renders empty layout, auto-saves to localStorage on debounced edit
3. User fills sections 1–3, clicks Save → POST /user-skills → 201 → /skills/[id]
4. Save draft → localStorage stays; toast; /skills lists "Drafts (N)" with resume links
5. Discard → confirm → clear localStorage → /skills
```

### Mode C — Fork

```
1. /skills/nda-review → "🔱 Fork" → /skills/new?fork=nda-review
2. SkillWizard mounts, fetches source:
   → GET /skills/nda-review → 200
   → hydrate:
       slug         ← "nda-review-fork" (auto-deduped if collides)
       display_name ← source.title + " (fork)"
       description  ← source.description
       body         ← source.content_md
       tags         ← source.tags
       forked_from  ← "nda-review"   (hidden, persists on save)
       slash_alias  ← null            (user picks their own)
3. User edits, clicks Save → POST /user-skills with forked_from set
   → audit row: action=user_skill_created, metadata.forked_from=nda-review
```

### Slash invocation

```
1. User types "/" at composer line-start
   → ChatComposer detects → SlashPopover opens
   → GET /skills/autocomplete?q=&limit=10 → popover shows recent skills
2. User types "nd"
   → debounced GET /skills/autocomplete?q=nd&limit=10
3. User picks via Enter
   → composer strips "/nd"
   → AttachedSkillPill appears in context row
   → popover closes
4. User types prompt, Send → POST /chats/{id}/messages with
   attached_skills: [{slug, source: "slash"}]
5. Alt: Esc/click-out → popover dismisses, "/" stays as plain text
```

### Try-it (wizard section 4 AND detail-page tab)

```
1. User clicks Try-it
   → POST /projects/sandbox/ensure → 200 {project: ...} (or 201 first time)
2. SkillTryItPane mounts with the relevant skill:
       wizard:     attached_skills: [{inline_body: <current wizard body>, source: "wizard-tryout"}]
       detail tab: attached_skills: [{slug: <saved slug>, source: "tryit-tab"}]
3. User sends test prompts → POST /chats/{id}/messages — same wiring as any chat,
   matter is_sandbox=true so cost/audit aggregation can filter
4. "Reset sandbox" → delete that chat row, keep the sandbox project
```

### Versions tab

```
1. /skills/[id]?tab=versions
   → GET /audit-log?target_type=user_skill&target_id=<uuid>&limit=50
2. Table renders: Timestamp · Actor · Action · Version
3. Built-in skill → empty state "Built-in skill · no edit history. Fork it to create your own version."
```

**Side-effect summary (cross-cutting):**

- Every skill save writes an `audit_log` row with rich `detail` JSON. The Versions tab is fed entirely from this.
- Every sandbox chat is tagged `is_sandbox=true` on the audit metadata.
- Slash usage records `source: "slash"` on the message's skill-attachment for receipts.

## 7. Error handling and edge cases

Grouped by domain. Principle: surface failures honestly, preserve user work, default to the conservative path.

### Slash invocation

| Case | Handling |
|---|---|
| Bare `/` typed, popover dismissed (Esc / click-out) | `/` stays in composer as plain text. Send-time backend doesn't re-attach — frontend pill is source of truth. |
| `/` typed mid-text (not line-start) | Popover does NOT open. Treated as plain text. |
| `/xyz` with no match | Popover shows "No matching skills · Esc to dismiss." |
| User has zero accessible skills | Popover: "You don't have any skills yet — [Browse built-ins] · [Create one]." |
| `slash_alias` collision (two user-skills share `/foo`) | **Prevented at write-time** via unique-per-owner-active index → 422 with field error naming the colliding skill. |
| `slash_alias` collides with a built-in | **Allowed** — intentional shadowing. Yellow note: "This shadows the built-in `/foo` for you only." |
| Autocomplete request fails | Popover: "Couldn't load suggestions" + retry. Send-time fallback: parse leading `/slug` if no pill, attach if resolves, else send plain text + `slash_unresolved` receipt. |
| Archived skill in slash command | Popover excludes archived. Send-time fallback also excludes. |
| Skill archived between selection and send | Message sends; attachment dropped + provenance event "skill no longer available." |

### Capture from chat (Mode A)

| Case | Handling |
|---|---|
| Slug derivation produces invalid chars (emoji/unicode) | Strip to ASCII-kebab-case; fallback `captured-skill-<short-msg-id>` if empty. |
| Slug shadows built-in | Yellow note; save proceeds. |
| Slug collides with another user-skill | Red error; user must edit. |
| Source message regenerated/deleted mid-modal | Save still succeeds with current modal body. `source_message_id` may dangle (documentary only). |
| Session expires mid-modal | 401; toast "Session expired"; modal state preserved for re-auth retry. |
| Capture during privileged matter | `minimum_inference_tier` does NOT auto-propagate; user sets explicitly in edit page if desired. |
| Empty body/name on save | Client-side prevented (Save disabled). |

### Wizard (Modes B / C)

| Case | Handling |
|---|---|
| Browser refresh/crash mid-edit | localStorage auto-save (debounced); `/skills` shows "Drafts (N)" affordance with resume links. |
| Two tabs open | Distinct UUID4 draft keys per tab — no collision. Cross-tab sync out of scope. |
| Fork source 404 | Wizard renders empty + banner "Couldn't load source; starting blank. [Pick a different source]." |
| Fork source has `slash_alias` | Fork does NOT inherit (aliases are per-owner). Field shows empty with helper text. |
| `slash_alias` regex fails client-side | Inline error; Save disabled until valid or cleared. |
| Server 422 on slash_alias collision | Form preserves state; field-level error rendered. |
| Try-it before body filled | Try-it button disabled; tooltip "Add a body first." |
| Logout with localStorage draft | Persists in their browser. Not synced cross-device — documented limit. |

### Sandbox

| Case | Handling |
|---|---|
| Concurrent `POST /sandbox/ensure` from same user | Endpoint uses `INSERT ... ON CONFLICT DO NOTHING RETURNING *` + SELECT fallback. Both return same row. |
| User manually archives their sandbox | Next ensure call creates a fresh row; archived row remains in matters list under "Include sandbox." |
| User tries to create a regular matter with slug `__sandbox__` | 422 — slug pattern `__*__` reserved for system-managed matters. |
| Sandbox audit | Sandbox conversations DO write audit rows; tagged `is_sandbox=true` so dashboards can filter. |
| Privileged-tier on sandbox | Sandbox = explicit non-privileged scope (`privileged=false`, no tier minimum). Skills marked privileged-floor still try in sandbox but fall back to standard tier. |
| Shared sandbox link | Per-user; another user can't open it (existing matter authorization rules). |

### Detail tabs

| Case | Handling |
|---|---|
| `?tab=tryit` on built-in skill | Works — Try-it attaches the built-in directly. |
| `?tab=versions` on built-in | Empty state: "Built-in skill · no edit history. Fork it to create your own version." |
| `?tab=versions` on team-skill as member | Read-only history rendered. |
| `?tab=` unknown value | Falls back to `use`. |

### General

| Case | Handling |
|---|---|
| Network failure on save | Form state retained; toast "Couldn't save — retry?"; localStorage preserved. |
| Concurrent team-skill edits | Last-write-wins (existing PATCH semantics). Audit log shows both edits; Versions tab makes divergence visible without merge UI. |
| Role downgrade mid-wizard | Save returns 403; toast names the role change; draft preserved. |

### Explicitly NOT handled in D.2

- Cross-device draft sync (localStorage only)
- Slash grammar arg parsing (`/slug arg=value`)
- Diff view in Versions tab
- Conflict resolution UI for concurrent team-skill edits (last-write-wins is the policy)
- Sandbox conversation rate-limiting beyond standard provider quotas

## 8. Testing

Per CLAUDE.md: 80% coverage target; regression tests on every fix; OpenAPI schema-conformance on new endpoints. Wave-D.1 lesson — lint-clean is not run-clean — is binding: every Cypress spec gets live-executed before D.2 closes.

### Backend unit (`api/tests/`)

- `test_user_skills_slash_alias.py` — regex validation, case sensitivity, length bounds, reserved prefixes.
- `test_skills_autocomplete_ranking.py` — prefix vs contains ranking, empty-q recent-fallback, resolver shadowing, limit clamping.
- `test_projects_sandbox_slug_reserved.py` — POST /projects rejects `slug="__sandbox__"` for non-sandbox writes.
- `test_skills_capture_payload.py` — `source_message_id` accepted but not enforced as FK; `forked_from` write-once; PATCH ignores those fields.

### Backend integration (`api/tests/integration/`, marker `integration`)

- `test_user_skills_create_with_slash_alias.py` — round-trip, 422 on duplicate alias, archived skills free alias.
- `test_skills_autocomplete_endpoint.py` — seed user-skills + built-ins, assert ordering + resolution + recent-fallback.
- `test_projects_sandbox_ensure.py` — first call 201, second 200 same id, archive-then-ensure → 201 new id.
- `test_projects_sandbox_concurrency.py` — two concurrent ensure calls return same row, single audit entry.
- `test_audit_log_filter_user_skill.py` — `target_type=user_skill&target_id=<uuid>` filter correctness + pagination.
- `test_skills_send_with_slash_unresolved.py` — leading `/unknown` falls through as plain text + `slash_unresolved=true`.

### Schema-conformance

- `test_openapi_wave_d2.py` — assert `/skills/autocomplete` + `/projects/sandbox/ensure` appear in generated OpenAPI; assert request/response shapes match `docs/api/backend-openapi.yaml` (updated in this wave).

### Frontend unit (Vitest, `web/src/lib/lq-ai/__tests__/`)

- `SkillWizard.test.ts` — section visibility, slug auto-derivation, slash_alias regex validation, Save button gating, localStorage draft auto-save/restore.
- `CaptureSkillModal.test.ts` — pre-population from an AI message fixture, Save call shape, "Edit in wizard" navigation with localStorage stash.
- `SlashPopover.test.ts` — opens on bare `/` at column 0, closes on Esc/blur, ArrowUp/Down nav, Enter pick emits selection, doesn't open mid-text.
- `SkillVersionsTab.test.ts` — empty state for built-in, rendered table for user-skill with N audit rows.
- `AttachedSkillPill.test.ts` — render + dismiss + a11y label.

### Cypress E2E — `wave-d2-skill-creator.cy.ts`

Six scenarios (wave-prefix convention from D.1; runs against live stack):

1. **Capture happy path.** Login → matter → prompt → AI reply → click Capture → modal pre-populated → edit → Save → toast → row appears in `/skills`.
2. **Wizard from scratch.** `/skills` → "+ New" → fill sections 1+2+3 → set `slash_alias` `/test-skill` → Save → land on `/skills/<id>` → Use it tab renders.
3. **Fork flow.** `/skills/nda-review` → 🔱 Fork → wizard pre-populated with `(fork)` suffix → modify slug → Save → audit-log shows `forked_from=nda-review`.
4. **Slash invocation.** Composer → type `/te` → popover → select skill from test 2 → pill in context row → composer text cleared → type prompt → Send (intercept assertion).
5. **Try-it sandbox.** Saved user-skill → Try-it tab → sandbox/ensure intercepted → send prompt → AI reply → navigate away → return → conversation persists.
6. **Versions tab + slug-collision.** Edit a user-skill twice → Versions tab shows 3 rows → attempt collision on `slash_alias` → inline error names colliding skill.

**Cypress flake hedge.** Tests 4 + 5 depend on real LLM round-trips (~30–60s). Per Wave D.1 pattern: split intercepts, viewport `1440x900`, accept live LLM response. Baseline target: **5/6 stable**.

### Documentation tests

- ⟳ `docs/api/backend-openapi.yaml` — add the two new endpoints + extended request bodies + query params.
- ⟳ `docs/db-schema.md` — document `projects.is_sandbox` + `user_skills.slash_alias` + `user_skills.forked_from`.
- ⟳ ADR 0007 amendment — formalize the dual-invocation model (Q1 decision). Separate planning task per handoff; if it lands in this wave, PLAN.md calls it out.
- ⟳ `docs/skill-authoring-guide.md` — document `slash_alias` frontmatter field for built-in authors (regex + uniqueness rules).

### Manual verification before D.2 closes

- Slash popover positioning on different chat panel widths.
- Try-it pane scroll behavior inside the wizard.
- Capture modal on a long AI response (~5K tokens).
- **Live-run discipline:** every Cypress test passes against the live stack (`docker compose up -d` + real LLM) before D.2 close. Lint-clean / type-check status is necessary but not sufficient.

### Coverage thresholds

- Maintain `api/` ≥ 80% (CI enforces no-decrease).
- New frontend code: 80% Vitest target.
- New backend code in `api/app/api/skills.py` + modifications in `api/app/api/projects.py`: 90% target (a higher local bar since these are the new contracts).

## 9. Deferred enhancements (DE-XXX candidates)

Brief catalog of items surfaced but explicitly out of D.2. To be filed in PRD §9 alongside DE-219..221 from the prior session.

- **DE-222 — Slash grammar `/slug arg=value` with `inputs:` schema.** When skills demand parameterized invocation. Adds a slash parser + per-arg autocomplete reading frontmatter.
- **DE-223 — Versions tab diffs.** Snapshot table (`user_skill_versions`) + diff renderer. When users start asking "what changed in v1.2?"
- **DE-224 — Conversational capture-with-skill-creator.** Two-step capture: thin modal → "polish with skill-creator guide?" → conversational iteration using the existing `skills/skill-creator/SKILL.md`.
- **DE-225 — Cross-device draft sync.** Server-side draft storage so users can resume on another device.
- **DE-226 — Per-user `override_tier_floor` permission for sandbox.** Today's policy: sandbox is non-privileged scope, full stop. If users want to test privileged-floor skills in sandbox, this becomes a per-user permission.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Slash popover positioning bugs in narrow chat panels | Manual verification step (see §8); fallback to fixed-bottom anchoring if portal-positioned popover drifts. |
| `projects.is_sandbox` migration on a populated database | Default `FALSE` makes it backfill-safe. Partial index `WHERE is_sandbox = false` keeps existing queries fast. |
| Wave E onboarding wants different sandbox semantics than D.2 | The column ships from D.2 with the simplest contract (per-user, non-privileged, lazy-created). Wave E can extend (e.g., pre-load Acme NDA into the same sandbox or a separate sandbox project type) without schema migration. |
| ADR 0007 amendment slips | The implementation lands the dual-invocation model independently. ADR amendment is documentary; PLAN.md surfaces this as an out-of-band doc task. |
| Cypress flake (LLM-dependent tests 4 + 5) | Mocking the LLM for these tests is a deliberate non-goal at M1 — the spec's design promise is that the slash → live skill → real reply round-trip works end-to-end. DE-227 candidate if flake becomes blocking. |

## 11. Implementation sequence (informative; PLAN.md formalizes)

Suggested rough ordering for the planning phase. Plan-phase may re-shape via dependency analysis.

1. **Schema migrations** (`0022`, `0023`, `0024`) — unblocks everything else.
2. **Backend new + modified endpoints** — autocomplete, sandbox-ensure, user-skills extensions, audit-log filters.
3. **Backend unit + integration tests + OpenAPI conformance** — completed before frontend work begins so contracts are stable.
4. **Wizard refactor** (`SkillWizard` + extracted `SkillWizardSection`) — refactor the existing 361-line flat form.
5. **Capture-from-chat** (modal + inline button + overflow menu + preference store).
6. **Fork flow** (button + `?fork=` query handling in the wizard).
7. **Try-it pane** (shared component + sandbox auto-create wiring).
8. **Detail tabs** — Try-it + Versions tabs added to `SkillDetailTabs`.
9. **Slash invocation** — popover + composer integration + pill component.
10. **Frontend unit tests + Cypress wave-d2 spec authoring**.
11. **Cypress live-run** — execute against full stack, fix integration bugs surfaced.
12. **Documentation** — OpenAPI YAML + db-schema.md + skill-authoring-guide.md + (optional) ADR 0007 amendment.

## 12. References

- Spec source: [M1 Frontend Design §7.2 — Skill Creator (three modes)](./2026-05-10-m1-frontend-design.md#72-skill-creator-three-modes)
- Q1 decision rationale: [claude-for-legal research §9](../../research/2026-05-12-claude-for-legal-review.md#9-decisions)
- Session handoff: [2026-05-12 pre-D.2](../../SESSION-HANDOFF-2026-05-12-pre-d2.md)
- ADR 0012 — DB-backed user skills (resolver order, single-row versioning)
- ADR 0007 — Skill prompt assembly (amendment pending Q1 dual-invocation)
- Visual companion mockups: `.superpowers/brainstorm/99948-1778682781/content/` (intro, wizard-layout, slash-composer)

---

*End of design. Next step is `writing-plans` skill → `PLAN.md` task breakdown.*
