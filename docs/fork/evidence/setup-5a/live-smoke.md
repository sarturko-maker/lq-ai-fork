# SETUP-5a — isolated live verification (2026-07-05)

The dev stack remains captive to the AIC migration chain (recorded trap), so live verification ran
ISOLATED (3a/3b/4a/4b precedent): throwaway `pgvector/pgvector:pg16` + `redis:7-alpine` + the branch
api (`lq-ai-api-dev` image, worktree `app/`+`alembic/` mounted read-only, full `alembic upgrade head`
from empty — proves the 0086→0087 chain from scratch, real uvicorn/HTTP). Run on the FINAL branch
(post-review-fix `1cf9109d`). Harness: session scratchpad `setup5a-smoke.sh` (extends the 4b harness);
log `setup5a-smoke-final.log`.

## API smoke (final branch): 33 passed / 0 failed

TWO api boots against one database, plus a one-shot boot-rejection probe — the only way to live-prove
all four tiers of the ADR-F063 resolution chain AND the `${VAR:-}` empty-string trap:

```
=== BOOT 1: RUN_DEFAULT_BUDGET_PROFILE="" (empty-string trap) ===
PASS: api boots with RUN_DEFAULT_BUDGET_PROFILE="" (""->None validator)
PASS: openapi /api/v1 path count still 171 (no new routes)
(+ 12-check SETUP-4b regression block re-passed: seed/inventory, create/attach/detach,
 read-model canonical order, PATCH name/unit_label, reorder + 422s)
=== 5a: default_budget_profile PATCH semantics ===
PASS: fresh area exposes default_budget_profile null
PASS: PATCH default=economy 200 + readback
PASS: invalid profile 422
PASS: PATCH name-only leaves default untouched
PASS: explicit null CLEARS default
=== 5a: resolution chain (boot 1: no deployment default) ===
PASS: tier-4 fallback: no explicit/area/deploy default -> balanced
PASS: tier-1 explicit generous wins
=== 5a: authz fence on the new field ===
PASS: member PATCH default_budget_profile 403
=== BOOT 2: RUN_DEFAULT_BUDGET_PROFILE=generous (deployment default) ===
PASS: api restart with deployment default
PASS: tier-3 deployment default: area null -> generous
PASS: PATCH commercial default=economy 200
PASS: tier-2 area default beats deployment: -> economy
PASS: at-create persistence: default cleared, run STILL economy
PASS: matterless run uses deployment default -> generous
=== BOOT-REJECTION probe: invalid RUN_DEFAULT_BUDGET_PROFILE ===
PASS: invalid deployment default rejected at boot (nonzero exit)
PASS: boot error names the offending setting
```

The "at-create persistence" check is the ADR's key property proven live: a run created while the
area default was `economy` keeps `economy` after the admin clears the default — a later default
change never silently re-prices an existing run.

## Browser pass (real UI against the isolated stack): Cypress 2/2

The web app served by the worktree's vite dev server (`PUBLIC_LQ_AI_API_BASE_URL` → the isolated
api, `LQ_AI_CORS_ORIGINS` set) and driven by a throwaway Cypress spec (login through the real login
page; spec deleted after the run — evidence only, not a committed test). Exercised end-to-end IN THE
BROWSER:

1. `/lq-ai/admin/areas/commercial` — "Default budget profile" select: pick Economy → Save → the
   PATCH body carries `"default_budget_profile":"economy"`, 200; survives reload; pick "Inherit
   deployment default" → Save → the PATCH body carries an EXPLICIT `"default_budget_profile":null`
   (the clears protocol), 200, cleared after reload → `setup5a-area-budget-economy.png`.
2. Composer — "Default" is the FIRST option and the initial selection; caption reads "Default — set
   by your area or deployment" → `setup5a-composer-default.png`. Picking Generous flips the caption
   to "Applies to this run — overrides the default" (the adversarial-review fix, proven live) →
   `setup5a-composer-explicit.png`.
3. With Default selected, a real run submitted: the POST `/agents/runs` body OMITS `budget_profile`
   entirely; the 202 response shows the api resolved it to `balanced` (area default cleared in step
   1, deployment default unset on this stack) → `setup5a-composer-run-default.png`.

No product defect was found by either pass on the final branch. (One harness bug was found and
fixed: the openapi count check must count `/api/v1` paths only, matching `test_openapi.py:292` —
the raw `paths` dict also carries `/health` + `/ready`.)
