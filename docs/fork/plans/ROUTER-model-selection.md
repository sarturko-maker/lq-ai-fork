# Research brief — task → model routing (RESEARCH FOR A FUTURE BUILD, not this round)

**Status:** drafting 2026-07-11 · maintainer reframed as **research, not implementation** · external
survey running (workflow `research-legal-ai-model-routers`), findings folded into § Field survey.
**Linked ADRs:** F010 (gateway sole egress + subagent model-key ban), F053 (budget envelopes),
F015 (model qualification). Future ADR when built: **F083** (task→model routing).

## The question, and the two things the maintainer actually wants

1. A way to **pick the model based on the task** — e.g. *an NDA review does not need a top-tier model;
   an M&A due-diligence fan-out may warrant a strong lead with cheap (Haiku-class) bulk workers*.
2. To **reconsider the taxonomy itself** — is a cost triple (`smart` / `fast` / `budget`) even the
   right abstraction, or should routing key on legal **task class** and **stakes**? Look at how
   **Harvey** and **Legora** do it (they already have routers). **This is OSS**, so whatever we pick
   must be model-**agnostic**.

## Direct answer to "can Agent and Subagents use different models today?"

**No, and it's deliberate.** A run picks ONE gateway alias (default `smart`); every subagent inherits
that exact model object. ADR-F010's **model-key ban** rejects naming a model on a subagent, because a
raw model *string* would let it reach a provider SDK from env keys and **bypass the gateway** (sole
egress / key-holder / tier / audit). Different models already run for different *purposes*
(`matter_consolidation`, citation judge) — just not lead-vs-helper within one run. Giving cheap
workers a different model IS possible (see § Agent-vs-subagent) but only via a gateway-bound model
*instance* injected in code, never a config string.

## The OSS insight that shapes everything: route by capability CLASS, not model name

Because this is OSS deployed into a customer's own cloud with the customer's own licensed models, the
router must **never hardcode "Fable 5" / "Sonnet 5" / "Haiku"**. Our architecture already gives the
right lever: the api only ever sends the gateway an **opaque alias**; `gateway.yaml` maps that alias to
a concrete provider/model (`gateway/app/router.py`). So:

> The router picks a **semantic label**; the **operator** maps that label to whatever model they
> licensed (a frontier API, Azure OpenAI, or a self-hosted open model). Agent code stays
> model-agnostic; model policy lives in one operator-owned config file.

This is the core design commitment. The open question is **what the set of labels should be** — which
is exactly the taxonomy the maintainer wants reconsidered.

## Recommended taxonomy (from the field survey — THREE ORTHOGONAL AXES)

