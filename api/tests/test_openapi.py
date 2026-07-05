"""OpenAPI surface tests.

The OpenAPI sketch at `docs/api/backend-openapi.yaml` is the contract.
Task A4 registers every path from the sketch as a 501-returning stub so
the OpenAPI document FastAPI generates matches the contract from day
one. This test pins that match.

When the sketch is updated, this test should be updated in the same PR.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

EXPECTED_PATHS: frozenset[str] = frozenset(
    {
        # auth
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/refresh",
        "/api/v1/auth/mfa/setup",
        "/api/v1/auth/mfa/verify",
        # D5 — MFA enrollment + verification
        "/api/v1/auth/mfa/enable",
        "/api/v1/auth/mfa/disable",
        "/api/v1/auth/change-password",  # B2
        # users
        "/api/v1/users/me",
        "/api/v1/users/me/export",
        # D6 — status-poll for queued export jobs (extends the sketch).
        "/api/v1/users/me/export/{job_id}",
        "/api/v1/users/me/delete",
        # D6 — cancel a pending account deletion (extends the sketch).
        "/api/v1/users/me/delete/cancel",
        # projects
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/skills",
        # C7 — detach skill by name (extends the sketch).
        "/api/v1/projects/{project_id}/skills/{skill_name}",
        "/api/v1/projects/{project_id}/files",
        # C7 — detach file by id (extends the sketch).
        "/api/v1/projects/{project_id}/files/{file_id}",
        # Wave D.1 T3 — matter <-> KB attach/detach (extends the sketch).
        "/api/v1/projects/{project_id}/knowledge-bases",
        "/api/v1/projects/{project_id}/knowledge-bases/{kb_id}",
        # chats + messages
        "/api/v1/chats",
        "/api/v1/chats/{chat_id}",
        "/api/v1/chats/{chat_id}/messages",
        "/api/v1/chats/{chat_id}/messages/{message_id}/citations",
        # skills
        "/api/v1/skills",
        "/api/v1/skills/{skill_name}",
        "/api/v1/skills/{skill_name}/fork",
        # internal (gateway → backend, ADR 0006 / C2)
        "/api/v1/internal/skills/{skill_name}",
        # D4-coverage — gateway-facing Organization Profile fetch
        "/api/v1/internal/organization-profile",
        # files
        "/api/v1/files",
        "/api/v1/files/{file_id}",
        "/api/v1/files/{file_id}/content",
        # knowledge bases (C6)
        "/api/v1/knowledge-bases",
        "/api/v1/knowledge-bases/{kb_id}",
        "/api/v1/knowledge-bases/{kb_id}/files",
        "/api/v1/knowledge-bases/{kb_id}/files/{file_id}",
        "/api/v1/knowledge-bases/{kb_id}/query",
        # organization profile
        "/api/v1/organization-profile",
        # D4 — convenience text/markdown endpoint (extends the sketch).
        "/api/v1/organization-profile/raw",
        # C3a (fork) — matter-memory: the human-authenticated pin endpoint (ADR-F042).
        "/api/v1/matters/{project_id}/memory/corrections",
        # C3c-1 (fork) — matter-memory read surface + wiki revert (ADR-F044).
        "/api/v1/matters/{project_id}/memory",
        "/api/v1/matters/{project_id}/memory/wiki/revert",
        # C3-UM (fork) — matter-memory human retire gestures (ADR-F042 / F044 §4B).
        "/api/v1/matters/{project_id}/memory/corrections/{entry_id}/retire",
        "/api/v1/matters/{project_id}/memory/facts/{entry_id}/retire",
        # ADR-F048 (fork) — authorship roster human-amend surface (add/edit/remove).
        "/api/v1/matters/{project_id}/roster",
        "/api/v1/matters/{project_id}/roster/{entry_id}",
        "/api/v1/matters/{project_id}/roster/{entry_id}/retire",
        # C7a (fork) — matter-files read surface (redline-download, ADR-F046).
        "/api/v1/matters/{project_id}/files",
        # ADR-F054 (fork) — per-matter capability panel (toggles).
        "/api/v1/matters/{project_id}/capabilities",
        # saved prompts
        "/api/v1/saved-prompts",
        "/api/v1/saved-prompts/{prompt_id}",
        # user skills (D8 — DB-backed user-scope skills per ADR 0012)
        "/api/v1/user-skills",
        "/api/v1/user-skills/{skill_id}",
        # Wave D.2 — version audit feed + slash_alias autocomplete
        "/api/v1/user-skills/{skill_id}/versions",
        "/api/v1/skills/autocomplete",
        # Wave D.2 Task 2.2 — sandbox matter find-or-create
        "/api/v1/projects/sandbox/ensure",
        # teams (D8.1a — admin CRUD + user-facing read)
        "/api/v1/teams",
        "/api/v1/teams/{team_id}",
        "/api/v1/admin/teams",
        "/api/v1/admin/teams/{team_id}",
        "/api/v1/admin/teams/{team_id}/members",
        "/api/v1/admin/teams/{team_id}/members/{user_id}",
        # Wave A — skill inspection (PRD §3.4) + Enhance Prompt (PRD §3.2)
        "/api/v1/skills/{skill_name}/contents",
        "/api/v1/skills/{skill_name}/inputs",
        "/api/v1/enhance-prompt",
        "/api/v1/enhance-prompt/{interaction_id}",
        # Wave A — user preferences (reasoning_visibility per PRD §3.2)
        "/api/v1/users/me/preferences",
        # Wave B — tier inquiry (PRD §3.13) + cost dashboard (PRD §5.5) + chat search (PRD §1.7)
        "/api/v1/inference/current-tier",
        "/api/v1/inference/tier-config",
        "/api/v1/admin/usage",
        "/api/v1/chats/search",
        # Wave C — RBAC role updates (PRD §5.2)
        "/api/v1/admin/users/{user_id}/role",
        # Wave B v2 — admin user list for DevRoleManagementCard
        "/api/v1/admin/users",
        # SETUP-3a (ADR-F061) — invite lifecycle + admin disable/enable
        "/api/v1/admin/users/invites",
        "/api/v1/admin/users/invites/{invite_id}/resend",
        "/api/v1/admin/users/invites/{invite_id}",
        "/api/v1/admin/users/{user_id}/disable",
        "/api/v1/admin/users/{user_id}/enable",
        # SETUP-4a (ADR-F062) — deployment-wide (Level 0) capability toggles
        "/api/v1/admin/capabilities",
        # SETUP-3a (ADR-F061) — unauthenticated lifecycle endpoints
        "/api/v1/auth/accept-invite",
        "/api/v1/auth/password-reset-request",
        "/api/v1/auth/password-reset",
        # admin
        "/api/v1/admin/audit-log",
        "/api/v1/admin/tier-policy",
        # M3-0.1 / DE-283 — unauthenticated fresh-install state probe
        "/api/v1/admin/bootstrap-status",
        # M3-0.3 / DE-276 — admin ingest-health aggregate
        "/api/v1/admin/ingest-health",
        # M3-B1 — Word add-in manifest generation (admin-only sideload helper)
        "/api/v1/admin/word-addin/manifest",
        # M3-B8 — Word add-in version handshake (unauthenticated)
        "/api/v1/word-addin/version",
        # libreoffice-editor Slice 2 (fork, ADR-F047) — WOPI host + editor-session mint.
        # CheckFileInfo (GET) + Lock family (POST) share one path; GetFile is /contents.
        "/api/v1/wopi/files/{file_id}",
        "/api/v1/wopi/files/{file_id}/contents",
        "/api/v1/files/{file_id}/editor-session",
        # M3-A2 — Playbook executor surface
        "/api/v1/playbooks/{playbook_id}/execute",
        "/api/v1/playbook-executions/{execution_id}",
        # M3-A4 — Playbook list + detail
        "/api/v1/playbooks",
        "/api/v1/playbooks/{playbook_id}",
        # M3-A6 — Easy Playbook wizard endpoints (Phase 5)
        "/api/v1/playbooks/easy",
        "/api/v1/playbooks/easy/{generation_id}",
        # D0.5 — model alias admin
        "/api/v1/admin/config",
        "/api/v1/admin/aliases",
        "/api/v1/admin/aliases/{name}",
        # Donna #7 — runtime provider-key (BYOK) admin proxy
        "/api/v1/admin/provider-keys",
        "/api/v1/admin/provider-keys/{provider}",
        # D0 — model availability proxy
        "/api/v1/models",
        # Wave D.1 T4 — admin tier-floor override re-run
        "/api/v1/inference/override-tier-floor",
        # Wave D.1 T5 — chat receipts (replay-at-read event log)
        "/api/v1/chats/{chat_id}/receipts",
        # Wave D.1 T6 — chat receipts JSONL export
        "/api/v1/chats/{chat_id}/receipts/export.jsonl",
        # M3-C2 — Tabular / Multi-Document Review surface
        "/api/v1/tabular/preview-cost",
        "/api/v1/tabular/execute",
        "/api/v1/tabular/executions",
        "/api/v1/tabular/matters/{project_id}/grids",
        "/api/v1/tabular/executions/{execution_id}",
        "/api/v1/tabular/executions/{execution_id}/cancel",
        # F2 Tabular T6 (ADR-F055 T6 / ADR-F042) — lawyer cell override
        # (POST set + DELETE clear share this one path).
        "/api/v1/tabular/executions/{execution_id}/cells/override",
        # M3-C4a — XLSX/CSV export.
        "/api/v1/tabular/executions/{execution_id}/export",
        # M3-D1 — slack-bridge persistence surface (bearer-token, no user)
        "/api/v1/integrations/slack/workspaces",
        # M3-D3 — teams-bridge persistence surface (bearer-token, no user)
        "/api/v1/integrations/teams/tenants",
        # M3-D4 — admin intake-bridges surface (admin-only)
        "/api/v1/admin/intake-bridges",
        "/api/v1/admin/intake-bridges/slack/{workspace_id}",
        "/api/v1/admin/intake-bridges/teams/{tenant_id}",
        # M4-A4-i — Autonomous sessions read/halt API (per-user)
        "/api/v1/autonomous/sessions",
        "/api/v1/autonomous/sessions/{session_id}",
        "/api/v1/autonomous/sessions/{session_id}/halt",
        # Findings read-model — a run's persisted findings (work-product)
        "/api/v1/autonomous/sessions/{session_id}/findings",
        # Artifacts read-model — a run's document-grade artifact refs (Donna #8)
        "/api/v1/autonomous/sessions/{session_id}/artifacts",
        # M4-B1 — per-user memory curation API (list, keep, dismiss, delete)
        "/api/v1/autonomous/memory",
        "/api/v1/autonomous/memory/{memory_id}/keep",
        "/api/v1/autonomous/memory/{memory_id}/dismiss",
        "/api/v1/autonomous/memory/{memory_id}",
        # M4-B2 — precedent board + promote-to-Project proposal lifecycle
        "/api/v1/autonomous/precedents",
        "/api/v1/autonomous/precedents/{precedent_id}/dismiss",
        "/api/v1/autonomous/precedents/{precedent_id}/promote",
        "/api/v1/autonomous/project-context-proposals",
        "/api/v1/autonomous/project-context-proposals/{proposal_id}/accept",
        "/api/v1/autonomous/project-context-proposals/{proposal_id}/reject",
        # M4-B3 — scheduled autonomous tasks (create/list/patch/delete)
        "/api/v1/autonomous/schedules",
        "/api/v1/autonomous/schedules/{schedule_id}",
        # M4-B4 — KB-arrival watches (create/list/patch/delete)
        "/api/v1/autonomous/watches",
        "/api/v1/autonomous/watches/{watch_id}",
        # M4-C1 — notification read/dismiss API (list + mark-read)
        "/api/v1/autonomous/notifications",
        "/api/v1/autonomous/notifications/{notification_id}/read",
        # Phase 1 §4.4 — one-off manual session spawn (run a skill/playbook now)
        "/api/v1/autonomous/run-now",
        # F0-S2 (fork) — agent-run records (kick-off + polled run/steps reads)
        "/api/v1/agents/runs",
        "/api/v1/agents/runs/{run_id}",
        # F0-S5 (fork) — conversations (ADR-F008): list + polled detail
        "/api/v1/agents/threads",
        "/api/v1/agents/threads/{thread_id}",
        # F0-S7 (fork) — SSE v2 run stream (ADR-F006 wire spec)
        "/api/v1/agents/runs/{run_id}/stream",
        # F1-S1 (fork) — run cancel (settle-first, ADR-F009)
        "/api/v1/agents/runs/{run_id}/cancel",
        # F1-S2 (fork) — cockpit reads (ADR-F002): practice areas + matters rollup
        "/api/v1/practice-areas",
        "/api/v1/agents/matters",
        # F1-S3 (fork) — practice-area config/admin (ADR-F002/F004/F010)
        "/api/v1/practice-areas/{key}",
        "/api/v1/practice-areas/{key}/skills",
        "/api/v1/practice-areas/{key}/skills/{skill_name}",
        # SETUP-4a (fork, ADR-F062) — practice-area tool-group attach/detach
        "/api/v1/practice-areas/{key}/tool-groups",
        "/api/v1/practice-areas/{key}/tool-groups/{group_key}",
        # ADR-F054 (fork) — admin playbook attach/detach (capability availability)
        "/api/v1/practice-areas/{key}/playbooks",
        "/api/v1/practice-areas/{key}/playbooks/{playbook_id}",
        # SETUP-4b (fork, ADR-F062 addendum) — bulk reposition
        "/api/v1/practice-areas/reorder",
        # PRIV-3 (fork) — ROPA register read API (ADR-F019)
        "/api/v1/ropa/processing-activities",
        "/api/v1/ropa/processing-activities/{activity_id}",
        "/api/v1/ropa/systems",
        "/api/v1/ropa/systems/{system_id}",
        # PRIV-5a (fork) — vendors/recipients
        "/api/v1/ropa/vendors",
        "/api/v1/ropa/vendors/{vendor_id}",
        # PRIV-6a (fork) — Article 30(1)(c) personal-data taxonomy
        "/api/v1/ropa/data-subject-categories",
        "/api/v1/ropa/data-categories",
        # PRIV-6b (fork) — privacy programme summary
        "/api/v1/ropa/programme-summary",
        # PRIV-6c (fork) — data-flow / lineage graph
        "/api/v1/ropa/data-flow",
        # PRIV-4a (fork) — Article 30 export
        "/api/v1/ropa/export",
        # PRIV-A3 (fork) — assessment register read API (ADR-F027)
        "/api/v1/ropa/assessments",
        "/api/v1/ropa/assessments/{assessment_id}",
    }
)


@pytest.mark.unit
async def test_openapi_paths_match_sketch() -> None:
    """All paths from `backend-openapi.yaml` are registered.

    Counts: 30 from A4 + 1 from B2 (change-password) + 2 from C7
    (project file/skill detach by id) = 33 total.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    actual = {p for p in spec["paths"] if p.startswith("/api/v1")}
    assert actual == EXPECTED_PATHS, (
        f"OpenAPI surface drift. Missing: {EXPECTED_PATHS - actual}, "
        f"Extra: {actual - EXPECTED_PATHS}"
    )
    # 67 distinct /api/v1 paths: D0's /api/v1/models + D0.5's three admin
    # alias endpoints + D5's two new MFA endpoints + D6's two new GDPR
    # endpoints (status-poll for /users/me/export/{job_id} and
    # /users/me/delete/cancel) + D4's /organization-profile/raw
    # convenience endpoint + D4-coverage's
    # /internal/organization-profile + D8's two /api/v1/user-skills
    # paths + D8.1a's six teams paths + Wave A's five paths +
    # Wave B's four paths + Wave C's /admin/users/{user_id}/role +
    # Wave B v2's /admin/users + Wave D.1's two matter <-> KB attach/detach paths
    # + Wave D.1 T4's /inference/override-tier-floor
    # + Wave D.2's three paths: /user-skills/{id}/versions,
    # /skills/autocomplete, /projects/sandbox/ensure.
    # + M3-0.1's /admin/bootstrap-status.
    # + M3-0.3's /admin/ingest-health.
    # + M3-A2's two playbook-executor endpoints.
    # + M3-A4's two playbook list/detail endpoints.
    # + M3-A6's Playbook CRUD adds POST/PATCH/DELETE methods on /playbooks +
    #   /playbooks/{id} — paths already counted from M3-A4's GET endpoints, so
    #   they contribute 0 new entries to this path-count assertion (the
    #   method-tuple assertion in test_endpoints.py is the load-bearing check
    #   for those).
    # + M3-A6's two NEW paths for the Easy Playbook wizard
    #   (POST /playbooks/easy + GET /playbooks/easy/{id}).
    # + M3-B1's /admin/word-addin/manifest.
    # + M3-B8's /word-addin/version.
    # + M3-C2's five NEW paths for the Tabular surface
    #   (/tabular/preview-cost, /tabular/execute, /tabular/executions,
    #    /tabular/executions/{id}, /tabular/executions/{id}/cancel).
    #   DELETE on /executions/{id} shares the GET path so it adds zero
    #   new paths here; the method-tuple count is in test_endpoints.py.
    # + M3-C4a's /tabular/executions/{id}/export.
    # + M3-D1's one NEW path for the slack-bridge persistence surface
    #   (POST /integrations/slack/workspaces). One method-tuple here;
    #   the bridge is the sole caller so additional verbs aren't needed
    #   in M3-D1 (uninstall comes in M3-D4 admin UI work).
    # + M3-D3's one NEW path for the teams-bridge persistence surface
    #   (POST /integrations/teams/tenants). Same posture as M3-D1's
    #   slack equivalent.
    # + M3-D4's three NEW paths for the admin intake-bridges surface
    #   (GET /admin/intake-bridges, DELETE /admin/intake-bridges/slack/{id},
    #   DELETE /admin/intake-bridges/teams/{id}). Admin-only.
    # M4-A4-i adds three new paths:
    # /api/v1/autonomous/sessions
    # /api/v1/autonomous/sessions/{session_id}
    # /api/v1/autonomous/sessions/{session_id}/halt
    # M4-B1 adds four new paths:
    # /api/v1/autonomous/memory
    # /api/v1/autonomous/memory/{memory_id}/keep
    # /api/v1/autonomous/memory/{memory_id}/dismiss
    # /api/v1/autonomous/memory/{memory_id}
    # M4-B2 adds six new paths:
    # /api/v1/autonomous/precedents
    # /api/v1/autonomous/precedents/{precedent_id}/dismiss
    # /api/v1/autonomous/precedents/{precedent_id}/promote
    # /api/v1/autonomous/project-context-proposals
    # /api/v1/autonomous/project-context-proposals/{proposal_id}/accept
    # /api/v1/autonomous/project-context-proposals/{proposal_id}/reject
    # M4-B3 adds two new paths:
    # /api/v1/autonomous/schedules
    # /api/v1/autonomous/schedules/{schedule_id}
    # M4-B4 adds two new paths:
    # /api/v1/autonomous/watches
    # /api/v1/autonomous/watches/{watch_id}
    # M4-C1 adds two new paths:
    # /api/v1/autonomous/notifications
    # /api/v1/autonomous/notifications/{notification_id}/read
    # Phase 1 §4.4 adds one new path:
    # /api/v1/autonomous/run-now
    # Donna #7 adds two new paths:
    # /api/v1/admin/provider-keys
    # /api/v1/admin/provider-keys/{provider}
    # Findings read-model adds one new path:
    # /api/v1/autonomous/sessions/{session_id}/findings
    # Artifacts read-model (Donna #8) adds one new path:
    # /api/v1/autonomous/sessions/{session_id}/artifacts
    # F0-S2 (fork) adds two new paths:
    # /api/v1/agents/runs (POST kick-off + GET list)
    # /api/v1/agents/runs/{run_id}
    # F0-S5 (fork) adds two new paths (ADR-F008):
    # /api/v1/agents/threads
    # /api/v1/agents/threads/{thread_id}
    # F0-S7 (fork) adds one new path (ADR-F006 SSE v2):
    # /api/v1/agents/runs/{run_id}/stream
    # +1: F2 Tabular T7 (ADR-F055) — GET /tabular/matters/{project_id}/grids.
    # +1: F2 Tabular T6 (ADR-F055 T6 / ADR-F042) — /tabular/executions/{id}/cells/override
    #   (POST set + DELETE clear share one path → +1 path, +0 count beyond it).
    # +8: SETUP-3a (ADR-F061) — invite lifecycle (create/list share one path;
    #   resend; revoke; = 3) + disable + enable (2) + accept-invite +
    #   password-reset-request + password-reset (3) = 8 new paths.
    # +3: SETUP-4a (ADR-F062) — practice-area tool-group attach/detach
    #   (/practice-areas/{key}/tool-groups + .../{group_key} = 2; POST /practice-areas
    #   and DELETE /practice-areas/{key} reuse existing paths → +0 here) + deployment
    #   capability toggles (GET/PATCH /admin/capabilities = 1 path).
    # +1: SETUP-4b (ADR-F062 addendum) — admin Areas + Capabilities UI backend:
    #   POST /practice-areas/reorder (bulk reposition). (A GET /admin/model-menu
    #   was added then DELETED in the same slice's review — the alias+tier pair is
    #   already member-visible via GET /api/v1/models; the admin UI derives it
    #   client-side.)
    assert len(actual) == 171  # +3: ADR-F054 capability panel (GET/PUT
    #   /matters/{project_id}/capabilities counts as 1 path; admin playbook
    #   attach/detach /practice-areas/{key}/playbooks + .../{playbook_id} = 2).
    # +3 prior: ADR-F048 authorship roster (POST /roster, PATCH
    #   /roster/{entry_id}, POST /roster/{entry_id}/retire).
    # +3 prior: libreoffice-editor Slice 2 WOPI host + mint (ADR-F047)
    #   — /wopi/files/{id} (CheckFileInfo GET + Lock POST share the path),
    #     /wopi/files/{id}/contents (GetFile), /files/{id}/editor-session (mint).
    # +1 prior: C7a matter-files read surface (redline-download, ADR-F046);
    # +2 prior: C3-UM matter-memory retire gestures (corrections + facts, ADR-F042/F044);
    # +2 prior: C3c-1 matter-memory read surface + wiki revert (ADR-F044); +1 prior: C3a
    # matter-memory pin endpoint (ADR-F042); +2 prior: PRIV-A3 assessment
    # register reads (list + detail, ADR-F027); +1 prior: PRIV-6c data-flow graph
    # (ADR-F022); +1 prior: PRIV-6b programme summary


@pytest.mark.unit
async def test_openapi_includes_health_and_ready() -> None:
    """Liveness and readiness are also documented in the spec."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    spec = response.json()
    assert "/health" in spec["paths"]
    assert "/ready" in spec["paths"]


@pytest.mark.unit
async def test_openapi_version_is_3_1() -> None:
    """We declare OpenAPI 3.1 — FastAPI emits this by default on recent versions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
    spec = response.json()
    # FastAPI >= 0.99 emits OpenAPI 3.1.x by default.
    assert spec["openapi"].startswith("3.1.")
