# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ C8 ✓ DELIVERED. Pickup = maintainer's call (C3 deal-context · C5 · C6 · C7).**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns.

## Done this slice (C8 — surgical-redline craft; ADR-F041; migration 0067)

**Decision (settled with the maintainer in-session):** surgical *craft* is a **prompt-quality property tuned
by eval, not a runtime gate**. Rejected D7 (a deterministic single-region rule — Adeu already renders each
edit surgically) and a mandatory per-run LLM critic (too slow). Integrity stays with C4's D1-D6 gate; Adeu
renders; the human owns the accept.

- **`skills/surgical-redline/SKILL.md`** (NEW) — the curated abstract-method craft skill: decompose a clause
  into several narrow edits, keep recognisable boilerplate (`shall indemnify, defend and hold harmless`, the
  cap stem) **bare**, fold insertions into the boundary, preview-then-apply. Worked §8/§9 before/after.
- **`api/alembic/versions/0067_commercial_surgical_redline_skill.py`** (NEW) — binds `surgical-redline` to
  Commercial (`practice_area_skills`) + refreshes the stale "lands in a later slice" tail of `profile_md` to
  point at the tools/skill. Idempotent never-clobber (`REPLACE ... WHERE POSITION(:old)>0` + `NOT EXISTS`).
- **`api/app/agents/commercial_tools.py`** — NEW guarded **`preview_redline`** tool (dry-run + reconstruct,
  **persists nothing**) for self-review; shared `_render_redline` pipeline (validate→fetch→gate→dry-run→apply)
  reused by apply + preview; **editor-error hardening** (Adeu raises → fix-and-retry, never a 500).
- **`api/app/agents/redline_render.py`** — added shared `bare_text` + `docx_text` (one definition; de-dup).
- **Eval (the maintainer's "run enough tests"):** `tests/agents/scenarios/test_commercial_redline_eval.py`
  (NEW, provider-marked) runs a 2-doc corpus (`securescan_msa` + new `databridge_license`) × N reps, judges
  craft with a sharpened rubric, writes the **surgical-craft rate** to `docs/fork/evidence/c8/`. Shared
  scaffolding in `commercial_redline_lib.py` (seed+real-cleanup, capture, judge) — this **fixed the C4
  live-test `_noop_cleanup` leak**.
- **ADR F041** (proposed). Plan `docs/fork/plans/C8-surgical-redline-craft.md`.
- **Verification:** ruff + mypy clean; **71** touched-area tests pass; full api suite **2526 passed / 2
  skipped** (lone failure = the documented env-sensitive `test_ready_reports_per_dependency_status`, which
  asserts deps are *unreachable* — they're up on the dev network; unrelated to C8, passes in CI).
  **Live eval (DeepSeek, 3 reps):** overall **2/6** surgical-craft passes; in-distribution SaaS MSA **2/3**;
  **§8 indemnity surgical in the passing runs** (boilerplate bare); boilerplate-bare in **4/5** redlined
  runs. NOT yet "reliably surgical" (out-of-distribution licence weaker; 1/6 produced no redline) — a
  model-bound ceiling, honestly recorded in `docs/fork/evidence/c8/README.md`. **Adversarial review (13
  agents) → SHIP-WITH-FIXES, 0 blockers**; all 6 findings fixed (helper de-dup, matter-scoped capture,
  idempotency operator-edit case, registry type, evidence consistency).

## ▶ PICK UP EXACTLY HERE — slice **C9 — Claude-judged manual redline tests (5 agreements)** (maintainer steer, 2026-06-22)

**Why:** C8's eval used DeepSeek as its own craft-judge (weak signal — same model). The maintainer wants a
**stronger judge: Claude (this agent) judges whether DeepSeek's redline is lawyer-like**, over **5 full (but
concise) agreements**, with the **produced `.docx` files surfaced for the maintainer to review**.

**Scope:** (1) a corpus of **5 concise but complete** vendor-favoured agreements (extend the C8 corpus —
`securescan_msa`, `databridge_license` + 3 more instruments: e.g. NDA, DPA, professional-services SOW); (2)
run DeepSeek on each under **purposive instruction** (the agent redlines to protect the client); (3) **the
agent (Claude) judges each produced redline** for lawyer-like surgical craft — *not* DeepSeek-judging-itself;
the manual/Claude judgement is the point; (4) **save every redlined `.docx` to an evidence dir** the
maintainer can open and review. Reuse C8's `apply_redline`/`preview_redline` + `seed_doc_matter`/
`capture_redline` + the reconstruction; the new piece is the corpus breadth + the Claude-as-judge step +
packaging the `.docx` deliverables. Likely no migration. Read memory `claude-judged-redline-tests-slice`.

**Other COMM slices (after C9, maintainer's call):** **C3** deal-context matter memory (first Commercial
migration now **`0068`** — C8 took 0067; mapping done) · **C5** negotiation rounds (needs C3+C4) · **C6**
controlling playbook skills (needs F036+F038) · **C7** complex-deal fan-out (50-page docs + redline budget
tier). **C8 follow-ups** (optional): broaden the skill's worked examples beyond MSAs (out-of-distribution
craft weaker); investigate the ~1/6 no-redline runs; re-run the C8 eval when a stronger model is qualified.

