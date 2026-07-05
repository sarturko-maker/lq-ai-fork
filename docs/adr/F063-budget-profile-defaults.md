# F063 — Budget-profile defaults: run-explicit > area default > deployment default > balanced

- Status: **proposed**
- Date: 2026-07-05
- Deciders: maintainer (Arturs), agent
- Slice: **SETUP-5a**. Builds on **ADR-F053** (per-run budget envelopes — the profiles this ADR
  picks a default FOR), **ADR-F061** (operator/admin actor split), **ADR-F062** (deployment→area
  config hierarchy). Companion plan: `docs/fork/plans/SETUP-5a-reconcile-budget-defaults.md`.

## Context

ADR-F053 gave every agent run a `budget_profile` (economy / balanced / generous) that resolves to the
four-brake envelope. Until this slice the default was a wire-schema constant:
`AgentRunCreate.budget_profile` defaulted to `balanced`, and the composer sent a client literal.
That has two problems for the hosted SETUP hierarchy. First, there was no way to give a practice
area or a whole deployment a different default — a tenant whose Commercial area should run economy
by default needed every lawyer to pick it on every run. Second, the always-concrete schema default
made a client OMISSION indistinguishable from an explicit balanced pick, so no server-side default
chain could ever be layered under it without silently overriding explicit choices.

The SETUP config hierarchy (ADR-F062, plan §7) already established the pattern: deployment-level
knobs are operator-owned env; area-level knobs are org-admin-owned data (`default_tier_floor` is
the column precedent).

## Considered options

1. **Keep the schema default; add only an area column consulted by the composer client-side.**
   No API change, but the client must fetch and reimplement the chain, and API callers (tests,
   scripts, future integrations) bypass it entirely — two sources of truth.
2. **Resolve at execution time (composition), not at run create.** The worker already re-resolves
   the envelope from the persisted profile; it could walk the chain there. But then
   `agent_runs.budget_profile` would have to stay NULL for "default" runs and a later default
   change would silently RE-PRICE an already-created run between create and execute (or on retry);
   telemetry (which profile actually governed the run) would need a second column anyway.
3. **Resolve ONCE at run create; persist the RESOLVED value (CHOSEN).**
   `AgentRunCreate.budget_profile` becomes `| None = None` (None = "resolve for me"); the endpoint
   walks run-explicit > area default (`practice_areas.default_budget_profile`, new nullable column,
   migration 0087) > deployment default (`Settings.run_default_budget_profile`, env
   `RUN_DEFAULT_BUDGET_PROFILE`) > `balanced`, and stores the winner on `agent_runs.budget_profile`.
   Everything downstream (`resolve_envelope`, max_steps materialization, composition re-resolution,
   telemetry) is untouched and stays honest.

## Decision outcome

Adopt **option 3**.

- **The chain: run explicit > area default > deployment default > balanced.** The most specific
  actor wins: the lawyer's per-run pick beats the area's default beats the deployment's default
  beats the code fallback. `resolve_envelope()` itself is UNTOUCHED — this ADR picks which TIER
  applies by default; ADR-F053's env-tunable balanced knobs still shape what balanced MEANS.

- **Resolution happens ONCE, at run create, and the RESOLVED value is persisted.** A run's price
  is fixed the moment it is accepted: a later change to an area or deployment default must never
  silently re-price an already-created run (the same immutability posture as the materialized
  `max_steps`). `agent_runs.budget_profile` therefore always carries the profile that actually
  governs the run — telemetry stays honest, and the worker's existing re-resolution from the
  persisted value is untouched.

- **Actor split (ADR-F061/F062).** The deployment default is OPERATOR-owned env
  (`RUN_DEFAULT_BUDGET_PROFILE`, forwarded `${VAR:-}` in both composes, optional wizard manifest
  key with an anchored `^(economy|balanced|generous)$` fence). The area default is ORG-ADMIN-owned
  data (`practice_areas.default_budget_profile`, PATCH `/practice-areas/{key}`, mirroring
  `default_tier_floor`). No new endpoint.

- **Explicit-null-clears PATCH semantics.** On `PracticeAreaConfigUpdate`,
  `default_budget_profile` is `Literal["economy","balanced","generous"] | None`: with
  `exclude_unset`, "key present with null" CLEARS the area default (column → NULL, area inherits
  the deployment default), "key absent" leaves it unchanged. This is the OPPOSITE of the
  `name`/`unit_label` null-rejection (those columns are NOT NULL) — deliberate, documented at the
  field, and NOT covered by the null-rejecting validator.

- **The `""` → None env trap.** The prod compose forwards `${RUN_DEFAULT_BUDGET_PROFILE:-}`, so an
  unset key reaches pydantic as EMPTY STRING, never None (the SETUP-3b `${VAR:-}` lesson). A
  `field_validator(mode="before")` normalizes `""`/None → None and REJECTS any other value outside
  the three profiles at Settings construction — a misconfigured deployment fails loud at boot
  instead of silently running every run on an unintended tier.

## Consequences

- The composer's budget dropdown gains a "Default" first option (empty value ⇒ the payload OMITS
  `budget_profile`; the server resolves the chain). Explicit picks send exactly as before.
  Rendering the RESOLVED label in the composer (so the lawyer sees which tier "Default" currently
  means for this matter) needs area context the composer does not cleanly have — deferred as
  polish, not built in this slice.
- One additive nullable column (migration 0087, named CHECK, no seed, no index); legacy rows and
  areas are unaffected (NULL = inherit). No new endpoint (`/api/v1` path count unchanged); no new
  dependency; the gateway is untouched.
- API callers that previously relied on the implicit schema default still get balanced when no
  area/deployment default is set — behavior-identical by construction; but an explicit
  `"budget_profile": "balanced"` is now distinguishable from omission (that is the point).
- A per-MATTER budget default (below the area) is explicitly out of scope — backlog, would ride
  the same chain one link more specific.
