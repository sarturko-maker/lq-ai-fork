# SETUP-4b — isolated live verification (2026-07-05)

The dev stack remains captive to the AIC migration chain (recorded trap), so live verification ran
ISOLATED (3a/3b/4a precedent): throwaway `pgvector/pgvector:pg16` + `redis:7-alpine` + the branch
api (`lq-ai-api-dev` image, worktree `app/`+`alembic/` mounted read-only, full `alembic upgrade head`
from empty, real uvicorn/HTTP). Run on the FINAL branch (post-review-fix `807e27e2`). Harness:
session scratchpad `setup4b-smoke.sh` (extends the 4a harness); log `setup4b-smoke-final.log`.

## API smoke (final branch): 32 passed / 0 failed

All 21 SETUP-4a checks re-passed as regression (create/attach/detach/Level-0-narrows-matter-panel/
delete-semantics/authz), plus the 11 new 4b checks:

```
=== 4b read-model (D2) ===
PASS: commercial bound_tool_groups canonical + bound_playbooks list
PASS: create with REVERSED group order 201
PASS: read-back is REGISTRY-canonical order (D4/F062)
=== 4b PATCH name/unit_label (D3) ===
PASS: PATCH name+unit_label 200, configured untouched
PASS: empty name rejected 422
=== 4b reorder (D4) ===
PASS: reorder 200 + response reflects new order
PASS: reorder persisted on re-read
PASS: subset reorder 422
PASS: duplicate-key reorder 422
PASS: unknown-key reorder 422
=== authz fence ===
PASS: member POST /practice-areas 403
PASS: member PATCH /admin/capabilities 403
PASS: member reorder 403
```

## Browser pass (real UI against the isolated stack): Cypress 1/1

The web app served by the worktree's vite dev server (`PUBLIC_LQ_AI_API_BASE_URL` →
the isolated api, `LQ_AI_CORS_ORIGINS` set) and driven by a throwaway Cypress spec (login through
the real login page; spec deleted after the run — evidence only, not a committed test). Exercised
end-to-end IN THE BROWSER:

1. `/lq-ai/admin/areas` — table renders the 5 seeded areas in position order with status badges
   and bound counts → `setup4b-areas-list.png`.
2. Create modal — key/name/unit-label + a registry tool-group checkbox → 201 → auto-navigates to
   the new area's detail page → `setup4b-areas-create-modal.png`.
3. Detail page — the created binding renders; attaching `tabular` via the attach select updates
   the bound list in place → `setup4b-area-detail.png`.
4. `/lq-ai/admin/capabilities` — sections render from the deployment inventory; the
   `tool:redlining` switch flips `aria-checked` true→false→true through real PATCHes; the Models
   section shows the graceful "Model menu unavailable." state (no gateway in the isolated stack —
   the degradation path proven live) → `setup4b-capabilities.png`.

A width probe (same viewport) recorded `scrollWidth == clientWidth == 1440` on both the new areas
page and the shipped users page — no horizontal overflow; the new pages match the admin layout's
existing behavior exactly.

Also visible in the screenshots: the created not-yet-configured area appears in the cockpit rail
as "Not configured" (inert, D5 semantics) — the honest no-fake-toggle behavior working live.

No product defect was found by either pass on the final branch.
