# F1-S3 — live verification evidence

Slice: practice-area config vocabulary + per-area Deep Agent. Dev compose stack;
api+arq-worker+ingest-worker+web rebuilt on the slice commit; live DB auto-migrated
0053 → 0054 on api boot (`alembic_version = 0054`).

## Config API (admin@lq.ai)

- `GET /practice-areas` → Commercial `configured=true`, `profile_md` 566 chars, `agent_config={}`,
  `bound_skills=[]`; inert areas `configured=false`, `profile_md=null` (derived from profile).
- File a matter under Commercial (`POST /projects` with `practice_area_id`) → 201; it appears in
  `GET /agents/matters` with `practice_area_key="commercial"` (filing is real).
- **ADR-F010 security guard, live**: `PATCH /practice-areas/commercial` with a subagent carrying
  `"model":"openai:gpt-5.5"` → **400**, not stored (re-read shows no subagents).
- File a matter under an **inert** area (disputes) → **400** (refuses runs under unconfigured areas).
- Sandbox `project_id` at `POST /agents/runs` → 404 (sandbox threads closed at the source).

## Tier floor enforced end-to-end (the reason Commercial seeds NO floor)

First E2E run under Commercial (seeded `default_tier_floor=2`) **failed** with the gateway's
`403 tier_below_minimum`: *"requires Inference Tier 2 or stronger (source: project), but the
routed model resolves to tier 4"* — i.e. the area floor was combined (`min`) and ENFORCED by the
gateway against MiniMax-M3 (tier 4). This is the mechanism working, but it proves a stronger area
floor makes Commercial unusable with the only S9-qualified model. **Fix:** Commercial seeds no
area floor (NULL); the floor is operator-set via `PATCH` once a qualifying model lands
(model-compatibility.md, S9). After `PATCH default_tier_floor=null`:

## Per-area Deep Agent grounds a real run (the headline)

A real MiniMax-M3 run on a Commercial-filed matter, prompt *"In one sentence, what kind of legal
work do you handle?"* → **completed**, answer verbatim:

> I handle commercial agreements — NDAs, MSAs, SOWs, DPAs, and their renewals and amendments —
> for the in-house legal team on a matter-by-matter basis.

The answer reflects the seeded area profile directly — the area profile reaches the system prompt
and shapes the agent's identity, end-to-end through the gateway. (`<think>` block round-trips
verbatim per the gateway contract.)

## Suites

- Containerized api (throwaway pgvector @ alembic head incl. 0054): full suite green
  (counts in the PR); affected suites re-run on a FRESH pg after the tier-seed fix:
  test_practice_areas + test_agent_composition + test_area_agent **38 passed**.
- Migration verified upgrade → downgrade → re-upgrade on throwaway pg.
- web: `npm run check` 0 errors; vitest 781; ruff/prettier/eslint clean.
- Adversarial review (6 dimensions incl. a dedicated gateway-bypass security pass): 26 agents,
  16 confirmed / 4 refuted / 0 pre-existing. **1 blocker fixed**: null-area matters (51/54 live)
  were invisible in the cockpit — AreaGrid now renders an "Unfiled matters" section
  (`after-landing-unfiled-matters.png`); 9/9 cockpit specs still pass. Should-fixes fixed:
  strict `agent_config` top-level schema (unknown keys rejected, playbooks/mcp_servers
  by-reference no-creds), matter-activity area-projection API tests, docstring 400. Nits
  deferred on record (HANDOFF): subagent-skill registry validation (skills not live this slice),
  audit/projects index coverage (slicing not queried yet). The gateway-bypass guard found NO
  live bypass (the stored-config top-level gap was latent defense-in-depth, now closed).
- After the fix, the landing shows Commercial with its filed matters AND the "Unfiled matters"
  section keeping legacy matters reachable.
