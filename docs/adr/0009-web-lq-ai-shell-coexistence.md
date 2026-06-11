# ADR 0009 — LQ.AI web shell co-exists alongside the OpenWebUI shell (does not replace it)

**Status:** Accepted (2026-05-08) — superseded by [ADR-F006](F006-ui-stack-and-design-system.md):
F0-S6 removed the OpenWebUI shell entirely; `/lq-ai` is the only shell (2026-06-11).
**Decision-makers:** Kevin Keller (initial maintainer)
**Affected components:** `web/`
**Supersedes:** none. **Refers to:** [ADR 0001](0001-openwebui-fork-pin.md), [PRD §1.3](../PRD.md#13-transparency-as-a-founding-principle), [Task C8 spec](../M1-IMPLEMENTATION-ORDER.md#task-c8--web-ui-chat-experience-parallel-from-c3-onward).

---

## Context

LQ.AI's web client is a fork of OpenWebUI v0.9.2 (per [ADR 0001](0001-openwebui-fork-pin.md)). OpenWebUI ships its own complete chat shell — its own auth flow, its own `/api/v1` surface, its own `Chat.svelte` (~3,100 lines), its own routing, its own model selection, its own admin pages. Our backend exposes a different `/api/v1` surface (LQ.AI's own auth, chats, messages, skills, files, projects).

Task C8 needs to deliver:

1. The chat experience documented in `docs/quickstart.md` Step 4 (project sidebar, attached files, skill picker with input form, streaming output, applied-skills chip, tier badge).
2. Delegated auth wiring against LQ.AI's `/api/v1/auth/login` (closes A5 deferred).
3. Forced-password-change route guard.
4. Dual-branding per ADR 0001 clause 4 (closes A5 deferred).

C8 surfaced an architectural choice the brief flagged for an explicit decision:

- **Path A — replace OpenWebUI's chat shell.** Mutate `Chat.svelte`, `MessageInput.svelte`, the auth route, the API clients under `lib/apis/`. Pros: single chat surface; nothing for users to choose between. Cons: very large diff against upstream (~3,100-line file plus dozens of supporting files); high rebase cost on every quarterly upstream refresh (ADR 0001 §"Refresh cadence"); breaking OpenWebUI's existing features (admin, RAG, workspace, etc.) is easy by accident.

- **Path B — co-exist: LQ.AI shell at `/lq-ai`, OpenWebUI shell at `/`.** Add a parallel chat shell as new files under `web/src/lib/lq-ai/` and `web/src/routes/lq-ai/`, leaving OpenWebUI's shell unmodified except for the dual-branding chrome that ADR 0001 clause 4 mandates anyway. Pros: zero conflict surface against upstream; the LQ.AI shell can move independently of OpenWebUI's release cadence; OpenWebUI's existing features keep working untouched (admin, RAG); easy to review (every file under `lq-ai/` is ours). Cons: two routes with overlapping concepts; users need to know which one to land on.

## Decision

**Adopt Path B.** The LQ.AI chat experience lives under `web/src/lib/lq-ai/` (component library) and `web/src/routes/lq-ai/` (route tree). The OpenWebUI shell at `/` is left intact except for ADR 0001 clause 4 dual-branding, which lands in dedicated dual-branding files (`Footer.svelte`, brand-name override) so the upstream rebase touches only the branding files.

**Concretely:**

- The LQ.AI shell is the canonical experience for the M1 quickstart. The quickstart's Step 4 walkthrough exercises `/lq-ai`. The OpenWebUI shell remains accessible at `/` for operators who want OpenWebUI's broader feature set (admin, RAG, model management) — those features are not part of M1's product and are not customized.
- All LQ.AI Svelte components, API client modules, stores, and tests are confined to `web/src/lib/lq-ai/`. The only files outside that directory that this task touches are: `web/src/routes/lq-ai/+page.svelte` and siblings (the route tree); `web/src/lib/components/layout/Footer.svelte` (dual-branding); and `web/src/lib/constants.ts` (brand name constant — already overridden by `WEBUI_NAME` env in A5 but we add the dual-brand attribution constant here).
- The LQ.AI API client in `web/src/lib/lq-ai/api/` is the canonical `/api/v1` surface for LQ.AI. It does **not** share state with OpenWebUI's `web/src/lib/apis/` clients. The two surfaces are intentionally isolated; the OpenWebUI client points at OpenWebUI's own backend (which is not our backend), the LQ.AI client points at our backend.
- Token storage uses a dedicated `lq_ai_access_token` / `lq_ai_refresh_token` pair in `localStorage`, distinct from OpenWebUI's `token` key. A user can be signed into both shells independently; they are different products from the user's perspective.
- The LQ.AI shell's auth flow goes through LQ.AI's `/api/v1/auth/login` (per [PRD §5.1](../PRD.md)); the OpenWebUI shell's auth flow continues to go through OpenWebUI's own auth surface untouched.

## Consequences

**Positive:**

- Upstream rebases are cheap. The patch surface against `v0.9.2` is dominated by additive files; the only modifications to upstream files are the dual-branding chrome (mandatory per ADR 0001 anyway) and a constant override.
- The LQ.AI shell can be redesigned, refactored, or rewritten without touching upstream code. The team's velocity on LQ.AI features is decoupled from OpenWebUI's release cadence.
- Reviewability: every file under `web/src/lib/lq-ai/` is ours; every file outside it is upstream-or-trivially-modified. Diffs are easy to read.
- Failure isolation: a bug in the LQ.AI shell does not break the OpenWebUI shell, and vice versa. Operators can fall back to either if the other has issues.
- The transparency principle (PRD §1.3) is preserved at the file-level — the LQ.AI shell's components are clearly LQ.AI's own and are visible work product, not embedded modifications inside an upstream component.

