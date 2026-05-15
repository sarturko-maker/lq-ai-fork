# Session Handoff — 2026-05-12 (Wave D.1 + Phase E shipped; 5-item queue for next session)

> **Purpose.** Hand off cleanly after a long session that shipped Backend Phase E, the claude-for-legal research deliverable, and Wave D.1 (in-chat power features). Next session has a 5-item queue, ordered.

---

## 1. State at handoff

- **Branch:** `kk/main/Frontend_Design` at HEAD `3067aa8`, pushed to remote.
- **Stack:** all 7 docker services healthy in `docker compose ps` (api/gateway/web/postgres/minio/redis/ingest-worker).
- **Tests:** Vitest 228/228 (38 files); backend pytest broader sweep `~90/90` across the wave-D.1 surfaces; Cypress spec lint-clean but NOT executed end-to-end (item 1 below).
- **Migrations:** 0001 → 0021 applied. New since previous handoff: 0020 (`messages.kind` discriminator), 0021 (`project_knowledge_bases` junction).
- **Container quirk discovered this session:** the api container does NOT bind-mount `./api/` — code edits don't live-reload. For migrations/code into the running container, use `docker cp <local-path> lq-ai-api-1:/app/<path-in-container>`. Pytest creates its own fresh test DB from migrations, so as long as alembic sees the file, tests work.
- **Local dev quirks (unchanged):** `POSTGRES_HOST_PORT=5433`, `web/Dockerfile` has `NODE_OPTIONS=--max-old-space-size=4096`, `.env` gitignored.

## 2. What landed this session

### Backend Phase E (2026-05-12 morning) — release readiness

**HEAD:** `951699f` (19 atomic commits). Shipped:

1. `.github/workflows/release.yml` — matrix build api/gateway/web on `v*.*.*` tag push (or `workflow_dispatch` dry-run)
2. SBOM generation (Syft → SPDX JSON, 90-day artifact retention)
3. SLSA L3 build provenance (`actions/attest-build-provenance@v1`)
4. cosign keyless signing of images + SBOM attestations (OIDC + Fulcio; no key custody)
5. In-repo Helm chart at `deploy/helm/lq-ai/` — 15 k8s resources (3 Deployments + 3 StatefulSets + 6 Services + 1 ConfigMap + 1 ServiceAccount + 1 Ingress); operator-managed Secrets for all credentials
6. Security docs: `threat-model.md` (STRIDE-by-component), `cryptography.md` (JWT/Fernet/bcrypt + key lifecycle), `audit-logging.md` (42 action types across 53 call sites), `dependencies.md` (Dependabot + SBOM scanning + cadence)
7. `docs/security/releases/README.md` — cosign verify walkthrough for operators
8. SECURITY.md GPG fix + README SLSA badge + `docs/security/README.md` status table flipped to "Landed"

**Code review caught 4 real bugs that would have failed at first real tag:**
- T0 fix: dead matrix `outputs:` block (matrix outputs collapse → false per-service-digest contract)
- T1 fix: SBOM job ran on dry-run trying to scan an image that wasn't pushed
- T3 fix: SBOM artifact-name mismatch between upload (image-prefix derived) and T3 download (literal `{service}.spdx.json`)
- T4 fix: Helm chart had DATABASE_URL env-var ordering bug + `/healthz` probe path that doesn't exist (api/gateway expose `/health` + `/ready`) + ServiceAccount foot-gun

### claude-for-legal research (2026-05-12 midday)

**HEAD:** `d14594c`. Doc at `docs/research/2026-05-12-claude-for-legal-review.md` (316 lines).

Catalogs all 13 Anthropic plugins + 163 SKILL.md files. **Recommendation: defer all incorporation to v1.1+.** Frontmatter formats differ fundamentally (Anthropic: 4 fields like `name`/`description`/`argument-hint`/`user-invocable`; LQ.AI: structured `lq_ai:` namespace with typed inputs/semver/jurisdiction/output_format). 5 plugins HIGH priority for v1.1+ porting (`ai-governance`, `corporate`, `employment`, `ip`, `privacy`, `product`). `legal-builder-hub`'s 7-gate install pipeline flagged as its own v1.1+ Wave G candidate.

**8 architectural questions filed for Kevin** (item 5 of next-session queue).

### Wave D.1 — in-chat power features (2026-05-12 afternoon)

**HEAD:** `3067aa8` (~30 atomic commits across T1–T21 + T7b bonus + 4 fix passes + 4 deferral-reversals).

