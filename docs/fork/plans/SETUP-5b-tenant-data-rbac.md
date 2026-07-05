# SETUP-5b — tenant-data RBAC (ADR-F064)

Close the Q1 RBAC deferral from the ADR-F061 addendum: **D1** make `viewer` an enforced read-only
account; **D2** exclude the platform `operator` from the pre-F061 `is_admin` admin-sees-all bypasses
on tenant data. AUTH PATH — the lead runs an independent deep security review after.

- **ADRs:** ADR-F064 (this slice), closing ADR-F061 Q1; frames mode-neutrally under ADR-F058.
- **No migration. No new routes** (`/api/v1` path count stays **171**). No new dependency. Gateway
  untouched.

## Goals

- `viewer` cannot mutate ANY tenant data (server-enforced, 403 on the caller's own role).
- `operator` cannot see/act on OTHER users' matters/playbooks/tabular runs; org-admin keeps
  admin-sees-all (regression-protected).
- A drift guard fails CI if a future mutating route ships without a role gate.

## Non-goals

- Viewer UI affordance-hiding (buttons still render, 403 surfaced) → backlog.
- `UserRole` (web) widening — `PlatformRole` already covers operator; `UserRole` is the assignable
  set. Documented, not widened (deviation from §C literal).

(Two §A–D deferrals were OVERTURNED on lead review and fixed in §E: the legacy `/autonomous/*`
mutations are now MutatingUser-gated, and `chat_receipts.py`'s cross-user 403 bypass is now a
`tenant_admin_visibility` + 404 seam.)

## Files

- `api/app/api/dependencies.py` — `operator` added to `_MUTATING_ROLES`; docstring; new
  `tenant_admin_visibility(user)` helper (ADR-F064 D2 seam); §E: `get_autonomous_enabled_user`
  stacks on `MutatingUser` (defined after it, block reordered) so autonomous mutations enforce
  BOTH the viewer role gate and the opt-in flag with zero handler churn.
- 14 routers — `ActiveUser` → `MutatingUser` on the 52 mutating handlers (D1);
  §E: + `autonomous.py` `halt_session` (the one autonomous mutation without the opt-in gate).
- `api/app/api/tabular.py`, `api/app/api/playbooks.py` — 13 `is_admin` seams →
  `tenant_admin_visibility` (D2); §E: + `chat_receipts.py` (14th seam, also 403 → 404).
- `api/tests/test_mutation_rbac.py` — drift guard + viewer/member/operator/admin behaviour tests.
- `web/src/lib/lq-ai/types.ts` — clarifying comment on `UserRole` (assignable vs display).
- `docs/adr/F064-*.md`, this plan, `docs/fork/MILESTONES.md`.

## Route classification (all 124 mutating `/api/v1` route-entries; ground truth = `app.routes`)

`class` ∈ {**mutating** = swapped to `MutatingUser`; **admin** = already `AdminUser`; **operator** =
already `OperatorUser`; **allow** = justified exception, keeps its own gate}. Drift guard accepts
`get_mutating_user` | `get_admin_user` | `get_operator_user`, else the (method,path) must be in the
allowlist.

### mutating → MutatingUser (68; D1 swap — 52 direct + 16 autonomous via §E)

| Router | Routes |
|---|---|
| agent_runs | POST `/agents/runs`, POST `/agents/runs/{id}/cancel`, DELETE `/agents/threads/{id}` |
| chats | POST `/chats`, PATCH+DELETE `/chats/{id}`, POST `/chats/{id}/messages` |
| enhance_prompt | POST `/enhance-prompt`, PATCH `/enhance-prompt/{id}` |
| files | POST `/files`, DELETE `/files/{id}`, POST `/files/{id}/editor-session` |
| knowledge_bases | POST `/knowledge-bases`, PATCH+DELETE `/knowledge-bases/{id}`, POST `/knowledge-bases/{id}/files`, DELETE `/knowledge-bases/{id}/files/{fid}` |
| matter_capabilities | PATCH `/matters/{id}/capabilities` |
| matter_memory | POST corrections, POST corrections/{id}/retire, POST facts/{id}/retire, POST wiki/revert |
| matter_roster | POST `/matters/{id}/roster`, PATCH `/roster/{eid}`, POST `/roster/{eid}/retire` |
| playbooks | POST `/playbooks`, PATCH+DELETE `/playbooks/{id}`, POST `/playbooks/{id}/execute`, POST `/playbooks/easy` |
| projects | POST/PATCH/DELETE `/projects[/{id}]`, POST `/projects/sandbox/ensure`, POST+DELETE files/skills/knowledge-bases attach |
| saved_prompts | POST `/saved-prompts`, PATCH+DELETE `/saved-prompts/{id}` |
| skills | POST `/skills/{name}/fork` |
| tabular | POST `/tabular/execute`, DELETE `/executions/{id}`, POST `/executions/{id}/cancel`, POST+DELETE `/executions/{id}/cells/override` |
| user_skills | POST `/user-skills`, PATCH+DELETE `/user-skills/{id}` |
| autonomous (§E) | POST `/autonomous/sessions/{id}/halt` (MutatingUser direct); the 15 opt-in-gated mutations — memory keep/dismiss/DELETE ×3, precedents dismiss/promote ×2, proposals accept/reject ×2, schedules POST/PATCH/DELETE ×3, run-now, watches POST/PATCH/DELETE ×3, notifications read — via `get_autonomous_enabled_user(user: MutatingUser)` (both checks hold; viewer 403 fires first) |

Note: this is BROADER than the brief's illustrative §5 list (which named the obvious writes). D1 =
"viewer enforced read-only" + the drift guard require EVERY tenant-data write gated; the extra ~18
(KB CRUD, saved-prompts, user-skills, roster, skills/fork, enhance-prompt, sandbox/ensure) are the
same class and were swapped for completeness. The 16 autonomous mutations were initially allowlisted
as "frozen legacy" and OVERTURNED on lead review (§E): the swap is an API-edge authz bugfix, not an
executor extension.

### admin → AdminUser (26; leave)

`/admin/capabilities` PATCH; `/admin/intake-bridges/{slack,teams}/{id}` DELETE ×2; `/admin/teams…`
×6; `/admin/users/invites…` + `/disable` + `/enable` + `/{id}/role` ×6; `/organization-profile` PUT;
`/practice-areas…` (POST, reorder, PATCH/DELETE `{key}`, playbooks ×2, skills ×2, tool-groups ×2) ×10.

### operator → OperatorUser (8; leave — gateway-egress fence, ADR-F061 D4)

`/admin/aliases` (POST + PATCH/DELETE `{name}`) ×3; `/admin/provider-keys` (POST + PATCH/DELETE
`{provider}`) ×3; `/admin/tier-policy` PATCH; `/inference/override-tier-floor` POST.

### allow (22; justified exceptions, keep own gate)

| Group | Count | Reason |
|---|---|---|
| `/auth/*` | 11 | pre-auth or self-service on the caller's OWN identity (login/refresh/reset; logout/change-password/mfa/*/accept-invite). No tenant-data surface. |
| `/users/me/*` | 5 | self-service account mgmt + GDPR data-subject rights on the caller's OWN account (PATCH me, prefs, export, delete, delete/cancel). |
| POST-shaped reads | 2 | `POST /knowledge-bases/{id}/query` (retrieval), `POST /tabular/preview-cost` (cost estimate) — no persistent state change; a viewer legitimately reads. |
| `/wopi/*` | 2 | WOPI file-scoped signed `access_token`, re-validated + owner-scoped per request (ADR-F047); not the user bearer. |
| `/integrations/*` | 2 | service-to-service bridge, shared-secret bearer (`require_bridge_auth`); no user context. |

## D2 seams (14; `user.is_admin` → `tenant_admin_visibility(user)`)

- `tabular.py`: `_load_caller_owned_documents` (doc visibility for execute/preview), `list_tabular_executions`, `_load_caller_execution` (detail/cancel/delete/override load).
- `playbooks.py`: `list_playbooks` + every ownership check in update / delete / execute / execution-read / easy-file+project load / detail load (10).
- `chat_receipts.py` (§E): `get_chat_receipts` owner check (also serves the JSONL export) — recon §6
  gap fixed on lead review; the non-owner branch now raises `NotFound` (was `Forbidden` — an
  existence leak; cross-user = 404 is the codebase rule).

## Verification

Dev container (`lq-ai-api-dev`, `--network lq-ai_default`, `DATABASE_URL` from `lq-ai-api-1` by name,
worktree `api/app`+`api/tests`+`api/alembic` mounted):

- `tests/test_mutation_rbac.py` (drift guard: 68 gated / 171 paths / 124 mutating / allowlist minimal;
  viewer-403 + member-passes parametrized across routers incl. autonomous halt; operator cross-user
  404 + org-admin sees-all regression on tabular/playbooks/chat-receipts; autonomous role-gate +
  opt-in stacking; non-owner receipts 404-not-403).
- Regression: `test_tabular_endpoints`, `test_playbook_*`, `test_wave_c`, `test_chat_receipts`,
  `tests/autonomous/`, `test_endpoints`, `test_openapi` green.
- mypy (api standard) + repo-root ruff (format + check, line-length 100).
- Web: `npm run check` (types.ts comment only).
