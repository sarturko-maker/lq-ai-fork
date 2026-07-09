# Plan — B-5: sub-agent roster admin UI (surface ADR-F034's roster, no JSON)

Status: **DRAFT for maintainer edit** (per CLAUDE.md: explore → written plan → human edits → implement).
Slice of Workstream B (`docs/fork/plans/MODULES-milestone.md` §B-5). Follows HITL-3 (PR #251, merged
`0fac8b2b`), which completed the B-6 HITL milestone. Grounded in a 6-explorer substrate map (2026-07-09).

## Context

The maintainer's brief for the agent-builder: *"configure sub-agents without touching JSON."* Today an
admin edits an area's fan-out roster (ADR-F034: document-researcher / clause-drafter / clause-reviewer)
through a **raw `agent_config` JSON textarea** — the SETUP-4b "Subagent roster (D6)" card on
`admin/areas/[key]`. B-5 replaces that textarea with a real per-sub-agent form: name, plain-language
instructions, and a skills multi-select bounded to the area's skills.

### The decisive finding: the backend is already done

`build_area_subagents` (`api/app/agents/area_agent.py:121-194`) is the exact validator we need, and it
**already runs at the admin write boundary** — not just at run time. So B-5 changes **no `api/` code, no
migration, no route, and adds no api tests** (they already exist). The whole slice is the web form emitting
the shape the server already accepts.

The contract the form must produce (all enforced on PATCH → HTTP **400** `ValidationError`, never persisted):

- `agent_config` is one JSONB dict. Top-level keys are strictly `{subagents, playbooks, mcp_servers}`
  (`_ALLOWED_CONFIG_KEYS`); any other key — notably `model` — is rejected (ADR-F010 gateway-bypass fence).
- The roster is the list at `agent_config["subagents"]`. Each entry's keys are strictly
  `{name, description, system_prompt, skills}` (`_ALLOWED_SUBAGENT_KEYS`); `name`/`description`/
  `system_prompt` are **required non-empty strings** (`_REQUIRED_SUBAGENT_KEYS`); `skills` is optional and
  must be `list[str]`.
- On PATCH, every `skills` entry must be in the area's **currently-bound** skill set
  (`known_skill_names = _bound_skill_names(area)` = `PracticeAreaRead.bound_skills`), else 400 (ADR-F017).
  On the run/render path the subset check is skipped (drift is dropped, not fatal) — so **the form is the
  last line of defence against a dangling skill ref.**

The existing api tests already cover this: forged-`model` → 400, skill-outside-area → 400, skills-subset
accept, and the Commercial roster round-trip read. **B-5 adds api tests only if it tightens the server
(it will not).**

## Goals

1. Replace the `admin/areas/[key]` "Subagent roster (D6)" raw-JSON textarea with a **structured
   per-sub-agent form**: list / add / edit / remove rows; fields = **name** (short input), **description**
   ("When to use this sub-agent" — the delegation trigger the lead reads), **instructions**
   (`system_prompt` — the required plain-language brief), **skills** (multi-select over the area's bound
   skills). No JSON textarea anywhere in the roster editor.
2. Emit **exactly** the `agent_config` shape `build_area_subagents` accepts, via the existing PATCH
   `agent_config` path — a forged `model` key is **impossible from the form** and still 400s at the boundary.
3. Render the shipped Commercial roster (3 sub-agents) as editable rows, and the empty-roster case
   (every other area) as an "add your first sub-agent" affordance — the F034 roster becomes visible,
   honest config.
4. Retire the dead JSON path (`parseRosterDraft` + its test block) — simplification-pass hygiene.

## Non-goals

- **No `api/` change, no migration, no new route, no new ADR.** UX-only over the unchanged
  ADR-F010/F016/F017 contract. (If the maintainer wants a paper trail, a one-paragraph ADR-F016 addendum
  noting the JSON→form swap is cheap — flagged below, not assumed.)
- **No per-sub-agent tool picker.** `tools` is deliberately outside the allowlist — sub-agents inherit the
  parent's guarded matter tools (a later slice if ever).
- **No editing of `playbooks` / `mcp_servers`.** They live in the same `agent_config` dict but are
  by-reference-only and not consumed by the renderer yet (playbooks bind via their own card; MCP is
  double-gated future work). The form **preserves them untouched** on every save (read-modify-write).
- **Does not touch the area-level skill *bind* card** (the `<select>` that edits `bound_skills` itself) —
  that stays; it is a different feature and is the source the roster's skills picker reads from.
- No wizard integration (that is B-7b, which consumes this card).

## The form (exact shape)

Per sub-agent row (an editable card):

