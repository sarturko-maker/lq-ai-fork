# PRIV-A — Assessment automation (PIA / DPIA / LIA / TIA) — P1 flagship decomposition

**Status:** PLAN for maintainer edit. **Date:** 2026-06-19. Governing: ADR-F018 (agentic modules —
agent proposes → deterministic code validates → human owns), ADR-F019 (relational deployment-global privacy
records). Grounding: `PRIV-onetrust-to-lqai-functionality-map.md` § Update 2026-06-19 (A = the biggest
genuine gap; both OneTrust & TrustArc lead with assessments). Reuses Oscar `pia-generation` /
`use-case-triage` / `dpa-review` (reference-only, port-and-improve).

## Why this is P1

The RoPA spine is ~at parity (PRIV-3→9b). The largest functional gap to OneTrust/TrustArc is **assessment
automation**: PIA/DPIA/TIA/LIA + AI-impact templates, conditional logic, a risk register with scoring,
stakeholder questionnaires, and **write-back to the inventory**. We have none yet. Our differentiator (the
whole reason to build it our way) is **PRIV-A4: the conversational-link intake** — replace their static
respondent web-form with a scoped agent the SME *talks to*, that code-validates and files into the ROPA.

The track is sequenced **domain → agent write → read UI/write-back → conversational link**, exactly the
PRIV-1→2→3 shape that worked for ROPA. (This supersedes the coarse A1/A2 split in the functionality map.)

## Entities (the spine)

- **`assessment`** — one PIA/DPIA/LIA/TIA record.
  - `id`, `type` (StrEnum: `pia` | `dpia` | `lia` | `tia` — extensible to `ai_risk` later),
    `title`, `summary`, `status` (StrEnum: `draft` | `in_progress` | `completed`),
    `risk_rating` (StrEnum: `low` | `medium` | `high` | nullable until assessed),
    `conditions` (text — required mitigations before proceeding; nullable),
    `source_project_id` (provenance, `ON DELETE SET NULL` — mirrors ROPA),
    `created_at` / `updated_at` (add `onupdate` this time — see carried debt below).
  - **M:N to `processing_activities`** (an assessment covers ≥1 activity) — composite-PK link table,
    CASCADE both ends, mirroring `processing_activity_systems`. (Optionally also M:N to `systems`; start
    with activities only — keep the first slice lean.)
- **`risk`** — a finding within one assessment.
  - `id`, `assessment_id` (FK, **CASCADE** — a risk has no meaning without its parent, the Transfer→Activity
    precedent), `description`, `likelihood` (StrEnum `low|medium|high`), `impact` (StrEnum `low|medium|high`),
    `mitigation` (text), `owner` (text, nullable), `status` (StrEnum `open|mitigated|accepted`),
    `created_at`.

**Scope decision to ratify (ADR):** assessments are **deployment-global like the ROPA** (ADR-F019) — they
link to global processing activities and form part of the company's accountability record — with
`source_project_id` provenance and the same shared-read posture. Confirm with maintainer; it's the
consistent choice but it IS a divergence-worthy call → fold into the PRIV-A ADR.

**Headline code-validation invariant (the ADR-F018 improvement over Oscar's trust-the-model writes):** pick
one clean, enforced-both-layers invariant, e.g. **a `dpia` (or any `risk_rating='high'`) assessment cannot
be `status='completed'` unless it has ≥1 `risk` with a non-blank `mitigation`** — the "you can't close a
high-risk DPIA with no documented mitigation" rule. Mirrored in Pydantic (`model_validator`) AND a DB CHECK
where expressible (cross-row count rules may need an app-layer guard + a within-row CHECK for the simpler
parts, exactly as ROPA did). This is the assessment analogue of `special_category ⇔ art9_condition`.

## Slices (each one PR, ≤2–3 days, full four-discipline DoD; migrations verified up/down/up on a throwaway
pgvector, never the dev DB; rebuild api+arq-worker+ingest-worker together)

- **PRIV-A1 — assessment domain spine + code validation. API-ONLY (migration; no agent, no UI).**
  Mirrors PRIV-1. New `app/models/assessment.py` (`Assessment` + `Risk` + the activity link table +
  relationships + CHECK mirrors), `app/schemas/assessment.py` (`AssessmentInput`/`RiskInput` write contracts
  with the StrEnums + the headline invariant + `extra="forbid"`; `*Read` DTOs). New migration (next head).
  **No endpoint, no agent wiring.** Tests: pure invariant accept/reject (the headline rule both directions),
  DB defense-in-depth (CHECK rejection + CASCADE), the enum-mirror. **This is the slice to start with
  post-compaction.**
- **PRIV-A2 — validated agent write path + PIA/DPIA skill.** Mirrors PRIV-2. `app/agents/assessment_tools.py`
  (`build_assessment_tools`): `propose_assessment`, `add_risk`, `link_assessment_to_activity`,
  `list_assessments` — all guarded (R5/R6 + audit, counts/types/IDs only), `source_project_id` closure-
  injected B-class, model-facing signatures A-class-only, code-validated reject-and-retry. Granted only to a
  matter filed under Privacy (the `composition.py` area-key pattern, like ROPA tools). A `pia-generation` /
  `dpia` SKILL.md (port-and-improve Oscar's 7-section template + risk-quality standard: specific,
  design-tied mitigations). Skill bound test-only first (PRIV-7 precedent), default-binding migration later.
- **PRIV-A3 — assessment read UI + register integration + write-back.** Mirrors PRIV-3/6b. Read API
  (`GET /ropa/assessments` + `/{id}`, shared-read `_active`; route-count contracts updated); a cockpit
  **Assessments** register tab + detail (linked activities, risk table, status/rating badges, F013 style,
  read-only — agent is sole writer); and **write-back**: an assessment's findings update/flag the linked
  ROPA activities (e.g. a completed DPIA can set a "DPIA on file" marker / surface required conditions).
- **PRIV-A4 — conversational-link external intake (THE DIFFERENTIATOR). ADR-F020.** Tokenized, time-boxed,
  no-login public link → a **scoped** Privacy agent (can only propose into one assessment's scope; no other
  tools/matters/data) → code-validated writes → human review/own. **Security-sensitive (unauthenticated
  external surface):** rate-limited, no data exfil, audit every turn, token rotation/expiry, strict CSP.
  Its own ADR (ADR-F020) + likely its own multi-slice sub-track. This is the flagship payoff; do it last,
  on top of a proven internal assessment loop.

## Carried debt to fix here (don't repeat)

- `created_at`/`updated_at` with **`onupdate`** from the start on the new tables (the ROPA tables shipped
  without `onupdate` — known-deferred across PRIV-3→6; the assessment status/risk rows genuinely mutate, so
  a real "last modified" matters here).
- Run the **FULL** `pytest -q` before pushing (new endpoints trip the route-coverage + OpenAPI contracts —
  the PRIV-3 lesson).
- Confirm a qualified model can call the new zero-arg `list_assessments` (the PRIV-2 note).

## Non-goals (this track)

GUI template-builder (templates live in SKILL.md, readable in source — our inversion); numeric risk-scoring
rubric beyond likelihood×impact bands; multi-stage human approval workflow (status + owner suffices first);
EU AI Act conformity assessment (a later `ai_risk` type once the spine exists).
