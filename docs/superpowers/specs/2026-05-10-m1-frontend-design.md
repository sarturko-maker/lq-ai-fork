# LQ.AI — M1 Frontend Design

| | |
|---|---|
| **Status** | DRAFT — awaiting Kevin's review |
| **Authored** | 2026-05-10 |
| **Branch** | `kk/main/Frontend_Design` |
| **Working dir** | `/Users/kevinkeller/Desktop/lq-ai` |
| **Anchors** | [PRD §1.3 Transparency](../../PRD.md), [M1-IMPLEMENTATION-ORDER](../../M1-IMPLEMENTATION-ORDER.md), [M1-PROGRESS](../../M1-PROGRESS.md), [ADR 0009 Web shell coexistence](../../adr/0009-web-lq-ai-shell-coexistence.md), [ADR 0011 Transparency-first model selection](../../adr/0011-transparency-first-model-selection.md), [ADR 0012 DB-backed user skills](../../adr/0012-db-backed-user-skills.md) |
| **Scope** | The `/lq-ai/*` web shell at M1 feature-complete. OpenWebUI shell at `/` is untouched per ADR 0009. Word add-in (M3), citation engine UX (M2), anonymization UX (M2) are out of scope. |

---

## 1. Problem framing

LQ.AI is positioning as the open-source alternative to gc.ai, Spellbook, and Legora — closed-source legal-AI products that compete on a combination of polish, opinionated workflow design, and FUD against open source ("security risk", "confidentiality loss", "loss of privilege", "no accountability").

The current `/lq-ai/*` frontend is correct but **technical and mechanical** — surfaces work, but they don't feel like a product an in-house attorney would choose over those competitors. The M1 backend is rich (chat + skills + KBs + projects/matters + tier-aware refusals + audit + MFA + saved prompts + DB-backed user skills + skill creator + encrypted keys) and is the source of LQ.AI's competitive durability, but at M1 handoff the surface has to actually *surface* that depth in a way non-technical attorneys can find, use, and understand.

This spec captures the design for the M1 frontend redesign — the work that takes the M1-feature-complete backend and surfaces it as a "very viable and very usable" alternative to the proprietary category leaders.

## 2. Goals and non-goals

**Goals:**
1. Approachable for non-technical attorneys (≤ 30 seconds to orient on first login)
2. Surface all M1 functionality in ways that are easy to *find · use · understand*
3. Visibly answer the open-source FUD (security, confidentiality, privilege, accountability)
4. Make the transparency principle from PRD §1.3 a *felt* property — present in every reply, not just claimed in marketing
5. Feel like serious practice software (not a toy) without intimidating non-technical users
6. Stay within the OpenWebUI rebase contract from ADR 0009 (`/lq-ai/*` only; OpenWebUI shell at `/` untouched)

**Non-goals (for this M1 frontend cycle):**
- Word add-in (M3)
- Citation engine UX (M2)
- Anonymization UX (M2)
- Playbooks (M3 — distinct from KBs)
- Slack/Teams (M3)
- Real-time multi-user collaboration on a matter (PRD §9 deferred)
- Mobile-first layout (desktop/tablet primary; phone gets usable-but-reduced)
- Dark mode (parallel palette specified but light-only at M1)

## 3. Design synthesis — "Approachable workspace with felt transparency"

The design rests on three claims, expressed by eight design decisions made during brainstorming:

**Approachable on the surface.** A Practice visual direction (white + sage + all-sans + generous whitespace) on a top-tabs nav, with a Guided Dashboard as the front door. The chrome reads as contemporary B2B SaaS — Spellbook/Legora-tier polish — not as developer software.

**Serious underneath.** When an attorney enters a matter, the canvas becomes a three-pane Workspace (matter rail · chat · outputs panel). Documents live next to chat. Outputs (drafts, redlines, action items) accumulate in their own pane. The workspace shape is what differentiates LQ.AI from "chat with my legal documents" toys.

**Transparent in every reply.** Every AI message carries inline provenance pills — `🛠️ Skill · 🔒 Tier · 🧠 Provider · 📎 KB chunks · 📜 Audit`. Tapping a pill drills into a Provenance/Audit tab in the outputs panel. A `Receipts` mode is always one click away from any chat, showing the full chronological event log. This makes transparency-first felt, and is the visible answer to the open-source FUD.

