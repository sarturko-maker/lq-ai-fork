# B-5 — sub-agent roster admin form (verification evidence)

Slice: replace the raw `agent_config` JSON textarea on `admin/areas/[key]` with a per-sub-agent form
(surfaces ADR-F034's fan-out roster; validated by the UNCHANGED `build_area_subagents`, ADR-F010/F017).
Branch `b5-subagent-roster-ui`. **Web-only — zero `api/` change, no migration, no new route.**

## Deterministic gate (run + green here)

- **Web typecheck** — `cd web && npm run check` → **0 errors** (svelte-check, 1537 files; the 5 warnings are
  all pre-existing in files this slice does not touch).
- **Web unit/component** — `CI=true npx vitest run` → **113 files / 1311 tests passed** (baseline 1290;
  +25 new B-5 helper tests, −4 retired D6 `parseRosterDraft` tests). The `[key]` page-helpers suite alone is
  **69 tests**, covering: `agentConfigToRoster` (defensive parse KEEPING `system_prompt`, malformed-row
  tolerance, non-string skill filtering), `serializeSubagents` (trim + omit-empty-skills), `rosterToAgentConfig`
  (whole-object build PRESERVING `playbooks`/`mcp_servers`, no-mutate, drop-key-when-empty), `rosterDirty`
  (round-trip false, whitespace-normalised false, real-edit true, passthrough-ignored), `rosterErrors`
  (required fields, out-of-bound skill = ADR-F017, duplicate-name client gate), and the immutable transforms.
- **Web lint (slice-scoped)** — `npx eslint <3 slice files>` → **0**. (Repo-wide lint has pre-existing drift
  and is NOT the gate; the web gate is `check` + `test:frontend` per CLAUDE.md.)

## Backend contract — already covered, unchanged

The form emits exactly the shape `build_area_subagents` accepts, over the existing PATCH `agent_config`
path. That validator + its admin-write wiring are already pinned by `api/tests/test_practice_areas.py`
(forged-`model` → 400, skill-outside-area → 400, skills-subset accept, seeded-roster round-trip read).
**This slice adds no `api/` code and therefore no api tests** — the standing suite is the contract proof.
`git diff --name-only main -- api` is empty.

## What the form does (the JSON→form swap)

- The seeded Commercial roster (document-researcher / clause-drafter / clause-reviewer, migration 0073)
  renders as editable rows — name (input), "When to use this sub-agent" (`description`), Instructions
  (`system_prompt`), and a skills checklist bounded to `area.bound_skills` (ADR-F017). Add / Remove rows.
- Save is one whole-object PATCH via `rosterToAgentConfig(draft, area.agent_config)` — the serialized
  roster spliced into a COPY of the current config, so by-reference `playbooks`/`mcp_servers` survive; a
  forged `model`/`tools` key is structurally impossible from the form (ADR-F010 fence). Dirty-gated +
  client-validated; the server 400 stays authoritative (surfaced via `describeMutationError`).

## Adversarial review

Fresh-context 5-dimension review (web-correctness, contract-fidelity, security, simplification,
test-quality) → per-finding refute-by-default verification. **3 confirmed** (2 should-fix + 1 nit); the
should-fixes are **fixed**:

- **should-fix (web-correctness) — orphaned-skill soft-lock, FIXED.** If an admin detached a skill a
  sub-agent still referenced, `rosterErrors` blocked the whole roster's Save, but the checkbox list only
  iterated `area.bound_skills` — so the orphaned skill had no control to un-check it (the raw JSON textarea
  used to allow inline removal). Fix: new `subagentSkillRows(bound, subSkills)` renders the UNION — bound
  skills plus any skill already on the sub-agent that is no longer bound, the latter as an amber
  "un-check to clear" chip — restoring inline recovery while keeping ADR-F017 server-authoritative validation.
- **should-fix (test-quality) — trim-normalization unpinned, FIXED.** The duplicate-name gate is client-only
  (no server backstop) and depends on `.trim()` matching `serializeSubagents`; the tests only fed pre-trimmed
  inputs. Added a trim-colliding duplicate case + a whitespace-only required-field case so a dropped `.trim()`
  would fail the suite.
- **nit (simplification) — `asStringArray` duplicated from `cockpit/helpers.ts`, DEFERRED on record.** A
  3-line private defensive coercion; lifting it to a shared util would add cross-file coupling for marginal
  benefit (the reviewer itself scored the merge "optional, low value"). The larger `agentConfigToRoster` vs
  cockpit `areaSubagents` overlap is a DELIBERATE divergence (keep `system_prompt`, keep malformed rows for
  repair), not duplication to remove.

Post-fix gate re-run green: svelte-check 0 errors · vitest 113 files / **1317** passed · slice eslint clean.

## Browser + real-model verification (maintainer's live gate)

`web/cypress/e2e/b5-subagent-roster.cy.ts` is a deterministic, no-LLM browser spec: it serves the seeded
Commercial roster (auth LIVE, list/capabilities/PATCH intercepted), asserts the three sub-agents render as
editable rows (not a JSON textarea), edits clause-drafter's instructions, clicks Save, and asserts the PATCH
body carries the edited `system_prompt`, all three sub-agents, the `playbooks` passthrough, and NO
`model`/`tools` key — then that Add surfaces the required-field gate.

**Not run green in this environment:** the spec uses the real login helper, and this dev DB's `admin@lq.ai`
password is not the committed default (re-seeded during ONBOARD-0) — the run fails at `login()`, not on any
B-5 assertion (identical blocker to `hitl3-confirm-card.cy.ts`). The spec runs green with valid dev creds
(`--env LQAI_ADMIN_PASSWORD=…`) / in CI-with-seeded-creds. The web container was rebuilt so the maintainer's
browser session serves the new form.

**The real-model UAT** — edit clause-drafter's instructions to plant a distinctive marker, run a coached
fan-out matter, and observe the marker inside the clause-drafter delegation boundary in the run timeline
(the edited `system_prompt` is server-side config, never emitted on the wire) — is the maintainer's browser
session, on record. Config-echo (that the save persisted) is proven by reloading the area form.
