# Wave D.1 — In-chat power features (Enhance Prompt expansion, KB attach modal, Tier-floor refusal block, Receipts drawer)

> **Status:** Design contract for the first slice of Wave D, derived from `docs/superpowers/specs/2026-05-10-m1-frontend-design.md` §7.1, §7.3, §7.4, §7.6. Implementation plan and code follow this spec. The second slice (Wave D.2 — Skill Creator wizard + try-it) is a separate cycle.

---

## 1. Scope contract

Wave D.1 ships the **four in-chat power features** named in M1 spec §8.1:

1. **Enhance Prompt expansion** (§7.1) — UX polish around the existing `/api/v1/enhance-prompt` endpoint
2. **KB attach modal** (§7.3) — searchable card grid + inline uploader + multi-select; 3 entry points → same modal
3. **Tier-floor refusal block** (§7.4) — refused turn persists as `kind=refusal` message; override flow with reason confirmation
4. **Receipts mode** (§7.6) — right-side toggleable drawer over the chat; chronological event log; filterable; JSONL export

The fifth power feature from §8.1 — **Skill Creator 3-mode wizard + try-it** (§7.2) — is **deferred to Wave D.2** (separate spec, separate cycle). Skill Creator is a `/lq-ai/skills/new` surface, not an in-chat feature; it has natural seams to ship independently.

**Out of scope (deferred to Wave F or later):**
- Outputs panel · Knowledge browser surface (`/lq-ai/knowledge`) · Saved Prompts surface (`/lq-ai/saved-prompts`) · Citation Engine UI — items the Wave C handoff mentioned for "Wave D" but which aren't in the spec §8.1 Wave D contract.
- Audit log polish (§7.5 — extends an existing surface; can ride with D.1 or wait for Wave F).

---

## 2. Backend additions

Wave D.1 is a **frontend-first slice with three backend additions and one schema migration**. The pattern follows Wave B v2 / Wave C — propose backend changes alongside the frontend plan; ship them together.

### 2.1 Migration 0020 — `messages.kind` discriminator

```sql
ALTER TABLE messages
  ADD COLUMN kind TEXT NOT NULL DEFAULT 'user'
  CHECK (kind IN ('user', 'ai', 'refusal', 'system'));

-- Backfill from existing role column
UPDATE messages SET kind =
  CASE
    WHEN role = 'assistant' THEN 'ai'
    WHEN role = 'user'      THEN 'user'
    WHEN role = 'system'    THEN 'system'
    ELSE 'user'
  END;

CREATE INDEX idx_messages_kind ON messages(kind);
```

**Why a dedicated column** (vs JSONB metadata): indexable for Receipts filtering and refusal-only queries; type-safe at SQLAlchemy + Pydantic layers; small migration footprint with cheap backfill. Selected during brainstorming over JSONB and hybrid shapes.

**Downstream model + schema changes:**
- `api/app/models/message.py` — add `kind: Mapped[str]`
- `api/app/schemas/message.py` — add `kind: Literal['user','ai','refusal','system']`
- Existing message-writing call sites pass `kind` explicitly (default `'user'` for client messages, `'ai'` for assistant replies)

### 2.2 `POST /api/v1/projects/{id}/knowledge-bases` (and DELETE)

Mirrors the existing `/files` and `/skills` attach endpoints in `api/app/api/projects.py`. Two routes:

```
POST   /api/v1/projects/{project_id}/knowledge-bases
       Body: { knowledge_base_id: UUID }
       Returns: updated Project

DELETE /api/v1/projects/{project_id}/knowledge-bases/{kb_id}
       Returns: 204
```

**Audit actions:** `project.knowledge_base_attached` / `project.knowledge_base_detached`.

**Authorization:** matter owner via existing RBAC scoping in `projects.py` (`require_project_access` pattern).

**Junction table:** if `project_knowledge_bases` doesn't exist, this migration creates it (composite PK on `project_id` + `knowledge_base_id`, FK CASCADE on either side). Verify state during plan-writing — if a junction already exists for another purpose, reuse.

### 2.3 `POST /api/v1/inference/override-tier-floor`

