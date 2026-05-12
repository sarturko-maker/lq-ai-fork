# Session Handoff — 2026-05-12 (Wave C closed; Backend Phase E queued)

> **Purpose.** Hand off cleanly between sessions at the Wave C → Backend Phase E seam. Wave C is fully shipped (matters list + 2-pane workspace + dashboard wiring + Cypress E2E). Backend Phase E (release-readiness — SBOM, SLSA, cosign, Helm chart, compliance docs) is queued as the next discrete chunk and is fully orthogonal to feature work.

---

## 1. State at handoff

- **Branch:** `kk/main/Frontend_Design` at HEAD `d44e0d3` (Cypress for Wave C matters), pushed to remote.
- **Stack:** all 7 services healthy in Docker (`docker compose ps`). Web container was rebuilt at 06:00-ish to pick up Wave C frontend changes; API container was rebuilt earlier to pick up the BE-A2/BE-C1 backend extensions. Gateway has live ANTHROPIC + OPENAI keys (set in `.env`) so Enhance Prompt actually calls out.
- **Tests:** Vitest 174/174 pass (started this session at 100; +74 across Wave B v2 + Wave C). Backend integration: 486 pass, 1 skipped, 0 fail (the 10 originally-reported pre-existing failures + 4 hidden behind `--maxfail=10` all resolved).
- **Migrations:** 0001 → 0019 applied. The session added 0019 (UserPreferences extension) but nothing in Wave C — Wave C is frontend-only.
- **Auth:** `admin@lq.ai` / current password. If lost, `docker compose exec api python -m app.cli reset-admin-password`. The smoke pattern: log in, hard-refresh after any web rebuild (Cmd+Shift+R) to bust browser cache.
- **Local dev quirks (unchanged):** `POSTGRES_HOST_PORT=5433`, `web/Dockerfile` has `NODE_OPTIONS=--max-old-space-size=4096`, `.env` is gitignored at line 100 and verified before the keys went in.

## 2. What landed in this session

**Net commits since the Wave B v2 kickoff HEAD `a9f1aa0` → current HEAD `d44e0d3`:** 33 atomic commits, all pushed. Breakdown:

### Wave B v2 closure (carried over from kickoff)

11 plan tasks shipped (T1 chat shell relocation through T9 Cypress) plus 3 backend reconciliation commits (BE-A2 UserPreferences extension via migration 0019, BE-B2 RBAC role enum docs, BE-C1 `GET /admin/users` list endpoint). See `docs/SESSION-HANDOFF-2026-05-11-frontend-wave-b-kickoff.md` for the lead-in.

### Backend test-suite cleanup (mid-session, after Wave B v2)

3 commits resolved the 10 originally-flagged pre-existing test failures plus 4 hidden behind `--maxfail=10`:
- `a14d52a` test(api): align 4 test files (UserSession session-timeout columns, autouse db_chat fixture for chats_skills_forwarding, staggered created_at for chats_endpoints list ordering)
- `11a2a09` test(api): multipage chunker fixture — replaced non-wrapping `insert_text` with `insert_textbox` so the 3-page PDF actually has 3 pages of content
- `a6eef12` test(api): retired 2 obsolete FK SET NULL tests per migration 0008's explicit retirement of the behavior

Backend integration suite now green: 486 passed, 1 skipped, 0 failed.

### Smoke-test polish

