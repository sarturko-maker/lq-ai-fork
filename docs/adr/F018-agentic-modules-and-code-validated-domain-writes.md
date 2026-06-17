# ADR-F018 — Agentic modules on the practice-area substrate: typed domain + code-validated agent writes

- Status: proposed
- Date: 2026-06-17
- Deciders: Arturs (maintainer)
- Supersedes / relates: extends ADR-F002 (practice areas = agent home), ADR-0013 D4/D5 (system
  proposes, user owns), ADR-F010 (no gateway bypass). First milestone after UX-B
  ([[ux-b-milestone-complete]] / `docs/fork/evidence/UX-B-MILESTONE-INDEX.md`).

## Context

UX-B proved the practice-area Deep Agent loop works end-to-end (configured areas → per-area skills →
on-demand subagents → honest cockpit). The next milestone delivers the long-range **agentic-modules**
vision ([[oscar-privacy-modules-vision]]): an enterprise adopts a **module** — a vertical capability where
the agent *does the work* — deployed on the same substrate. The fork is being positioned as **"LQ.AI Oscar
Edition"** (cutting-edge: Deep Agents + modules; upstream stays reserved — its own ADR when the rebrand
executes).

The first module is **Privacy / ROPA** — a OneTrust-equivalent where the whole **Records of Processing
Activities + privacy programme** is maintained by the agent. The reference is the maintainer's prior
deployed product, **Oscar Privacy** (private repo) — used **reference-only**: take the *idea and domain*,
not the code. Oscar is explicitly **not** the model for *how*: its engine is a single LLM call returning
fixed JSON dispatched by ~28 hardcoded executors, with provider keys in `.env` and no validation gate — the
linear "fill-JSON-slots" pattern this fork exists to replace, built on older models. (The ICO RAG that Oscar
carried is dropped.)

A module differs from a plain practice area in one structural way: it owns a **typed domain** (ROPA entities)
that the agent must **persist**, not just chat about or stuff into free-form `projects.context_md`. The open
question is how the agent writes to that domain safely. Oscar largely **trusted the model's writes**. We can
do better — and "better" is the whole reason to rebuild rather than lift.

What already exists (so this is smaller than it looks): `practice_areas` + the matter/unit-of-work binding
(`projects.practice_area_id`, `context_md`) shipped in F1-S3; the gateway sole-egress + `guarded_tool_call`
chokepoint (R5 halt / R6 grant); per-area skills/subagents; the run loop with `parent_step_id`. **Missing:**
the typed ROPA domain tables and a validated write path.

## Considered Options

1. **Free-form only (Oscar-minus-engine).** Keep matter state in `context_md` / unstructured notes; no typed
   domain. Cheapest, but you cannot query/report a ROPA, enforce completeness, or detect gaps — it is not a
   ROPA platform, just chat with memory.
2. **Typed domain, model writes directly (Oscar's actual approach).** Add ROPA tables; let the agent's tool
   calls write rows. Gets structure, but trusts the model for integrity — exactly Oscar's weakness, and it
   violates "validate at the boundary, reject don't sanitize."
3. **Typed domain + code-validated agent writes (chosen).** Add ROPA tables as typed SQLAlchemy models with
   **Pydantic domain schemas carrying code-level invariants**. The agent *proposes* a write through a
   `guarded_tool_call`-wrapped tool; **deterministic code validates before commit**; an invalid proposal is
   **rejected back to the agent** (which sees the reason and retries) — never silently written, never
   silently fixed. Human review/approval rides the existing `confidence`/review posture (ADR-0013 D4).

## Decision Outcome

**Chosen: option 3.** A **module** = a practice area extended with (a) a typed domain schema, (b)
**code-validated agent writes** — agent proposes, code disposes — and (c) deliverable generation on the run
artifact surface. The Privacy/ROPA module is the first; it is built **module-driven** (enablers — run
artifact surface, deliverable-playbooks — are built in service of it, not speculatively up front) and
**thin-vertical-first** (one entity end-to-end before breadth). Oscar is reference-only: break it down,
reimplement, **improve** — the headline improvement being code-validated entries over Oscar's trusted-model
writes. MCP and ICO are **not** on this module's critical path (ICO dropped; MCP stays a later enabler now
that the privacy module's external-source need is gone). Redlining is the **next** module/track (Commercial/
M&A), not part of this one.

The write path extends, never bypasses, the existing chokepoint: validation is a deterministic gate layered
on `guarded_tool_call` (R5/R6 still apply); all model calls still route through the gateway (ADR-F010); the
agent loop is deepagents/langgraph (ADR-F001) — no return to a fixed-action dispatcher.

## Consequences

- **Good:** deterministic domain integrity independent of model quality (the Oscar improvement, and exactly
  why a tier-4-weak model is tolerable here); a real, queryable ROPA → real deliverables + gap detection; the
  "module = typed domain + validated writes" shape generalizes to future modules; honest by construction (a
  rejected write is visible, never faked).
- **Cost:** each module brings a schema + migration + validation code + tools (real work, but bounded and
  short-sliceable); validation invariants must be authored and kept in step with the domain; the agent must
  handle rejection-and-retry (a prompt/skill + scenario-calibration concern, the natural place to also test
  whether a large programme triggers subagent delegation — the open UX-B-4 question).
- **Follow-ups:** the rebrand to "LQ.AI Oscar Edition" gets its own ADR when executed; redlining/adeu gets
  its own ADR at the next track; if a module later needs an external source, MCP via the gateway tool-egress
  boundary (cf. upstream ADR 0014/0015) is the route.