**Negative:**

- Two chat-like routes exist at `/` (OpenWebUI) and `/lq-ai` (LQ.AI). Users may be confused about which to land on. **Mitigation:** the post-login redirect for the LQ.AI auth flow targets `/lq-ai`; the deployment docs and quickstart direct users to `/lq-ai`. Operators can configure the SvelteKit `+page.svelte` at `/` to redirect to `/lq-ai` if they don't want the OpenWebUI shell exposed at all (this is a one-line operator-side change documented in the quickstart's troubleshooting section).
- Some duplicate UI primitives (a "send" button, a chat list item) exist in both shells. **Mitigation:** the LQ.AI shell uses the same Tailwind primitives the OpenWebUI shell uses, so the visual language is consistent.
- The OpenWebUI shell's admin/RAG/model-management UI continues to point at OpenWebUI's own backend endpoints, which are not LQ.AI endpoints. **This is by design** — those features are not part of M1's product and we deliberately don't customize them. A note in the OpenWebUI shell's chrome (or a deferred enhancement) can hide-link these surfaces from operators who don't want them visible.

**Reversibility:**

If a future maintainer prefers Path A, the migration is mechanical: move the LQ.AI shell's components from `web/src/lib/lq-ai/` into `web/src/lib/components/chat/` (replacing OpenWebUI's components) and `web/src/routes/lq-ai/` into `web/src/routes/(app)/c/`. The LQ.AI components are written to OpenWebUI's design-system primitives, so the swap is structural rather than visual.

---

## Operational notes

**Where the LQ.AI shell lives:**

```
web/
├── src/
│   ├── lib/
│   │   └── lq-ai/                      # LQ.AI's chat shell library
│   │       ├── api/                    # canonical /api/v1 client (typed)
│   │       │   ├── client.ts           # base fetch wrapper + auth handling
│   │       │   ├── auth.ts             # /auth/login, /auth/refresh, etc.
│   │       │   ├── chats.ts
│   │       │   ├── messages.ts
│   │       │   ├── skills.ts
│   │       │   ├── files.ts
│   │       │   └── projects.ts
│   │       ├── auth/
│   │       │   ├── store.ts            # token + user reactive store
│   │       │   └── refresh.ts          # token-refresh scheduler
│   │       ├── sse/
│   │       │   └── parser.ts           # SSE consumer for /messages stream
│   │       ├── components/
│   │       │   ├── ChatSidebar.svelte
│   │       │   ├── ProjectPicker.svelte
│   │       │   ├── AttachedFilesPanel.svelte
│   │       │   ├── SkillPicker.svelte
│   │       │   ├── SkillInputForm.svelte
│   │       │   ├── MessageList.svelte
│   │       │   ├── MessageBubble.svelte
│   │       │   ├── AppliedSkillsChip.svelte
│   │       │   ├── TierBadge.svelte
│   │       │   ├── DualBrandingFooter.svelte
│   │       │   └── ChangePasswordCard.svelte
│   │       ├── stores/
│   │       │   ├── chat.ts             # active chat store
│   │       │   ├── projects.ts
│   │       │   └── skills.ts
│   │       └── types.ts                # OpenAPI-shaped types
│   └── routes/
│       └── lq-ai/
│           ├── +layout.svelte          # auth gate + force-change-password gate
│           ├── +page.svelte            # chat shell
│           ├── login/+page.svelte
│           └── change-password/+page.svelte
```

**OpenAPI shapes are ground truth.** The types in `web/src/lib/lq-ai/types.ts` are hand-typed against `docs/api/backend-openapi.yaml`. Drift is caught by a thin runtime contract test (a Vitest unit that asserts the types match the OpenAPI sketch's required field list for the dozen schemas the UI consumes). A future enhancement could generate types from the OpenAPI sketch via `openapi-typescript`; this is a candidate DE-XXX entry. For M1 we hand-type because the schema surface is small and stable.

**Streaming.** SSE consumption uses `eventsource-parser` (already a transitive dep via the OpenWebUI shell's streaming module). The LQ.AI parser is in `web/src/lib/lq-ai/sse/parser.ts` and is a thin wrapper that emits typed `MessageStart` / `MessageDelta` / `MessageComplete` / `Error` frames matching the backend OpenAPI sketch's `MessageStreamEvent` `oneOf`.

**Token refresh.** Access tokens last ~15 minutes (B1). The auth store schedules a refresh at `expires_in - 60s`; on 401 from any LQ.AI API call the client transparently attempts a refresh-and-retry-once and signs the user out if that fails.

**Forced password change.** The +layout.svelte for `/lq-ai` checks `user.must_change_password` after login and redirects to `/lq-ai/change-password`; that route is the only `/lq-ai/*` route that the layout doesn't gate behind the must_change_password check. A 403 with `code=password_change_required` from any API call also redirects.

---

*Superseding this ADR (e.g., to adopt Path A in a future major refactor) requires an explicit follow-on ADR. Updating the directory layout under `web/src/lib/lq-ai/` is an in-place edit to this document.*
