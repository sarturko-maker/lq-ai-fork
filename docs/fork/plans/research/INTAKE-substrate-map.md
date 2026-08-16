# INTAKE research 3/4 — fork substrate map (Sonnet Explore sub-agent, 2026-08-16)

> Commissioned for the INTAKE milestone plan (`docs/fork/plans/INTAKE-INBOX-plan.md`, task #536).
> Codebase facts with file:line refs; verbatim from the research agent, unedited.
> Code is canonical — re-verify line numbers at implementation time.

## 1. HITL substrate (ADR-F071)

**Where `interrupt()` is raised:** not in our code. `api/app/agents/hitl.py:42` `compile_hitl_policy(policy, granted) -> dict|None` compiles `practice_areas.hitl_policy` into deepagents' `interrupt_on` kwarg:

```python
compiled[name] = {"allowed_decisions": list(_ALLOWED_DECISIONS), "description": _describe(name)}
```
(`_ALLOWED_DECISIONS = ["approve", "reject"]`, `hitl.py:32`). This is fed to `create_deep_agent(interrupt_on=...)` at `api/app/agents/composition.py:1300` / `runner.py:834-835`, which hands it to langchain's **`HumanInTheLoopMiddleware`** (`after_model` hook, deepagents-native) — that middleware raises the actual `interrupt()`, not us. `hitl.py:103` (`stamp_subagent_opt_out`) sets `spec["interrupt_on"] = {}` on fork-authored subagents (LEAD-only scope).

**Payload shape.** At pause, `runner.py:623-660` reads `interrupt.value = {"action_requests": [{"name": tool_name, "args": {...}}, ...]}` (plural array, keys `name`/`args`). This is **not** LangChain's older `HumanInterrupt{action_request:{action,args}, config:{allow_accept,allow_edit,allow_respond,allow_ignore}, description}` — ours has a plural `action_requests` array, `allowed_decisions` closed to `["approve","reject"]` (not four boolean flags), and a per-tool static `description`.

**Reaching the UI: a settled DB row, not a new SSE frame.** One `agent_run_steps` row, `kind="hitl_request"` (migration `0093`; enum `AgentRunStepKind.hitl_request`, `schemas/agent_runs.py:57`), written at `runner.py:991-1001` with `summary=json.dumps([{"tool":name,"args":{...}}], sort_keys=True)`. It mirrors on the wire as a generic `data-step` part (`agents/stream.py:120`); the terminal `data-run` part (`stream.py:148`) carries `status="awaiting_input"`. Run settles via `AgentRun.status="awaiting_input"` (`models/agent_run.py`, migration `0093`), `finished_at` stamped, lease untouched.

**Resume endpoint:** `POST /agents/runs/{run_id}/resume` (`api/app/api/agent_runs.py:1067-1073`), body `AgentRunResume{decision: ResumeDecision}`, `ResumeDecision{type: Literal["approve","reject"], message: str|None}` (`schemas/agent_runs.py:116-139`), owner-scoped `MutatingUser` (404 not 403), 409 on `run_not_awaiting_input`/`run_superseded`/`thread_busy`. Builds `Command(resume={interrupt_id: {"decisions":[...]}})` via `runner.py:684 _build_resume_command`, one human decision fanned across every gated call.

**Web components:** `web/src/lib/lq-ai/components/agents/HitlConfirmCard.svelte` (parses the settled step's `summary` defensively via `parseHitlActions`) rendered from `web/src/lib/lq-ai/components/agents/ConversationPanel.svelte`, calling `resumeRun()` (`web/src/lib/lq-ai/api/agents.ts:224`). Widened stream validators live in `web/src/lib/lq-ai/agents/run-stream.ts` (`parseRunPayload` line 183).

## 2. Run lifecycle

`POST /agents/runs` → `create_agent_run(body: AgentRunCreate, user: MutatingUser, ...)` (`api/app/api/agent_runs.py:272-278`), 202. `AgentRunCreate` (`schemas/agent_runs.py:75-105`): `prompt` (required, 1-32768), `model_alias="smart"`, `budget_profile: BudgetProfile|None`, `max_steps: int|None` (1-600), `thread_id`/`project_id` (mutually exclusive). **`project_id` is NOT mandatory** — omitting both creates a "blank workspace" thread (`agent_runs.py:400-407`).

**Composition root:** `compose_and_execute_run(*, run_id, lease=None, broker=None, ...)` at `api/app/agents/composition.py:646`. It reads *everything* from `run_id` alone via DB: matter binding, `PracticeArea.agent_config`/`hitl_policy`, skills via `practice_area_skills`, tool-group availability via `practice_area_tool_groups` + per-matter overrides in `MatterCapabilityToggle` (read at `composition.py:879-880`, resolved through `build_area_inventory`, `agents/capabilities.py:662`).

**Headless start — already the norm.** `agent_run_job(ctx, run_id: str)` (`workers/agent_run_worker.py:151-159`) takes *only* `run_id`; `execute_run_job` (line 78) claims a lease then calls `compose(run_id=run_id, ...)`. `enqueue_agent_run_job(run_id)` (`workers/queue.py:375-412`) enqueues job name `agent_run_job` onto arq queue `arq:m3a6` with a deterministic `_job_id`. **Precedent for bypassing HTTP entirely:** `api/tests/agents/scenarios/test_commercial_deal_change_live.py:80-110` inserts `AgentThread`/`AgentRun` rows directly with SQLAlchemy, then calls `compose_and_execute_run(run_id=run_id, session_factory_provider=..., checkpointer_provider=lambda: None, ...)` in-process — no HTTP, no arq. A background job could do either this or the enqueue path.

**arq queues/workers today:** ingest queue (`arq app.workers.document_pipeline.WorkerSettings`, `ingest-worker` container) and `arq:m3a6` (`M3_PLAYBOOK_QUEUE_NAME`, `workers/arq_setup.py:105`, `arq-worker` container) shared by `easy_playbook_generation_job`, `playbook_execution_job`, `tabular_execution_job`, `autonomous_session_job`, `agent_run_job` (`max_tries=1`, `arq_setup.py:360-369`). Cron: `autonomous_idle_watchdog`/`autonomous_schedule_dispatcher` (:00 every min), `agent_run_orphan_sweep` (:30 every min), `checkpoint_gc_job` (04:30 daily) — `arq_setup.py:288-301`. **Existing non-HTTP trigger:** `autonomous_schedule_dispatcher` (cron) enqueues `autonomous_session_job` on its own — a separate execution path from `agent_runs`, but proves scheduled/background-triggered execution is an established pattern.

**Status/poll:** `GET /agents/runs` (`agent_runs.py:486`), `GET /agents/runs/{id}` (526), `GET /agents/threads` (908), `GET /agents/threads/{id}` (987), `GET /agents/runs/{id}/stream` (766, SSE).

**BudgetProfile resolution:** `agent_runs.py:409-439` — chain `body.budget_profile` > `PracticeArea.default_budget_profile` (joined via thread's project) > `Settings.run_default_budget_profile` (env `RUN_DEFAULT_BUDGET_PROFILE`) > `BudgetProfile.balanced`; envelope via `resolve_envelope()` in `agents/budget.py`. **Capability toggles:** resolved inside composition per matter (`composition.py:879-880`); absent row = enabled (default-on).

## 3. Matters/projects

`projects` columns (`api/app/models/project.py:92-139`): `id, owner_id, practice_area_id(nullable FK SET NULL), name, slug, description, context_md, privileged(bool), minimum_inference_tier(smallint 1-5), is_sandbox(bool), ensemble_verification(bool), created_at, updated_at, archived_at`. **No `status`/`kind`/`origin` column** — only `archived_at` (soft-delete) and `is_sandbox` exist as state markers; sandboxes are CHECK-forbidden from having `practice_area_id` (line 86-89).

Creation: `POST /projects` → `create_project` (`api/app/api/projects.py:342-354`).

`matter_memory_entries` (`project.py:278-379`): `id, project_id(FK CASCADE), user_id(FK CASCADE), kind, body_md, trust, run_id, superseded_at, author, source_citation, fact_type, valid_at, invalid_at, superseded_by, created_at`.

`matter_participants` (`project.py:410-505`): `id, project_id(FK CASCADE), user_id(FK CASCADE), display_name, aliases(JSONB), organization, role_label, side(ours/counterparty/other/unknown), trust(inferred/confirmed), source_citation, run_id, superseded_at, created_at, updated_at`.

**Archive/delete:** `DELETE /projects/{id}` (`projects.py:601-636`) is **soft** — sets `archived_at=now()`, idempotent (already-archived → 404). No cascade; docstring: `"Hard-delete is owned by D6"` (the GDPR erasure flow), not this endpoint.

## 4. File ingest

`POST /files` (multipart) → `upload_file` (`api/app/api/files.py:169-185`), optional `project_id` form field (422 pre-bytes if not owned/active). `files` columns (`api/app/models/file.py:43-123`): `id, owner_id, project_id(plain UUID, no FK), filename, mime_type, size_bytes, hash_sha256, storage_path, ingestion_status(default 'pending'), ingestion_error, created_by_run_id(FK agent_runs SET NULL), parent_file_id(FK files SET NULL), is_snapshot(bool), summary, summary_updated_at, summary_run_id(FK agent_runs SET NULL), summary_author, created_at, updated_at, deleted_at`.

Ingest enqueue: `enqueue_ingest_job(file_id)` at `files.py:357`, job `"ingest_file_job"` on the **default** arq queue (not `arq:m3a6`), consumed by `ingest-worker`. Failure is non-fatal (row stays `pending`, worker startup sweep re-enqueues).

**Storage seam:** `api/app/storage.py` — aioboto3, `s3_client()` (line 88, built per-call from `Settings.s3_*`). `stream_upload(...)` (line 156) backs the HTTP route; `upload_bytes(*, storage_path, body: bytes, content_type)` (line 457) is a **raw-bytes primitive already used by non-HTTP callers** (WOPI's PutFile). **No packaged "ingest bytes" service function exists** — `upload_file` inlines validate→store→row-insert→enqueue; a background job wanting the same would compose `upload_bytes` + a `File` row + `enqueue_ingest_job(file_id)` itself, duplicating logic.

**Dedup (ADR-F082):** not enforced at write time (no unique constraint on `hash_sha256` — duplicate bytes upload fine); detected at read time for the agent by `duplicate_of_map()` (`api/app/agents/tools.py:566-600`), grouping a matter's files by identical `hash_sha256`.

## 5. Inbound-callback precedent

**WOPI** (`api/app/api/wopi.py`, prefix `/wopi`): `GET /wopi/files/{id}` (225, CheckFileInfo), `GET /wopi/files/{id}/contents` (262, GetFile), `POST /wopi/files/{id}` (319, lock family), `POST /wopi/files/{id}/contents` (404, PutFile). Mounted **without** the `ActiveUser` gate (`wopi.py:18-19`). Auth = a file-scoped signed JWT we mint ourselves: `create_wopi_token(user_id, file_id, *, name)` (`api/app/security/jwt.py:216-234`, HS256, claims `sub/fid/name/iat/exp/typ="wopi"`) minted behind `POST /files/{id}/editor-session` (`files.py:463`, MutatingUser-gated). Every handler re-decodes + re-checks `fid==URL id` + re-runs `_load_visible_file` (cross-user → 404, never 403); write ops also re-check live role (`_require_live_mutating_user`, `wopi.py:196`). CORS irrelevant — server-to-server on the compose network.

**Closer precedent for a genuine third-party webhook:** `slack-bridge`/`teams-bridge` are **separate microservices** (`docker-compose.yml` services, dirs `/slack-bridge`, `/teams-bridge`). `slack-bridge/app/main.py:100` `POST /slack/events` receives Slack's webhook and verifies Slack's own signature:

```python
def verify_slack_signature(*, signing_secret, timestamp, body: bytes, signature, now=None) -> bool
```
(`slack-bridge/app/signing.py:31`) — HMAC-SHA256 over `v0:{timestamp}:{body}`, headers `X-Slack-Signature`/`X-Slack-Request-Timestamp`, 5-min replay window. The bridge then authenticates *itself* to `api` with a static shared bearer secret: `require_bridge_auth()` (`api/app/api/dependencies.py:312-339`) constant-time-compares `Authorization: Bearer` against `LQ_AI_BRIDGE_TOKEN`, guarding `POST /integrations/slack/workspaces` (`api/app/api/integrations_slack.py:48-54`, mounted without the user gate). Admin visibility over these connections: `api/app/api/admin_intake_bridges.py` (`GET/DELETE /admin/intake-bridges/...`, `AdminUser`-gated).

**Reusable pattern:** verify the external sender's own signature at the edge (mirror `verify_slack_signature`), then cross into `api` via the existing `require_bridge_auth` shared-secret dependency (or a new dedicated secret), on a router mounted without `ActiveUser` — exactly the WOPI/Slack/Teams posture.

## 6. Admin/org config

Admin gate: `AdminUser = Annotated[User, Depends(get_admin_user)]` (`api/app/api/dependencies.py:137-158`); e.g. `admin_intake_bridges.py:56-58`.

`practice_areas` (`api/app/models/practice_area.py:50`) carries `agent_config`(JSONB) + `hitl_policy`(JSONB, ~line 100). Module-binding tables: `PracticeAreaSkill`/`practice_area_skills` (119/129), `PracticeAreaPlaybook`/`practice_area_playbooks` (152/165), `PracticeAreaKnowledgeBase`/`practice_area_knowledge_bases` (194/212), `PracticeAreaToolGroup`/`practice_area_tool_groups` (248/264, ADR-F062 availability table), `OrgLibraryEntry`/`org_library_entries` (291/313, ADR-F065).

Org-level settings tables: `organization_profile` (singleton, `api/app/models/organization_profile.py:27-41`: `id, content_md, created_at, updated_at, updated_by`); `branding` (ADR-F068). **Closest existing precedent for an "intake inbox binding":** `slack_workspaces`/`teams_tenants` (org-level external-bridge connection tables, soft-deleted via `deleted_at`, upserted on re-install) — same shape a mailbox-to-practice-area binding would need.

**Profile manifests (B-7a):** `profiles/{commercial,privacy,blank}/profile.yaml` + `doctrine.md`, loaded at boot by `api/app/profiles/loader.py`. Schema `ProfileManifest`/`ProfileBindings` (`api/app/profiles/schema.py:44-90`): `bindings: {skills: [...], tool_groups: [...]}`, `agent_config: {subagents:[...]}`, `hitl: {tool: true}`, `area_key`, `unit_label`, `default_tier_floor`, `default_budget_profile`; applied via `POST /profiles/{name}/apply` (copy-not-link).

## 7. Web cockpit

Outer shell nav is minimal: `web/src/lib/lq-ai/cockpit/CockpitHeader.svelte` (logo + Settings) + practice-area rail `AreaRail.svelte`. The meaningful **tabs are matter-scoped**, declared in `ConversationHost.svelte:158-192`: `matterTab = $state<'conversation'|'register'|'memory'|'documents'|'grids'|'capabilities'>`, list built lines 185-192.

Run timeline + HITL: `web/src/lib/lq-ai/components/agents/ConversationPanel.svelte` (turn/step stream + budget dropdown) embeds `HitlConfirmCard.svelte`.

SSE consumption: `web/src/lib/lq-ai/sse/parser.ts` + `ui-message-stream.ts` → `web/src/lib/lq-ai/agents/run-stream.ts` (`parseStepPayload`, `parseRunPayload` line 183) → `ConversationPanel.svelte`.

**Grids tab (T7) precedent:** API `GET /tabular/matters/{project_id}/grids` (`api/app/api/tabular.py:403-410`, `response_model=list[TabularExecutionSummary]`); web `GridsPanel.svelte` rendered in `ConversationHost.svelte:691-701` when `matterTab==='grids'`, row-click opens dedicated `/tabular/[id]` route (`TabularWorkspace.svelte`) — the closest list+detail shape for an inbox-style approvals UI.

## 8. Scenario/live-test harness

`api/tests/agents/scenarios/*_live.py` gated by `pytestmark=[pytest.mark.provider, pytest.mark.skipif("LQ_AI_GATEWAY_KEY" not in os.environ, ...)]` — e.g. `test_commercial_deal_change_live.py:47-52`, `test_cuad_dataroom_fanout_live.py:32-34`, `test_tabular_grid_live.py:31-33`; CI-skipped, run manually with `DATABASE_URL`/`LQ_AI_GATEWAY_URL`/`LQ_AI_GATEWAY_KEY`/`LQ_AI_SCENARIO_MODEL`/`LQ_AI_SKILLS_DIR`.

Pattern (no HTTP): `harness.py` `seed_matter`/`seed_multi_doc_matter` (lines 66-194) insert `User`+`Project`+`File`+`Document`+`DocumentChunk` rows directly; the test then inserts `AgentThread`+`AgentRun` rows directly (`test_commercial_deal_change_live.py:80-96`) and calls `compose_and_execute_run(run_id=..., checkpointer_provider=lambda: None, skill_registry_provider=lambda: registry, broker=broker)` (104-110), draining an in-process `RunStreamBroker` for assertions/evidence (`UX_B1_EVIDENCE_DIR`).

## 9. Gateway

Purpose allowlist is a **hardcoded Python frozenset**, `_KNOWN_PURPOSES` (`gateway/app/api/inference.py:1344-1354`: `{"chat","judge_paraphrase","embedding","agent_loop","consolidate_matter_memory","adversarial_review"}`), applied in `_purpose_from_request()` (1357-1377) — any unrecognized `lq_ai_purpose` silently falls back to `"chat"`. This is **not** part of the hot-reloadable `gateway.yaml` (ADR-0010 covers only the model-alias map) — adding `"intake_triage"` needs a gateway source edit + rebuild/restart, no live-reload path.

Per-area model-tier floor: `PracticeArea.default_tier_floor` combined with `Project.minimum_inference_tier` via `combine_tier_floors()` (`api/app/agents/area_agent.py:226-232`, `min()` of present floors — lower = stronger), computed at `composition.py:1150-1152`, sent as `extra_body["lq_ai_project_minimum_inference_tier"]` (`api/app/agents/factory.py:66,90-91`) — the gateway enforces it when resolving the alias to a concrete model.

## 10. Network/deploy topology + gaps

`docker-compose.yml`: every host port defaults to `${..._BIND_ADDR:-127.0.0.1}` — api `260`, web `484` (`:8080`→3000), gateway `167`; collabora has **no host port** at all. No top-level `networks:` section — all services share Compose's single default bridge, so `api`/`arq-worker`/`ingest-worker` reach each other **and the public internet** via normal Docker NAT; nothing in dev restricts egress. `api` is **not** reachable from the public internet in dev (127.0.0.1 bind) — an AgentMail webhook would need a tunnel. Egress restriction exists only as an **opt-in prod overlay** (ADR-F070 "private profile", `docker-compose.private.yml`); default prod (ADR-F060) fronts `api`/`web` behind a public Caddy edge that 404s `/api/v1/internal*` and `/api/v1/wopi*` (`deploy/caddy/Caddyfile:93-108`) while proxying the rest of `/api/v1/*` to `api:8000` (line 121) — a new webhook route there would be publicly reachable in that topology.

### Gaps & risks for the intake milestone (facts, not designs)
- No email/AgentMail integration code anywhere in the repo — no inbound webhook route, no outbound client, no related env vars.
- No "candidate matter" concept — `projects` has no draft/pending/candidate status column; every matter is fully owned/created via `POST /projects`.
- No code inside `api/` verifies a third-party's own webhook signature — the two existing unauthenticated-router patterns are either self-minted-JWT (WOPI) or a **separate bridge microservice** doing the signature check before a shared-bearer call into `api`.
- `api` is not exposed to the public internet by default in dev — nothing in the repo sets up a tunnel.
- No packaged "ingest bytes without HTTP" function — upload logic is inlined in `files.py:upload_file`.
- No project-level auto-routing to a practice area — `practice_area_id` is always set by a human or the profile-apply flow.
- Gateway `_KNOWN_PURPOSES` has no hot-reload path (unlike the model-alias map).
- HITL v1 is LEAD-only, approve/reject-only, no per-matter policy override, no auto-expiry TTL, no `edit` decision.
- No table records "which mailbox/address maps to which practice area" — `slack_workspaces`/`teams_tenants` bind a whole tenant, not a per-address routing rule.
