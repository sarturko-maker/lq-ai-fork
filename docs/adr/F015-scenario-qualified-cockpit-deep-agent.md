# F015 — making the cockpit Deep Agent production-real: scenario-based model qualification as the gate

- Status: proposed
- Date: 2026-06-16
- Deciders: maintainer (Arturs) — _pending_ (raised the UX-B mandate "Deep Agents must truly work, the
  cockpit must be perfect; run MiniMax through scenario testing — you create scenarios and see how it handles
  them; configure sensible default practice areas and test those"; chose to start with the scenario harness +
  Commercial baseline, to include skills activation in the milestone, and to review a short plan + ADR
  before building)
- Extends: [[F010]] (per-area Deep Agent — config vocabulary, the gateway-bypass guard, the tier-floor
  envelope), [[F004]] (conversation identity + durable state — the run/thread/step model the harness
  observes), [[F009]] (at-most-once runs — the durability the harness depends on), [[F002]]
  (practice-areas-and-agent-home — the destination this milestone serves)
- Supersedes: none

## Context

The cockpit Deep-Agent loop is **built and unit-tested**, but only against a **scripted** model
(`ScriptedToolCallingModel` in `test_agent_composition.py`). The real loop runs:
`POST /api/v1/agents/runs` → arq worker → `composition.py:compose_and_execute_run` →
`runner.py:_drive_agent` (streams `astream_events` v2, per-event commit) → the **Inference Gateway** (real
MiniMax-M3) → SSE (AI-SDK v1 frames). Multi-turn checkpointing, per-area tier-floor envelopes
(`min(matter, area)`), per-area audit slicing, and the ADR-F010 model-bearing-subagent rejection are all
genuine and tested. One provider-marked test (`test_deepagents_spike.py`) proves MiniMax *itself* picks a
tool through the gateway — but with **one** tool, **one** scenario.

**UX-B** ("capability convergence" — the third leg of the ADR-F012 split after F2-visual + UX-A-nav; the
delivery of the roadmap's "F3 — Practice-area IA re-centre"; "Deep Agents truly work / cockpit perfection",
see [[oscar-privacy-modules-vision]]) is about to raise the bar on the model substantially:

- **Configure 4 more practice areas** (Disputes / M&A / Privacy / Employment are inert — no `profile_md`).
- **Activate skills** (drop the `composition.py:151` `bound_skill_names=[]` stub; attach `SkillsMiddleware`)
  — which **expands the tool surface**, making tool selection materially harder.
- **Exercise subagents** (declarative specs exist + are validated, but have never run against a real model).

The model is **dependency-injected** (MiniMax-M3 today, swappable; **tier-4-weak**, and the only
S9-qualified provider). The open question this ADR answers: **how do we know the agent actually works with a
real model — well enough to call an area "configured", skills "activated", a subagent "blessed" — rather
than assuming it?** Authoring profiles, tier floors, and skill bindings *blind to how MiniMax actually
behaves* risks either a dishonest hollow shell (violates the transparency rule) or config the model cannot
honor.

## Considered Options

1. **Scripted-model unit tests only (status quo).** Deterministic, free, always CI-green. But proves the
   *plumbing*, not the *model* — it cannot tell us whether MiniMax selects the right tool among many,
   chains steps, delegates to a subagent, or refuses safely. Shipping configured areas + activated skills on
   this basis is assumption, and a likely hollow shell.
2. **A scenario-based live qualification harness, used as the gate (CHOSEN).** A provider-marked
   (live-gateway, real-MiniMax) suite that runs the agent through cockpit-realistic scenarios per area and
   capability, capturing honest receipts (tool selection, step count, final-answer correctness, refusal/
   guard behaviour, subagent delegation) into a committed **behavior report**. Nothing in UX-B ships until
   the harness shows the model handles it; default-area profiles + tier floors are **calibrated to observed
   behaviour**. Reusable for every future model swap (the model is DI).
3. **Manual exploratory testing only.** Honest but not repeatable, not regression-proof, leaves no durable
   artifact, and does not scale to 5 areas × N capabilities × model swaps.

## Decision Outcome

**Option 2, with Option 1 retained for plumbing — they are complementary.** Scripted-model unit tests stay
the CI gate (fast, deterministic, gate every PR). The **scenario harness is the gate for "production-real"
claims** and runs **out-of-CI** (manual / nightly, behind `@pytest.mark.provider`), with its **behavior
report committed as the durable evidence artifact**. The rule for the milestone:

> An area is not shipped as `configured`, skills are not `activated`, and a subagent spec is not blessed
> until the scenario harness shows MiniMax-M3 handles it — and the default-area profiles + tier floors are
> calibrated to the harness's observed behaviour, not to assumption.

UX-B is sequenced behind this: **UX-B-1** builds the harness + a Commercial baseline; **UX-B-2** configures
the four default areas calibrated to that baseline; **UX-B-3** activates skills only after the harness
re-qualifies the harder tool selection; **UX-B-4** exercises a live subagent; **UX-B-5** surfaces the proven
loop in the cockpit UI. (Slices in `docs/fork/plans/UX-B-deep-agents-truly-work-decomposition.md`.)

## Consequences

- **(+)** Every "this works" claim (area configured, skills on, subagent blessed) is backed by an observed
  receipt — satisfies the transparency rule (no hollow shell).
- **(+)** The harness is a **reusable model-qualification regression suite** — when the injected model
  changes (MiniMax → anything), re-run it; the report tells us what regressed. This is the natural home for
  the S9 qualification gate.
- **(+)** Default-area profiles + tier floors are calibrated to MiniMax's real tier-4-weak limits, not
  guessed — so the cockpit degrades honestly where the model is weak rather than promising what it can't do.
- **(−)** Live provider runs cost tokens, are non-deterministic, and **cannot gate CI** — they run manually/
  nightly; the committed report is the artifact, and CI still runs only the scripted suite. This is an
  accepted, documented split (mirrors the existing `@pytest.mark.provider` boundary).
- **(−)** Scenarios are a maintenance surface — they drift as areas/skills evolve; each UX-B slice owns
  updating its scenarios + report.
- **Security (per-slice pass, [[security-review-every-slice]]):** provider keys stay inside the gateway —
  the harness builds the model via `build_gateway_chat_model()` and never holds a key; scenario fixtures and
  the behavior report carry **observations** (tool names, step counts, pass/fail, bounded answer excerpts),
  never provider keys or raw secret-bearing payloads. **Skills activation (UX-B-3) gets its own deeper security
  pass**: skill-bound tool dispatch must route through the existing `guarded_tool_call` chokepoint (R4/R5/R6
  preserved), and skill content is treated as curated/read-only (company- and practice-level memory remain
  read-only to agents — prompt-injection posture unchanged).
