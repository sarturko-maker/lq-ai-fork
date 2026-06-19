# F027 — Assessment track: deployment-global domain + completion invariant

- Status: accepted
- Date: 2026-06-20
- Extends: ADR-F018 (agentic modules = typed domain + code-validated agent writes + domain UI), ADR-F019
  (relational, deployment-global Privacy register)
- Milestone: PRIV-A1 (Privacy / assessment automation — P1 flagship track)

## Context

The ROPA spine (PRIV-1→9b) reached ~OneTrust/TrustArc parity for the *inventory* axis. The largest remaining
functional gap to both leaders is **assessment automation**: PIA / DPIA / LIA / TIA records, a risk register,
and (the differentiator, PRIV-A4) a conversational intake. PRIV-A1 lays the domain spine — the
`assessment` + `risk` entities and their integrity invariants — with no agent and no endpoint yet
(API-only migration), mirroring how PRIV-1 laid the ROPA spine.

Two decisions on this slice are architectural and worth recording before the agent (PRIV-A2) and UI
(PRIV-A3) build on them:

1. **Scope.** Are assessments owned by a matter (like a private work product), or are they part of the
   company's standing accountability record (like the ROPA register, ADR-F019)?
2. **The headline integrity invariant + where it is enforced.** ADR-F018's contract is "agent proposes →
   deterministic code validates → human owns." ROPA picked one clean enforced-both-layers invariant per
   entity (`special_category ⇔ art9_condition`, `restricted ⇔ mechanism`). The assessment track needs its
   own — and it is naturally a *cross-row* rule (an assessment's closeability depends on its risk rows),
   which a single-row DB CHECK cannot express.

## Considered Options

**Scope**

1. **Matter-scoped assessments** — `project_id` ownership FK, reads/writes scoped per matter. Diverges from
   the register it assesses (a DPIA covers company-wide processing activities that are themselves
   deployment-global); forces awkward cross-matter joins and a second authz model beside the shared register.
2. **Deployment-global, like the ROPA register (chosen)** — assessments link to the global processing
   activities and form part of the company accountability record; nullable `source_project_id`
   (`ON DELETE SET NULL`) for provenance only, shared-read posture (ADR-F019). Consistent with the data they
   reference; no new tenancy/authz machinery.

**Headline invariant enforcement**

A. **DB trigger** for the full cross-row rule — enforced everywhere, but adds a stored-procedure surface the
   rest of the schema deliberately avoids (ROPA keeps cross-row link rules in the app layer).
B. **App-layer pure guard for the cross-row rule + a within-row DB CHECK for the expressible part**
   (chosen) — the same split ROPA used; no trigger; the agent write path is the single writer (ADR-F019),
   so the app-layer guard is on the only path that can create the inconsistency.

## Decision Outcome

**Scope: option 2 — deployment-global.** `assessments` and `risks` carry no ownership FK; `assessments` has a
nullable `source_project_id` (provenance). The shared-read posture and the "cross-user→404 does not apply to
the shared register; 404 = genuinely missing id" rule of ADR-F019 extend unchanged to assessments. The agent
write path (PRIV-A2) remains gated by the area-keyed tool grant (only Privacy matters receive assessment
tools) and the `guarded_dispatch` chokepoint (R5/R6 + audit, counts/types/IDs only).

**Headline invariant: option B.** The enforced rule is:

> **A DPIA — or any assessment rated `high` — cannot be `completed` unless it has at least one risk carrying
> a non-blank mitigation.**

This is the accountability point: you cannot sign off a high-risk assessment with no documented mitigation.
It is enforced in two layers, split by what each layer can express:

- **Within-row half — `completed ⇒ risk_rating present`** — a Pydantic `model_validator` on
  `AssessmentInput` **and** a DB CHECK (`chk_assessments_completed_requires_rating`). You cannot close an
  unrated assessment, at either boundary.
- **Cross-row half — `completed high-risk ⇒ ≥1 risk with a mitigation`** — the pure
  `validate_assessment_completable(...)` guard in `app.schemas.assessment`, which the PRIV-A2 write path
  calls with the proposed status/type/rating and the linked risks' mitigations. A violation is rejected back
  to the agent verbatim (never a silent write/fix). No DB trigger: the agent is the sole writer, so the
  guard sits on the only path that can produce the inconsistency.

**Entities.** `assessment` (id, `type` pia|dpia|lia|tia, title, summary?, `status` draft|in_progress|completed,
`risk_rating` low|medium|high?, conditions?, `source_project_id`, created_at, `updated_at` with `onupdate`)
M:N to `processing_activities` (composite-PK link, CASCADE both ends); `risk` (id, `assessment_id` FK CASCADE,
description, `likelihood`/`impact` low|medium|high, mitigation?, owner?, `status` open|mitigated|accepted,
created_at). Enum-ish columns are `Text` + CHECK against the allowed set (authoritative list = the Pydantic
StrEnums), the ROPA pattern.

## Consequences

- Assessments inherit the shared-register authz posture (ADR-F019) — a deliberate, documented divergence from
  per-user ownership, not an authz hole. Cross-user→404 still protects private matters and a missing id.
- `updated_at` carries `onupdate` from the start — fixing the ROPA carried debt (its tables shipped without
  it); assessment status/rating rows genuinely mutate, so "last modified" is meaningful here.
- The cross-row invariant is only as strong as the single-writer assumption. A future second writer (a direct
  SQL path, a bulk import) would bypass the app-layer guard; if that ever lands, the rule must move to a
  trigger or a service-layer chokepoint shared by all writers. Called out so it is not mistaken for a DB-level
  guarantee.
- Read DTOs and the read endpoint are deliberately **deferred to PRIV-A3** (with their consumer), matching the
  actual PRIV-1→PRIV-3 sequence — A1 ships write contracts + spine only, no consumer-less code.
- Establishes the spine the rest of the track hangs off: agent write tools + PIA/DPIA skill (PRIV-A2), read UI
  + ROPA write-back (PRIV-A3), conversational-link external intake (PRIV-A4, its own ADR-F020).
