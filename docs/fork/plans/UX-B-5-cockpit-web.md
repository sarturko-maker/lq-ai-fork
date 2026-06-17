# UX-B-5 — cockpit perfection (web): area-pick at matter creation · subagent boundary · area-config visibility

**Milestone:** UX-B (capability convergence — "Deep Agents truly work / cockpit perfect"), the gate for the
agentic-modules / Oscar-Privacy direction. Decomposition `docs/fork/plans/UX-B-deep-agents-truly-work-decomposition.md`
§UX-B-5. Design language: **ADR-F012/F013** (Vercel charcoal `#111` + scarce blue; no black bg).

**One-line:** surface the now-proven backend loop on the web, honestly — let the user pick the practice area
at matter creation, render the subagent delegation boundary when it occurs, and make an area's config
(profile / skills / subagents) readable. **Web-only — no api/gateway change** (every datum already exists on
the wire; this slice only consumes it).

## Why this is web-only

The Explore pass confirmed all three data dependencies are already served:

- **Area binding** — `POST /projects` already accepts `practice_area_id` (`types.ts:ProjectCreate`);
  `GET /practice-areas` already returns `configured` + `unit_label` + `id`; the matter→area binding already
  drives the whole server-side agent identity (`composition.py`). The web just doesn't let the user *set* it
  at creation beyond the implicit "you're inside an area" navigation context.
- **Subagent boundary** — `parent_step_id` already flows over REST (`GET /agents/threads/{id}` →
  `AgentRunStep.parent_step_id`) **and** SSE (`data-step` parts carry it). `groupTurnSteps()` already computes
  a `nested` boolean and `ConversationPanel` already styles `.ag-step--nested`. The gap is purely
  *hierarchical grouping* (a `task`→delegated-children block), not data.
- **Area-config** — `GET /practice-areas` already returns `profile_md`, `bound_skills`, and `agent_config`
  (subagents). The web fetches the whole object into the cockpit context (`context.svelte.ts:loadAreas`) and
  never displays the config fields.

## Goals (this slice)