1 commit on the frontend layout: `ab87f63` fix(web): enable vertical scroll on non-chat /lq-ai/* surfaces. OpenWebUI's `app.html` pins `html { overflow-y: hidden }` for the chat UI's own scroll management; settings + admin surfaces had no scroll mechanism. Locked `.lq-shell` to `height: 100vh` and made `<main>` the scroll container.

### Wave C (matters surface)

10 commits across the plan's 9 tasks plus the plan doc itself:

```
d44e0d3 test(web): Cypress E2E smoke for Wave C matters surfaces
38f2d48 feat(web): flip matters tab available + wire dashboard recent matters
3f229ec feat(web): matter rail skill attachments
b40d902 feat(web): matter rail file attachments
5a7bb5c feat(web): matter rail metadata inline-edits + archive
e97a800 feat(web): /lq-ai/matters/[id] 2-pane workspace skeleton
3ae189d feat(web): NewMatterModal — create matter with privileged + tier-floor
ef6982c feat(web): /lq-ai/matters list surface
a4f75ca refactor(web): extract ChatPanel component for cross-surface reuse
d58d319 docs(plan): Wave C — Matters list + 2-pane workspace skeleton
```

### Wave C deliverables (what an attorney sees today on /lq-ai/*)

1. **Matters list at `/lq-ai/matters`** — card grid (auto-fill min 320px), archived toggle, "+ New matter" button. Each MatterCard shows name, description excerpt, Privileged + Tier-floor TrustPills, file/skill counts, "Open →" navigation. Empty state with "+ Start your first matter" CTA. Wired to `GET /api/v1/projects?archived=…`.

2. **NewMatterModal** — Practice-styled overlay; name (required, 1-200), description, Privileged checkbox, Tier-floor select. Client-side enforces the backend CHECK constraint (`privileged ⇒ tier_floor IS NOT NULL`) before POST. On success: redirect to `/lq-ai/matters/{newId}`. 7 unit tests against `validateNewMatter` helper.

3. **Matter workspace at `/lq-ai/matters/[id]`** — 2-pane composition: MatterRail (320px fixed) + ChatPanel (`flex: 1`). The rail composes 4 sections:
   - MatterRailMetadata — view/edit toggle on name/description/privileged/tier-floor; PATCH; archive flow with inline confirm
   - MatterRailFiles — list of attached files + "+ Attach" popover; uses new `attachFile`/`detachFile` API helpers
   - MatterRailSkills — TrustPill chips for attached skills + "+ Attach" popover; uses `attachSkill`/`detachSkill`
   - Chat list — pulls `chatsApi.listAllChats({ project_id })`; "+ New" creates a chat scoped to the matter; clicking a row sets `activeChatId` which the workspace page forwards to ChatPanel via `initialChatId={activeChatId}`

4. **ChatPanel extracted** — `/lq-ai/chats/+page.svelte` reduced from 590 lines to 16; the chat composition lives in `web/src/lib/lq-ai/components/ChatPanel.svelte` with 2 new props (`projectIdFilter`, `initialChatId`). When `projectIdFilter` is set, ChatPanel hides the project filter in ChatSidebar (matter rail already represents the project). Used at both `/lq-ai/chats` and `/lq-ai/matters/[id]`.

5. **Dashboard RecentActivity wired** — replaced the Wave C placeholder "matters coming soon" card with live `projectsApi.listProjects({ archived: false })` (sliced to 5). Empty state links to `/lq-ai/matters`.

6. **Matters tab flipped to available** — `tabs.ts` `matters` is now `available: true`. Tab routes natively to `/lq-ai/matters`; no longer triggers ComingSoonModal.

7. **API client additions** — `web/src/lib/lq-ai/api/projects.ts` gained `attachFile`, `detachFile`, `attachSkill`, `detachSkill` (each returns updated `Project`). Backed by 4 new tests in `projects-attach-api.test.ts`.

8. **Cypress E2E** — `web/cypress/e2e/wave-c-matters.cy.ts` with 5 scenarios: matters tab routes, NewMatterModal open/close, create-and-redirect to workspace, create chat in rail, privileged matter requires tier-floor.

### Wave C scope NOT covered (deferred per architectural calls 2026-05-12)

- **Outputs panel** — Wave D. No first-class draft/redline data model in M1; likely shape is a view over `messages.applied_skills` filtered to skill-applied AI replies.
- **Knowledge browser + KB-to-matter attach loop** — Wave D. Reference architecture: Kevin's OpenLoris repo (`Tucuxi-Inc/OpenLoris`) for company-wide KB with Good-Until-Date (GUD) functionality. Look at it during Wave D planning before authoring the plan.
- **Saved Prompts dedicated surface** — Wave D. The tab stays ComingSoonModal until then.
- **Sandbox onboarding** (`matters.is_sandbox` column) — Wave E. Per priority 4 ordering.
- **Receipts mode + Citation Engine UI** — Wave D. PRD §1.3 transparency keystones.

### Wave C V2-FALLBACK count

**Zero.** Wave C wires every surface to real backend endpoints — no hardcoded fallbacks, no localStorage-as-signal-source. (Wave B v2 had 5 V2-FALLBACKs; Wave C ships clean.)

## 3. Backend Phase E — queued

**Goal of Phase E:** release-readiness. Make M1 actually shippable as a self-hosted product per the open-source posture in PRD §1.3 + spec §10.

**Five workstreams** (per the orientation we did this session — see plan section below for breakdown):

| Workstream | Typical artifacts | Touches |
|---|---|---|
| SBOM generation | CycloneDX or SPDX JSON per release (Python + JS deps + container layer manifests) | `.github/workflows/release.yml`, `Makefile` target |
| SLSA build provenance | Attestation file per release (build inputs, builder identity, output hash); SLSA Level 3 target | `.github/workflows/release.yml`, GitHub Actions `actions/attest-build-provenance` |
| cosign signing | Public/private keypair; CI signs container images + SBOM + provenance; verify-on-pull operator docs | `.github/workflows/release.yml`, `docs/security/verify-release.md` (new) |
| Helm chart | `deploy/helm/lq-ai/` chart: templates for api/gateway/web/postgres/minio/redis + values.yaml + NOTES.txt; ConfigMap for gateway.yaml; Secret refs for API keys | `deploy/helm/lq-ai/` (new dir) |
| Compliance docs | `docs/security/threat-model.md` (the V2-FALLBACK placeholder from Wave B v2 T3 TrustArtifactsCard) + `SECURITY.md` reference list + SLSA badge in README | `docs/security/`, root `SECURITY.md`, root `README.md` |

**Orthogonal to feature work** — Phase E touches `.github/workflows/`, `deploy/`, `docs/security/`, root markdown. Zero overlap with `web/` or `api/app/`. Safe to do in sequence on the same branch without merge anxiety.

**Estimated scope:** 6-10 atomic commits across a single session. Most of the work is mechanical (Helm templates, GH Actions YAML, doc writing).

**Recommended approach for the next session:**
1. Write a plan at `docs/superpowers/plans/2026-05-12-m1-backend-phase-e-release-readiness.md` (~20 minutes) with each workstream as a task
2. Dispatch subagent-driven execution OR do inline since the workstreams are largely independent
3. The Helm chart is the largest single task (~3-4 commits); SBOM/SLSA/cosign are CI-config-heavy (~1-2 commits each); compliance docs are writing (~1 commit per doc)
4. Final verification: trigger the release workflow on a tag (or dry-run) and confirm artifacts emit

**Open questions to resolve before Phase E starts:**
1. **Signing key custody.** Cosign needs a private key. Options: (a) GitHub Actions OIDC + Fulcio + keyless signing (no key custody needed), (b) operator-controlled key in `secrets.COSIGN_PRIVATE_KEY`. (a) is the modern standard; (b) is for air-gapped deployments. Probably (a) for the public OSS release, with docs on how a fork/operator can swap in (b).
2. **Helm chart distribution.** Push to a chart registry (OCI artifact in ghcr.io) vs publish to a Helm repo (GitHub Pages) vs just commit the chart in-repo and let operators `git clone + helm install`? In-repo is simplest for the OSS-first audience.
3. **Threat model depth.** Aim for STRIDE-by-component (api / gateway / web / postgres / minio) at "summary table + named threats" depth, not a 50-page document. PRD §5 + ADR 0009 already cover most of the design intent.

## 4. How to start the next session

### Kevin's stated workflow

Same pattern as Wave A → Wave B v2 → Wave C handoffs:

1. **Invoke `superpowers:subagent-driven-development`** at session start (or just resume inline if the workstreams are small enough to do without a planner subagent).
2. **Read this handoff doc** for orientation.
3. **Read `docs/PRD.md` §5 (Security & Compliance)** for the compliance-doc intent — `docs/db-schema.md` is up to date through migration 0019 from this session.
4. **Read existing `.github/workflows/`** to see what CI is currently doing — Phase E likely extends `release.yml` (or whatever the release entry point is) rather than authoring from scratch.
5. **Greet Kevin, summarize this handoff in ~3 sentences, then ask whether to proceed with Phase E plan-then-execute or just execute inline.**

### Pre-flight verification

```bash
cd /Users/kevinkeller/Desktop/lq-ai
git status -sb               # expect: clean, on kk/main/Frontend_Design
git log -1 --oneline         # expect: d44e0d3 test(web): Cypress E2E smoke for Wave C matters surfaces
cd web && npm run test:frontend -- --run 2>&1 | tail -5
                             # expect: Tests 174 passed (174)
docker compose ps            # expect: 7 services healthy
docker compose exec -w /app api pytest tests/ -m integration -q 2>&1 | tail -3
                             # expect: 486 passed, 1 skipped, 0 failed
```

### Auth shortcut (if you need to log in during smoke)

- URL: `http://localhost:3000/lq-ai/login`
- Email: `admin@lq.ai`
- Password: whatever was last set; if lost, `docker compose exec api python -m app.cli reset-admin-password` and read the password from `docker compose logs api 2>&1 | grep "First-run admin password"`

## 5. Lessons from this session

These are explicit Kevin patterns that surfaced during execution. Treat as load-bearing for the next session.

1. **Plan-vs-backend reconciliation pattern.** When a frontend plan references backend endpoints/types/enums, verify against OpenAPI sketch BEFORE dispatching the implementer. Kevin consistently chooses "extend backend" over frontend workarounds. Three instances this session: UserPreferences extension, role enum docs, `/admin/users` list endpoint. See `feedback_plan_vs_backend_reconciliation.md` in auto-memory.

2. **Conventional commit prefix discipline.** All commits should carry the `feat(web):` / `feat(api):` / `fix(web):` / `test(web):` / `refactor(web):` / `docs(plan):` prefix. Earlier in the session, 3 commits skipped this when the implementer prompt didn't enforce it explicitly. Subsequent prompts pinned the convention and the rest of the commits comply. **Always pin the prefix in the implementer prompt.**

3. **DCO sign-off + Co-author trailer mandatory on every commit.** `git commit -s -m "..."` with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` in the body. Verify before pushing: `git log -1 --format=fuller`.

4. **Stack rebuild scope-of-effect.** Frontend changes need `docker compose up -d --no-deps --build web` to take effect (the image bakes a static SvelteKit build). Backend changes need `docker compose up -d --no-deps --build api` (the api image bakes `app/` at build time). Migrations apply once via `make migrate` or via the api container's startup. Gateway env-var changes (e.g., new API keys in `.env`) require `docker compose up -d --no-deps --force-recreate gateway`.

5. **Test-fixture drift after schema evolution.** Migrations 0017 (`role` enum) and 0018 (`absolute_expires_at` / `last_active_at` on user_sessions) silently broke tests that pre-dated them. Anytime a migration adds NOT NULL columns to a table fixtures construct directly, sweep the test directory for stale fixtures BEFORE shipping the migration. Pattern: `grep -rn "ModelName(" api/tests/ | wc -l` to count fixture sites; spot-check each.

6. **OpenWebUI `app.html` overflow constraint.** The fork pins `html { overflow-y: hidden !important; }` for chat-UI scroll management. Any LQ.AI surface that isn't the chat shell needs its OWN scroll container (`<main overflow-y: auto>` in the outer `+layout.svelte`, fixed in `ab87f63`). New surfaces in Wave D + E should inherit this and won't need bespoke scroll handling.

7. **Session handoff at wave seams.** Wave A → Wave B v2 → Wave C all handed off cleanly at wave-close. Kevin's preference: close the current wave fully (including Cypress + verification) before handing off; don't hand off mid-wave. Backend Phase E is a natural next chunk because it's orthogonal to wave-numbered feature work.

8. **Architectural questions only when genuine.** Three calls this session went to Kevin (outputs panel data source, KB attachment UX, chat-embedding approach). Three more were auto-decided (V2-FALLBACK shapes, ChatPanel test scope, validation helper extraction). Kevin's pattern: surface the architectural calls, but make pragmatic local choices inline. Don't ask 6 questions when 2 will do.

## 6. Things NOT to do at Phase E kickoff

- Don't squat on Wave D scope. The Wave D plan is unwritten — Knowledge browser, KB-attach loop, outputs panel, Saved Prompts surface, Receipts mode, Citation Engine UI are all queued but not designed. Phase E is the immediate next chunk; Wave D comes after.
- Don't extend Phase E to "while we're at it, let's clean up X." Stay scoped. The 5 workstreams above are the contract.
- Don't write a Helm chart that templates pre-decision fields (e.g., signing-key custody) — leave those as values defaults with clear NOTES.txt prompts for the operator.
- Don't auto-trigger a real release. The release workflow should be ready, but tag-and-publish is Kevin's call.
- Don't force-push. Standard `git push` only.

## 7. Open items already routed

- **Wave D Knowledge browser** — will draw inspiration from `Tucuxi-Inc/OpenLoris` (Kevin's other repo) for the firm-wide KB with Good-Until-Date pattern. Read it during Wave D planning, NOT during Phase E.

- **Sandbox onboarding (`matters.is_sandbox` column)** — Wave E. Backend migration + frontend onboarding cascade per spec §6. Defer until Phase E ships + Wave D ships.

- **The 5 V2-FALLBACK items from Wave B v2** — still in code:
  1. `TrustDataResidencyCard` hardcodes compose hostnames (V2-FALLBACK)
  2. `TrustAuditHealthCard`-equivalent placeholder
  3. `DevApiDocsCard` hardcoded URLs
  4. Getting-started checklist signals fall back to localStorage
  5. Dashboard tier panel shows "default" because `/inference/current-tier` requires `(provider, model)` params
  
  These get cleaned up in **Wave F** (deferred to priority 3 per Kevin 2026-05-12). Don't fold them into Phase E.

---

**End of handoff.** Branch is clean at HEAD `d44e0d3`. Greet Kevin, summarize this in 3 sentences, ask if he wants to plan Phase E first or just start.
