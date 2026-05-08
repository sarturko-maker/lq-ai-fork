# M1 Implementation Order

> **Purpose:** A dependency-ordered task list for the M1 build. Each task is a discrete unit of work — typically a focused Claude Code session of 1–4 hours, with a verifiable end-state. The order is the dependency graph: Task N+1 builds on Task N. Tasks marked **[parallel]** can run concurrently with their predecessor task once it completes.
>
> **Audience:** Anyone — human or agent — implementing M1. Hand this document to Claude Code along with the PRD, OpenAPI sketches, DB schema, and gateway.yaml example, and the implementation flows from the order documented here.
>
> **Live status & deferred items:** see **[`docs/M1-PROGRESS.md`](M1-PROGRESS.md)** — the running ledger of what's done, what's next, and which deferred items each upcoming task pulls along.

The M1 milestone is the foundation: a working self-hosted release with the 10 starter skills, Projects, Organization Profile, Inference Tier Awareness, MFA option, per-user export/delete, and the launched Compliance Alignment Pack. Per [PRD §8](docs/PRD.md#m1--foundation-6-weeks), M1 lands in approximately 6 weeks of focused work.

This document breaks that 6-week block into ~35 tasks across 5 phases. The phases run roughly sequentially with parallel-execution opportunities flagged.

---

## Phase A — Foundation scaffolding (Week 1)

Lays the substrate. By the end of Phase A, the repository has running services that don't do much but talk to each other and the database is migrated.

### Task A1 — Repository scaffold ✅ Done (2026-05-07)

**Scope:** Create `api/`, `gateway/`, `web/` subdirectories with empty Python packages and OpenWebUI fork stub. `docker-compose.yml` at repo root with services for postgres (with pgvector), redis, minio, api, gateway, web. `.env.example` with **every** environment variable that any of the three services reads, documented inline (purpose, default, required-vs-optional). `Makefile` (or `justfile`) with conventional targets: `install`, `test`, `lint`, `format`, `migrate`, `run-dev`, `clean`. Health endpoints (`/health`, `/ready`) on all three application services returning 503 with structured "not implemented" body. Pin OpenWebUI fork at the version chosen in `docs/adr/0001-openwebui-fork-pin.md` and check the fork builds in Docker (no customization yet — just confirm the upstream build works inside our Compose).

**Dependencies:** None. This is the first task.

**Output:** `docker compose up` starts all services; all six containers report ready; `make install` installs Python and Node dependencies; OpenWebUI fork builds and serves its default UI; `.env.example` is complete enough that a new contributor could fill it in and run.

**Verification:** `docker compose ps` shows all 6 services running and healthy; `curl http://localhost:8000/health` and `:8001/health` return **200** with a structured `{"status": "alive", ...}` body (K8s liveness convention — the process is up; readiness via `/ready` returns 503 until A3/A4 wire dependencies); `curl http://localhost:3000` returns the OpenWebUI default page; every env var in `.env.example` is referenced by exactly one service.

**Effort:** 8–10 hours. The estimate was originally 4–6h; expanded during M1 planning when the breadth (six services, three OpenAPI surfaces, OpenWebUI fork build, complete env-var inventory) was assessed end-to-end. If the OpenWebUI fork build fights back, this can split into A1a (Compose + Python services) and A1b (web fork + env-var inventory).

### Task A2 — Database migration scaffolding ✅ Done (2026-05-07)

**Scope:** Alembic configured, initial migration `0001_initial.py` creates Phase A1 tables (`users`, `user_sessions`, `audit_log`, `inference_routing_log`). Migration runner integrated into `make migrate`. Test database setup (`pytest-postgresql` or Docker-launched).

**Dependencies:** A1.

**Output:** `make migrate` runs all migrations against Postgres; migrations have working `downgrade()`; pytest fixtures provide an isolated migrated database.

**Verification:** `psql` against the dev DB shows the tables exist; `make migrate-down && make migrate-up` produces an identical schema.

**Effort:** 3–4 hours.

### Task A3 — Inference Gateway minimal scaffold [parallel with A2] ✅ Done (2026-05-07)

**Scope:** FastAPI service in `gateway/` with: health endpoint, OpenAI-compatible chat-completions endpoint stub, OpenAI-compatible embeddings endpoint stub. Loads `gateway.yaml` and validates against the schema. Returns 501 for actual inference (not implemented yet).

**Dependencies:** A1.

**Output:** Gateway service runs, accepts requests at `/v1/chat/completions` and `/v1/embeddings`, returns 501 with descriptive error.

**Verification:** `curl -X POST http://localhost:8001/v1/chat/completions -d '{"model":"smart","messages":[]}'` returns 501.

**Effort:** 3–4 hours.

### Task A4 — Backend minimal scaffold [parallel with A2, A3] ✅ Done (2026-05-07)

**Scope:** FastAPI service in `api/` with: health endpoint, postgres connection, Redis connection, MinIO connection, OpenAPI 3.1 spec autogenerated and served at `/openapi.json`. Empty endpoint stubs matching `backend-openapi.yaml` (return 501 for everything except health).

**Dependencies:** A1, A2.

**Output:** Backend service runs, OpenAPI spec served, all expected endpoints registered (returning 501).

**Verification:** `curl http://localhost:8000/openapi.json | jq '.paths | keys'` shows the expected endpoints.

**Effort:** 4–6 hours.

### Task A5 — Web shell scaffold (OpenWebUI fork) [parallel with A2, A3, A4] ⏳ Partial (2026-05-07)

**Scope:** Fork OpenWebUI to `web/`. Apply LQ.AI branding (logo placeholder, color scheme, footer). Configure to point at the LQ.AI backend instead of OpenWebUI's default. Build runs in Docker via `docker compose`.

**Dependencies:** A1.

**Output:** Web app loads at `http://localhost:3000`, displays the login screen, has LQ.AI branding.

**Verification:** Visiting localhost:3000 shows the LQ.AI-branded login.

**Effort:** 6–8 hours (most time on getting OpenWebUI fork building cleanly).

**Status (2026-05-07): partially complete; full delivery folded into Phase B/C/D UI work.**

What landed in A1.d + A1.c: OpenWebUI v0.9.2 imported (per ADR 0001), builds in Docker via `docker compose`, `WEBUI_NAME=LQ.AI` and `WEBUI_AUTH=false` set in `.env.example`. The container starts healthy and serves OpenWebUI's default UI with the LQ.AI display name in its header.

What's deferred:
- **Delegated auth wiring** — the OpenWebUI fork needs Svelte-component changes to call the LQ.AI backend's `/api/v1/auth/login` instead of OpenWebUI's built-in auth (per ADR 0002). Folds into B1's verification (the auth flow is end-to-end testable once both pieces exist).
- **Visual branding (LQ.AI logo, color scheme, footer)** — needs design decisions plus dual-branding per ADR 0001's branding-clause analysis. Folds into D2 (Tier-Awareness UI work) where we're already touching the OpenWebUI shell.

This is a deliberate sequencing choice: A5's full scope requires UI design decisions and Svelte-component work that's better done with the auth + tier substrate already in place. The env-var branding done in A1 is sufficient for Phase B/C work to proceed.

---

## Phase B — Core authentication and routing (Week 2)

Users can sign in. The backend can route inference requests through the gateway to a real LLM. The first end-to-end happy path works.

### Task B1 — User model + auth endpoints (backend) ✅ Done (2026-05-07)

**Scope:** Implement `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/refresh`, `/api/v1/users/me`. Bcrypt password hashing. JWT access tokens (short-lived, 15 min). Refresh tokens (long-lived, 7 days, hashed in DB).

**Dependencies:** A4.

**Output:** Login flow works end-to-end with username/password.

**Verification:** Integration test creates a user, logs in, fetches `/api/v1/users/me` with the bearer token, refreshes, logs out.

**Effort:** 6–8 hours.

### Task B2 — First-run admin user setup

**Scope:** On first start, create admin user with a randomly generated password. Print password to API container logs (matching the quickstart's expected behavior). Force password change on first login.

**Dependencies:** B1.

**Output:** First-run experience matches the documented quickstart.

**Verification:** Fresh deployment → admin password in logs → login → forced password change → permanent password works.

**Effort:** 2–3 hours.

### Task B3 — Anthropic provider adapter (gateway) ✅ Done (2026-05-07)

**Scope:** Implement provider adapter for Anthropic in `gateway/providers/anthropic.py`. Translates between OpenAI Chat Completions format (the gateway's surface) and Anthropic Messages format. Supports both streaming and non-streaming.

**Dependencies:** A3.

**Output:** Gateway accepts OpenAI-format requests routed to Anthropic, makes the call, returns OpenAI-format responses.

**Verification:** With ANTHROPIC_API_KEY set, `curl` request to `/v1/chat/completions` with model `claude-sonnet-4-6` returns a real completion.

**Effort:** 6–8 hours.

### Task B4 — Gateway router + alias resolution + tier derivation

**Scope:** Implement model alias resolution (`smart` → `claude-opus-4-7`), provider routing, and basic fallback chain. Reads `gateway.yaml`. For M1 baseline, single Anthropic provider; fallback structure in place but not exercised until B6. **Tier derivation is built into routing**: every routed request is annotated with `routed_inference_tier` (1–5) derived from the resolved provider/model and the gateway's `inference_tiers.defaults` block. The tier value is included in the response metadata (so the backend and UI can read it without re-deriving) and written to every `inference_routing_log` row. Per-skill / per-Project tier-floor enforcement (refusing requests below a declared minimum with HTTP 403 and `tier_below_minimum` error code) is split out to D1 — but the derivation itself lands here, where the data path is being built.

**Dependencies:** B3.

**Output:** Gateway resolves aliases per `gateway.yaml`; routes correctly; logs routing decisions to `inference_routing_log` **with `routed_inference_tier` populated**; response metadata includes the tier so downstream consumers don't re-derive.

**Verification:** Request with model `smart` lands at the configured Anthropic model; routing log entry created with the expected tier; the gateway's HTTP response includes `routed_inference_tier` in a documented header or response metadata field.

**Effort:** 5–7 hours. Originally 4–6h; +1h for tier derivation lifted from D1.

**Why tier derivation lives here, not in D1:** the data path runs through B4 (and B5 right after). If tier derivation lands in D1 after the path is built, it backfills through gateway → backend → DB → UI. Doing it here keeps the audit log and message rows correct from the first inference call. D1 then narrows to the refusal logic and 403 handling — which is genuinely a separate concern.

### Task B5 — Backend ↔ Gateway integration

**Scope:** Backend has a gateway client that calls the gateway with the gateway API key. Backend chat endpoint stub now calls through the gateway and returns the response.

**Dependencies:** A4, B4.

**Output:** End-to-end inference path: backend receives request → calls gateway → gateway calls Anthropic → response returns through both layers.

**Verification:** Integration test sends a chat message via backend API and receives a real response.

**Effort:** 4–6 hours.

### Task B6 — Additional provider adapters [parallel; can defer to Phase E]

**Scope:** Implement adapters for OpenAI, Vertex (Anthropic on Vertex), Bedrock. Optional for M1 baseline; recommended for breadth. Ollama adapter is critical for Mode 2.

**Dependencies:** B3 (template).

**Output:** Each provider can be configured and routed to.

**Verification:** Per provider: configure in `gateway.yaml`, send a request, verify response.

**Effort:** 3–4 hours per provider.

---

## Phase C — Capability layer (Weeks 3–4)

The substantive features. Skills load, chats persist, files upload, knowledge bases work, projects scope.

### Task C1 — Skill Service: filesystem loading

**Scope:** On gateway startup, load all skills from `skills/` filesystem directory. Parse frontmatter, validate schema, register in memory. Reload on SIGHUP. Expose `GET /api/v1/skills` and `GET /api/v1/skills/{name}`.

**Dependencies:** A4.

**Output:** All 10 starter skills loaded and queryable.

**Verification:** `curl http://localhost:8000/api/v1/skills` returns the 10 skills with their metadata; `curl http://localhost:8000/api/v1/skills/nda-review` returns full skill content.

**Effort:** 6–8 hours.

### Task C2 — Skill Service: prompt assembly

**Scope:** When a skill is attached to a chat, the skill's `SKILL.md` body is prepended to the chat's system prompt. Reference files are loaded and prepended too. Skill input values (from form-shaped attachment) are interpolated into the prompt.

**Dependencies:** C1.

**Output:** Attaching NDA Review to a chat results in its instructions being part of the actual prompt sent to the model.

**Verification:** Send a chat message with NDA Review attached; inspect the gateway log; the gateway received a prompt containing the skill's instructions.

**Effort:** 6–8 hours.

### Task C3 — Chat service + message persistence

**Scope:** Implement `/api/v1/chats` (CRUD), `/api/v1/chats/{id}/messages` (POST creates new exchange and streams response). Persist messages to DB. Stream chunks via SSE. Persist final message with citations, routed_inference_tier, cost.

**Dependencies:** B5, C2.

**Output:** Full chat flow: create chat → attach skill → send message → stream response → see message in chat history.

**Verification:** Integration test exercises the full flow; Postgres has expected rows in `chats` and `messages`.

**Effort:** 10–12 hours.

### Task C4 — File upload + storage

**Scope:** Implement `/api/v1/files` (POST upload, GET metadata, DELETE). Files stored in MinIO with `storage_path` recorded. `ingestion_status` set to `pending` initially.

**Dependencies:** A4.

**Output:** Users can upload files; files accessible by ID.

**Verification:** Upload a PDF; verify it's in MinIO; download it via API; bytes match.

**Effort:** 4–6 hours.

### Task C5 — Document pipeline (basic)

**Scope:** Document Pipeline Service that processes files: Docling for PDFs, PyMuPDF for backup, **character-precise offsets preserved on every chunk**. Async worker via Redis queue. Updates `documents` table on success. **No OCR yet** (M2). **No citation verification yet** (M2 — basic chunks only).

**Character-fidelity requirement (load-bearing for M2):** even though M1 does not yet verify citations, `document_chunks.char_offset_start` and `char_offset_end` must be character-precise against the original document text. The M2 Citation Engine's deterministic substring verification depends on these offsets being correct from the first ingestion — re-ingesting the M1 corpus to fix offset drift is expensive and avoidable. PyMuPDF gives byte-precise offsets; Docling's structured output is reconciled against PyMuPDF's character stream during chunking. Add a unit test that picks a random chunk, slices the original text by `[char_offset_start:char_offset_end]`, and asserts byte-equality against `chunk.content`.

**Dependencies:** C4.

**Output:** Uploaded PDF is parsed; chunks created; embeddings generated; `documents` and `document_chunks` populated; offset-fidelity test passes against a representative document corpus.

**Verification:** Upload a PDF; wait for `ingestion_status: ready`; query `document_chunks` and confirm content is present, offsets are character-precise (assertion above), and embeddings are non-null.

**Effort:** 10–14 hours.

### Task C6 — Knowledge Service: hybrid retrieval

**Scope:** `/api/v1/knowledge-bases` CRUD. Hybrid retrieval combining pgvector cosine similarity and Postgres FTS. Configurable `hybrid_alpha` parameter (0=vector, 1=FTS).

**Dependencies:** C5.

**Output:** Files added to a KB are searchable; queries return relevant chunks with scores.

**Verification:** Add 5 files to a KB; query for content; verify expected chunks appear in top results.

**Effort:** 6–8 hours.

### Task C7 — Project service

**Scope:** `/api/v1/projects` CRUD. Attached files and skills tracked in join tables. Free-form context document stored. `privileged` flag with constraint that `minimum_inference_tier` must be set.

**Dependencies:** C1, C4.

**Output:** Projects work as documented in the quickstart.

**Verification:** Create project, attach skill, attach file, set context, verify all persist and round-trip correctly.

**Effort:** 4–6 hours.

### Task C8 — Web UI: chat experience [parallel from C3 onward]

**Scope:** OpenWebUI fork customized for LQ.AI: chat sidebar, attached-files panel, skill picker, streaming message display, markdown rendering. Inherit Project context when chat is in a project.

**Dependencies:** C3.

**Output:** Web UI delivers the chat experience documented in the quickstart.

**Verification:** Manual walkthrough of quickstart Step 4: attach skill, upload file, run, see streamed output.

**Effort:** 16–20 hours (most UI work concentrated here).

---

## Phase D — M1 differentiators (Week 5)

The features that make this LQ.AI rather than just another chat-with-LLMs app: tier awareness, audit log fields, organization profile, MFA, per-user delete.

### Task D1 — Tier-floor enforcement (refusals)

**Scope:** Per PRD §4.4, the gateway refuses requests below `minimum_inference_tier` (declared on the skill, on the Project, or on the request itself). Returns HTTP 403 with structured error code `tier_below_minimum` and a body explaining which floor was violated. Backend surfaces the refusal as a user-visible error (not a generic 500). Refusals land in `inference_routing_log` with `refused: true` and `refusal_reason: 'tier_below_minimum'`.

**Tier *derivation* itself moved to B4** during M1 planning — it's part of the routing data path, not a downstream concern. D1 is now narrowly the refusal-and-403 logic.

**Dependencies:** B4 (derivation), C7 (Projects, for project-level minimum_inference_tier).

**Output:** Refusals work correctly across all three sources of a tier floor (skill frontmatter, Project setting, request override). The 403 body is structured and stable.

**Verification:** (a) Request with `minimum_inference_tier: 1` against Tier 4 provider returns 403 with descriptive error. (b) Skill with `minimum_inference_tier: 2` attached to a chat routed at Tier 4 → 403. (c) Project with `minimum_inference_tier: 3` containing a chat routed at Tier 4 → 403. (d) Audit log shows the refusal with the correct `refusal_reason`.

**Effort:** 3–4 hours. Reduced from 4–6h since derivation is no longer scoped here.

### Task D2 — Inference Tier Awareness UI

**Scope:** Tier badge in chat header showing routed tier (1–5). Click for details panel: provider, retention policy, training implications. The badge updates per-message based on `routed_inference_tier` returned in the message.

**Dependencies:** D1, C8.

**Output:** UI surfaces tier as documented in PRD §3.13 and shown in the quickstart.

**Verification:** Send messages routed to different tiers; badge updates correctly; details panel shows correct provider info.

**Effort:** 4–6 hours.

### Task D3 — Audit log: privilege fields

**Scope:** Every action that lands in `audit_log` has `privilege_marked` and `privilege_basis` populated correctly. Chat in a privileged Project → all messages and chat events marked privileged. Routed inference tier captured.

**Dependencies:** B1, C7.

**Output:** Audit log queries by `privilege_marked = true` return all privileged actions.

**Verification:** Create privileged project, send chat, query audit log filtered by `privilege_marked = true`, get expected entries.

**Effort:** 4–6 hours.

### Task D4 — Organization Profile singleton

**Scope:** Organization Profile is a singleton skill at the deployment level. `/api/v1/organization-profile` GET/PUT. Constraint enforced via partial unique index. Profile content prepended to every other skill's prompt unless `use_organization_profile: false` in the skill's frontmatter.

**Dependencies:** C2.

**Output:** Profile creation, retrieval, and update work; profile content actually shapes downstream skill output.

**Verification:** Set Organization Profile saying "we always recommend Delaware as choice of law"; run NDA Review; output reflects this preference.

**Effort:** 4–6 hours.

### Task D5 — MFA enrollment + verification

**Scope:** `/api/v1/auth/mfa/setup` and `/api/v1/auth/mfa/verify`. TOTP via `pyotp`. QR code generation for provisioning URI. Recovery codes (10 single-use codes, hashed). Login flow detects `mfa_enabled` and returns 423 with MFA challenge if required.

**Dependencies:** B1.

**Output:** Users can enroll in MFA; subsequent logins require TOTP code; recovery codes work.

**Verification:** Full enroll → login → unenroll cycle. Recovery code single-use enforcement verified.

**Effort:** 6–8 hours.

### Task D6 — Per-user export and delete (GDPR Articles 17 and 20)

**Scope:** `/api/v1/users/me/export` generates a ZIP with the user's data (chats, messages, files, projects, skills). `/api/v1/users/me/delete` schedules account deletion with a grace period (default 30 days). Hard delete after grace period.

**Dependencies:** C3, C4, C7.

**Output:** Both endpoints work; export includes everything; delete actually removes data after grace period.

**Verification:** Create a user with realistic data; export and verify the ZIP; delete and verify data is removed after the grace period (test with shortened grace period).

**Effort:** 6–8 hours.

### Task D7 — Saved Prompts (per Issue 04)

**Scope:** `/api/v1/saved-prompts` CRUD. Sidebar in web UI. "Promote to Skill" affordance.

**Dependencies:** C8.

**Output:** Saved prompts work as documented in Issue 04.

**Verification:** Create, list, update, delete saved prompts; promote-to-skill opens Skill Creator with content seeded.

**Effort:** 4–6 hours.

---

## Phase E — Procurement and release readiness (Week 6)

The artifacts that make M1 launch-ready beyond just "the code works."

### Task E1 — Compliance Alignment Pack mappings (initial)

**Scope:** Fill in `docs/compliance/soc2-alignment.md` and `docs/compliance/iso27001-alignment.md` with substantive control responses. M1 ships with these two; ISO 42001 / GDPR / HIPAA / FedRAMP fill in over M2.

**Dependencies:** D3 (audit log fields), D5 (MFA), D6 (export/delete) — the controls being mapped.

**Output:** Two complete alignment documents; references in the README and PRD updated.

**Verification:** Reviewing-counsel pass on the documents.

**Effort:** 8–12 hours (substantive, requires care).

### Task E2 — SBOM generation in CI

**Scope:** GitHub Actions workflow generates SBOM (SPDX format) on each release. SBOM committed to release artifacts.

**Dependencies:** None (CI infrastructure).

**Output:** Releases include SBOM.

**Verification:** Tag a release; SBOM artifact appears.

**Effort:** 4–6 hours.

### Task E3 — Signed releases (Sigstore/cosign)

**Scope:** Container images signed with cosign keyless signing; signatures verifiable via published CI provenance.

**Dependencies:** E2.

**Output:** Signed images per the verification command in `docs/security/README.md`.

**Verification:** Verification command from `SECURITY.md` succeeds against a real release artifact.

**Effort:** 4–6 hours.

### Task E4 — SLSA-3 build provenance

**Scope:** GitHub Actions workflow generates SLSA-3 provenance attestations alongside signed releases.

**Dependencies:** E3.

**Output:** Each release has SLSA-3 provenance.

**Verification:** Verification per slsa-verifier tooling.

**Effort:** 4–6 hours.

### Task E5 — Public threat model

**Scope:** `docs/security/threat-model.md` covering: assets, attackers, attack vectors, mitigations. Calibrated to the actual M1 deployment posture, not aspirational.

**Dependencies:** All preceding tasks (the threat model needs to reflect what was actually built).

**Output:** Threat model published; cross-referenced from PRD and README.

**Verification:** Reviewing-security pass on the document.

**Effort:** 8–10 hours.

### Task E6 — End-to-end smoke tests

**Scope:** Playwright tests covering the quickstart's happy path: clone → up → login → org profile → project → skill → run → review output → tier badge → audit log. Runs in CI on every PR.

**Dependencies:** All of Phase C and D.

**Output:** Quickstart-equivalent flow runs in CI; failures block merge.

**Verification:** CI pipeline runs the test against a fresh deployment.

**Effort:** 8–12 hours.

### Task E7 — Quickstart validation pass

**Scope:** Walk through `docs/quickstart.md` against the actual M1 deployment. Note every place where the quickstart says X happens and Y actually happens. Update either the quickstart or the implementation to align.

**Dependencies:** E6.

**Output:** Quickstart works as documented; no surprise gotchas.

**Verification:** Hand the quickstart to a friendly reviewer who hasn't touched the codebase; they complete it without external help.

**Effort:** 4–6 hours.

### Task E8 — Helm chart for Kubernetes

**Scope:** Initial Helm chart at `deploy/helm/lq-ai/`. Templates for each service. Configurable via `values.yaml`. Documented in the deployment cookbook.

**Dependencies:** All of Phase C and D.

**Output:** `helm install` produces a working deployment.

**Verification:** Deploy to a kind/k3d cluster; smoke-test the deployment.

**Effort:** 8–12 hours.

---

## Total effort estimate

| Phase | Tasks | Effort |
|---|---|---|
| **A — Foundation scaffolding** | 5 | ~28 hours (A1 expanded from 4–6h to 8–10h) |
| **B — Authentication and routing** | 6 | ~31 hours (B4 +1h for tier derivation) |
| **C — Capability layer** | 8 | ~70 hours |
| **D — M1 differentiators** | 7 | ~34 hours (D1 reduced; derivation moved to B4) |
| **E — Procurement and release** | 8 | ~50 hours |
| **Total** | 34 | ~213 hours |

~213 hours is a focused 6-week build for a single contributor working full-time, or 8–10 weeks for someone working part-time with parallelization on UI work (Task C8 specifically benefits from a frontend-specialized contributor). First-time-through-this-architecture friction usually warrants a 1.3–1.5× contingency on the per-task estimates.

---

## How to use this with Claude Code

The recommended workflow:

1. **Hand Claude Code this document, plus the PRD, OpenAPI sketches, DB schema, gateway.yaml example, and CLAUDE.md.**
2. **Pick the next task by ID.** "Implement Task A1 — Repository scaffold."
3. **Let Claude Code execute the full task in one session.** Each task is sized to fit comfortably in a single session.
4. **Verify against the documented verification step.** If verification fails, work with Claude Code to fix; do not move to the next task until the current task verifies.
5. **Move to the next task.** Tasks marked **[parallel]** can run concurrently, but for an agentic workflow it's usually cleaner to run sequentially unless you specifically have parallel agents available.
6. **Don't let Claude Code make architectural decisions mid-task.** If a task surfaces a question that wasn't anticipated in the PRD, OpenAPI, or DB schema, stop, decide, document the decision (in PRD §9 if it's a forward-looking choice; in an ADR if it's a structural choice), and resume.
7. **Surface ideas as DE-XXX entries.** When Claude Code surfaces useful ideas that are out of scope for the current task — and it will — file them as deferred enhancements in PRD §9 rather than expanding the task scope.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Claude Code drifts mid-task and rebuilds something differently than the PRD | Hand it the PRD section explicitly at task start; reference PRD section IDs in tasks |
| Schema evolves during the build | Update `db-schema.md` in the same PR as the migration; failure to do so blocks merge |
| Task takes longer than estimated | Estimates assume happy-path with no novel decisions; budget 1.5x for tasks that touch more than one subsystem |
| OpenWebUI fork drifts from upstream | Pin to a specific commit at fork time; document the patches; rebase quarterly |
| End-to-end testing reveals integration issues late | Task E6 (E2E tests) is intentionally near the end; some operators may want to lift it earlier — at the cost of slower happy-path development |

---

*Implementation order maintained alongside the PRD. As tasks complete, mark them so the next contributor (or agent) sees current state. Tasks that turn out to need decomposition are split in-place and the document updated.*
