# HITL-3 — verification evidence (ADR-F071 HITL-3)

Slice: cockpit confirm card + admin `hitl_policy` write. Branch `b6-hitl-3-confirm-card`.

## Deterministic gate (run + green here)

- **Web typecheck** — `cd web && npm run check` → **0 errors** (svelte-check, 1537 files).
- **Web unit/component** — `npx vitest run` → **113 files / 1290 tests passed**. Covers: the card's
  own logic (`HitlConfirmCard` module script — `parseHitlActions` defensive parse of the untrusted
  digest, `hitlToolNames`, `hitlAskLine`, `formatHitlArgs`), `resumeRun` (POST body shape), the two
  widened stream validators (`isStepKind` accepts `hitl_request`, `parseRunPayload` accepts
  `awaiting_input`, garbage still rejected), `pendingHitlStep`, the `Needs you` badge, and the admin
  `hitlEnabledTools` / `hitlPolicyDirty` helpers.
- **Web lint (slice-scoped)** — `npx eslint <slice files>` → **0**. (Repo-wide `npm run lint` has
  pre-existing drift and is NOT the gate; the web gate is `check` + `test:frontend` per CLAUDE.md.)
- **API lint/type** — `ruff format --check` + `ruff check` + `mypy app` (229 files) → clean
  (CI-parity dev image, repo root mounted).
- **API blast-radius suite** (dev image, real Postgres ephemeral `lq_ai_test_*`) →
  **229 passed / 1 skipped**: `test_practice_areas.py` (the HITL PUT: sets+persists+audits;
  PUT-replace normalises `false`→absent; unknown tool → **400** and nothing persisted; non-admin →
  403; unknown area → 404; read model exposes `hitl_policy` + `hitl_eligible_tools`),
  `test_capabilities.py` (`area_hitl_eligible_tool_names`), `test_agent_composition.py` +
  `test_hitl.py` (the pause path is unchanged), and all five endpoint/RBAC drift guards
  (`test_endpoints` IMPLEMENTED_ROUTES; `test_mutation_rbac` 137/186/70; `test_openapi` 186 +
  EXPECTED_PATHS).

The BACKEND behaviour change (the admin PUT) is therefore **live-verified on a real Postgres**.

## Adversarial review

5 fresh-context dimension reviewers (web-correctness, backend-correctness, security, simplification,
tests) → per-finding adversarial verification (refute-by-default). **4 findings refuted, 1 confirmed**
(a documentation nit — a stale "422" in the `_bound_policy` validator docstring where the echo path is
400) — **fixed**. No blockers, no should-fixes.

## Browser + real-model verification (maintainer's live gate)

`web/cypress/e2e/hitl3-confirm-card.cy.ts` is a deterministic, no-LLM browser spec: it serves a paused
(`awaiting_input`) run with an `apply_redline` `hitl_request` step, asserts the "Waiting for your
go-ahead" card renders with the tool + Approve/Refuse, clicks Approve, asserts the
`{decision:{type:'approve'}}` body to `/resume`, and asserts the card dissolves once the resume run is
the thread tail.

**Not run green in this environment:** the spec uses the real login helper, and this dev DB was
re-seeded (ONBOARD-0) with an admin password that is not the committed default — the run fails at
`login()`, not on any HITL-3 assertion. Resetting the maintainer's admin password (or mounting the
whole cockpit load-graph hermetically) was judged out of scope for a screenshot. The spec runs green
with valid dev creds / in CI-with-seeded-creds.

**The real-model UAT** — a Commercial agent (DeepSeek/Adeu) emitting `apply_redline`, pausing, and the
lawyer clicking Approve to apply the redline — is the maintainer's browser session, on record since the
HITL-3 kickoff. The confirm-card wiring it exercises is what the deterministic suite above pins.
