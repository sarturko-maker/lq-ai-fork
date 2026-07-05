# SETUP-5b — isolated live verification (2026-07-05)

Isolated run (3a→5a precedent): throwaway `pgvector/pgvector:pg16` + `redis:7-alpine` + the branch
api (`lq-ai-api-dev`, worktree `app/`+`alembic/` ro-mounted, `alembic upgrade head` from empty, real
uvicorn/HTTP). Run on the FINAL branch (`67afc2ba`, post-security-review-fix). Single boot minting
BOTH first-run accounts (`FIRST_RUN_ADMIN_EMAIL` + `FIRST_RUN_OPERATOR_EMAIL`). Harness: session
scratchpad `setup5b-smoke.sh`; log `setup5b-smoke-final2.log`.

## The ADR-F064 role matrix, live: 30 passed / 0 failed

```
=== bootstrap: admin + operator minted, rotated, logged in ===
PASS: admin bootstrap+rotate+login
PASS: operator bootstrap+rotate+login
PASS: openapi /api/v1 path count still 171
=== accounts: member + viewer via invites ===
PASS: member invited+accepted+login
PASS: viewer invited+accepted+login
=== member seeds tenant data ===
PASS: member POST /projects 201
PASS: member POST /chats 201
PASS: member POST /playbooks 201
PASS: opted-OUT member autonomous mutation 403 via the OPT-IN gate
PASS: member opts into the Autonomous Layer (self-service allowlist) 200
PASS: opted-IN member passes BOTH gates -> 404 owner lookup
=== D1: viewer is read-only ===
PASS: viewer GET /projects 200
PASS: viewer GET /users/me 200
PASS: viewer POST /projects 403
PASS: viewer 403 body names the role requirement
PASS: viewer POST /chats 403
PASS: viewer POST /agents/runs 403
PASS: viewer PATCH member project 403 (role gate fires first)
PASS: viewer autonomous mutation 403 via the ROLE gate (fires before opt-in)
PASS: viewer self-service change-password still allowed 204
=== D2: operator excluded from cross-user tenant data ===
PASS: operator mutates rows it OWNS (in _MUTATING_ROLES) 201
PASS: operator PATCH member playbook 404 (never 403)
PASS: operator GET member chat receipts 404 (the 14th-seam fix, never 403)
PASS: operator playbook list EXCLUDES member's playbook
=== org-admin regression: still sees all tenant data ===
PASS: admin PATCH member playbook 200 (sees-all regression)
PASS: admin GET member chat receipts 200
PASS: admin playbook list INCLUDES member's playbook
=== fence regression (ADR-F061 unchanged) ===
PASS: admin GET /admin/config still fenced 403
PASS: operator GET /admin/config passes authz (not 403; 5xx = gateway absent, fine)
PASS: operator still passes AdminUser surfaces (GET /admin/users 200)
```

The load-bearing proofs:

- **D1 gate ordering, three layers live:** on the same legacy `/autonomous/*` mutation, a viewer
  gets 403 naming the read-only role rule (the MutatingUser gate fires FIRST), an opted-out member
  gets 403 naming the Autonomous Layer opt-in, and an opted-in member passes both gates through to
  the 404 owner lookup. Self-service stays open to viewers (change-password 204, preferences PATCH
  used for the opt-in) — read-only means tenant data, not their own account.
- **D2 without existence leaks:** the operator's cross-user probes return 404 (playbook PATCH,
  chat receipts — the receipts path previously 403'd after fetching the row), indistinguishable
  from missing; the org-admin's identical probes return 200 — sees-all preserved exactly.
- **F061 fence unchanged:** admin still 403 on `GET /admin/config`; operator passes it (5xx =
  gateway absent in the isolated stack, i.e. authz passed) and still passes AdminUser surfaces.

An earlier run (`setup5b-smoke-run1.log`, 27/28) failed one HARNESS expectation: the member's
autonomous probe expected 404 but correctly got the opt-in 403 (the member had not opted in). The
harness was upgraded to assert the full stacking order shown above — no product defect.

## Deep security review (auth path — 4 lenses + per-finding skeptic verification)

Fresh-context adversarial workflow: authz-matrix / bypass-hunt (Opus, high effort, attacking with
viewer + operator tokens across the WHOLE api surface incl. the 22 allowlist entries and residual
`is_admin` seams) / semantics-regression / hygiene lenses; every finding independently verified.

- **4 confirmed → all fixed in `67afc2ba` (§F):** (1) should-fix — the WOPI write path authorized
  on token claims alone, so a member demoted to viewer mid-editing-session kept write access to
  their OWN file until the (10h-default) WOPI token expired; fixed with a per-write-op role +
  liveness re-check (`_require_live_mutating_user`, importing `_MUTATING_ROLES` from the bearer
  gate so the two can never drift; 401-as-session-invalid; reads deliberately stay open) — proven
  by 3 new tests (demote-mid-session PUT 401 / GetFile still 200 / disabled-account PUT 401).
  (2)+(3) the D2 seam docstrings still said "admins see all" (6 sites) and (4) the viewer-gate 403
  message omitted the newly-mutating operator role — both prose-truth fixes, no behavior.
- **3 refuted on record:** the allowlisted KB-query audit row is an owner-scoped audit write, not a
  tenant-data mutation; the loose pre-existing chat-receipts test is byte-identical to main
  (untouched by this slice); the route-walk introspection duplication across guard tests is a
  consolidation refactor out of slice scope.
