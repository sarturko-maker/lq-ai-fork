# SETUP-3b fence audit — admin web pages vs the operator fence (ADR-F061 D4)

Audited 2026-07-03 against the fence table: operator-only = `/admin/aliases*` (×5),
`/admin/provider-keys*` (×4), `GET /admin/config`, `PATCH /admin/tier-policy`,
`POST /inference/override-tier-floor`; `GET /admin/tier-policy` stays admin-readable.
Backend dependency per route verified in `api/app/api/admin.py`, `api/app/api/word_addin.py`,
`api/app/api/admin_intake_bridges.py`, `api/app/api/inference_override.py`.

## Pages under `web/src/routes/lq-ai/(app)/admin/`

| Page | Endpoints called | Backend dep | Verdict | Action taken |
|---|---|---|---|---|
| `audit-log/+page.svelte` | `GET /admin/audit-log` | `AdminUser` | admin-safe | none |
| `users/+page.svelte` (NEW) | `GET /admin/users`, `PATCH /admin/users/{id}/role`, `POST/GET /admin/users/invites`, `POST /admin/users/invites/{id}/resend`, `DELETE /admin/users/invites/{id}`, `POST /admin/users/{id}/disable\|enable` | `AdminUser` | admin-safe | built admin-guarded (audit-log precedent) |
| `models/+page.svelte` | `GET /admin/aliases`, `POST /admin/aliases`, `PATCH /admin/aliases/{name}`, `DELETE /admin/aliases/{name}`, `GET /admin/config`, `GET /models` | `OperatorUser` (aliases + config); `ActiveUser` (/models) | **operator-only** | page guard tightened `is_admin` → `role === 'operator'`; sub-nav link hidden for non-operators |
| `word-addin/+page.svelte` | `GET /admin/word-addin/manifest` | `AdminUser` | admin-safe | none |
| `intake-bridges/+page.svelte` | `GET /admin/intake-bridges`, `DELETE /admin/intake-bridges/slack/{id}`, `DELETE /admin/intake-bridges/teams/{id}` | `AdminUser` | admin-safe | none |
| `developer/+page.svelte` — `DevApiDocsCard` | none (static doc/metrics links) | — | admin-safe | none |
| `developer/+page.svelte` — `DevApiPlaygroundCard` | none (reads the caller's own JWT from the local auth store) | — | admin-safe | none |
| `developer/+page.svelte` — `DevRoleManagementCard` | `GET /admin/users`, `PATCH /admin/users/{id}/role` | `AdminUser` | not fenced, but consolidated | **deleted** (plan D5) — component removed, imports cleaned; function lives on the Users page |
| `developer/+page.svelte` — `DevForkCallout` | none (static) | — | admin-safe | none |
| `+layout.svelte` (sub-nav) | none | — | — | `Users` link added; `Models` link rendered only for `role === 'operator'` |

## Fenced endpoints with NO admin-page consumer (verified by repo-wide grep)

| Endpoint | Web consumer | Verdict |
|---|---|---|
| `/admin/provider-keys*` (×4) | none anywhere in `web/src` | no UI action needed |
| `GET /admin/tier-policy` / `PATCH /admin/tier-policy` | none anywhere in `web/src` | no tier-policy UI exists — the plan's "renders read-only for admins" clause is vacuously satisfied; nothing to gate |

## Finding outside the audited scope — FIXED in the review-fix pass (F5)

- `POST /inference/override-tier-floor` (now `OperatorUser`) is called by
  `TierFloorOverrideModal.svelte` via `RefusalMessageBubble.svelte`'s override button —
  a **chat** surface, not an admin page. Originally flagged only: `showOverrideButton()`
  gated on `role === 'admin'` while the endpoint 403s org-admins.
  **Fixed (review fix F5):** `showOverrideButton()` now returns true only for
  `role === 'operator'`, and `ChatPanel`'s `currentUserRole` derivation passes the true
  `'operator'` role through unmapped (it previously collapsed operator → 'admin' via the
  `is_admin` back-compat fallback); the `currentUserRole` prop type is widened along the
  ChatPanel → MessageList → MessageBubble → RefusalMessageBubble chain. Org-admins no
  longer see a button that can only 403; the operator keeps a working one.
