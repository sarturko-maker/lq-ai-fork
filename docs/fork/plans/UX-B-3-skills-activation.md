# UX-B-3 — Skills activation (S9). Plan.

Milestone: **UX-B** (Deep Agents truly work / cockpit perfect), gate **ADR-F015**. Decomposition:
`UX-B-deep-agents-truly-work-decomposition.md` §UX-B-3. Builds on UX-B-2 (5 areas configured on a clean
matter-tool surface). MiniMax-M3 is the DI model (tier-4-weak).

## What "skills activation" actually is (corrects the HANDOFF premise)

`SkillsMiddleware` adds **no tools**. It loads skill *metadata* from a deepagents **backend** and injects
each skill's name/description/path into the system prompt (progressive disclosure); the model reads the
full `SKILL.md` on demand via the deepagents **builtin `read_file`** tool. Our agent already carries the
builtin filesystem tools (`ls`/`read_file`/`glob`/`grep`/`write_file`/`edit_file`/`execute`/`task`/
`write_todos`) over an empty in-memory `StateBackend()` (deepagents default). Those builtins are **not**
wrapped by our `guarded_dispatch` chokepoint — only the two matter tools are (extending the guard to the
full tool universe is F1's job, `runner.py:546-551`). So the slice's security posture comes from
**constraining the backend the builtins see**, not from the guard.

## Decision (maintainer-ruled 2026-06-16) — registry-backed virtual backend

One skill **library** (the in-memory `SkillRegistry`, loaded once per process; MD files users add land there
via the loader). **No duplication**: areas reference skills **by name** (`practice_area_skills` m2m); nothing
is copied per area. An agent is **never** exposed to the whole library (the maintainer's "all skills confuses
it"): a per-run **virtual backend** over the registry exposes **only the area's bound subset** as a virtual
`/skills/<name>/SKILL.md` tree. Relevant skills land in each area **by default** (seeded bindings); users
**extend** via the existing admin attach endpoint. Same by-reference `agent_config` slots already exist for
**playbooks** and **MCPs** — this generalizes to them later (the redlining MCP rides the MCP plumbing slice;
**out of scope here**, noted forward in ADR-F016).

Why backend-over-registry beats the alternatives: tightest least-privilege (`read_file` reaches the bound
subset and nothing else — no host FS, no matter data, no unbound skills), zero-copy per run (most efficient),
and it closes the registry-drift gap structurally (a bound name the registry forgot simply isn't in the
backend). Rejected: FilesystemBackend-at-`/skills` (exposes the *whole* library to every agent — the
confusion the maintainer warned against + a wider injection surface); per-run seeded StateBackend (copies
skill bodies into every thread checkpoint — duplication at runtime).

## Goals / non-goals

**Goals:** bound skills reach the live agent via the virtual backend; relevant skills bound per area by
default; harness re-qualified with skills on (committed report); drift gap closed; ADR-F016.

**Non-goals (noted forward):** playbooks + MCP plumbing (incl. the redlining MCP) — the `agent_config`
by-reference slots stay validated-but-unconsumed; extending `guarded_dispatch` to the builtin filesystem
tools + R4 budgets (F1); the cockpit skills UX / slash-command skill invocation (UX-B-5 / later); live
subagents (UX-B-4, `agent_config={}` stays).

## Files

- **`app/agents/skill_backend.py` (NEW)** — `RegistrySkillBackend`, a read-only `BackendProtocol` adapter over
  a `SkillRegistry` snapshot + an explicit allow-list of skill names. Serves a virtual tree
  `/<root>/<name>/SKILL.md` (body = the registry record's reconstructed `SKILL.md`). Implements `ls/als`,
  `download_files/adownload_files`, `read/aread` (+ `glob/grep` as needed by the middleware). Mutations
  (`write/edit/upload/execute`) return a read-only error — the library is curated. A bare factory
  `build_area_skill_backend(registry, names)`; the single deepagents-`BackendProtocol` import site (the
  `factory.py` "absorb churn here" posture).
- **`app/agents/area_agent.py`** — `render_area_agent` already filters `bound_skill_names` to
  `known_skill_names`; keep. `build_area_subagents` gains a `known_skill_names` param and validates each
  subagent's `skills` entries against it (close the drift gap the HANDOFF named) — surfaced at PATCH time.
- **`app/agents/composition.py`** — new `skill_registry_provider` injection seam (default reads the
  worker/api `app.state.skill_registry` holder, the autonomous-executor precedent). Load the area's
  `practice_area_skills` names; render with `bound`/`known`; when the rendered `skills` is non-empty build the
  backend over that subset + the source path and thread `skills=[source]` + `backend=` into
  `execute_agent_run`. Drop the `bound_skill_names=[]` stub at :151.
- **`app/agents/runner.py` / `factory.py`** — thread `skills` + `backend` through `execute_agent_run` →
  `build_deep_agent` → `create_deep_agent`; ADR-F010 subagent guard still runs.
- **`alembic/versions/0056_default_area_skill_bindings.py` (NEW)** — idempotent seed of default
  `practice_area_skills` (insert-only-when-absent; symmetric downgrade removes only the seeded pairs). Default
  mapping (focused, to avoid the "too many skills" confusion — user-extendable):
  - Commercial: `msa-review-commercial-purchase`, `msa-review-saas`, `contract-qa`, `nda-review`
  - Privacy: `dpa-checklist-review`, `vendor-privacy-policy-first-pass`, `contract-qa`
  - M&A: `nda-review`, `contract-qa`, `contract-snapshot`
  - Disputes: `contract-qa`, `action-items-from-client-alert`
  - Employment: `contract-qa`, `nda-review`, `action-items-from-client-alert`
  (`enhance-prompt`/`skill-creator`/`playbook-easy-extract`/`*-snapshot`/`comms-improver` stay
  user-attachable, not default — system/meta or niche.)
- **`docs/adr/F016-skills-activation-registry-backend.md` (NEW)** — the decision above + the
  unguarded-builtin/backend-bounding security rationale + the playbooks/MCP forward path.
- **Tests** — `tests/agents/test_skill_backend.py` (ls/read/subset-isolation/read-only/drift); composition
  wiring test (skills + backend passed iff bound, empty → unchanged graph); `test_area_agent.py` drift
  validation; `tests/test_migration_0056*` idempotency; update `test_practice_areas` if list shape shifts.
- **Harness** — add a skills-on scenario to `area_fixtures.py` (Commercial: a prompt whose best path is to
  recognise + read + apply a bound review skill against the synthetic MSA). Commit
  `docs/fork/evidence/ux-b-3/` report. Per ADR-F015 a shape-miss is a finding, not a gate.
- **`docs/fork/HANDOFF.md`** — rewrite top entry + Next slice → UX-B-4.

## Security pass (this slice earns the deeper one)

- The builtin `read_file`/`ls` are unguarded — **bounded by the backend**: `RegistrySkillBackend` is
  read-only, serves only the allow-listed names, no host FS, no matter data. Assert the isolation in a test
  (a name not in the allow-list 404s; mutations refused). Note in ADR-F016 that wrapping the builtins in
  `guarded_dispatch` + R4 is the F1 universe-wrap, deliberately out of scope.
- Skill content = curated **but untrusted** model input (prompt injection): it stays read-only and
  registry-sourced; company/practice memory remains read-only to agents.
- Drift: subagent-referenced skill names validated against the registry at config time (close the gap).
- No secrets in the backend, reports, audit, or fixtures (re-scan).

## Verification

Containerized api suite (Dockerfile.dev image, mount `api/`→`/app` + `skills/`→`/skills:ro`) — counts quoted;
ruff+mypy clean. Migration on the conftest throwaway test DB only. Dev stack: migrate 0055→0056 (rebuild
api+arq-worker+ingest-worker together; never `down -v`/host `alembic upgrade`). Live skills-on harness report
committed. Fresh-context adversarial + security + simplification review. Merge per ADR-F005 against
`sarturko-maker/lq-ai-fork`.
