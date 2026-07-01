# AIC-1 — the `ai_systems` register (first entity end-to-end)

Slice plan of record. Second slice of the **AI Compliance** module (ADR-F057); the
PRIV-3 analogue — the first typed domain entity, end-to-end, mirroring Privacy/ROPA.
Parent plan: `docs/fork/plans/AI-COMPLIANCE-module.md`. Governing ADR: `docs/adr/F057`.

## Goal

A matter filed under the **AI Compliance** area (seeded configured in AIC-0, key
`ai-compliance`) can maintain a company-wide **register of AI systems** under the EU
AI Act — the agent records the *facts* about each system through a guarded,
code-validated write tool, and the lawyer watches the register fill in a read-only
cockpit panel beside the conversation (the ROPA "watch it happen" UX).

## The load-bearing design call (ADR-F057 presence gate)

The register holds **FACTS ONLY**. There is deliberately **no** risk-tier or
legal-role column and **no** tool that writes one. Under the EU AI Act a risk
classification is a *legal determination*; ADR-F057 makes it the property of a
deterministic engine (AIC-2), not something the model asserts. AIC-1 therefore
stores `intended_purpose`, `lifecycle_status`, `development_origin` (the raw
build-vs-buy fact that *informs* the provider/deployer role — the engine derives
the authoritative role), and the GPAI carry-flags. The schema's `extra="forbid"`
actively refuses a `risk_tier` the model might try to smuggle in (tested).

## Non-goals (deferred, by design)

- **The verdict engine + any tier/role output** → AIC-2/AIC-3.
- **`self_declared_role` + authoritative role + Art 25 flip triggers** → AIC-3
  (keeps the presence gate unambiguous in the first cut; `development_origin` is the
  only role-relevant fact stored now).
- **GPAI/Chapter V obligation logic** → AIC-4b (AIC-1 carries `is_gpai` /
  `gpai_systemic` flags only, coherence-constrained).
- **The `visible_filter()`/`can()` policy seam** (ADR-F021) is *not built here*. The
  register ships **shared-read, identical to ROPA** (ADR-F019). But the row carries
  a durable **NON-NULL `practice_area_id`** so the later flip to area-membership
  enforcement is a pure read-path change **with no migration** — "born flip-ready"
  per ADR-F057's authz-ready-by-construction commitment.
- Providers/conformity (AIC-4), FRIA (AIC-5), incidents/deadlines (AIC-6),
  Art 111 transitional facts, lifecycle split (placed-on-market vs put-into-service).

## Scope decisions (made during the slice)

| Decision | Call | Why |
|---|---|---|
| Register scope | **Deployment-global** (F019): `source_project_id` nullable provenance, shared-read `/compliance` router | Mirror ROPA; the org's own AI inventory is company-wide |
| Authz-readiness | **NON-NULL `practice_area_id` FK RESTRICT**, but seam deferred | F057/F021 "born flip-ready" — cheap column now, migration-free flip later |
| Live-wash | **Included** (ledger + SSE frame + cockpit highlight) | Completes the "watch it happen" vertical; runner/live_changes stay area-agnostic |
| Soft-retire | **Included** (retire tool + `retired_at`/`retirement_reason`) | Faithful ROPA parity; never destroy a register row |
| `self_declared_role` | **Deferred to AIC-3** | Keep the presence gate crisp in the first cut |

## Files

**Backend (new):** `api/app/models/compliance.py` (AiSystem), `api/app/schemas/compliance.py`
(AiSystemInput + AiSystemRead + enums + validators), `api/alembic/versions/0085_ai_systems.py`
(down_revision 0084), `api/app/agents/ai_system_changes.py` (AiSystemChangeLedger),
`api/app/agents/compliance_tools.py` (`COMPLIANCE_AREA_KEY="ai-compliance"`,
`COMPLIANCE_TOOL_NAMES`, `build_compliance_tools`, `_propose_ai_system` / `_retire_ai_system`
/ `_list_ai_systems`), `api/app/api/compliance.py` (`/compliance` read router).

**Backend (edited):** `api/app/models/__init__.py` (register AiSystem),
`api/app/agents/capabilities.py` (`AI_SYSTEMS_GROUP` + `AREA_TOOL_GROUPS` row),
`api/app/agents/composition.py` (elif branch + imports), `api/app/agents/stream.py`
(`ai_system_changed` publisher), `api/app/api/__init__.py` (mount `/compliance`).

**Frontend (new):** `web/src/lib/lq-ai/api/compliance.ts`,
`web/src/lib/lq-ai/components/compliance/ComplianceRegister.svelte`.

**Frontend (edited):** `web/src/lib/lq-ai/agents/run-stream.ts` (`parseAiSystemChangePayload`),
`web/src/lib/lq-ai/components/agents/ConversationPanel.svelte` (`compliancechange` dispatch +
`data-compliance-change` case), `web/src/lib/lq-ai/cockpit/ConversationHost.svelte`
(`isComplianceMatter`/`isRegisterMatter` generalisation, conditional register render;
privacy path behaviour-identical).

**Tests (new):** `api/tests/test_compliance_schema.py`, `api/tests/agents/test_compliance_tools.py`,
`api/tests/test_compliance_read.py`; extended `api/tests/agents/test_capabilities.py`.

## Linked ADRs

F057 (module + presence gate — the concrete AIC-1 calls are recorded in its
Implementation-notes addendum), F018 (code-validated writes), F019 (deployment-global),
F021 (authz-ready column), F023/F024 (soft-retire + live-wash), F054 (capability toggle).

## Verification (ADR-F005 gate)

- **Deterministic (dev container):** 74 passed (compliance schema/tools/read +
  capabilities + practice-area seed) on a throwaway DB migrated through 0085; broader
  `tests/agents` (non-scenario) + ROPA-router regression sweep quoted in the PR. Ruff
  check + format clean (repo-root config, line-length 100); mypy clean; web
  `svelte-check` 0 errors.
- **Live (behaviour change):** rebuild api + arq-worker + ingest-worker + web; confirm
  an AI Compliance matter surfaces the AI-systems register and the agent's
  `propose_ai_system` writes appear live (OOM-aware; on the maintainer's go).
- Fresh-context adversarial review incl. the mandatory security + simplification pass.

## Next

**AIC-2 — the deterministic verdict engine** (`app/aiact/classify.py`): consumes
these facts, produces the tier/role/obligations verdict with `verdict_hash` +
`ruleset_version`, gated so the model cannot self-certify a tier. Web-research +
counsel-review the **adopted Digital Omnibus (2026-06-30)** before encoding the rules.