**Personalization throughline.** Every prominent surfacing pattern is user-toggleable to its quieter form. Featured tools demote to inline toolbar. Workspace collapses to 2-pane or 1-pane. Trust pills shrink to dots. Provenance pills collapse on hover. The product educates aggressively on day 1 and gets out of the way on day 30.

**Onboarding cascade.** First launch drops the attorney into a pre-loaded sandbox matter (Acme Mutual NDA + sample playbook attached) with a guided walkthrough that *uses* the product on their behalf. A Getting-started checklist persists on the dashboard for remaining wins; auto-hides when complete. A re-runnable concierge tour lives under a `?` menu. JIT tooltips layer over everything.

---

## 4. Information architecture and primary surfaces

### 4.1 Top-tab nav (always visible, authenticated surfaces)

```
Home · Chats · Matters · Skills · Knowledge · Saved Prompts                  ⌘K · ?menu · Sarah ▾
```

Admin renders only for admin users. The `?menu` provides re-runnable tour, "What's new", "Trust & Privacy" link, keyboard shortcuts.

### 4.1.1 RBAC role enum

The three-role system from PRD §5.2 is the canonical contract. Frontend consumes the backend's enum verbatim:

```ts
type UserRole = 'admin' | 'member' | 'viewer';
```

| Role | UI implications |
|---|---|
| `admin` | Admin tab visible. Full mutation access. Sees role-management card, audit log, model/tier policy. |
| `member` | Admin tab hidden. Full mutation access on owned resources (chats, skills, prompts, KBs). Default role for new signups. |
| `viewer` | Admin tab hidden. Read-only across the product — composer disabled, "Save", "Delete", "Edit" buttons hidden or surfaced as a polite "read-only" affordance. Mutating endpoints reject `viewer` via the backend's `MutatingUser` dependency. |

**Gate pattern.** Tab/component visibility uses `role === 'admin'` (forward-compatible) with `is_admin === true` as a back-compat fallback for legacy callers; the backend keeps `role='admin'` in sync with `is_admin=true` per migration 0017. Read-only UX for `viewer` is implemented as a layer in §5 (visual treatment of disabled affordances + a small read-only badge in the ambient chrome) — **shipping the read-only UX is Wave C scope; Wave B v2 only consumes the enum for the admin-tab gate.**

### 4.2 Primary surfaces

| Surface | Route | What it is | Key components |
|---|---|---|---|
| Home (Guided Dashboard) | `/lq-ai` | Post-login front door | Trust panel · Composer · Featured tools (Enhance · Skill Creator · KB · Apply skill) · Getting-started checklist (when active) · Recent matters · Recent chats |
| Chats | `/lq-ai/chats` *(new)* | All conversations | Thread list with tier/skill/matter pills · filter by matter/skill/tier · "New chat" |
| Matters | `/lq-ai/matters` *(new)* and `/lq-ai/matters/[id]` *(new)* | Project workspace (PRD C7 surfaces as "Matters") | List view (cards) · detail view = 3-pane Workspace (matter rail · chat · outputs panel) |
| Skills | `/lq-ai/skills`, `/lq-ai/skills/new`, `/lq-ai/skills/[id]`, `/lq-ai/skills/[id]/edit` | Library + creator (D8) | Built-in + user/team skills · scope filter chips · prominent "Create skill" · skill detail = tabbed (Use it · View source · Try it · Versions) |
| Knowledge | `/lq-ai/knowledge` *(new)* and `/lq-ai/knowledge/[id]` *(new)* | KB browser / uploader | Card grid · embedding status · attach-to-matter shortcut · upload zone |
| Saved Prompts | `/lq-ai/saved-prompts` *(new)* | D7 deliverable | List · run · edit · "convert to skill" |
| Admin (gated) | `/lq-ai/admin/*` | Audit, models, providers, developer support | Existing `/admin/audit-log` and `/admin/models` extended; new `/admin/developer` *(Wave B)* — links to backend OpenAPI docs (Swagger UI / ReDoc) and a developer "API playground" panel for trying endpoints with the operator's own auth token |
| Trust & Privacy | `/lq-ai/trust` *(new)* | Procurement-grade FUD-buster | Data residency map · providers configured · external-turn counts · SBOM / signed-releases / threat-model links |

Cross-cutting surfaces (not tabs, but reachable from chrome):
- ⌘K Launcher — universal jump
- ? Menu — re-runnable tour, what's new, trust & privacy, keyboard shortcuts
- Receipts — toggle inside any chat (`💬 Chat ⇄ 📜 Receipts`)