## Gotchas / durable traps (C8 + C4 + carried)

- **C8 — Adeu crashes on a PURE zero-width insertion** (`new_text` that merely appends after an unchanged
  anchor → `Op=INSERTION at [n:n]` → `AttributeError` in `adeu/redline/engine.py`). Fold an addition into
  the **boundary** instead (end the anchor at the clause's punctuation, replace it and continue — the working
  §9 carve-out shape). The skill teaches this; `preview_redline`/`apply_redline` catch the crash and return
  `_EDITOR_ERROR_MSG` (no partial write). Golden/skill examples MUST use the boundary pattern.
- **C8 — the surgical-craft eval is provider-marked** (`test_commercial_redline_eval.py`): run live with
  `LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_REDLINE_EVAL_REPS=N UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c8`.
  It regenerates ALL eval files in one run — if a (doc,rep) yields no redline, no per-rep file is written, so
  reconcile the dir against `eval-report.json` before committing (delete stale files from a prior run).

- **Adeu is installed `--no-deps`** (4 places: api/Dockerfile, api/Dockerfile.dev, ci.yml, + any dev-image test
  command). Its `fastmcp[apps]` dep bumps starlette 0.48/pydantic 2.13/mcp → breaks `APIRouter`. The SDK
  (`RedlineEngine`/`ModifyText`/`process_batch`) needs only `diff-match-patch` + `structlog` (+ lxml/python-docx
  /rapidfuzz/pydantic already in-tree). **Dev-image test commands MUST `pip install diff-match-patch structlog`
  + `pip install --no-deps adeu==1.12.1`** or `from adeu import …` fails `ModuleNotFoundError: structlog`.
- **`apply_redline` redlines the named doc FRESH each call (no stacking)** — the agent must pass ALL edits in
  ONE batched call (the tool docstring says so). Multiple calls each re-redline the ORIGINAL → only the last
  call's edits survive in its output File. For long docs needing >50 edits/call → chain on the prior output or
  fan out (C7). A redline run is step-intensive; ADR-F026 budget is 100 steps/900s (fine for one batched
  single-doc redline; **50-page docs need C7 fan-out + a redline budget tier** — recorded as a finding).
- **`max_steps` is API-capped at `le=100`** (`schemas/agent_runs.py`); the harness sets it directly on the
  AgentRun row (bypasses the schema), so live scenarios can exceed 100 if needed — but production is 100.
- **Killed-container test-DB contamination:** killing a `docker compose run` suite container mid-run leaves the
  reused test DB dirty (leftover admin/session rows) → spurious CLI/audit/last-admin failures on the next run.
  Re-run the suspect files in a FRESH container to confirm. The `test_ready_reports_per_dependency_status`
  health test is separately env-sensitive (passes isolated; "fails" on the live network).
- **Provider tests need the gateway key UNSET to skip:** `docker compose run api` inherits `LQ_AI_GATEWAY_KEY`
  from the api service env, so the full suite would RUN the provider tests (slow/hangs on real gateway calls).
  Run the regression suite with `-e LQ_AI_GATEWAY_KEY= -m 'not provider and not e2e'`.
- **Live redline scenario:** `tests/agents/scenarios/test_commercial_redline_scenario.py` (provider-marked) seeds
  the real `securescan_msa.build_msa_docx()` into MinIO + runs DeepSeek + writes `.docx`/reconstruction/
  accept-clean/judge to `UX_B1_EVIDENCE_DIR`. The judge's input was truncated at first (false WEAK); caps are
  now generous (must fit the full redline). Run via the dev image on `lq-ai_default` with the api gateway env +
  `UX_B1_EVIDENCE_DIR` mounted; `chown` the root-owned evidence before `git add`.
- **Migration head is still `0066`** (C4 added none — output is a `File` row). **C3 adds `0067`.** Fresh-head
  check before any migration; rebuild api+arq-worker+ingest-worker after one; never host-side `alembic upgrade`
  on the dev DB; never `compose down -v`.
- **The per-area grant seam** is `composition.py` (`area_key == PRIVACY_AREA_KEY` / now `== COMMERCIAL_AREA_KEY`).
  `COMMERCIAL_AREA_KEY = "commercial"` lives in `commercial_tools.py` (mirrors `PRIVACY_AREA_KEY` in ropa_tools).
- **Dev-image suite/lint recipe:** `docker compose run --rm --no-deps --entrypoint bash -v "$PWD/api:/app"
  -v "$PWD/skills:/skills" -v "$PWD/ruff.toml:/ruff.toml" -e LQ_AI_SKILLS_DIR=/skills api -c "pip install -q
  pytest pytest-asyncio respx mypy types-PyYAML 'ruff>=0.6' diff-match-patch structlog && pip install --no-deps
  adeu==1.12.1 && <cmds>"`; `chown -R $(id -u):$(id -g) app tests` after. CI ruff = `ruff>=0.6`; format with it
  before pushing (version drift). `mypy app` via unpinned mypy false-flags `ropa_export.py`/`tabular.py` — ignore.
- Dev login `admin@lq.ai` (password in local `.env`, not committed); api :8000, web :3000, gateway :8001.
  Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`. Adeu SDK-only — never `adeu.server`/`adeu.mcp_components`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) when behaviour changes + HANDOFF
updated. `gh` always `--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
