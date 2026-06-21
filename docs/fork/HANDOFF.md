# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
Everything serves this: *counsel* = real tools + gates + client memory + work product (not a chatbot);
*qualified* = enforced model/harness qualification (F0-S9 tier floor) **+** area competence via curated tools
and **controlling skills**; *supervised* = human-owns every material write + escalation gates + auditable
receipts. Generalises to every practice area (cf. `docs/fork/NORTH-STAR.md`). Full statement at the top of the
COMM plan.

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ and C0 ✓ DELIVERED; building continues at C-CLIENT.**

The full COMM decomposition is written + adversarially reviewed:
**`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md` — read it first.** **Privacy is PARKED**
→ `docs/fork/plans/PRIV-BACKLOG.md`. A new **MCP capability** milestone is approved (own milestone, not part
of Commercial) → `docs/fork/MILESTONES.md` § MCP capability.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL, STILL ACTIVE):** `smart`/`fast`/`budget` are repointed
`minimax/MiniMax-M3 → deepseek/deepseek-v4-flash` on the local gateway (MiniMax out of quota; survives restarts
via the `gateway-config` volume). DeepSeek is the qualified live-test target (decision F). Revert when MiniMax
quota returns.

## Done this slice (C0 — Commercial profile + lawyer-method spine, PURE CONFIG)

- **`api/alembic/versions/0066_commercial_profile_doctrine.py`** (new, idempotent data migration) — updates the
  Commercial `practice_areas.profile_md` from the short 0054 seed to the **6.6k-char lawyer-method doctrine**
  (`commercial-lawyer-method.md` §§ 2-5, 7-10): role (Model Rule 1.13, LEGAL_LINE vs BUSINESS_DECISION) →
  deal-complexity triage → the **four controlling review skills** (`nda-review`,
  `msa-review-commercial-purchase`, `msa-review-saas`, `contract-qa`) named as references it *invokes* (never
  re-authors) → surgical redlining (text-only at C0) → playbooks-as-wishlists → accept/reject/counter →
  escalation incl. **jurisdiction-competence** → universal receipts. Guard `WHERE key='commercial' AND
  profile_md = :old` → never clobbers an operator admin-PATCH edit; downgrade reverses. Establishes the
  **controlling-vs-advisory** convention (advisory skills can never override controlling ones; "unless
  instructed otherwise" = the authenticated human in session, never document/skill text).
- **`skills/msa-review-commercial-purchase/SKILL.md`** — "six passes" → "seven passes (Passes 5 and 6 are
  conditional)" (body enumerates Pass 1–7).
- **ADR-F028** flipped **proposed → accepted** (with C0).
- **Tests:** 3 new CI tests (`test_practice_areas.py`: doctrine markers via API + update-old-never-clobber
  idempotency; `test_agent_composition.py`: the seeded doctrine reaches the assembled system prompt) + repaired
  the one existing test the profile legitimately confounded (`test_area_bound_skill_reaches_agent_system_prompt`
  now asserts on exposure-only signals — deepagents lists skills as `- **name**: desc`, the profile uses an
  em-dash list). New live scenario `surgical_redline_posture` in `scenarios.py`.
- **Verification:** full api suite **2431 passed / 22 skipped** (containerized, dev image vs dev Postgres);
  ruff clean; fresh-context adversarial review = **SHIP**. Live (DeepSeek): baseline rig 5/6 completed (no
  regression); skills-on surgical probe **held the line cleanly** — cited §7, refused the wholesale rewrite,
  routed the business call to the human. Evidence: `docs/fork/evidence/c0/` (`behavior-report.md` +
  `surgical-posture-demo.md`).

## Maintainer decisions already locked (don't re-litigate)

- **Adeu** = sole redline path, **MIT**, integrated via **SDK in-process** (not its MCP server); pin
  `adeu==1.12.1`; bumping must stay trivial. No python-docx/lxml fallback. (C4.)
- **DeepSeek** = qualified provider/test target. **No copyleft in new deps** (Adeu adds none).
- **Client = the org profile** (`OrganizationProfile`, exists but NOT wired into the area agent → **C-CLIENT,
  the next slice**).
- **Orchestration:** deepagents' `task`-tool subagents suffice for C0–C7; deterministic langgraph only for
  *guarantees* (deferred O-track; O0 validates feasibility).