### 4.3 Personalization toggles

Four toggles in `/lq-ai/settings/appearance` *(new)*:
- **Featured tools**: Prominent cards (default) | Inline toolbar
- **Workspace layout**: Three panes (default) | Two panes | Single pane
- **Trust pills**: Labels (default) | Dots
- **Provenance pills**: Always shown (default) | Collapsed; expand on hover

Defaults are the brave choices (more visible, more orienting). Veterans can dial back. State persists per-user.

---

## 5. Cross-cutting patterns and the Practice visual system

### 5.1 Ambient trust chrome

A persistent, low-volume reassurance layer on every authenticated surface.

**Top bar (right of brand):**
- `● self-hosted` (sage pill) — tap opens Trust & Privacy
- `🔒 privileged ✓` (sage pill) — tap opens "Why this tier?"
- `⌘K` (subtle kbd hint)
- User menu

**Footer (chat surfaces):**
- `● anthropic-claude · privileged-floor` — current routed provider+tier
- `✓ audit on · 0 leaks today` — tap opens today's audit log

**State transitions:**
- Tier-floor refusal in flight → top-bar tier pill flips to amber `⚠ tier mismatch` for 5s before refusal renders
- External provider call mid-stream → footer provider name briefly highlights
- Audit write fails → footer pill flips to red `⚠ audit unhealthy` (intentional — if audit breaks, the trust claim breaks)

### 5.2 Inline provenance pills

Every AI message has a pill row attached to its bottom edge.

| Pill | Always shown? | Tap behavior |
|---|---|---|
| 🛠️ Skill | Only if a skill ran | Provenance tab → Skill source card with `view source` link to skill markdown |
| 🔒 Tier | Always | "Why this tier?" explainer (floor + override history + provider chosen) |
| 🧠 Provider | Always | Provider detail (model + tokens + cost estimate + latency) |
| 📎 KB chunks | Only if retrieval happened | "Retrieved passages" with chunk text + source doc + relevance |
| 📜 Audit | Always | Audit tab filtered to this message's audit entries |
| ✨ Enhanced | Only if user's prompt was enhanced before send | Original-vs-enhanced diff |

Pills are sage-on-cream by default; tier pill shifts to amber if the tier was lower than expected.

### 5.3 JIT messaging taxonomy

Three trigger classes:

1. **Pre-action heads-up** — before a sensitive action, an inline banner appears in the composer (first-time external provider call, first-time tier override, first-time KB attach). Dismissable-with-don't-show-again per user.
2. **Mid-action inline explainers** — `(?)` icons next to non-obvious chrome labels. Hover = 2-sentence explanation; click = Trust & Privacy section.
3. **Post-action moments** — first-success cheers after applying a skill, using Enhance Prompt, opening Receipts, encountering a tier-floor refusal.

All dismissals stored in `user_preferences.jit_dismissals[]`.

### 5.4 Practice visual system