| Field | Control | Server key | Rule |
|---|---|---|---|
| Name | short text input | `name` | required, non-empty; **unique within the roster** (client gate — deepagents dispatches on `name`) |
| When to use this sub-agent | textarea | `description` | required, non-empty (multi-line prose) |
| Instructions | textarea | `system_prompt` | required, non-empty (multi-line prose) |
| Skills | multi-select (checkbox/chips) over `area.bound_skills` | `skills` | optional; ⊆ bound skills; **omit the key when empty** (matches render-drop semantics) |

- **Save** is one whole-object PATCH `{agent_config: {...}}` via `practiceAreasApi.updatePracticeArea`,
  **read-modify-write**: rebuild `{subagents: [...]}` and splice back any existing `playbooks`/`mcp_servers`.
  Dirty-gated (`disabled={rosterBusy || !rosterDirty || hasClientErrors}`) — no no-op PATCH, mirroring the
  HITL card. On success re-seed the draft from `updated.agent_config` (never a full reset).
- **Skills picker** offers only `area.bound_skills` (list of names). Labels via
  `bindingLabel(skillCatalogAll, name)` (catalog title ?? raw name) for parity with the bind card. When
  `bound_skills` is empty, the picker is disabled with the existing "bind a skill first" hint. Degraded
  (bound-but-not-adopted) skills stay selectable with the existing amber chip (server admits them).
- The server 400 message (`str(ValueError)`, e.g. *"agent_config.subagents[0] requires non-empty string
  'system_prompt'"*) is surfaced verbatim via `describeMutationError` as the authoritative backstop; the
  client gate just pre-empts the obvious cases.

## Files / seams

**Web — the whole slice.**
- `web/src/routes/lq-ai/(app)/admin/areas/[key]/+page.svelte` — rewrite the Roster card (currently
  ~L545-576: `draftRoster` `<Textarea>` + `parseRosterDraft` gate + `saveRoster`) into the per-sub-agent
  form. Slots in the **same position** (section 2, after Details, before Tool groups — well before Danger
  zone). State/save pattern mirrors the freshly-shipped HITL "Ask before acting" card (state vars
  ~L256-282; shared draft-seed `$effect` keyed on `area.key !== loadedKey` ~L179-190 — add the roster-draft
  seed there). Runes mode: mutate the draft array **immutably**.
- `web/src/routes/lq-ai/(app)/admin/areas/[key]/page-helpers.ts` — new pure helpers (unit-tested, no Svelte
  runtime): `SubagentDraft` type; `agentConfigToRoster(agent_config)` (defensive parse of the opaque
  `Record<string,unknown>` → editable rows, mirroring `cockpit/helpers.ts:areaSubagents` **but keeping
  `system_prompt`**); `rosterToAgentConfig(draft, prevConfig)` (build `{subagents:[...]}`, preserve
  passthrough keys); `subagentDraftErrors` / `rosterErrors` (required non-empty, skills ⊆ bound, unique
  names); `rosterDirty(agent_config, draft)`; immutable `addSubagent`/`removeSubagent`/`updateSubagent`/
  `toggleSubagentSkill`. **Retire `parseRosterDraft`.**
- `web/src/lib/lq-ai/api/practiceAreas.ts` — no change (PATCH `{agent_config}` already exists;
  `bound_skills: string[]` already on `PracticeArea`).

**Tests.**
- `web/.../admin/areas/[key]/__tests__/page-helpers.test.ts` — add a `describe` per new helper (round-trip
  `agentConfigToRoster`↔`rosterToAgentConfig` incl. passthrough preservation; error gates: blank required
  field, out-of-bound skill, duplicate name; dirty detection). **Remove the `parseRosterDraft (D6)` block.**
  The `area()` fixture already carries `agent_config: {}` → **no fixture break** (confirmed in all three
  fixture files).
- API: **none** (existing `test_practice_areas.py` coverage is complete for the unchanged contract).

**Docs.** `MODULES-milestone.md` (mark B-5 done), `HANDOFF.md` (B-5 SHIPPED block + traps + next), memory,
evidence `docs/fork/evidence/b5-subagent-roster/`. No ADR unless the maintainer wants the F016 addendum.

## Traps (carried from the substrate map — all cross-verified)

1. **Whole-object PATCH, not a merge.** `agent_config` is replaced wholesale (`area.agent_config = cfg`).
   Read-modify-write: preserve existing `playbooks`/`mcp_servers` or they are silently dropped.
2. **`system_prompt` is required and the cockpit `areaSubagents` reader OMITS it** — do NOT reuse that
   shape as the edit model; a blank instructions field is a 400.
3. **Skills picker binds to `area.bound_skills`, not the Library catalog.** Subset check is case-sensitive
   exact match. Empty bound set ⇒ any skill-bearing sub-agent 400s (disable the picker, keep the hint).
4. **400, not 422.** Roster-shape violations come from `build_area_subagents` raising `ValueError` →
   `ValidationError` → HTTP 400 with `details.field == 'agent_config'`. (Pydantic body 422 is a different
   path.) Same quirk as HITL-3's unknown-tool.
5. **Runes immutability** — reassign the draft array/objects (`draftSubagents = [...]`) so `$derived`/
   `$effect` re-run (the HITL `toggleHitlTool` spread is the pattern).
6. **Draft-seed in the `area.key !== loadedKey` `$effect` only** — never on post-save refresh (would
   clobber in-flight edits in sibling cards).
7. **Retire `parseRosterDraft` + its test block** — leaving dead code is a simplification-pass finding.
8. **`data-testid` convention** on this page is `lq-admin-area-*` — keep the roster form under it.
9. **Rebuild the prebuilt `web` container** before any UI verification.
10. **Web gate is `npm run check` + `test:frontend`, NOT lint/format** — the repo has pre-existing eslint
    drift; `npm run format` reformats ~170 unrelated files (never run it broadly).

## Verification / DoD (ADR-F005 gate)

- **Deterministic:** `cd web && npm run check` (svelte-check 0 errors) + `npx vitest run` (all green, incl.
  the new page-helpers describes; round-trip proves the payload emits the exact `build_area_subagents`
  shape and a forged `model` key is structurally impossible from the form); slice-scoped eslint clean.
- **Backend already-green:** quote the existing `test_practice_areas.py` roster tests (forged-model 400,
  skill-outside-area 400, subset accept, round-trip) as the standing contract proof — B-5 adds none.
- **Live (maintainer browser session — the acceptance evidence):** the edited `system_prompt` is **never on
  the wire** (no step/frame echoes it), so timeline proof is **behavioral**: plant a distinctive marker in
  clause-drafter's instructions (e.g. *"Begin with the marker DRAFTER-EDIT-OK."*) → run a **coached**
  fan-out matter (fan-out is the model's choice — ADR-F015 findings-only; the `_ROSTER_DRAFT` nudge in
  `test_vendor_review_fanout_live.py` reliably forces the dispatch) → expand the "Delegating to a
  sub-agent…" boundary labeled clause-drafter and read the marker in its output. Config-echo (that the save
  persisted) is proven by reloading the area form.
