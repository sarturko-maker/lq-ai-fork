# SETUP-4a — isolated live smoke (2026-07-04)

The dev stack is still captive to the AIC migration chain (recorded trap), so live verification
ran ISOLATED (3a/3b precedent): throwaway `pgvector/pgvector:pg16` + `redis:7-alpine` + the branch
api (`lq-ai-api-dev` image, worktree `app/`+`alembic/` mounted read-only, full
`alembic upgrade head` from empty — migration 0086 exercised for real — real uvicorn, real HTTP).
Run TWICE: against the pre-review-fix stack and re-run in full against the final fixed branch
(`e4355dd0`). Harness: session scratchpad `setup4a-smoke.sh`; log `setup4a-smoke-final.log`.

## Result (final branch): 21 passed / 0 failed

```
PASS: admin bootstrap + rotate + login
=== seed + inventory ===
PASS: GET /practice-areas 200, 5 seeded areas
PASS: deployment inventory: 4 registry groups, all Level-0 enabled
=== create area (D8) ===
PASS: POST /practice-areas 201
PASS: duplicate key 409
PASS: bad slug 422
PASS: unknown tool_group on create 404
=== attach/detach (D10) ===
PASS: attach tabular 204
PASS: duplicate attach 409
PASS: unknown group attach 404
PASS: detach 204
PASS: idempotent detach 204
=== Level-0 threading (D6/D7) ===
PASS: matter panel shows redlining pre-disable
PASS: Level-0 disable redlining 200
PASS: matter panel LACKS redlining post-disable (Level 0 narrows)
PASS: re-enable restores redlining
PASS: unknown key rejected 422
=== delete semantics (D9) ===
PASS: DELETE refused with live matter 409
PASS: DELETE succeeds once matter archived 204
PASS: procurement gone from list
=== authz fence ===
PASS: member POST /practice-areas 403
PASS: member PATCH /admin/capabilities 403
=== RESULT: 21 passed / 0 failed ===
```

## What this proves live (beyond the 3251-test suite)

- Migration 0086 migrates a REAL empty database to head and the names-only seed lands
  (commercial→{redlining,tabular}, privacy→{ropa,assessment} visible in the deployment inventory).
- The full admin-created-area lifecycle against a real server: create (with a registry-validated
  `tool_groups` list) → attach/detach round-trip with the exact 404/409/idempotency contract →
  delete refused (409) while a live matter is filed under the area, succeeding (204) once the
  matter is archived — the D9 data-protection semantics, end to end.
- **Level-0 narrowing through the one chokepoint (D6):** deployment-disabling `redlining` makes it
  vanish from a commercial MATTER's capability panel (the same inventory composition consumes);
  re-enabling restores it. Unknown keys are rejected 422 at the PATCH boundary.
- The authz fence: a freshly-invited member (created through the 3a invite flow, itself
  re-exercised here) gets 403 on both new admin surfaces.
- Boundary rejections: bad slug 422, duplicate key 409, unknown tool group 404 — reject, never
  sanitize.

Two earlier harness-side defects (SQLAlchemy expire-on-commit ID capture; wrong response field
name in the panel check) were fixed in the harness — no product defect was found by the smoke in
either run.