**Palette** (reference; CSS variables for downstream theming per §10):
- Background: `#ffffff` canvas · `#fafbfa` inset · `#f7faf8` sage-tinted trust inset
- Text: `#1a1a1a` primary · `#4b5563` secondary · `#9ca3af` tertiary
- Sage primary: `#1f7a6b` (buttons, active tabs, secure-state)
- Sage soft: `#e8f4ec` (pill backgrounds, panel tints)
- Slate accent: `#355a82` (privilege/tier — distinct from sage so they don't blur)
- Amber: `#a16e1f` on `#fdf3e2` (warnings, JIT pre-action banners, tier override)
- Red: `#b54848` on `#fbeaea` (audit unhealthy, errors — rare)

**Typography:**
- Family: Inter (variable)
- Weights: 400 body · 500 emphasis · 600 headers/buttons
- Sizes: 12 label · 13.5 body-small · 14 body · 16 panel-header · 18 page-header · 22 welcome
- Numeric: tabular-nums for token counts, audit timestamps, tier-floor numbers

**Component contracts:**
`TrustPill`, `ProvenancePill`, `FeaturedToolCard`, `MatterCard`, `ChecklistPanel`, `ComposerToolbar`, `JITBanner`, `OutputsPanel`, `ReceiptsView`, `EnhanceExpansion`, `SkillCreatorWizard`, `SkillDetailTabs`, `KBAttachModal`, `TierFloorRefusal`, `SandboxBanner`, `Tour`.

OpenWebUI primitives (chat bubbles, markdown, syntax highlighting) are imported, not modified, per ADR 0009.

---

## 6. Onboarding flow (hybrid: sandbox + checklist + re-runnable tour)

### 6.1 First-launch gate

A user is in first-launch state when `users.onboarding_completed_at IS NULL` (net-new column).

```
Login → must-change-password gate (B2) → password rotated →
  IF onboarding_completed_at IS NULL → Sandbox first-launch flow
  ELSE → Dashboard
```

Skip sets `onboarding_completed_at = now()` without completing the walkthrough; checklist remains active on dashboard.

### 6.2 Sandbox sample matter

Seeded per-user on first launch via `POST /api/v1/onboarding/seed-sandbox` *(new)*:
- Matter name: "Acme Corp — Mutual NDA (sample)"
- Documents: `acme-mutual-nda-v3.docx` (4-page synthetic mutual NDA with intentional playbook-violating clauses), `acme-redlines.pdf` (sample counterparty redlines)
- KB attached: "NDA Playbook (sample)" — synthetic playbook the NDA-Review skill cites against
- Tier: `privileged-floor`
- Persistent sandbox banner (sage gradient): "Sample matter — nothing here is shared outside your stack. [Delete sandbox when ready]"

Storage:
- Static content in `web/static/onboarding/sandbox/`
- Seeded as real matter rows owned by the user; `matters.is_sandbox = true` (net-new column) so the dashboard banner and checklist can detect

### 6.3 Guided walkthrough (5 steps)

| # | Anchor | Teaches | User action |
|---|---|---|---|
| 1 | Trust panel | "Your data is in your firm's stack." | Got it → step 2 |
| 2 | Sample matter card | "We've set up a sample so you can try the product." | Click matter → step 3 |
| 3 | Composer + Featured Tools | "This is where you ask. Let's run NDA-Review." | Apply skill → step 4 |
| 4 | Provenance pills | "Every reply shows what the AI did." | Tap a pill → step 5 |
| 5 | Outputs panel | "Drafts and redlines collect here." | I've got it → done |

After step 5: `onboarding_completed_at = now()`, checklist item #1 auto-checks, success toast.

### 6.4 Getting-started checklist (persists on dashboard)

`<ChecklistPanel>` between trust panel and Featured Tools. Auto-detects completion (no manual check-off). Auto-hides when all complete (reset link in settings).

| # | Item | Detection | Est. |
|---|---|---|---|
| 1 | Log in & rotate password | `must_change_password = false` | done |
| 2 | Run a skill on a document | ≥1 message with `skill_id IS NOT NULL` | 2 min |
| 3 | Try Enhance Prompt | ≥1 message with `enhance_prompt_used = true` | 30 sec |
| 4 | Attach a knowledge base | ≥1 matter with ≥1 KB attachment | 3 min |
| 5 | Save a prompt as a skill | ≥1 row in `user_skills` OR `saved_prompts` | 1 min |

MFA enrollment lives in account settings with its own JIT nudge (not part of the AI-ramp checklist).

### 6.5 Re-runnable concierge tour (? menu)

`?menu → Take a tour`. A 4-step annotated overlay that walks the chrome of whatever surface the user is currently on. Same overlay component as the first-launch walkthrough, parameterized by anchor list.

### 6.6 JIT triggers (M1 set)

| Moment | Class | Copy |
|---|---|---|
| First external provider call ever | Pre-action | "Routes to Anthropic Claude (your firm's key). Continue · Route to local · Why?" |
| First tier override | Pre-action | "You're overriding your firm's default tier-floor. Audit logs this. Continue · Cancel" |
| First KB attach | Pre-action | "KB content is included every turn. Got it · How does retrieval work?" |
| First skill applied | Post-action | "✓ [Skill] ran. The outputs panel shows what it produced and where it pulled from." |
| First Enhance Prompt use | Post-action | "✓ Enhanced prompt was 4× longer and got a more specific reply. Capture as a skill →" |
| First tier-floor refusal | Mid-action | "This is your firm's tier policy at work. Here's why →" |
| First Receipts open | Post-action | "Receipts shows every event chronologically. Great for sharing with GC." |

---

## 7. Power-feature UX

### 7.1 Enhance Prompt

- ✨ button in composer toolbar (or `⌘E`)
- Inline expansion below composer: Original (dimmed) + Enhanced (with model used) cards
- Three actions: `[Use enhanced]` / `[Edit enhanced]` / `[Keep original]` — never silent overwrite
- First-time JIT post-action toast (see 6.6)
- Sent enhanced messages get a `✨ enhanced` provenance pill; tapping shows diff
- Power-user toggle: `Settings → Composer → Auto-enhance on send` (off by default)
- Edge cases: empty composer disables button; >500-token prompt becomes "Refine"; error shows inline retry

### 7.2 Skill Creator (three modes)

**Mode A — From chat:**
- After a productive turn, inline `📝 Capture as a skill` button
- Modal pre-populated with trigger prompt + skill body + suggested slug + suggested description
- Editable, savable as user-scope (ADR 0012 shadows built-in)

**Mode B — From scratch (`/lq-ai/skills/new`):**
- Reorganized as 4-section wizard:
  1. What does this skill do? (display name + description)
  2. When should it run? (trigger words / use case examples)
  3. What does it produce? (prompt body)
  4. Try it out (embedded sandbox)
- Save / Save draft / Discard

**Mode C — Fork existing:**
- `🔱 Fork as my own` button on any skill detail page
- Pre-populates the wizard with the source skill content

**Skill detail page (`/lq-ai/skills/[id]`):**
- Hero: name, description, scope badge, version
- Tabs: `Use it` (rendered SKILL.md) · `View source` (raw markdown — transparency-first concrete form) · `Try it` (temp chat with skill applied) · `Versions` (audit log)
- Actions: Fork, Edit (if owned), Apply to chat, Favorite

**Try-it sandbox:** side-by-side prompt + AI reply; uses a `try-it-sandbox` matter scope tagged `non-billable, sandbox` so cost/audit telemetry stays clean.

### 7.3 Attach Knowledge Base

Three entry points → same modal:
1. In chat composer: 📎 button
2. In matter rail: Knowledge section → `+ Attach KB`
3. From Knowledge tab: card → `Attach to matter…`

Modal: searchable card grid (name · doc count · last updated · attached count) + `Upload new KB` inline uploader + multi-select.

First-time JIT pre-action banner inside modal (see 6.6).

Knowledge tab `/lq-ai/knowledge`: card grid, embedding status per KB (`✓ indexed` / `⏳ indexing 47%` / `⚠ failed`), prominent upload CTA. Detail page lists docs + per-doc embedding status + attachment management.

### 7.4 Tier-floor refusal (D1 polish)

Refused turn renders as a persisted message of `kind = refusal` (schema discriminator — column or metadata field, see §12 open questions) in the chat — so it shows in Receipts and audit-cross-link works:

```
🛡 Refused at privileged-floor

This task was about to route to a `standard` tier provider,
but your firm's policy enforces `privileged-floor` for this matter.
We refused to keep your work in privileged-only providers.

[Re-run at privileged-floor]   [Override for this turn]*   [Why am I seeing this?]
* Override requires audit-trail confirmation
```

Amber-tinted (not red — guardrail, not error). Provenance pills: `🔒 tier mismatch (requested standard, enforced privileged)` · `📜 audited`. No provider pill (no call made).

First-time JIT post-action explainer (see 6.6).

Override confirmation requires reason; only available with `override_tier_floor` permission.

### 7.5 Audit log (`/lq-ai/admin/audit-log` extended)

D3-coverage shipped a filter UI; M1 polish adds:
- Filter chips: user · action type · date range · privilege tag · matter
- Entry expansion shows full event detail incl. before/after diff for updates
- Cross-links: "View related chat" · "View related message in Receipts"
- Export filtered: CSV or JSONL
- Saved filters as quick-access chips: "Today's external turns" · "All tier overrides" · "Failed audit writes"

### 7.6 Receipts mode

Toggle inside any chat: `💬 Chat ⇄ 📜 Receipts`. Chronological event log:

| Time | Event | Detail |
|---|---|---|
| 10:14:02 | 💬 Chat opened | matter Acme NDA · tier-floor privileged |
| 10:14:08 | 🛠️ Skill applied | NDA-Review v1.2 (forked from built-in) |
| 10:14:09 | 📎 KB retrieval | NDA-Playbook v2.1 · 3 chunks · 412 tokens |
| 10:14:10 | 🧠 Provider call | Anthropic Claude · 3,108 in · 612 out · 4.2s |
| 10:14:14 | 📜 Audit written | inference_request · m_88f0 |
| 10:14:33 | 👤 User message | "Replace §7.1?" — privilege-tag privileged |

- Filter chips: events · retrievals · provider calls · audit · errors only
- Export receipts as JSONL (matches audit export; diff-able against)
- First-time JIT post-action when entering (see 6.6)

---

## 8. Implementation considerations

### 8.1 Phasing within this branch

| Wave | Scope | Depends on |
|---|---|---|
| A — Foundation | Practice visual system; `TrustPill`, `ProvenancePill`, base layout chrome with top tabs + ambient pills; visual update to existing routes (login, change-password, skills list/new/detail, admin/audit-log, admin/models). No new surfaces. | — |
| B — Dashboard + IA | Home (Guided Dashboard) with trust panel, featured tools, checklist scaffold; settings/appearance; Trust & Privacy page; **Admin Developer Support tab (§10.4)** — backend OpenAPI doc links + API playground. | Wave A; backend `/api/v1/trust/*`; backend config-exposure endpoint surfacing OpenAPI URLs |
| C — Matter Workspace | `/lq-ai/matters` list + `/lq-ai/matters/[id]` 3-pane Workspace; chat wired into workspace. Largest single piece. | Wave A; backend `/api/v1/matters/*` |
| D — Power features | Enhance Prompt expansion · Skill Creator 3-mode wizard + try-it · KB attach modal · tier-floor refusal block · Receipts mode toggle. | Wave C for in-chat surfaces; backend power-feature routes |
| E — Onboarding | Sandbox seed + walkthrough overlay + JIT triggers + concierge tour overlay. | Waves A–D; backend onboarding routes; sandbox content authored |
| F — Polish | Cross-link audit ↔ receipts; export flows; saved filters; accessibility pass; narrow-viewport behavior. | Waves A–E |

Each wave is a coherent set of commits. Waves can ship sequentially or some parallelize once backend dependencies land.

### 8.2 Existing vs net-new (routes)

**Extended (visual update + delta):** `/lq-ai`, `/lq-ai/login`, `/lq-ai/change-password`, `/lq-ai/skills`, `/lq-ai/skills/new`, `/lq-ai/skills/[id]`, `/lq-ai/skills/[id]/edit`, `/lq-ai/admin/audit-log`, `/lq-ai/admin/models`.

**Net-new:** `/lq-ai/chats`, `/lq-ai/matters`, `/lq-ai/matters/[id]`, `/lq-ai/knowledge`, `/lq-ai/knowledge/[id]`, `/lq-ai/saved-prompts`, `/lq-ai/trust`, `/lq-ai/settings/appearance`, `/lq-ai/settings/account`.

### 8.3 OpenWebUI rebase contract (ADR 0009)

- Allowed: import OpenWebUI primitives into `/lq-ai/*` (chat bubbles, markdown, syntax highlighting, file uploads)
- Allowed: new files under `web/src/routes/lq-ai/**` and `web/src/lib/lq-ai/**`
- Not allowed: modifying files outside the LQ.AI subtree, except ADR 0009's named exceptions
- Rebase checklist addition: when OpenWebUI's chat-bubble primitive changes, the LQ.AI message wrapper (which adds provenance pills) is re-tested

### 8.4 Testing

Per CLAUDE.md test strategy:
- Component unit tests (Vitest) for net-new components
- E2E (Playwright) for primary journeys: first-launch sandbox walkthrough; matter → KB attach → skill → see provenance; tier-floor refusal → override; capture chat as skill
- AXE accessibility checks on all primary surfaces; keyboard-only navigation works for all power features
- Visual regression for the Practice palette (optional — flag in plan)

---

## 9. Backend route gaps (handoff to backend implementation)

The frontend depends on these backend resources. Many exist or have stubs; some are net-new. Grouped by surface and ordered by wave that needs them.

### 9.1 Wave B prerequisites

**Trust & Privacy:**
- `GET /api/v1/trust/data-residency` — Postgres/MinIO/gateway host info, deployment topology
- `GET /api/v1/trust/providers` — configured providers + key-encryption status (per ADR 0011)
- `GET /api/v1/trust/external-turns` — daily count for footer + 7-day rollup for dashboard panel
- `GET /api/v1/trust/audit-health` — audit-write success-rate health check
- `GET /api/v1/trust/sbom-link` — signed SBOM artifact URL
- `GET /api/v1/trust/threat-model-link` — published threat model URL

**User preferences:**
- `GET/PUT /api/v1/user/preferences` — personalization toggles + `jit_dismissals[]`
- Migration: `user_preferences` table OR `users.preferences` JSONB (design decision for backend)

**Developer support (admin-only, §10.4):**
- `GET /api/v1/admin/developer/openapi-urls` — returns `{ backend_openapi: "...", backend_redoc: "...", backend_swagger_ui: "...", gateway_openapi: "..." }` resolved from the operator's deployment config
- (FastAPI already exposes `/openapi.json`, `/docs`, `/redoc` natively on api/ and gateway/; this endpoint just tells the frontend the canonical URLs for the current deployment so the developer tab can link to them correctly)

### 9.2 Wave C prerequisites

**Matters (PRD C7 "projects" may need surface aliasing):**
- `GET /api/v1/matters` — list with filters
- `GET /api/v1/matters/{id}` — detail incl. attached KBs, applied skills, tier-floor
- `POST/PATCH/DELETE /api/v1/matters` — CRUD
- `POST /api/v1/matters/{id}/knowledge-bases` — attach KB
- `DELETE /api/v1/matters/{id}/knowledge-bases/{kbId}` — detach
- Migration: `matters.is_sandbox` (boolean, default false)

**Chats / messages:**
- Message schema: `messages.kind` (enum/string: `user`, `ai`, `refusal`, `system`) so refused turns persist
- `messages.enhance_prompt_used` (boolean) — or derive from message metadata JSONB
- `messages.tier_override` (boolean + reason text) — or via metadata JSONB

### 9.3 Wave D prerequisites

**Power features:**
- `POST /api/v1/enhance-prompt` — runs `enhance-prompt` skill server-side; takes `{text, context}`; returns `{enhanced_text, model_used}`
- `POST /api/v1/skills/{id}/try-it` — sandbox-executes a skill against a mock prompt
- `POST /api/v1/skills/from-chat` — captures a chat turn into a draft skill
- `POST /api/v1/knowledge-bases/{id}/attachments` (and DELETE) — attach/detach KB ↔ matter
- `GET /api/v1/knowledge-bases` — browse-list with attachment counts
- `GET /api/v1/knowledge-bases/{id}/attachments` — which matters this KB is on
- `POST /api/v1/inference/override-tier-floor` — capability with audit-trail confirmation; gated by `override_tier_floor` permission

**Receipts:**
- `GET /api/v1/chats/{id}/receipts` — chronological event log per chat

**Audit polish:**
- `GET /api/v1/audit-log/export` — CSV/JSONL with filter params

**Saved Prompts (D7 confirmation):**
- `GET/POST/PATCH/DELETE /api/v1/saved-prompts` — confirm D7 route shape matches surface needs
- `POST /api/v1/saved-prompts/{id}/convert-to-skill` — promote saved prompt to user skill

### 9.4 Wave E prerequisites

**Onboarding:**
- `POST /api/v1/onboarding/seed-sandbox` — seeds the Acme NDA sample matter, docs, KB
- `GET/PATCH /api/v1/onboarding/status` — reads/writes `users.onboarding_completed_at`
- `GET /api/v1/onboarding/checklist-status` — booleans for each detection signal
- Migration: `users.onboarding_completed_at` (timestamptz, nullable)

---

## 10. Theming, customization, and developer extensibility (open-source posture)

This design is built to be **a great default, not the only answer**. LQ.AI is open source and downstream firms should be able to fork the frontend to match their own UI/UX opinions — or replace it entirely — without disturbing the backend. The frontend's job is to surface the backend power; the *shape* of that surface is a decision an operator gets to make.

### 10.1 Theming (visual identity)

CSS architecture exposes semantic tokens (`--lq-accent`, `--lq-secure`, `--lq-warn`, `--lq-tier`, `--lq-canvas`, etc.) at `web/src/lib/lq-ai/styles/practice.css`. A fork can swap visual identity by overriding these variables — no component code changes required. Practice is the reference palette but not the only palette.

### 10.2 Component extensibility

Net-new shared components live under `web/src/lib/lq-ai/components/` and follow a deliberately narrow public-API contract (typed props, no internal-state coupling to consumers). A fork that wants different chrome can:

- Override individual components by re-implementing them with the same prop interface
- Replace whole regions (top-bar, footer, sidebar) by swapping the corresponding `<*Chrome>` composition
- Keep the LQ.AI logic stores (`$auth`, `$activeChatStore`, etc.) and just re-skin the view layer

### 10.3 Layout pluggability

The `+layout.svelte` for `/lq-ai/*` is the single mount point that wires the top-tab nav + ambient chrome around route content. A fork that wants a different IA (left rail instead of top tabs, no chrome at all, embedded-in-Word shape) replaces this one file. Routes underneath continue to work because they don't depend on the layout's chrome — they consume the same data layer.

### 10.4 Backend API access for developers (the Developer Support tab)

The Admin surface includes `/lq-ai/admin/developer` *(Wave B)* — a one-stop developer support panel surfacing:
- Direct links to the backend's auto-generated API docs (FastAPI's `/docs` Swagger UI and `/redoc` ReDoc), scoped to the configured backend host
- Direct link to the Inference Gateway's OpenAPI spec
- A small "API playground" panel where a developer can paste a JWT and try endpoints inline (or click "Open in Swagger" to launch the full UI in a new tab)
- Pointers to the SBOM, signed releases, and threat model artifacts (cross-link with the Trust & Privacy page)
- A "Build your own frontend" call-out that links to a forthcoming developer-fork guide (see §10.5)