```
POST /api/v1/inference/override-tier-floor
Body: {
  message_id: UUID,           # the refusal message being overridden
  reason: str                  # 10..500 chars, required
}
Returns: {
  ai_message: Message,         # the new kind=ai response from re-run
  routing_log_id: UUID         # the new inference_routing_log row
}
```

**Behavior:**
1. Load the refusal message by ID (`kind='refusal'`); 404 if not found or not refusal.
2. Verify caller has `override_tier_floor` permission (check RBAC role enum — add if missing).
3. Re-run inference for the original user prompt with `tier_floor=None` for this turn only (do not persist a downgrade on the matter).
4. Write a new `kind='ai'` message with the response.
5. Write audit row: `action='inference.tier_floor_overridden'`, `actor_user_id`, `subject_id=message_id`, `details={reason, original_floor, original_provider_attempted, new_provider, new_message_id}`.
6. Return the new AI message + routing log ID.

**Permission:** the spec §7.4 says "only available with `override_tier_floor` permission." Check the role enum; if absent, add as a column-level permission (not a role; bound to admin + member explicit grant). Confirm during plan-writing.

### 2.4 `GET /api/v1/chats/{id}/receipts` (replay-at-read)

Handler merges events from multiple source tables for a given `chat_id` and returns a chronological JSON array.

**Sources to union:**
- `messages` — every message row → event `{kind: 'message', ts, detail: {message_id, message_kind, role, token_count?}}`
- `inference_routing_log` — every provider call → event `{kind: 'inference', ts, detail: {provider, model, tier, input_tokens, output_tokens, duration_ms}}`
- `chat_skill_applications` — every skill applied → event `{kind: 'skill', ts, detail: {skill_id, version, applied_by}}`
- `audit_log` — audit rows where `resource_type='chat' AND resource_id=chat_id` → event `{kind: 'audit', ts, detail: {action, actor_user_id, ...}}`
- KB retrievals — extracted from `inference_routing_log.retrieved_chunks` JSONB if present (each chunk → one retrieval event), OR a dedicated `kb_retrieval_log` table if one exists. Confirm during plan-writing.

**Query params:**
- `event_kinds=message,inference,skill,audit,retrieval,error` (comma-separated subset)

**Export endpoint:**
- `GET /api/v1/chats/{id}/receipts/export.jsonl` — same payload, one event per line, `Content-Type: application/jsonl`, served with `Content-Disposition: attachment; filename="chat-{id}-receipts.jsonl"`

**Why replay-at-read** (vs materialized table): M1 chats are bounded (<100 events typical); no migration; no drift risk; cheapest to ship. Selected during brainstorming. If chat sizes grow past replay's comfortable latency, a materialized `chat_receipts` table is the v1.1+ option.

---

## 3. Frontend features

### 3.1 Composition (the chat surface)

D.1 lives entirely in two existing routes:

- `/lq-ai/chats` (standalone chat shell, Wave C)
- `/lq-ai/matters/[id]` (2-pane workspace: matter rail + ChatPanel, Wave C)

The composition (validated visually during brainstorming):

```
┌──────────┬────────────────────────────┬──────────┐
│  Matter  │  ChatPanel                 │ Receipts │
│  rail    │  ┌─ user message ───────┐  │ drawer   │
│  (140px) │  │ Quick check — can…   │  │ (240px,  │
│  Wave C  │  └──────────────────────┘  │  toggle) │
│          │  ┌─ kind=refusal ───────┐  │ Wave D.1 │
│          │  │ 🛡 Refused at…       │  │          │
│          │  │  [Re-run][Override]  │  │ filter   │
│          │  │  [Why?]              │  │ chips    │
│          │  └──────────────────────┘  │          │
│          │  ─────────────────────────  │ event    │
│          │  📎 ✨ 📜  [composer…]      │ list     │
└──────────┴────────────────────────────┴──────────┘
```

- Receipts drawer width: **240px** default, **closeable** (toggle on/off persists per-user per-chat in localStorage)
- Composer toolbar (left-to-right): **📎 KB attach · ✨ Enhance prompt · 📜 Receipts toggle**, then existing send affordance on the right
- Refusal block is a `MessageBubble.svelte` variant dispatched on `kind === 'refusal'`