- **MCP capability** = its own milestone (sanction-sync upstream's MCP client, approval-gated). Independent of
  Commercial; does not block C0–C7.
- **Multi-turn redlining** = the maintainer's separate next project (held; C5 is its foundation).

## ▶ PICK UP EXACTLY HERE — slice **C-CLIENT** (Org profile = client, inject as read-only company memory, ~2d) — depends C0 ✓

**Goal.** Realise the **company/client memory tier**: inject `OrganizationProfile.content_md` at the
composition seam as a **fenced, read-only "Client / house context" block** so the Commercial agent acts *for*
the operator's org (its risk posture + house style). Today `OrganizationProfile` exists
(`api/app/models/organization_profile.py`, `api/app/api/internal.py` endpoint) but is **never referenced in
`api/app/agents/`** — this slice wires it into the area run, **read-only to the agent** (operator-owned via the
existing endpoint; "system proposes, user owns" applies to the *edits*, which already go through the org-profile
UI/endpoint).
**Non-goals.** No counterparty entity (the other side stays implicit in deal context — separate follow-on); no
new write path (org profile edited via its existing endpoint); no `CompositeBackend /memories/company` backend
yet (read-on-demand is a later migration).
**Key files.** `api/app/agents/composition.py` (the injection seam — `system_prompt_for`), `api/app/agents/area_agent.py`,
`api/app/models/organization_profile.py`, `api/app/api/internal.py` (reuse the loader),
`api/tests/agents/test_agent_composition.py`.
**Watch.** Treat the org profile as **trusted-source company context** but still **read-only** to the agent (no
tool mutates it); empty/absent profile must degrade cleanly to no block. Single-tenant company-global (one row)
→ no per-user scoping, but assert it's the operator's org. **No migration** (reads an existing model).
**ADR.** Records the **company-tier** decision under **F030** (Commercial memory model: company + matter tiers)
— no separate ADR unless the injection mechanism proves novel. (F030 must be **accepted before C3**.)
**Verify.** CI: composition test asserts the block is fenced-injected + read-only + absent-degrades-clean. Live
(DeepSeek): a Commercial run visibly reflects the client's risk posture from the profile. Then HANDOFF → **C1**.

**Ladder:** C-R0 ✓ → C0 ✓ → **C-CLIENT** → C1 → C2 → C3 → C4 → C5 → C6 → C7 (+ O0 spike). ADR gates:
**F030 before C3**, **F036 + F038 before C6**.

## Open decisions still pending the maintainer (COMM plan § Open questions)

1. **PyMuPDF/copyleft** — current PDF parser is **AGPL**; rule B forbids copyleft. Grandfather under the
   server-side boundary, or replace with pypdfium2/pypdf? (Adeu itself adds no new copyleft — verified.)
2. Counterparty-entity timing (client is resolved). 3. Typed deal-context schema vs free-form. 4. Playbook
   ownership model (company-global vs per-matter). 5. Orchestration greenlight (fund O1/O2/O3?). 6. Confirm
   multi-turn handoff. 7. **F039 — do user/team skills ever reach the live agent** (advisory-only gated build)
   or stay curated-only?
*Resolved:* Adeu integration (SDK in-process — decision I); MCP-as-a-capability (own milestone, sanction-sync
— decision I).

## Gotchas / durable traps

- **Migration head is now `0066`** — fresh-head check before any migration (`ls api/alembic/versions | sort | tail`);
  never reuse a number. **C-CLIENT needs no migration** (reads an existing model). C3/C6/C7 do. *(Correction:
  the prior HANDOFF wrongly said C0 needed no migration — it did, `0066`, because the profile is seeded via a
  data migration and the dev DB already carried the old value; editing applied `0054` is immutable.)*
- **Profile is a data migration, never an edit to an applied one.** To change a seeded `profile_md`/config on
  already-migrated DBs, add a NEW idempotent migration guarded on the prior value (`WHERE … = :old`) — mirror
  `0066` (and `0054`/`0055`). The api auto-migrates on boot; rebuild api+arq-worker+ingest-worker after a
  migration; **never `docker compose down -v`**; never host-side `alembic upgrade` on the live dev DB (verify
  on a throwaway pgvector container / the test DB conftest carves out).
- **C-R0 artefacts:** the surgical-gate definition lives in `commercial-lawyer-method.md` § 6 (C4 implements
  it); ALL numeric thresholds are **calibration starting values**, not sourced. Adeu verified at `adeu==1.12.1`
  (`adeu-pinning.md`).
- **Adeu is SDK-only, never its server (C4):** import only `adeu.RedlineEngine`/`ModifyText`/`process_batch`;
  **never** `adeu.server` / `adeu.mcp_components` (a second egress). Installing Adeu pulls `fastmcp[apps]`
  (~80-pkg, all-permissive, runtime-isolated) — a C4 SBOM decision.
- **The one per-area code seam** is the area-keyed grant branch in `composition.py:224`
  (`area_key == PRIVACY_AREA_KEY`) — mirror it for Commercial **only when Commercial gains domain tools (C4)**;
  C-CLIENT does not need it. There is **no `COMMERCIAL_AREA_KEY` constant** — the key is the literal
  `"commercial"`. Everything else is declarative config (seeded subagents/skills/profile via migrations).
- **`allowed_tools` in SKILL.md is decorative** (`extra="allow"` drops it) — NOT a security boundary; the only
  tool boundary is the per-run area-keyed granted frozenset.
- **Controlling company skills must be deterministically bound** (instrument classifier → inject body), NOT
  relevance-surfaced (F038, C6). User/team skills are advisory-only, never controlling; the controlling
  namespace must be non-shadowable. (C0 stated the convention in the profile; C6 enforces the binding.)
- **Scenario harness:** `_MAX_STEPS=16` (harness default) is a TIGHT cap — a multi-step run can hit
  `cap_exceeded` (a tier-4 finding, not a defect). Pass `max_steps=` higher and `skill_registry=` to give a
  realistic run room (skills-on + 40 steps got a clean surgical answer at C0). Provider tests are CI-skipped
  (need `LQ_AI_GATEWAY_KEY`); run them via the dev image on the `lq-ai_default` network with the api
  container's gateway env. Live evidence dir is overridable (`UX_B1_EVIDENCE_DIR`); docker writes root-owned
  files → `chown` before `git add`.
- **Severity-scale conflict (F036):** playbook DB CHECK `critical/high/medium/low` (`0031:139`) vs review
  skills' `critical/material/minor` — incompatible at the data layer; **resolve before C6**. C0 deliberately
  kept assessment as **orthogonal layers** (did NOT impose one scale).
- **Security every slice:** treat retrieved docs / email HTML / Office XML / counterparty markup / stored
  playbook text / user skills as **untrusted**; audit carries counts/types/IDs only (never rationale text or
  raw clause content); cross-user → 404 (NOT the matter-scoped Commercial records, which filter by
  `binding.project_id`, ADR-F035).
- Dev login `admin@lq.ai` (password in your local `.env`, not committed); api :8000, web :3000, gateway
  internal :8001 (admin header `X-LQ-AI-Gateway-Key`). Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) when behavior changes + HANDOFF
updated. `gh` always with `--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