This is admin-gated because exposing live API docs publicly is a security-surface decision an operator should make explicitly.

### 10.5 Companion developer-fork documentation

A companion guide ships alongside the M1 codebase (target: post-Wave-F, to be authored in a separate cycle):

- **Anatomy of the `/lq-ai/*` shell** — what each component does and what extending it looks like
- **The data layer** — auth store, API client, SSE streaming, types — what survives a fork unchanged
- **Swap-the-shell recipe** — replacing top tabs with a left rail; replacing the chrome entirely; embedding LQ.AI logic into an existing firm intranet
- **Theming recipe** — overriding the Practice palette without touching component code
- **Versioning and rebase** — keeping a fork updated against upstream LQ.AI without losing your customizations

This guide lives at `docs/developer-fork-guide.md` and is referenced from the Developer Support tab.

### 10.6 PRD anchor

This whole section is the visual/architectural expression of PRD §1.3 transparency-as-forkability — extended from "skills are forkable" to "the entire frontend is forkable." Operators who want LQ.AI's backend with their own brand and IA shouldn't have to fight the codebase to do it.

---

## 11. Content authoring dependency (non-blocking flag)

The sandbox sample matter needs **synthetic but realistic** content authored by someone with legal knowledge:
- A 4-page mutual NDA with intentional playbook-violations (5-yr term, broad indemnity, missing carve-outs)
- A counterparty redline doc showing comparison flow
- A short synthetic NDA Playbook with 3-4 standard clauses to cite against

