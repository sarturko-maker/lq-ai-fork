# SETUP-5a — Reconcile paperwork + budget-profile defaults

Status: **ACCEPTED (working model — lead-authored, maintainer-ratified ladder)**
Date: 2026-07-05 · Branch: `fork/setup-5a-reconcile-budget-defaults` (off `main` @ `0b908abe`)
ADRs: **F063** (new, proposed), F054 (status flip + D1-supersession addendum), F062 (status flip)

## Context

SETUP-4a (ADR-F062) superseded ADR-F054 D1 for tool-group *availability* but deliberately reserved
the F054/F062 status-flip paperwork for SETUP-5. Separately, the budget profile (ADR-F053) had only
a wire-schema constant default (`balanced` baked into `AgentRunCreate` + a composer client literal)
— no per-area or per-deployment default was possible, and a client omission was indistinguishable
from an explicit balanced pick. This slice does both halves in one PR: the reconcile paperwork and
the budget-profile default chain (ADR-F063).

## Goals

1. **Reconcile paperwork (docs only).** Flip ADR-F054 to accepted with the house partial-supersession
   status style (F030/F042 precedent) + a dated addendum recording (a) D1 superseded FOR AVAILABILITY
   by F062 (names-only rows; grants stay code in `TOOL_GROUP_REGISTRY`; option-2 rejection honored,
   not violated), (b) the two superseded Consequences lines, (c) D2–D6 unchanged and binding (D5
   governs the 4b UI). Flip ADR-F062 to accepted (plan §7 row 9 ratification, 2026-07-03). MILESTONES:
   4b done-line (PR #220 `0b908abe`), 5a in-flight, backlog lines for SETUP-3c, SETUP-6, and the
   matter-level `CapabilitiesPanel.svelte` whole-state-snapshot optimistic-revert defect.
2. **Budget-profile defaults, backend (ADR-F063, migration 0087).**
   - `practice_areas.default_budget_profile` TEXT NULL + named CHECK
     (`chk_practice_areas_budget_profile`, 0087 chains off 0086; AIC branches renumber on THEIR rebase).
   - `PracticeAreaRead` + `PracticeAreaConfigUpdate` gain the field; on PATCH, explicit JSON null is
     MEANINGFUL (clears the area default — inherit deployment); key absent = unchanged; deliberately
     NOT covered by the null-rejecting validator (opposite of name/unit_label — documented at the seam).
   - `Settings.run_default_budget_profile` (env `RUN_DEFAULT_BUDGET_PROFILE`) with a `mode="before"`
     validator: "" → None (the `${VAR:-}` compose trap) and boot-loud rejection of unknown values.
   - Run create (`api/app/api/agent_runs.py`): `AgentRunCreate.budget_profile` → `BudgetProfile | None
     = None` (None = "resolve for me"); chain `body.budget_profile or area_default or
     settings.run_default_budget_profile or BudgetProfile.balanced`, area default via ONE query on the
     run's bound matter's `practice_area_id`. The RESOLVED value is persisted on
     `agent_runs.budget_profile` (telemetry honest) and drives `resolve_envelope`/`max_steps` as today.
   - Compose forwarding (`${RUN_DEFAULT_BUDGET_PROFILE:-}` on api + arq, prod AND dev), `.env.prod.example`
     + `.env.example` commented keys, wizard optional manifest key behind an anchored
     `^(economy|balanced|generous)$` fence (line omitted from `.env.prod` when unset).
3. **Web (frontend).** API types mirror the field; the SETUP-4b area detail page gains a "Default
   budget profile" select (testid `lq-admin-area-budget-profile`) wired into the dirty-fields-only
   PATCH (Inherit → explicit null ONLY when changed); the composer budget dropdown gains a FIRST
   "Default" option (`''`, the initial selection) and `buildRunPayload` OMITS `budget_profile` on `''`.

## Non-goals

- **NO viewer/operator RBAC** — that is SETUP-5b (next slice, ADR-F064).
- **No budget ENVELOPE changes** — `resolve_envelope()` untouched; this picks which TIER applies by
  default, not what the tiers mean.
- **No per-matter budget default** (backlog; would ride the same chain one link more specific).
- **No composer resolved-label rendering** (needs area context the composer doesn't cleanly have;
  recorded as polish in ADR-F063 Consequences).
- No new `/api/v1` routes (openapi guard count unchanged); no new dependency; gateway untouched.

## Decisions (ADR-F063)

- Chain: **run explicit > area default > deployment default > balanced**.
- Resolution **ONCE at run create; resolved value persisted** — a later default change never
  silently re-prices an already-created run (vs re-resolving at execute).
- Actor split (F061/F062): deployment default = operator-owned env; area default = org-admin data.
- Explicit-null-clears PATCH semantics; "" → None env normalization + boot-loud rejection.

## Files

Docs: `docs/adr/F054-…`, `docs/adr/F062-…`, `docs/adr/F063-budget-profile-defaults.md` (new),
`docs/fork/MILESTONES.md`, this plan.
Backend: `api/alembic/versions/0087_practice_area_default_budget_profile.py` (new),
`api/app/models/practice_area.py`, `api/app/schemas/practice_areas.py`,
`api/app/schemas/agent_runs.py`, `api/app/api/practice_areas.py`, `api/app/api/agent_runs.py`,
`api/app/config.py`, `docker-compose.prod.yml`, `docker-compose.yml`, `.env.prod.example`,
`.env.example`, `scripts/setup-tenant.sh`.
Web: `web/src/lib/lq-ai/api/practiceAreas.ts`,
`web/src/lib/lq-ai/components/agents/ConversationPanel.svelte`,
`web/src/routes/lq-ai/(app)/admin/areas/[key]/{+page.svelte,page-helpers.ts}`.
Tests: `api/tests/{test_config,test_migrations,test_practice_areas,test_setup_tenant_wizard}.py`,
`api/tests/agents/test_agent_runs_api.py`,
`web/src/lib/lq-ai/__tests__/ConversationPanel-helpers.test.ts`,
`web/src/routes/lq-ai/(app)/admin/areas/[key]/__tests__/page-helpers.test.ts`.

## Verification

- Migration 0087 up → down → up on a throwaway pgvector container (never the live dev DB); column +
  named CHECK verified via `\d practice_areas`.
- Containerized api tests (dev image, dev-stack DATABASE_URL read from the api container env by name):
  chain resolution (explicit/area/deployment/fallback), PATCH set/absent-unchanged/null-clears/422,
  Settings ""→None + boot rejection, migration CHECK, wizard accept/omit/refusal, openapi guards.
- Repo-root `ruff format` + `ruff check api scripts`; `mypy app` clean.
- Web: `npm run check` 0 errors + `CI=1 npx vitest run` green (diffPatch null/omit semantics; payload
  omission + explicit cases).
- Live UAT (lead): area select round-trip on `/lq-ai/admin/areas/{key}`; composer "Default" run lands
  with the resolved profile on the run card.
