# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (end of F1-S3 — practice areas are real agent identities)

- **F1-S3 merged via PR #46** (or merging — confirm on main): `practice_areas` config
  vocabulary + per-area Deep Agent + cockpit filing. Plan:
  `docs/fork/plans/F1-S3-practice-area-config-deep-agent.md`. New ADR: **F010**
  (gateway-only model binding; model-bearing subagent specs rejected). Follows F1-S2.1.
- Dev stack: 8 services healthy; **DB at 0054** (api auto-migrated on boot); api +
  arq-worker + ingest-worker + web rebuilt together on slice code. Login:
  http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (the ONLY S9-qualified model,
  **tier 4**). CALL-based token plan.
- Suites at gate: web check 0 errors + vitest 781; api containerized green at alembic
  head incl. 0054 (full suite was 2056-passing pre-review-fix; affected suites re-run
  on fresh pg after fixes: 41 passed); migration verified upgrade/downgrade/re-upgrade.
  CI: confirm green on the final commit before merge. Adversarial review: 26 agents,
  16 confirmed (1 blocker + should-fixes ALL FIXED), 4 refuted, 0 pre-existing.
  Evidence: `docs/fork/evidence/f1-s3/`.

## Done (F1-S3, this slice)

- **Schema 0054** (additive, reversible): `practice_areas` += `profile_md`,
  `default_tier_floor` (1–5 CHECK), `agent_config` JSONB; `projects.practice_area_id`
  (nullable FK SET NULL; CHECK forbids it on sandboxes; partial index);
  `audit_log.practice_area_id`; `practice_area_skills` join. Commercial seeded with a
  real profile + **NO area tier floor** (see Gotchas — a floor would break it with the
  tier-4-only model).
- **Per-area Deep Agent** (`api/app/agents/area_agent.py`, one renderer): area row →
  system-prompt suffix (profile) + tier floor (min-combined API-side) + declarative
  subagents. **ADR-F010 guard at `build_deep_agent`**: rejects any subagent `model`
  string (gateway bypass via `init_chat_model`); `agent_config` strict top-level schema
  (unknown keys rejected; playbooks/mcp_servers by-reference, no creds). Composition
  folds profile/tier/subagents, threads `practice_area_id` into guard+audit.
  **Proven live**: a real MiniMax-M3 run answered in-character from the Commercial
  profile; a model-bearing PATCH → 400.
- **Config/admin API**: GET reads carry profile/config (transparency); `PATCH /{key}`
  + skill attach/detach are admin-only; 404-not-403; sandbox `project_id` rejected at
  `POST /agents/runs`.
- **Cockpit**: matters file by area; `/agents/matters` carries `practice_area_id/key`;
  AreaGrid counts per area + an **"Unfiled matters"** section keeps legacy/null-area
  matters reachable (review blocker fix); MattersPanel shows only the area's matters;
  NewMatterDialog files under the area; `configured` derived.

## Next slice — pick up exactly here

1. **Legacy-surface design rollout** (maintainer point c from S2.1; order ratified in
   the S2.1 plan §Goals-3): **wave 1** = ConversationPanel markup/typography + the
   ChatPanel tree (restyles chats, matters workspace, agents tab, cockpit pane); then
   **wave 2** knowledge/skills/playbooks/tabular; **wave 3** settings/admin/trust/
   saved-prompts/learn (+ `autonomous/` only if it survives F2/F3) + `(tools)` chrome.
   Sequence with the maintainer against F1-S4/S5.
2. **F1-S4** (subagent tree + SSE v3-projection adapter) and **F1-S5**
   (`(run_id, tool_call_id)` idempotency ledger + attribution fan-out) — see
   `docs/fork/plans/F1-replan.md`. S4 consumes deepagents v3 `stream_events` typed
   projections to render the per-area subagent tree S3 stood up.
3. **Area skills / subagents ACTIVATION** (S9-gated): S3 landed the config + renderer +
   guard but does NOT attach SkillsMiddleware or pass subagents for Commercial (seeded
   with none) — attaching them changes the harness profile, which **re-runs the S9
   qualification matrix** (`docs/fork/model-compatibility.md`). The activation slice
   wires `composition.py` to pass area skills/subagents into the live agent AND adds the
   qualified matrix row. The machinery + security guard already ship and are tested.
4. Every slice: explore → written plan (docs/fork/plans/…) → implement → full ADR-F005 gate.

## Carry-overs / review deferrals