Recommendation: a contributing attorney or Kevin drafts these. Claude can scaffold but legal realism is what makes the "wow" moment work.

---

## 12. Open implementation questions

Questions surfaced during brainstorming that the implementation plan should resolve:

1. **Matter vs. project naming.** PRD C7 calls these "projects"; this design surfaces them as "Matters" (closer to legal practice idiom). Backend can alias at the API layer or rename. Decide before Wave C.
2. **User preferences storage shape.** Table vs JSONB column on `users`. JSONB simpler; table better if preferences grow. Decide before Wave B.
3. **Refused-message schema.** `messages.kind` enum or `messages.metadata.kind`. Decide before Wave C.
4. **Top-tab overflow behavior at narrow viewports.** Last items collapse into `… More` dropdown — confirm rule of thumb with first responsive pass.
5. **Visual regression tooling.** Percy or Loki or none. Decide before Wave A ships.
6. **Audit log saved filters: client-side or server-side persistence.** Client-side is fine for M1; flag for revisit if usage grows.

---

## 13. Visual companion artifacts

The design was brainstormed with interactive mockups in the visual companion. Mockup files preserved at `.superpowers/brainstorm/39673-1778458451/content/` on this branch:

- `01-front-door.html` — front-door shape question (chose Guided Dashboard)
- `02-trust-layer.html` — trust dose (chose Ambient)
- `03-surfacing.html` — power-feature surfacing (chose Featured + ⌘K, user-demotable to inline)
- `04-nav-ia.html` — navigation pattern (chose Top tabs)
- `05-visual-direction.html` — visual language (chose Practice)
- `06-onboarding.html` — onboarding shape (chose hybrid)
- `07-chat-layout.html` — working surface (chose 3-pane Workspace)
- `08-transparency.html` — transparency UX (chose Inline pills + Receipts + drill-tabs)

These are wireframes, not final designs. They establish shape and intent; production fidelity comes during Wave A implementation.