### 3.2 Enhance Prompt expansion (§7.1)

Existing assets in `web/src/lib/lq-ai/`:
- `components/EnhancePromptExpansion.svelte`
- `api/enhancePrompt.ts`
- Tests: `__tests__/EnhancePromptExpansion.test.ts`, `__tests__/enhance-prompt-api.test.ts`

**Plan-time audit:** during plan-writing, grade the current implementation against spec §7.1 line by line and ship only the deltas. Likely gaps to verify:

| §7.1 requirement | Status |
|---|---|
| ✨ button in composer toolbar | likely present (handoff confirmed) |
| `⌘E` keyboard shortcut | verify |
| Inline expansion below composer | verify |
| Three actions: Use / Edit / Keep | verify all three |
| First-time JIT post-action toast | verify |
| `✨ enhanced` provenance pill on sent | verify |
| Tap pill → diff view | verify |
| Settings toggle: auto-enhance on send | verify; add to `/lq-ai/settings/appearance` if missing |
| Empty composer disables button | verify |
| >500-token prompt → "Refine" framing | verify |
| Error → inline retry | verify |

Each gap = 1 atomic commit during execution.

### 3.3 KB attach modal (§7.3)

**Modal shape (`AttachKBModal.svelte`):**

```
┌────────────────────────────────────────────────────┐
│ Attach Knowledge Bases                          ×  │
├────────────────────────────────────────────────────┤
│ [search bar: "Search by name…"      ] [sort ▼]    │
├────────────────────────────────────────────────────┤
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│ │ NDA-Playbook│  │ M&A Templates│ │ Lease KB   │ │
│ │ 47 docs     │  │ 23 docs     │  │ 12 docs    │ │
│ │ ✓ indexed   │  │ ⏳ 67%      │  │ ✓ indexed   │ │
│ │ on 3 matters│  │ on 1 matter │  │ on 5 mat.   │ │
│ │ ☐           │  │ ☐           │  │ ☐ (current) │ │
│ └─────────────┘  └─────────────┘  └─────────────┘ │
│                                                    │
│ ─── or upload a new KB ────────────────────────── │
│ [📎 Upload files…]                                 │
├────────────────────────────────────────────────────┤
│              [Cancel]  [Attach 2 selected]         │
└────────────────────────────────────────────────────┘
```

- **Card grid:** auto-fill, min-width 200px per card. Each card shows: name · doc count · embedding status (`✓ indexed` / `⏳ {pct}%` / `⚠ failed`) · attached-count badge (e.g., "on 3 matters") · multi-select checkbox.
- **Search bar:** filters by name client-side (KB count is small).
- **Sort menu:** Recently used · Alphabetical · Most attached · Indexing status. Default: Recently used.
- **Inline uploader:** "or upload a new KB" section below the grid; click triggers a file picker, uploads via `/api/v1/knowledge-bases` POST + immediate `/files` attach. New KB appears in the grid with `⏳` indexing status.
- **Multi-select:** checkbox on each card; primary CTA counter ("Attach N selected") updates live.
- **Already-attached state:** cards for KBs already on this matter render with a subtle "currently attached" badge and a different default (checkbox unchecked but a "Detach" link surfaces).
- **First-time JIT pre-action banner:** dismissible amber banner at top of modal on first open — spec §6.6 trigger.

**3 entry points → same modal:**
1. In chat composer: 📎 button
2. In matter rail Knowledge section: `+ Attach KB`
3. From `/lq-ai/knowledge` card → `Attach to matter…` (Wave F — out of D.1 scope; D.1 only ships entry points 1 and 2)

### 3.4 Tier-floor refusal block (§7.4)

**`RefusalMessageBubble.svelte`** — variant of `MessageBubble.svelte` dispatched when `message.kind === 'refusal'`. Amber treatment (background `#fffbeb`, border `#f59e0b`, text `#92400e`/`#78350f`).