The survey (Harvey, Legora, the routing field, OSS framing) converges hard: **`smart`/`fast`/`budget`
is the wrong *primary* axis.** It conflates three different things (capability, latency, price) into
one knob; "budget" misreads as "worse model" when the real meaning is "right-sized for a low-judgment,
high-volume call"; and it has nowhere to hang per-task operator policy, so "NDA=cheap, M&A=strong" ends
up hardcoded in agent prompts where every operator inherits one opinion. Keep it only as a **back-compat
synonym** (the api's `run.model_alias` defaults to `"smart"` — never break that). Route on three axes:

- **Axis 1 — capability-ROLE spine (required; the ONLY vocabulary agent code resolves).** ~3 labels
  naming the *shape/economics* of the call, not its price: **`reasoning`** (hardest judgment — fan-out
  lead, final synthesis, drafting, adversarial review), **`balanced`** (default workhorse — routine
  review, Q&A, research), **`bulk`** (high-volume low-judgment — fan-out leaves, extraction, triage,
  classification, LLM-as-judge). Plus the existing governance-local `local` / `local-fast` /
  `local-thinking`. Agent code stays both model-agnostic AND task-vocabulary-agnostic.
- **Axis 2 — task-class aliases (optional, operator-tunable, shipped as aliases-OF-roles).** Legible to
  a legal admin: `nda-review`, `redline`/`contract-drafting`, `dd-fanout-lead`, `dd-fanout-worker`,
  `legal-research`, `clause-extraction`, `judge`. The emitter names the most specific label it can; the
  gateway chain degrades **task-class → role → concrete model**. This is where per-task operator policy
  and per-practice-area eval results land — where model licenses and cost/quality tradeoffs actually
  live. A cost-hawk operator repoints `nda-review → bulk`; a high-stakes shop pulls it `→ reasoning`;
  agent code is unchanged either way.
- **Axis 3 — tier / security floor (ALREADY IN CODE; keep SEPARATE — never fold into capability).**
  Derived from the operator's provider contract, enforced as a hard 403 before any upstream call. This
  orthogonality is load-bearing: if `bulk` hardcoded "cheapest consumer model" it would violate a
  privileged matter's floor. In a floor-2 matter, `bulk` must still resolve to a tier ≤ 2 model — an
  operator-map decision the api validates model-agnostically by reading `routed_inference_tier` from
  `GET /v1/models` (integers only, never a model name).

**Net:** a routing choice is `(task-class × agent-role) → {min-model floor, default model, optional
sparse escalation-advisor, cost/latency tiebreaker}` — a matrix keyed to the fork's practice areas +
subagent roles, **populated by per-practice-area eval**, strictly richer than and back-compatible with
the old triple.

## Worked task→label policy (the maintainer's examples)
Emit the most specific label; the gateway degrades task-class → role → concrete model:
- **NDA review** → `nda-review` → **`balanced`** (routine; "needs no top model"). Operator repoints to
  `bulk` (cost-hawk) or `reasoning` (high-stakes) with zero agent-code change.
- **M&A due-diligence fan-out LEAD** (plan + delegate + synthesise) → `dd-fanout-lead` → **`reasoning`**
  — Harvey's "Partner" orchestrator role.
- **M&A fan-out BULK WORKER** (one subagent per document: extract/triage/flag) → `dd-fanout-worker` →
  **`bulk`** (Haiku-class / a local 4B). The headline "different model for agent vs subagent" case;
  economics (reasoning-class lead + bulk-class leaves) live entirely in `gateway.yaml`.
- **Drafting / redlining** → `redline`/`contract-drafting` → **`reasoning`** (judgment-heavy; Harvey
  routes drafting to extended-reasoning models).
- **Legal research** → `legal-research` → **`balanced`** (recall-oriented).
- **Classification / clause-extraction / verdict-gate / LLM-as-judge** → `clause-extraction`/`judge` →
  **`bulk`** (bounded sub-steps only — Harvey swapped an eval grader to a mini model for 40–100× savings;
  cheap models are legitimate for bounded sub-steps, never the primary answer).

**Signals, in priority order:** (1) task type / call-shape — PRIMARY, because model strengths are
*non-transitive* (Harvey: "Gemini excels at drafting but struggles at trial prep"); a flat cost scalar
erases exactly this. (2) fan-out role (lead=reasoning, leaf=bulk). (3) stakes = a quality FLOOR
("cheapest above a correctness bar", a hard constraint not a slider). (4) matter sensitivity / tier
floor — a separate hard axis (403). (5) difficulty-within-class — the one thing the old triple captured.
**Rule of thumb:** emit the cheapest role appropriate to the work-shape, always forward the tier floor,
**keep the LEAD model stable across a run**, only downshift fan-out LEAVES.

## Field survey — Harvey / Legora / the routing field (2026)
- **Harvey** runs a *portfolio* (OpenAI + Anthropic + Google via Bedrock/Vertex, plus fine-tuned custom
  and open-source models), not one frontier model. Default is **"Auto"** routing (admin-gated Model
  Selector to override); a **"Partner" orchestrator** plans, decomposes, and delegates each *sub-step* to
  a task-appropriate model, then synthesises. Selection is **by task-class with explicitly non-transitive
  strengths** (drafting vs recall/research vs jurisdiction) and is **eval-gated** (BigLaw Bench → the
  Legal Agent Benchmark: ~1,200 long-horizon tasks across 24 practice areas, graded **all-pass** —
  "eight of ten risks is not 80% useful; it is materially incomplete"). A cheap worker can **self-escalate
  to a frontier "callable advisor"** on hard sub-steps (<1 call/task). The exact routing predicate is
  *not published*.
- **Legora** (ex-Leya) is explicitly **model-agnostic**, hides model choice behind the task, and
  eval-gates it platform-side ("no user model picker").
- **The routing field**: a single quality scalar loses orthogonal capability info (RouterArena's
  domain×difficulty grid; InferenceDynamics capability profiling) and causes documented **"routing
  collapse"** (~100% of queries funnel to the strongest model under loose budgets). Established techniques
  — complexity classifiers, cascade/escalation, semantic routing, strong-model-as-judge — all exist
  (RouteLLM, OpenRouter, NotDiamond, Martian, Portkey/LiteLLM), but the commercial internals are
  proprietary black boxes. The transparency mandate argues for a **static, auditable operator map** over a
  learned router.
- **The eval gap is the real prerequisite.** Both Harvey and Legora *eval-gate* model choice; the fork
  has not done this for routing. Which task-class clears which min-model floor should come from the
  per-practice-area **CUAD / masked-judge harness that already exists in-repo**, not a guess. Every
  concrete model name / price in the survey is near-stale by 2026 — keep all model identity in
  `gateway.yaml`, re-verify live before acting.

## Where a router would live (architecture, confirmed in code)
- **Run-creation seam (cleanest):** the alias is chosen once, at run creation (`agent_runs.py:448`),
  copied verbatim onto the row; the gateway resolves it. A selector there maps task→label, persists
  the chosen label (transparency), and reuses 100% of gateway routing + tier enforcement + routing log.
  Must emit an **alias, never a raw provider/model** (raw passthrough skips tier-floor/log discipline).
- **Tier-floor constraint (hard):** effective floor = `min(matter, area)`, enforced as a 403 at the
  gateway ("M3 tier-4 trap"). A run-creation router must resolve the floor there (or only pick labels
  whose routed tier can't violate it) or it will fail the run. Sequencing note: the floor is combined
  at *composition* today, the router wants to choose at *run creation* — reconcile before building.

## Agent-vs-subagent (the "strong lead + cheap workers" case)
F010-legal ONLY by passing a pre-built gateway-bound `BaseChatModel` **instance** and attaching it to
specific subagent specs. The area-config JSON path is a **dead end** — `build_area_subagents` rejects
any key outside `{name,description,system_prompt,skills}` (`area_agent.py:164`). It must be injected in
composition, between `render_area_agent` and `build_deep_agent` (`composition.py:1062 → 1172`), by
mutating `wiring.subagents` with a cheaper gateway model instance. **Verify first**: confirm the pinned
deepagents 0.6.8 actually honours a per-spec model instance override (`spec.get("model", parent)`) at
runtime before committing.

## Build options (ranked, for the future ADR)
- **A) CONFIG-ONLY — reframe `gateway.yaml.example` (DO FIRST; lowest risk).** The gateway already
  resolves **multi-level aliases** (`resolve_alias_chain`, validated acyclic at load), so ship the
  capability-role spine (`reasoning`/`balanced`/`bulk`) + task-class aliases as **aliases-of-aliases**
  all resolving to today's targets, keeping `smart`/`fast`/`budget` as synonyms. No agent code, no
  migration, fully reversible — and it immediately lets an operator express the maintainer's examples
  (repoint `nda-review → bulk`, or `→ reasoning` for a high-stakes shop) without touching agent code.
  Optionally have the api validate each new alias's `routed_inference_tier` via `GET /v1/models` at
  bind/setup so a `bulk`/worker alias that would violate a matter's floor is caught up front
  (integers only, never a model name).
- **B) PER-RUN alias selection (small api slice).** Let composition / the capability panel / area
  binding choose the run's single `model_alias` from a task-class instead of the hardcoded `"smart"`;
  the tier floor is already forwarded. Still one alias per run — no fan-out split.