- **NEW (F1-S3 review, deferred on record)**: subagent-spec skill names bypass registry
  validation (skills not live-attached this slice — validate on the activation slice);
  `audit_log.practice_area_id` has no index + the `projects` partial index doesn't cover
  the FK-delete scan (per-area audit slicing isn't queried yet — add an index when it is);
  `CompiledSubAgent`/`AsyncSubAgent` dicts aren't guarded (out of scope — the renderer
  only emits declarative dicts).
- **Area tier floor is operator-set** until a model stronger than tier 4 is S9-qualified
  (Commercial seeds none — a floor stronger than 4 makes every run fail
  tier_below_minimum; the gateway enforces it, proven live).
- auth/refresh hardening (HMAC index + injected semaphore; dev session prune needs
  maintainer approval — 186 rows) — legacy-bugfix candidate.
- ADR-0011 disclosure on the agent surface — after F1-S5's attribution extension.
- Live SSE token deltas DEAD until a Redis pub/sub publisher lands — ride F1-S4.
- Flood brake counts queued-unclaimed runs (ADR-F009). Ingest orphan recovery
  startup-only (cron sweep Backlog). Mismatch read-noise metric / L2 judge seam — S9.
- ADR-0011/F003 conversation memory + compaction — F2. Cypress pre-existing reds:
  wave-b Enhance-Prompt + skill-detail, wave-c chat-in-matter (control-proven).

## Gotchas (carried + new)

- **NEW: the only S9-qualified model (MiniMax-M3) is tier 4 (weak).** Any
  `default_tier_floor` < 4 on an area makes EVERY run under it fail the gateway's
  `tier_below_minimum` (403). Seed areas with NO floor; operators set one when a
  stronger model qualifies. The floor MECHANISM works (gateway min()-combines + enforces
  — proven live).
- **NEW: deepagents 0.6.8 subagent `model` is a gateway-bypass vector** — a STRING model
  → `init_chat_model` → direct provider SDK. App-authored subagents OMIT `model` (inherit
  the gateway-bound parent instance). The guard lives at `factory.build_deep_agent`
  (single deepagents import site) — ADR-F010. Inheritance (verified vs source):
  permissions REPLACE, tools OVERRIDE-on-presence-else-inherit, middleware never inherits
  (fresh stack per subagent).
- **NEW: attaching area skills/subagents to the LIVE agent changes the harness profile →
  re-run the S9 matrix** (model-compatibility.md "re-run on any deepagents change").
  S3 deliberately does NOT do this for Commercial.
- **NEW: null-practice-area matters need a home in the cockpit** — they're NOT in the
  unfiled-CONVERSATIONS bucket (that's threads without a matter); AreaGrid's "Unfiled
  matters" section surfaces them. Don't filter them to nowhere.
- **NEW: agent_config is operator input — keep it strictly validated** (build_area_subagents
  rejects unknown top-level + per-subagent keys, forbids `model`, forbids credential keys
  in playbooks/mcp_servers). Validate on BOTH write and render.
- **NEW: prettier reformats whole legacy files** (practice.css 2-space → tabs) — format
  ONLY new-code files; restore legacy files byte-identical. **ruff** needs the repo-root
  ruff.toml (run from /repo, not /work) — line-length 100, else it flags 234 files.
- **NEW: ValidationError → 400** (not 422; Pydantic boundary errors are 422). agent_config
  shape rejection is 400.
- migrations: NEVER host-side alembic against the live dev DB — verify on throwaway pg
  (recipe below), api auto-migrates on boot; rebuild api+arq-worker+ingest-worker
  together + web. Fix a live row via the admin API, not host alembic.
- New API endpoints register in tests/test_openapi.py (count assert — now **129**) +
  tests/test_endpoints.py IMPLEMENTED_ROUTES. Containerized pytest needs `/skills`
  mounted (migration 0032 seed).
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork`
  AND `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3.
  Host Python 3.11; api/gateway need 3.12 — all py tooling in containers.
- Throwaway-pg recipe:
  ```bash
  docker run -d --name s3pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s3pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```
- NEVER `docker compose down -v`. headless cypress captures lie about dark theme — capture
  headed. cockpit panel re-homing: keep the `{#key}` STABLE for the panel-created thread.
- MiniMax-M3 emits `<think>` inline + a `reasoning` delta; both round-trip verbatim.
  GET /agents/runs/{id} returns `{run, steps}`.
