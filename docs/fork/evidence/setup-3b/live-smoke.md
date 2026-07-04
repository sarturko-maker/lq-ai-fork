# SETUP-3b — isolated live smoke (2026-07-04)

The dev stack is captive to the AIC migration chain (recorded trap: its DB head is an AIC-branch
revision the main chain can't resolve), so live verification ran ISOLATED, mirroring the SETUP-3a
precedent: throwaway `pgvector/pgvector:pg16` + `redis:7-alpine` + the branch api
(`lq-ai-api-dev` image, worktree `app/`+`alembic/` mounted, full `alembic upgrade head` from empty,
real uvicorn, real HTTP). No SMTP configured (the weekend bring-up posture). UI-in-browser
verification is deferred to the staging bring-up / post-AIC dev stack (bundle build proof below).

Harness: session scratchpad `setup3b-smoke.sh`; log `setup3b-smoke.log`.

## Result: 27 passed / 2 environmental (see interpretation)

```
=== PHASE 1: FIRST_RUN_OPERATOR_EMAIL set to EMPTY STRING (prod-compose ${VAR:-} case) ===
PASS: bootstrap-status 200
PASS: hosted=False on empty-string operator email (review fix F1, live)
PASS: default_password_active=True on fresh install
PASS: scraped bootstrap admin password from log
PASS: admin change-password 204
PASS: admin re-login after rotate
PASS: invite create 201
PASS: invite email_sent=False (SMTP off)
PASS: accept_url has base + real /lq-ai/accept-invite path (D1)
PASS: accept-invite 201
PASS: accepted role=member
PASS: invited member logs in
PASS: token single-use: replay 400
PASS: invites list shows accepted
PASS: users list finds member
PASS: role member->admin 200, is_admin synced
PASS: role back to member
PASS: role=operator refused 422 (D3 escalation guard)
PASS: disable 200
PASS: disabled member login 401
PASS: enable 200
PASS: re-enabled member logs in
PASS: role=operator filter rejected 400
PASS: reset-request uniform 202 + identical body (anti-enum)
PASS: reset-confirm 204
PASS: old password dead after reset
PASS: reset password logs in
PASS: org-admin GET /admin/config fenced 403
FAIL: org-admin GET /admin/tier-policy still readable 200 (got=[503] want=[200])

=== PHASE 2: FIRST_RUN_OPERATOR_EMAIL=operator@lqsmoke.net (hosted tenant stack) ===
PASS: hosted=True with operator email (D8)
PASS: operator minted + password logged once
PASS: operator change-password 204
FAIL: operator GET /admin/config 200 (got=[503] want=[200])
PASS: operator row VISIBLE in users list (D6)
PASS: org-admin cannot touch operator row 403
PASS: org-admin cannot disable operator 403

=== RESULT: 27 passed / 2 failed ===
```

## Interpretation of the two 503s (environmental, and themselves conclusive)

Both endpoints PROXY to the Inference Gateway, which does not exist in the isolated network. The
503 ("gateway unreachable") fires only AFTER the authorization dependency has passed — so the
pair of outcomes proves the fence layering end-to-end:

- org-admin `GET /admin/config` → **403** (OperatorUser fence fired BEFORE any proxying — the
  fence, not the missing gateway, rejected it);
- operator `GET /admin/config` → **503** (fence PASSED; only the absent gateway failed);
- org-admin `GET /admin/tier-policy` → **503** (AdminUser passed — proving this route is NOT
  operator-fenced, per D4's transparency carve-out; a fence would have 403'd).

## Web bundle build proof

CI's Web job runs svelte-check + vitest but not the Vite build, so the bundle was built from the
branch explicitly: `npm run build` → adapter-static "Wrote site to build" — exit 0
(`setup3b-web-build.log`). New routes (`/lq-ai/admin/users`, `/lq-ai/accept-invite`,
`/lq-ai/reset-password`) compile into the SPA bundle.

## What this proves live (beyond the 3198-test suite)

- The full invited-user lifecycle against a real server + real Postgres from an empty DB:
  invite → accept at the REAL `/lq-ai/accept-invite` path (D1) → login → role change (+ is_admin
  sync) → disable (401) → enable → reset-request (uniform 202, identical bodies for
  existing/unknown email) → reset-confirm → old password dead.
- Review fix F1 in the exact prod-compose failure mode: `FIRST_RUN_OPERATOR_EMAIL` injected as an
  EMPTY STRING (`${VAR:-}`) reads as `hosted=false`; a real address reads `hosted=true` (D8).
- D3 escalation guard: `role=operator` refused (422) on the role endpoint; operator rows
  untouchable (403 on role change and disable) yet VISIBLE in the list (D6).
- Token single-use under replay (second accept → uniform 400).