- **C) LEAD/WORKER split at the fan-out seam (the M&A case; needs an ADR + slice).** Build a SECOND
  `build_gateway_chat_model(model_alias="dd-fanout-worker", project_minimum_inference_tier=floor, …)`
  and attach that pre-built gateway-bound **instance** onto the worker subagent spec — F010-legal
  (a string bypasses the gateway; an instance does not). `FanOutQuotaMiddleware` already caps the
  builtin `task` tool, so worker economics stay bounded. The worker MUST forward the same
  `effective_tier_floor` or it 403s. Gated on confirming deepagents 0.6.8 honours a per-spec instance.
- **D) DYNAMIC quality-aware router (learned/semantic/cascade) — DEFER, maybe never.** Opacity,
  documented **routing-collapse** risk, an eval burden, and it fights the fork's transparency mandate;
  if ever built, make it an operator-swappable module gated on per-practice-area eval, not a default.

## Non-negotiables for any future build
Gateway sole egress (no direct provider call, ever). Emit aliases, never raw ids. Model-agnostic:
operator maps labels→models in one config file, no model names in agent code. Persist + surface every
routing decision (transparency is load-bearing). Keep model choice inside the budget-envelope story
("system proposes, user owns"; economy dials down). Respect the tier floor.

## Decisions to put to the maintainer when we move to build
1. Adopt which taxonomy (recommend the survey-backed scheme; hypothesis: task-class → capability-tier)?
2. Router at run-creation (A) vs gateway-side (B) vs per-area policy (C)?
3. Build the agent-vs-subagent split (D) now or after A/B land?
4. Default operator alias→model map to ship (so it works out of the box, overridable without code)?
