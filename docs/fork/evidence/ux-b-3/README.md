# UX-B-3 — skills-on re-qualification report (ADR-F015/F016)

Live MiniMax-M3 scenario runs for **Commercial with its bound skills activated**
(migration 0056: `msa-review-saas` / `msa-review-commercial-purchase` /
`contract-qa` / `nda-review`), driven through the production agent loop by the
UX-B-1 harness with `run_scenario(..., skill_registry=…)`. The composition point
builds the **read-only registry-backed backend** (`app/agents/skill_backend.py`,
ADR-F016) exposing **only** Commercial's bound subset; the model's tool surface
expands with the deepagents builtin filesystem tools + the `SkillsMiddleware`
skill listing. Per ADR-F015 these are **observations**, not a pass/fail gate: a
shape-miss is a finding that calibrates, and the final-answer excerpt in each
report is the authoritative record, not the coarse `shape_matched` heuristic.

Reproduce (out-of-CI, live gateway):

```
docker run --rm --network host \
  -v "$PWD/api:/app" -v "$PWD/skills:/skills:ro" \
  -v "$PWD/docs/fork/evidence/ux-b-3:/evidence" \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e DATABASE_URL=postgresql+asyncpg://lq_ai:$POSTGRES_PASSWORD@localhost:5432/lq_ai \
  -e LQ_AI_GATEWAY_URL=http://localhost:8001 -e LQ_AI_GATEWAY_KEY=$LQ_AI_GATEWAY_KEY \
  -e UX_B3_EVIDENCE_DIR=/evidence -w /app lq-ai-api-dev \
  pytest -q -m provider tests/agents/scenarios/test_skills_on_scenarios.py -s
```

## What the snapshot shows

**The mechanism works.** With skills activated, the model genuinely sees and
uses the bound skills through our backend: in *Skill recognition* it issued
**five `read_file` calls** against the virtual `/skills/<name>/SKILL.md` tree
(progressive disclosure — it recognised the review skills and opened them),
interleaved with `search_documents` / `read_document`. The registry-backed
backend served exactly the bound subset and nothing else (the integration test
`test_area_bound_skill_reaches_agent_system_prompt` locks that a bound,
registry-known skill reaches the prompt while an unknown name is filtered).

**Finding (calibration target, NOT a defect — and deliberately not tuned away):**
the expanded tool surface **amplifies M3's known multi-step inconsistency**
(UX-B-1/2 already flagged it over-explores).

- **Grounded review (focused ask) — clean.** "Review the limitation of liability
  clause … is the cap acceptable?" → `search_documents` → `read_document` →
  grounded, cited (Section 7), customer-perspective analysis. 7 steps,
  `completed`. Skills on did **not** derail the grounding path for a focused ask.
- **Skill recognition (broad ask) — over-explores to `cap_exceeded`.** "Do a
  structured risk review …" → the model read **multiple** SKILL.md files +
  searched repeatedly and **never converged on a final answer** within the step
  budget (16 steps, no deliverable). The bigger surface gave a tier-4-weak model
  more room to wander.

This is the honest signal UX-B exists to surface: skills are wired correctly,
but a tier-4 model handed the full review-skill surface on a broad prompt can
spend its budget reading skills instead of answering. Raising the bound to chase
green would be gaming; the finding stands. Calibration options for a later slice:
a profile note ("consult at most one skill, then answer"), a tighter per-skill
hint, fewer default bindings on broad-review areas, or a stronger qualified model.

## Decisions recorded here

- **Backend, not the guard, is the security boundary (ADR-F016).** The builtin
  `read_file`/`ls` the model used are not wrapped by `guarded_dispatch` (the F1
  universe-wrap is out of scope); `RegistrySkillBackend` is read-only, serves
  only the bound names, and reaches no host FS or matter data — so the worst a
  prompt-injected model does through them is read a skill the area already bound.
- **Default bindings are focused (migration 0056).** A few relevant skills per
  area, not the catalogue — both to match the unit of work and because the
  finding above shows a broad skill surface degrades convergence.
- **No scenario tuned to pass.** The `cap_exceeded` finding is kept verbatim; the
  step bound (14) reflects the real grounding+skill-read cost, not a green target.