Per M1 spec §8.1: Enhance Prompt expansion · KB attach modal · Tier-floor refusal block · Receipts drawer.

**Backend additions:**
- Migration 0020: `messages.kind` discriminator (NOT NULL column with CHECK over `{user, ai, refusal, system}` + index; backfilled from `role` column; `assistant→ai`, `tool→system`)
- Migration 0021: `project_knowledge_bases` junction (composite PK + CASCADE FKs + `attached_at` + `attached_by_user_id`)
- `POST/DELETE /api/v1/projects/{id}/knowledge-bases` — matter↔KB attach/detach (mirrors `/files` and `/skills` pattern)
- `POST /api/v1/inference/override-tier-floor` — admin-gated re-run of refused inference with reason (10..500); writes `kind='ai'` message + audit row
- `GET /api/v1/chats/{id}/receipts` — replay-at-read merge of 4 sources (messages, inference_routing_log, audit_log, applied_skills denorm)
- `GET /api/v1/chats/{id}/receipts/export.jsonl` — JSONL export with proper Content-Disposition
- KB retrieval audit-row write at `hybrid_search` call site (action `inference.kb_chunks_retrieved`)
- **T7b chat-send RAG step:** added the actual retrieval+context-injection that the chat path was missing; per-KB iteration with merge+sort by score; `top_k=5` per KB, max 10 total chunks; full chunk text injected as a system message prepend so the LLM uses them. Closes the architectural gap where receipts wouldn't show retrieval events during normal chat use.

**Frontend additions:**
- 4 API clients: `projectKnowledgeBases.ts`, `inferenceOverride.ts`, `receipts.ts`, `knowledgeBases.ts` (the last was missing pre-D.1)
- 7 Svelte components: `AttachKBModal`, `RefusalMessageBubble`, `TierFloorOverrideModal`, `ReceiptsList`, `ReceiptsDrawer`, `EnhancedDiffModal`, `MatterRailKnowledge`
- 1 helper module: `receiptsExport.ts` (JSONL download trigger + JSONL-validation helper)
- ChatPanel integration: composer 📎 / ✨ / 📜 buttons; refusal-message dispatch; override-modal state; receipts drawer with localStorage-persisted open-state per chat
- Enhance Prompt audit closed: 8 §7.1 items already present; 3 shipped (Refine framing >500 tokens, JIT strip, auto-enhance settings toggle); ✨ enhanced provenance pill + tap-to-diff added on reversal pass

**Latent T1 bug caught + fixed:** `_persist_assistant_message` never explicitly set `kind`, so every new assistant message was being written with the server default `'user'`. Added a `kind: str = 'ai'` parameter and updated all callers. Receipts filtering by `kind='ai'` would have silently missed all M1 assistant messages without this fix.

