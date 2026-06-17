# UX-B-5 — cockpit perfection (web): evidence

Headed Cypress (electron, `DISPLAY=:0`) capture of the three UX-B-5 deliverables on the F013 design
language (Vercel charcoal `#111` + scarce blue), light + dark. Web-only slice — no api/gateway change.

Reproduce:

```
cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
  --spec 'cypress/e2e/ux-b-5-cockpit.cy.ts' \
  --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
```

## Shots

- **`ux-b-5-after-area-config-{light,dark}-wide.png`** — the read-only **area-config disclosure** open in
  Commercial's matters panel, against the **live dev backend** (real data): the area PROFILE (rendered
  markdown), its bound SKILLS as chips (`msa-review-commercial-purchase`, `msa-review-saas`, `contract-qa`,
  `nda-review`), and its SUBAGENTS — `document-researcher` with its description and its own (⊆ area) skill
  subset (`contract-qa`, `nda-review`), plus the honest on-demand-delegation note. This is the transparency
  rule made visible: what the agent *can* do, read from `GET /practice-areas` (no api change).
- **`ux-b-5-after-new-matter-area-pick-{light,dark}.png`** — the **new-matter dialog** now carries an
  explicit **practice-area picker** (defaulting to the contextual area, Commercial), making the
  matter→area binding that drives the whole server-side agent identity (`composition.py`) explicit and
  visible at creation. Only configured areas are fileable (ADR-F002).
- **`ux-b-5-after-delegation-boundary-{light,dark}-{wide,narrow}.png`** — the **subagent delegation
  boundary** in a run timeline: the `task` call + the steps that ran inside the subagent, folded into one
  bounded "Delegated to `document-researcher`" block with the child tool cards indented beneath it. This
  shot is **STUBBED** (a fixtured delegated run) — see below.

## Why the delegation boundary is stubbed (honest note, ADR-F015)

A tier-4 model (MiniMax-M3) usually does **not** elect to fan out at a small matter size — UX-B-4 recorded
both RFQ scenarios completing with `task_calls=0` (it read the documents itself). So a *live* delegated run
isn't guaranteed on the dev stack, and forcing one would game the qualification. The boundary's rendering is
therefore proven two honest ways instead:

- **Deterministic unit test** (the gate): `groupTurnTree` / `subagentTypeOf` in
  `web/src/lib/lq-ai/agents/__tests__/helpers.test.ts` — a `task` call + its `parent_step_id`-nested
  children + the task result fold into exactly one delegation segment, labelled from the call's args; a turn
  with no `task` stays flat (the common case). This is the data shape the production runner emits (F0-S7
  `parent_step_id`, runner.py `task` args digest).
- **Cypress stub**: the spec intercepts `GET /agents/threads/{id}` with a fixtured delegated run so the
  boundary renders for the screenshot. The fixture is synthetic (no secrets); it mirrors the real
  `AgentRunStep` wire shape.

The boundary degrades gracefully: with no delegation it renders nothing extra — the cockpit never implies a
fan-out that didn't happen.