- **Fresh-context adversarial review** incl. the mandatory security + simplification pass (no secrets,
  admin-only surface preserved, no injection via the opaque config, `parseRosterDraft` fully removed).
- HANDOFF + memory updated; merge under the full ADR-F005 gate (branch `b5-subagent-roster-ui` off main
  `0fac8b2b`; `gh ... --repo sarturko-maker/lq-ai-fork`).

## Decisions I've made (grounded in precedent — override in review if you disagree)

- **No extracted `RosterEditor.svelte` component** — keep the form as `+page.svelte` glue over pure
  `page-helpers.ts` helpers (the SETUP-4b / HITL-3 precedent on this exact page). Consequence: no new
  component-test file; the page-helpers tests cover the logic. (Fallback: extract a
  `SubagentRosterCard.svelte` with `<script module>` helpers + a `RosterCard.test.ts` mirroring
  `HitlConfirmCard.test.ts` **only if** the markup gets unwieldy.)
- **Unique sub-agent names: client-only gate.** deepagents dispatches on `name`, so duplicates are
  genuinely broken — but enforcing it server-side means touching `build_area_subagents` (breaks "zero
  backend"). Client gate now; a server rule is a separate hardening slice if wanted.
- **No roster-length cap** in v1 (server is permissive; a handful of sub-agents is the real shape).
- **Degraded skills stay selectable** with the existing amber chip (the server admits any bound skill).
- **Preserve `playbooks`/`mcp_servers` untouched**, do not surface them.
- **No new ADR** (UX over unchanged contract).

## Open question(s) for the maintainer

1. **Field labels.** I've mapped `description` → **"When to use this sub-agent"** (the delegation trigger)
   and `system_prompt` → **"Instructions"**. Both are server-required. Happy to relabel.
2. **ADR paper trail** — do you want a one-paragraph ADR-F016 addendum recording the JSON→form swap and the
   "no `model`/`tools` from the form" invariant, or is the plan doc + HANDOFF enough? (I lean: plan doc is
   enough — no architectural call is being made.)

## Recommended order

pure helpers + tests in `page-helpers.ts` (round-trip, gates, dirty) → rewrite the Roster card in
`+page.svelte` (mirror the HITL card state/save) → retire `parseRosterDraft` + its test block →
`npm run check` + `vitest` → rebuild `web` → screenshots (empty roster + Commercial 3-row + a 400 surfaced)
→ HANDOFF/memory/evidence → adversarial review → PR + merge under the ADR-F005 gate. Maintainer browser
behavioral-marker verify is the live acceptance, on record.
