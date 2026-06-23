# F030 — Commercial memory model: company/client tier + matter tier

- Status: accepted (2026-06-21, with slice C-CLIENT — the company/client tier landed; the matter tier is
  decided in direction here and built at C3) — **§2A (matter-tier propose/accept) superseded-by-F042 for the
  unit-of-work tier; §1A and the company/client tier remain in force** (metadata pointer per the ADR-0009
  precedent; the body below is unchanged/immutable)
- Date: 2026-06-21
- Relates: ADR-F028 (Commercial method doctrine — the area profile this tier sits beside), ADR-F002 (the
  practice area IS the agent identity), ADR-F013/0013 ("system proposes, user owns" for memory writes),
  ADR-F018 (code-validated agent writes — the pattern the matter tier reuses)
- Milestone: COMMERCIAL — company tier accepted with **C-CLIENT**; matter tier built at **C3** (this ADR is
  the gate that must be accepted before C3)

## Context

CLAUDE.md's target is a **4-level memory model** — company/client → practice area → user → unit of work —
all four injected as context. Three of the four levels already have a home: the **practice-area** tier is the
area `profile_md` (F1-S3 / ADR-F028), the **user** tier is `autonomous_memory`, and the **unit-of-work** tier
is `projects.context_md`. The **company/client** tier had none in the agent path: `OrganizationProfile`
(singleton, `content_md`, migration 0010) exists but is **never referenced in `api/app/agents/`** — it only
reaches a model through the legacy gateway skill-assembly prepend, and only when a skill is attached, so plain
agent runs get **zero company context** (CLAUDE.md blocker #5).

The Commercial agent must act *for* a specific organisation — its risk posture and house style shape how hard
it pushes, what it flags, and when it escalates (ADR-F028). For a single-client in-house agent the **client
is the operator's own org** (Model Rule 1.13; conflicts are N/A by construction). So the company/client tier
and "who is the client" are the same question, and both resolve to the org profile. This ADR records how the
company tier reaches the agent now (C-CLIENT) and how the matter tier will accumulate (C3), so C3 builds on a
decided shape rather than an ad-hoc one.

## Considered Options

**1. The company/client tier — how the org profile reaches the agent**
- A. **Read-only injection at the composition seam (chosen).** Load the singleton `OrganizationProfile`
  in `compose_and_execute_run` and append `content_md` as a **fenced "Client / house context" block** in
  `system_prompt_for`, for *every* run (bound or unbound, any area), positioned **before** the area profile
  so the area's controlling method stays the final word. Read-only to the agent (no tool mutates it; the
  operator edits it via the existing `PUT /organization-profile`). Empty/absent → no block.
- B. **A new per-company client entity / table.** Rejected this milestone — there is exactly one operator org
  (single-tenant singleton); a second entity adds schema and a write path for no behaviour the singleton
  can't carry. Counterparty (the *other* side) is a separate, still-deferred entity, not the client.
- C. **A `CompositeBackend /memories/company` read-on-demand backend** (the eventual target). Rejected as
  premature — the profile is small and always relevant, so eager injection is honest and simpler; read-on-
  demand is a later migration when company memory grows past a promptable size.

**2. The matter (unit-of-work) tier — how deal memory accumulates**
- A. **Free-form `projects.context_md` + a propose/accept reconciliation path (chosen direction; built C3).**
  Keep the existing free-form matter context as the store; the agent **proposes** additions/changes through a
  code-validated path and the **human owns** the accepted result (ADR-F018 + "system proposes, user owns").
  A small propose/accept table records proposals and reconciles them into `context_md`.
- B. **A fully typed deal-context schema now.** Deferred — the right field set isn't known pre-C3 (open
  question #3); typing too early ossifies the wrong shape. C3 may introduce typed fields *over* the
  free-form store once the shape is observed.
- C. **Direct agent writes to `context_md`.** Rejected — violates "system proposes, user owns"; matter memory
  is durable client work product and must not change without human ownership.

## Decision Outcome

Adopt **1A** (now, C-CLIENT) and **2A** (direction; built at C3). The **company/client tier** is the operator's
`OrganizationProfile.content_md`, injected **read-only** at the composition seam as a fenced, structurally
bounded "Client / house context" block, on every run, before the area profile. The block is operator-authored
**trusted source** but still **fenced** — embedded text must never be read as a role/instruction change
(defense in depth; CLAUDE.md treats stored prose as model input). It **never overrides** professional duties
or the area's controlling method (ADR-F028); it tells the agent *who* it acts for, the area profile tells it
*how* to practise. The **matter tier** stays `projects.context_md`, accumulated through a code-validated
propose/accept path with the human owning every accepted write (C3). No new company or counterparty entity
this milestone; no `CompositeBackend` yet.

## Consequences

- **C-CLIENT** wires the company tier: `system_prompt_for(binding, area, client_context)` +
  `_load_client_context_md` in `api/app/agents/composition.py`; no migration (reads an existing model). This
  closes blocker #5 — plain agent runs now carry company context — for **every** area, not just Commercial
  (the seam is area-agnostic; the live demo is Commercial × a synthetic Zendesk client).
- The company tier is **company-global** (one singleton row) — never per-area or per-matter, and never a
  second writer (the only writer stays the operator endpoint). Tests assert read-only + empty-degrades-clean.
- **C3 is unblocked** (this ADR is its gate). C3 adds the propose/accept matter-memory path over `context_md`;
  a typed schema, if any, is layered there once the field shape is observed — not pre-committed here.
- There is **no `company_tier` rating field** — "tier" in this milestone means the *memory level*, not a
  numeric grade. (Inference-tier floors remain the area's `default_tier_floor`, an unrelated gate.)
- Counterparty-entity timing is still open (the client is resolved = the org profile); revisit when a deal
  needs the other side modelled as data rather than implied by matter documents.