**Content:**
- 🛡 icon + bold "Refused at {enforced_tier}-floor" heading
- Body paragraph (templated from spec §7.4 with `{requested_tier}`, `{enforced_tier}` substitutions)
- Three buttons:
  - **`[Re-run at {enforced_tier}-floor]`** — primary CTA; re-sends the original prompt with the enforced floor; backend creates a new `kind=ai` message via the normal /chat path
  - **`[Override for this turn*]`** — secondary; opens `TierFloorOverrideModal.svelte`
  - **`[Why am I seeing this?]`** — tertiary; opens a JIT explainer (links to docs or inline modal)
- Provenance pills: `🔒 tier mismatch (requested {x}, enforced {y})` · `📜 audited`
- No provider pill (no call was made to a provider)

**`TierFloorOverrideModal.svelte`** — confirmation modal:
- Title: "Override tier floor for this turn"
- Body: "This will route to a {original_tier} provider for this single turn. The override is logged in the audit trail. State a reason:"
- Required textarea: 10..500 chars
- Cancel + Confirm. On confirm: `POST /api/v1/inference/override-tier-floor`. On 200: replaces the refusal with the new AI response in-place; on error: inline error banner.

**Hidden when user lacks `override_tier_floor` permission** — the Override button doesn't render. Re-run + Why remain.

### 3.5 Receipts drawer (§7.6)

**`ReceiptsDrawer.svelte`** — right-side toggleable drawer.

**Shape:**
- Width: 240px (collapsible to closed via × button or composer 📜 toggle)
- Header: `📜 Receipts` · close button
- Filter chips row (horizontal scroll on overflow): all (default) · events · retrievals · providers · audit · errors
- Event list: chronological, newest at bottom (or top — confirm during plan; spec is ambiguous, default to newest-at-bottom matching chat scroll direction)
- Each event row: timestamp (HH:MM:SS) · icon + short description · expandable detail on click
- Sticky footer: `⤓ Export JSONL` button

**`ReceiptsList.svelte`** — pure render component fed by `receipts.ts` API client.

**State:**
- Open/closed state persists per-user per-chat in localStorage (`lq_ai_receipts_drawer_open_{chat_id}`)
- Filter selection is session-only (resets on reload)

**Refresh strategy:** poll every 5s while drawer is open AND chat is active (a new message just arrived). Stop polling when drawer closes. Plan-time refinement: consider SSE-driven invalidation off the existing chat stream instead of polling.

---

## 4. File structure / component map

### Net-new files

```
web/src/lib/lq-ai/components/
  ReceiptsDrawer.svelte
  ReceiptsList.svelte
  ReceiptsExport.ts
  RefusalMessageBubble.svelte
  TierFloorOverrideModal.svelte
  AttachKBModal.svelte

web/src/lib/lq-ai/api/
  receipts.ts
  inferenceOverride.ts
  projectKnowledgeBases.ts

web/src/lib/lq-ai/__tests__/
  ReceiptsDrawer.test.ts
  ReceiptsList.test.ts
  ReceiptsExport.test.ts
  RefusalMessageBubble.test.ts
  TierFloorOverrideModal.test.ts
  AttachKBModal.test.ts
  receipts-api.test.ts
  inference-override-api.test.ts
  project-knowledge-bases-api.test.ts

web/cypress/e2e/
  wave-d1-power-features.cy.ts

api/app/api/
  inference_override.py
  chat_receipts.py
  (extend projects.py with /knowledge-bases routes)

api/app/models/
  (extend message.py with kind column)

api/app/schemas/
  (extend message.py schema)

api/alembic/versions/
  0020_messages_kind_discriminator.py
  0021_project_knowledge_bases_junction.py  (if not already present)
```

### Modified existing files