1. **Area selection at matter creation.** `NewMatterDialog` becomes area-aware: it renders a labelled area
   **picker** of *configured* areas (only configured areas are fileable — ADR-F002), defaulting to the
   contextual area when there is one (the MattersPanel / matter-bound-conversation path), and the dialog's
   noun + title follow the chosen area's `unit_label`. The chosen area's `id` is posted as `practice_area_id`.
   This makes the binding **explicit and visible** at creation instead of implicit-from-navigation, and lets
   the no-context paths (an unfiled conversation's "new matter") pick an area rather than silently filing
   unfiled. Threaded from the cockpit context's `areas` into `MattersPanel` + `ConversationHost`.

2. **Subagent boundary rendering** in the run timeline. Extend the pure step-grouping so a `task` tool-call
   row carries its delegated children (the steps whose `parent_step_id` === the task step's id) as a nested
   block, and render it as a **labelled delegation boundary** — "Delegated to `<subagent_type>`" header + an
   indented child timeline reusing the existing row renderer. Honest by construction: the boundary appears
   **only when delegation actually occurred** (a `task` step exists); when M3 doesn't fan out (the common
   tier-4 case, UX-B-4 finding) nothing extra renders — graceful degradation, no implied fan-out. One level
   of nesting is exercised (Commercial's single `document-researcher`); the grouping is written
   recursion-capable but only single-level is claimed.

3. **Area-config visibility (read-only).** A disclosure in the area context (MattersPanel header — the
   natural "you are in area X" home) surfacing the area's **profile** (rendered through the shared
   `renderModelMarkdown` sink — it is operator-authored but rendered as untrusted model-class input for one
   consistent media-forbid policy), its **bound skills** (names), and its **subagents** (name + description +
   each subagent's own skill subset). Satisfies the transparency rule ("every prompt, skill, agent
   instruction and tool grant must be readable in the UI or the source"). Collapsed by default.

## Non-goals (this slice — recorded, deferred)

- **Admin PATCH editor for area config.** Read-only visibility satisfies transparency; an editor needs a web
  PATCH client (`updatePracticeArea`), a form for `profile_md` / `default_tier_floor` / `agent_config.subagents`,
  and client-side mirroring of the server validation (no dangling skill refs ADR-F017, no top-level `model`
  ADR-F010). That is its own slice. (The server PATCH endpoint already exists and is admin-gated.)
- **A richer SSE subagent *frame type*** (CLAUDE.md blocker #4). The HANDOFF explicitly permits scoping to the
  nested-`parent_step_id` rendering and noting the richer end-to-end frame projection as follow-up — which is
  what this slice does. `parent_step_id` is already on every `data-step`, so the boundary renders live and on
  replay with **no protocol change**; a dedicated subagent/tool frame type stays follow-up.
- **Folding `MatterRail` into the cockpit rail** (the UX-A-3 two-rail density note) — orthogonal.
- Any api/gateway/schema change. Any new dependency.

## Files (anticipated)

- `web/src/lib/lq-ai/cockpit/NewMatterDialog.svelte` — area picker; noun/title follow the chosen area.
- `web/src/lib/lq-ai/cockpit/MattersPanel.svelte` — pass `areas` (configured) to the dialog; host the
  read-only **area-config disclosure** in the header.
- `web/src/lib/lq-ai/cockpit/ConversationHost.svelte` — pass `areas` (configured) to the dialog (default
  still the matter's bound area).
- `web/src/lib/lq-ai/agents/helpers.ts` — extend `TurnRow` / grouping with the delegation hierarchy (new
  `groupTurnTree` building on `groupTurnSteps`, or a hierarchy field — chosen to keep existing tests green).
  Pure, unit-tested.
- `web/src/lib/lq-ai/components/agents/ConversationPanel.svelte` — render the delegation boundary block.
- Possibly a small `AreaConfigDisclosure.svelte` (cockpit) if MattersPanel grows too big.
- Tests: `agents/__tests__/helpers.test.ts` (delegation grouping), cockpit `__tests__/helpers.test.ts`
  (unchanged unless a launch helper changes), new Cypress capture spec under `cypress/e2e/`.

## Linked ADRs

ADR-F002 (practice-areas-and-agent-home / launcher-not-composer), ADR-F004 (settled rows decide; bounded
digests), ADR-F010 (no gateway bypass — subagents carry no model), ADR-F012/F013 (design language),
ADR-F016/F017 (skills + per-subagent skill sources — the config this slice surfaces). No new ADR anticipated
(this surfaces decided architecture; if the subagent-grouping shape proves architecturally load-bearing I'll
draft one).

## Verification (web DoD)

`cd web && npm run check` (0 err) + `npx vitest run`; rebuild the `web` container; headed Cypress
(`DISPLAY=:0`, electron) before/after, light+dark × wide+narrow → `docs/fork/evidence/ux-b-5/`. The
delegation boundary is captured against a **scripted/seeded delegated run** if the dev stack has one, else a
fixture-driven render (M3 usually won't fan out at small matter size — UX-B-4 — so a live delegated run isn't
guaranteed; the unit test is the deterministic gate, the screenshot is best-effort). Fresh-context
adversarial + **security + simplification** pass ([[security-review-every-slice]]): no `{@html}` outside the
sanitised sink, no secrets, no new `--lq-*` color tokens, nothing retired. Merge per ADR-F005 against
`sarturko-maker/lq-ai-fork`.

## Honesty caution (carried from UX-B-3/4)

A tier-4 model (MiniMax-M3) over-explores a big skill surface and does **not** spontaneously delegate at
small matter sizes. The web must present the loop honestly — never imply subagent fan-out happens when it
usually won't; render delegation when it occurs, degrade gracefully when it doesn't. The area-config
disclosure shows what the agent *could* do (its configured subagents), not a promise that it will.