**Bonus T7b chat-RAG (per Kevin's "even if just a stub" call):** the chat path didn't do retrieval at all — RAG was only via the standalone `/query` endpoint. Wired retrieval+audit+context-injection into the chat send-message handler. Now receipts shows `📎 KB retrieval` events during normal chat use.

**4 deferrals from T20/T21 reversed at Kevin's pushback** (per [[feedback_honest_framing]]):
- `✨ enhanced` provenance pill on enhanced messages (was deferred for "missing backend flag" — turned out frontend can inject `'enhance-prompt'` into `payload.skills` cleanly)
- Tap-to-diff modal on the pill (was deferred as dependent on the pill)
- Cypress scenario 3 (admin override) — un-skipped via `cy.intercept` mock pattern
- Cypress scenario 5 (member no override) — un-skipped via `cy.intercept`
- Cypress scenario 4 actual export click (was elided as "would pollute downloads" — Cypress has `cypress/downloads/` for exactly this)

## 3. Wave D.1 deliverables — what an attorney sees today

1. **Composer toolbar in chat:** 📎 (KB attach) · ✨ (Enhance Prompt) · 📜 (Receipts drawer) — all three usable on `/lq-ai/chats` and `/lq-ai/matters/[id]`.
2. **KB attach modal:** card grid with search + sort + multi-select + inline uploader; "currently attached" badge for KBs already on the matter; first-time JIT banner.
3. **Tier-floor refusal block:** if a chat sends a prompt that would route to a lower-tier provider than the matter requires, the response renders as an amber `kind=refusal` message with three actions (Re-run at enforced floor · Override for this turn (admin-only) · Why am I seeing this).
4. **Tier-floor override modal:** admin clicks Override → modal with required reason textarea (10..500 chars) → confirm → POST to `/api/v1/inference/override-tier-floor` → refusal replaced in-place with the new AI response.
5. **Receipts drawer:** 240px right-side drawer, toggleable from 📜; chronological merged event stream (messages · inference calls · audit rows · skill applications · KB retrievals · refusals); 6 filter chips; polls every 5s while open; export JSONL.
6. **Chat-send RAG:** when a chat has KBs attached, the api retrieves top-K chunks per KB (max 10 total), writes the audit row (so receipts shows the event), and prepends a system-message context block so the LLM actually uses them.
7. **Enhance Prompt expansion:** spec §7.1 fully shipped except v1.1+ items — provenance pill + tap-to-diff added on reversal pass.

## 4. Next session — 5-item queue (ordered)

Kevin specified: "run the items in order 1-5 in a new session." All five are deferrable from Wave D.1's "outstanding before M1 merge" list.

### Item 1 — Cypress live-run for Wave D.1

Spec at `web/cypress/e2e/wave-d1-power-features.cy.ts`. 5 scenarios total; 3 use live backend calls, 2 use `cy.intercept` mocks for tier-floor refusal (no clean way to deterministically trip a refusal against real backend without infra work).

```bash
cd /Users/kevinkeller/Desktop/lq-ai/web
npx cypress run --spec cypress/e2e/wave-d1-power-features.cy.ts 2>&1 | tail -30
```

Expected: 5/5 pass. If runtime issues surface (intercept timing, route-not-mocked, etc.), adjust the spec accordingly. The spec is lint-clean as of `3067aa8` but has not been executed end-to-end.

### Item 2 — PR-validation CI authoring

Phase E shipped a **release-only** CI workflow at `.github/workflows/release.yml`. There's NO workflow that runs on PR (test, lint, typecheck). For M1 merge readiness this should exist.

Scope (estimated 1 session):
- `.github/workflows/ci.yml` triggered on PR + push to default branch
- Run Vitest (`cd web && npm run test:frontend -- --run`)
- Run pytest integration suite (`docker compose exec -w /app api pytest tests/ -m integration -q`)
- Run `svelte-check`, `ruff`, `mypy` (gateway strict mode, api standard mode)
- Cypress headless run against a stack-up step (heavier; optional for v1)

Out of scope for this item: code coverage gates, dependency-license check (probably Wave F polish).

### Item 3 — Wave D.2 — Skill Creator 3-mode wizard + try-it

Brainstorm + spec + plan + execute. Spec contract at `docs/superpowers/specs/2026-05-10-m1-frontend-design.md` §7.2. Three modes:
- **Mode A** — From chat: `📝 Capture as a skill` button after a productive turn; modal pre-populated with trigger prompt + skill body + suggested slug
- **Mode B** — From scratch: 4-section wizard at `/lq-ai/skills/new` (display + trigger + body + try-it sandbox)
- **Mode C** — Fork existing: `🔱 Fork as my own` button on any skill detail page

Plus the Skill detail page tabs (Use it · View source · Try it · Versions) and try-it sandbox (uses a `try-it-sandbox` matter scope tagged `non-billable, sandbox`).

Likely larger than Wave D.1 (multiple new routes + new sandbox-scope matter type). Brainstorm should slice into D.2.1/D.2.2 if needed.

### Item 4 — Phase E pre-tag dry-run

Gated on Phase E workflow being on the default branch. After Wave D.2 merges, the workflow_dispatch dry-run becomes available:

```bash
gh workflow run release.yml -f dry_run=true
gh run watch
```

Expected: 3 `build-and-push` matrix legs succeed; 3 `sbom` legs and 3 `sign` legs are SKIPPED (job-level `if:` guards on dry_run); final status success.

This is the last verification before cutting `v0.1.0`. Should be < 5 minutes of wall time.

### Item 5 — claude-for-legal incorporation decisions

Research doc at `docs/research/2026-05-12-claude-for-legal-review.md` has 8 architectural questions for Kevin to resolve before any v1.1+ Wave G starts:

1. Should LQ.AI support slash-command invocation alongside our existing match-on-trigger-words model?
2. Should the Managed-Agents-equivalent scheduled-agent capability be in v1.1+ scope?
3. Verbatim port (with attribution) vs LegalQuants-authored variant for each ported skill?
4. Should `legal-builder-hub`-style community skill installation be a v1.1+ Wave G or later milestone?
5. License: Apache 2.0 is compatible; should we re-license downstream or preserve upstream attribution per-skill?
6. Tool-use / MCP parity scope (LQ.AI doesn't surface MCP today)?
7. Organization Profile scoping (how to namespace per-firm overrides)?
8. NOTICES.md handling for adopted skills?

This is a brainstorming session, not an execution session. Output is decision-recording + scoping a v1.1+ Wave G if Kevin wants to proceed.

## 5. Open items routed forward

- **5 V2-FALLBACK items from Wave B v2 still in code** (Wave F cleanup queued after the 5-item sequence above).
- **Wave D.3 candidates:** KB browser surface `/lq-ai/knowledge`, Saved Prompts surface `/lq-ai/saved-prompts`, outputs panel, Citation Engine UI — all deferred from Wave D.1 brainstorm per spec §8.1 honoring.
- **Wave E:** sandbox onboarding with `matters.is_sandbox` column + Acme NDA pre-load + guided walkthrough per spec §6.
- **Per-user `override_tier_floor` permission infrastructure** — currently admin-role gated; per-user grant is v1.1+ if operator demand surfaces.
- **Materialized `chat_receipts` table** — v1.1+ if replay-at-read latency degrades at scale.
- **Original-prompt persistence for Enhanced diff view** — currently session-scope; historical messages show a "not preserved" fallback. v1.1+ enhancement.

## 6. Lessons from this session

1. **Don't silently defer items.** Wave D.1 T20+T21 implementer punted 4 items to v1.1+ without consultation. Kevin called it out; reversed in one fix pass. Subagents should surface deferrals as explicit choices when not pre-authorized. See [[feedback_honest_framing]].

2. **Code review catches real bugs, not just style.** Phase E review pass surfaced 4 production-failure bugs (dead outputs block, SBOM dry-run failure, artifact-name mismatch, Helm DATABASE_URL ordering). Wave D.1 T4 review surfaced the latent T1 `kind` default bug. Two-stage review (spec then quality) is load-bearing for production-bound changes.

3. **Input-regime-first discipline keeps paying.** This session: T2 reviewer caught that the model wasn't registered in `__init__.py` (would have broken T3 imports); T7 surfaced the architectural gap that chat path doesn't do RAG today (led to T7b bonus); T20 found the `messages.applied_skills` denormalization path so the enhanced-pill could ship without a migration. See [[feedback_input_regime_first]].

4. **Subagent-driven execution scales.** Wave D.1 was 21 tasks + bonus + 4 fix passes + 4 deferral-reversals across one session — feasible because each subagent has isolated context and Kevin is shielded from the multi-step ceremony. Continuous execution (no "should I keep going?" prompts) was the right default.

5. **Spec drift discovered at brainstorm.** Wave D.1 scope contract differed between the M1 spec §8.1 (`Power features` = enhance + skill creator + KB attach + tier-floor + receipts) and the Wave C handoff (`Outputs + KB browser + Saved Prompts + Citation Engine + Receipts`). Surfaced before any planning; resolved at brainstorm by honoring §8.1. Saved a ~3x scope expansion.

6. **The "even if just a stub" gambit.** Kevin authorized T7b chat RAG with "even if just a stub to a search provider." Implementer shipped actual RAG (full chunk text injection) because the infrastructure was already there. Lower the bar to lower the friction, then deliver above the bar when feasible.

## 7. Pre-flight checks for the next session

```bash
cd /Users/kevinkeller/Desktop/lq-ai
git status -sb                # expect: clean on kk/main/Frontend_Design
git log -1 --oneline           # expect: 3067aa8 test(web): Cypress un-skip refusal scenarios + export
                               # OR a subsequent handoff-doc commit
docker compose ps              # expect: 7 services healthy
cd web && npm run test:frontend -- --run 2>&1 | tail -3
                               # expect: 228 passed (228)
docker compose exec -w /app api alembic current 2>&1 | tail -3
                               # expect: 0021 (head)
```

## 8. Auth shortcut

- URL: `http://localhost:3000/lq-ai/login`
- Email: `admin@lq.ai`
- Password: whatever was last set; if lost, `docker compose exec api python -m app.cli reset-admin-password`

---

**End of handoff.** Branch is at `3067aa8` on `kk/main/Frontend_Design`. Next session starts with item 1 (Cypress live-run) and works the 5-item queue in order.