```
web/src/lib/lq-ai/components/MessageBubble.svelte
  — dispatch to RefusalMessageBubble when kind === 'refusal'

web/src/lib/lq-ai/components/ChatPanel.svelte
  — receipts drawer slot + composer-toolbar receipts toggle
  — KB attach 📎 button → opens AttachKBModal

web/src/lib/lq-ai/components/Composer.svelte
  — ⌘E enhance hotkey
  — empty-composer button-disabled behavior
  — Refine-vs-Enhance label switch at >500 tokens

web/src/routes/lq-ai/settings/appearance/+page.svelte
  — auto-enhance toggle (if missing)

web/src/lib/lq-ai/components/MatterRailKnowledge.svelte
  (or wherever the matter rail's KB section lives — verify)
  — "+ Attach KB" → opens AttachKBModal

api/app/api/projects.py
  — add POST/DELETE /api/v1/projects/{id}/knowledge-bases routes

api/app/audit.py
  — add new action constants: project.knowledge_base_attached,
    project.knowledge_base_detached, inference.tier_floor_overridden,
    receipts.exported (if audit-on-export is desired — confirm)

api/app/api/__init__.py
  — register inference_override + chat_receipts routers
```

---

## 5. Testing strategy

### Vitest (per Wave C precedent — 7-8 unit tests per major component)

- `ReceiptsDrawer.test.ts` — open/close toggle, localStorage persistence, filter chip selection, export-button click
- `ReceiptsList.test.ts` — event rendering by kind, timestamp formatting, expand-on-click
- `ReceiptsExport.test.ts` — JSONL serialization
- `RefusalMessageBubble.test.ts` — 3 buttons render, permission gating hides Override, copy variants for tier strings
- `TierFloorOverrideModal.test.ts` — reason validation (10..500 chars), confirm calls API, error display
- `AttachKBModal.test.ts` — search filters, sort changes, multi-select counter, inline upload triggers /knowledge-bases POST
- API-client tests: `receipts-api.test.ts`, `inference-override-api.test.ts`, `project-knowledge-bases-api.test.ts`

### Pytest (api/)

- `tests/api/test_messages_kind.py` — migration 0020 backfill correctness; new `kind` column constraints; refusal kind round-trip
- `tests/api/test_inference_override.py` — 3 happy-path tests + permission-denied + missing-reason + non-refusal-message-id
- `tests/api/test_chat_receipts.py` — replay-at-read merges all 4 sources correctly; filter param works; export endpoint emits valid JSONL
- `tests/api/test_project_knowledge_bases.py` — attach + detach + audit row written + permission-scoped

### Cypress E2E

`web/cypress/e2e/wave-d1-power-features.cy.ts` covering:
1. Enhance prompt: composer ⌘E → expansion appears → click Use enhanced → message sends with provenance pill
2. KB attach modal: composer 📎 → modal opens → search + select 2 → Attach → modal closes → matter rail reflects 2 new KBs
3. Tier-floor refusal: send a prompt that triggers refusal → amber block renders → click Override → modal → reason → confirm → block replaced with AI response
4. Receipts drawer: composer 📜 → drawer opens → filter chips work → export JSONL downloads
5. Refusal without override permission: same as #3 but Override button absent

---

## 6. Open items routed forward

- **Saved Prompts surface** — out of D.1 (deferred to Wave F or post-M1 per spec contract).
- **Citation Engine UI** — out of D.1 (deferred per spec).
- **Outputs panel** — out of D.1 (deferred).
- **`/lq-ai/knowledge` browser surface** — out of D.1 (entry point 3 to AttachKBModal). Wave F or a separate cycle.
- **Audit log polish (§7.5)** — extends an existing surface; can ride with D.1 if it lands easily, otherwise Wave F.
- **Materialized `chat_receipts` table** — v1.1+ option if replay-at-read latency becomes a problem.

---

## 7. Definition of done

D.1 ships when:

1. Migration 0020 (and 0021 if needed) applied; backfill verified.
2. Three new backend endpoints implemented + tested.
3. Six new Svelte components + three API clients shipped + unit-tested.
4. Five Cypress scenarios pass.
5. Zero V2-FALLBACKs introduced (Wave C precedent).
6. Vitest baseline maintained (174 → 174 + new tests).
7. Backend integration suite green (486 + new tests).
8. Smoke-tested: log into `admin@lq.ai`, open a matter, exercise each of the 4 features in a real chat.
9. Atomic commits per task per Wave C precedent (`feat(web):` / `feat(api):` / `test(web):` etc., DCO sign-off, Co-Author trailer).
