# AIC-2 — The deterministic EU-AI-Act verdict engine (ADR-F057 core)

**Status:** DELIVERED 2026-07-01 (three decisions confirmed by the maintainer: facts snapshot on the verdict;
conservative Art 6(3) + `draft_basis`; tier-badge-only UI). Stacked on AIC-1 (`fork/aic-1-ai-systems-register`,
PR #189); rebase to main when #189 (and #188) merge. Two refinements vs the sketch below, recorded in the
ADR-F057 AIC-2 addendum: (a) the Art 6(3) derogation is a *modifier* (trace + refs + `draft_basis`), not a
sixth route — the five routes map 1:1 to terminal tiers; (b) the derogation claim is a single
`art6_3_derogation_condition` enum (`none` = not claimed), dropping the redundant boolean.

## Why this slice

AIC-1 shipped the **facts-only** `ai_systems` register — deliberately no risk tier, because a risk tier
is a *legal determination*, not a data field. AIC-2 is the module's genuine IP: a **deterministic engine
that OWNS the verdict**, gated so the model supplies facts and can never mint or assert a tier (ADR-F057
option 3). This is the honest differentiator over a OneTrust-style questionnaire-with-a-chatbot — a system
cannot be *talked into* a lower tier, and the verdict is reproducible and auditable independent of model
quality (the same property that lets a tier-4 model run the ROPA).

It is also the slice that surfaces the **depth** the register currently lacks: the moment the engine runs, a
per-system **risk-tier badge** appears in the cockpit register.

## Legal grounding (web-researched 2026-07-01; counsel-review is the maintainer's gate)

The **Digital Omnibus** was adopted after my knowledge cutoff (Council final green light 29 June 2026;
EP endorsement 16 June 2026; publication imminent). Researched against Gibson Dunn, White & Case, and
aiactblog.nl summaries, three sources agree:

- **The classification TEST did not change.** Art 5 (prohibited), Art 6(1)+Annex I (embedded safety
  component requiring third-party conformity assessment), Art 6(2)+Annex III (standalone high-risk),
  Art 6(3) (derogation), and Art 50 (transparency) remain structurally the **baseline Reg 2024/1689** — the
  Omnibus replaced the Commission's proposed conditional-trigger mechanism with **fixed deferred dates**.
- **What moved is DATES** (these belong to AIC-6's regulatory calendar, NOT this tier engine):
  Annex III standalone high-risk **2 Aug 2026 → 2 Dec 2027**; Annex I embedded high-risk **2 Aug 2027 →
  2 Aug 2028**; FRIA (Art 27) **→ 2 Dec 2027**; Art 50 transparency **not postponed (2 Aug 2026)** with an
  Art 50(2) marking grace period **→ 2 Dec 2026**; sandboxes (Art 57) **→ 2 Aug 2027**.
- **One new prohibition** (Art 5): AI generating/manipulating **non-consensual intimate imagery / CSAM**
  ("nudifiers"), transition to **2 Dec 2026**. Engine gets one new Art-5 branch.
- **No Annex III or registration-scheme substance change.**

**Consequence for scope:** AIC-2's tier logic is well-grounded and mostly pre-cutoff-stable; the only moving
part (dates + the one new prohibition) is isolated to versioned data. The ruleset ships as **versioned data
with a `ruleset_version` stamp + a "pending counsel review — not legal advice" disclaimer**; a lawyer
validates before any verdict is authoritative (ADR-F057 open item #8). This slice encodes the researched
adopted text; it does not *certify* it.

Sources (for the record, not shipped in code):
- https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/
- https://www.orrick.com/en/Insights/2026/05/EUs-Digital-Omnibus-on-AI-7-Key-Changes-You-Need-to-Know
- https://www.aiactblog.nl/en/posts/digital-omnibus-ai-act-what-changes-what-now-2026

## Goals

1. A **pure deterministic engine** `app/aiact/classify.py`: `classify(facts) -> Verdict` where
   `Verdict{tier, route, article_refs, predicate_trace, ruleset_version, verdict_hash, draft_basis}`. No LLM
   call, no I/O, no key — a total function of `(facts, ruleset_version)`.
2. A **structural presence gate**: the ONLY path to a tier is `classify_ai_system(ai_system_id, <facts>)`
   through `guarded_dispatch`; its `ClassificationFactsInput` is `extra="forbid"` with **no tier/risk
   field**, so a smuggled `risk_tier` is a hard reject (tested). No column and no tool writes a tier directly.
3. **Sealed, re-derivable persistence** (`risk_classifications`, migration 0086) with **recompute-on-fact-
   change**: one *current* verdict per system; a fact change that alters the hash supersedes the prior row.
4. **Visible depth**: a per-system risk-tier badge in `ComplianceRegister.svelte`, washed live via the
   existing `AiSystemChangeLedger` (verb `classified`).
5. **Eval-gated legal correctness**: a deterministic golden fact→verdict table over every waterfall branch
   (the real legal-logic gate, $0, no model) + an adversarial presence-gate test + one live masked scenario.

## The engine (baseline Reg 2024/1689 + Omnibus NCII/CSAM branch)

`classify(facts)` is an ordered waterfall; the first rule that fires sets the tier and route, and each step
appends to `predicate_trace` (predicate, value, effect):

1. **Art 5 prohibited screen** → `tier=prohibited, route=art5_prohibited`. Includes the baseline Art 5
   practices *plus the new NCII/CSAM branch*. (Facts carry one `art5_trigger` enum, default `none`.)
2. **Annex I embedded** — `annex_i_safety_component AND requires_third_party_conformity_assessment` →
   `tier=high, route=annex_i_safety_component` (Art 6(1)).
3. **Annex III standalone** — `annex_iii_area != none`:
   - `profiling_of_natural_persons` → `tier=high, route=annex_iii` **regardless of derogation** (Art 6(3)
     last subparagraph: profiling never derogates).
   - else `art6_3_derogation_claim AND art6_3_condition != none` → **not high**; record
     `route=art6_3_derogation`, set `draft_basis=true` (Art 6(3) conditions are the least-settled
     predicate); fall through to steps 4–5 for the residual tier.
   - else → `tier=high, route=annex_iii` (Art 6(2)).
4. **Art 50 transparency** — any of `interacts_with_natural_persons | generates_synthetic_content |
   emotion_recognition | biometric_categorisation` → `tier=limited, route=art50_transparency`.
5. else → `tier=minimal, route=minimal`.

GPAI: `is_gpai`/`gpai_systemic` (carried on `ai_systems`, read by the tool) only add the Art 50(4) GPAI
marking cite to `article_refs` at step 4; **no GPAI obligation logic** (AIC-4b). Role (provider/deployer)
does **not** affect the tier — it changes *obligations* (AIC-3) — so it is out of this engine.

`ruleset_version = "2024-1689+omnibus-2026-06-30.v1"`. Predicates, `article_refs` text, and the disclaimer
live in `app/aiact/ruleset.py` so a legal update is a data + version bump, not an engine rewrite.
`verdict_hash = sha256(canonical(normalized_facts + ruleset_version + tier + route + sorted(article_refs)))`
— unsigned content digest v1 (ADR-F057); identical facts+ruleset ⇒ identical hash ⇒ idempotent.

## Classification facts (where they live — the one real design call)

The register (`ai_systems`) stays **thin**. The richer classification facts are a separate structured
`ClassificationFactsInput` **snapshotted onto the verdict row** (JSONB), not new columns on `ai_systems`:

- `art5_trigger`: enum `none | subliminal_manipulation | exploits_vulnerabilities | social_scoring |
  predictive_policing_profiling | untargeted_facial_scraping | emotion_recognition_workplace_education |
  biometric_categorisation_sensitive | realtime_rbi_public_le | ncii_csam_generation`
- `annex_i_safety_component`: bool; `requires_third_party_conformity_assessment`: bool
- `annex_iii_area`: enum `none | biometrics | critical_infrastructure | education | employment |
  essential_services_credit_insurance | law_enforcement | migration_border | justice_democracy`
- `profiling_of_natural_persons`: bool
- `art6_3_derogation_claim`: bool; `art6_3_condition`: enum `none | narrow_procedural_task |
  improves_prior_human_activity | detects_deviations_no_replace | preparatory_task`
- Art 50: `interacts_with_natural_persons | generates_synthetic_content | emotion_recognition |
  biometric_categorisation`: bools

`extra="forbid"`, **no tier field**. Coherence validators (raise, don't sanitize): a derogation condition
requires the claim; `requires_third_party_conformity_assessment` is only meaningful with
`annex_i_safety_component`. Rejected facts return `_rejection_text` (never raised), mirroring
`compliance_tools`.

**Why snapshot on the verdict, not the register (Option A, recommended):** keeps the presence gate crisp
(the register can *never* hold a tier), makes the verdict a self-contained sealed artifact, and makes
"recompute-on-fact-change" a clean single trigger (re-run the tool → new sealed row supersedes). Option B
(fact columns on `ai_systems`) bloats the thin register with classification-only fields and muddies the
recompute trigger — rejected.

## Persistence — `risk_classifications` (migration 0086)

Columns: `id` (uuid gen_random_uuid); `ai_system_id` FK `ai_systems.id` ondelete **RESTRICT** (systems are
soft-retired, never hard-deleted); **`practice_area_id`** FK `practice_areas.id` RESTRICT **NON-NULL**
(born flip-ready, mirrors AIC-1); `source_project_id` FK `projects.id` **SET NULL** (provenance);
`facts` JSONB; `facts_hash` Text; `tier` Text + CHECK `in ('prohibited','high','limited','minimal')`;
`route` Text + CHECK (the 6 routes); `article_refs` JSONB; `predicate_trace` JSONB; `ruleset_version` Text;
`verdict_hash` Text; `draft_basis` Boolean server_default false; `created_at` TIMESTAMPTZ now();
`superseded_at` TIMESTAMPTZ nullable. **Partial unique index** `WHERE superseded_at IS NULL` on
`ai_system_id` — exactly one *current* verdict per system. Index on `ai_system_id`. Constraint names
byte-match the model (the AIC-1 discipline).

`classify_ai_system` (guarded write, `db.flush()` not commit; ledger records after flush): validate facts →
`classify()` → look up the current row; identical `verdict_hash` ⇒ idempotent (return existing, no write);
else set the old row's `superseded_at`, insert the new sealed row, record the ledger change (`classified`).
One gateway-agnostic audit row (counts/types/IDs — never the raw facts values).

## Read API + UI

- Router (`api/app/api/compliance.py`): `GET /compliance/ai-systems/{id}/classification` → the current
  `VerdictRead` (tier, route, article_refs, predicate_trace, ruleset_version, draft_basis, verdict_hash,
  created_at); 404 when unclassified. Extend the list projection with an **optional current-verdict summary**
  (LEFT JOIN on `superseded_at IS NULL`) so the register renders a badge in one round-trip. `VerdictRead`
  omits `facts`/`facts_hash`/`practice_area_id`/`source_project_id` from the read surface (internal).
- `ComplianceRegister.svelte`: a **Risk tier** column — `prohibited` (red), `high` (amber), `limited`
  (blue), `minimal` (grey), `unclassified` (muted) — with the `draft_basis` marker when set. Live-washed via
  the existing `data-compliance-change` path (zero new frame type). Predicate-trace/article-refs detail
  drawer: **deferred** (recommend fast-follow or fold into AIC-3 when obligations join the drawer).

## Non-goals (explicit — each is a later slice)

- **Role + obligations checklist** (AIC-3) — role does not change the tier; out of this engine.
- **Regulatory calendar / deadlines / Art 73 incident clock** (AIC-6) — AIC-2 cites *articles*, does no date
  arithmetic; the deferred dates above live there.
- **GPAI Chapter V obligations** (AIC-4b) — flags carried; only the Art 50(4) marking cite is added.
- **FRIA** (AIC-5); **provider/conformity chain** (AIC-4).
- **Cryptographic verdict signing** — unsigned digest v1 (ADR-F057).
- **authz `visible_filter()`/`can()` seam** — still deferred; the NON-NULL `practice_area_id` column is the
  only born-flip-ready surface (ships shared-read like AIC-1/ROPA, ADR-F019).
- **No new dependency; no gateway change** — the engine is pure in-process compute with no LLM call.

## Files

**NEW:** `api/app/aiact/__init__.py`; `api/app/aiact/ruleset.py` (versioned predicates + article_refs +
disclaimer + `RULESET_VERSION`); `api/app/aiact/classify.py` (`classify()` + `verdict_hash`);
`api/app/schemas/classification.py` (`ClassificationFactsInput` extra=forbid, `RiskTier`/`ClassificationRoute`
enums, `VerdictRead`); `api/app/models/classification.py` (`RiskClassification` + CHECKs);
`api/alembic/versions/0086_risk_classifications.py`.

**EDITED:** `api/app/agents/compliance_tools.py` (add `classify_ai_system`; extend `COMPLIANCE_TOOL_NAMES`);
`api/app/models/__init__.py`; `api/app/api/compliance.py` (classification read + list join);
`api/app/agents/ai_system_changes.py` (add `classified` verb if not generic); web
`web/src/lib/lq-ai/api/compliance.ts` (+ `VerdictRead`, classification on `AiSystemRead`);
`web/src/lib/lq-ai/components/compliance/ComplianceRegister.svelte` (tier-badge column).

**TESTS (new):** `test_classify_engine.py` (golden fact→verdict table, every branch incl. NCII/CSAM,
profiling-blocks-derogation, both derogation directions); `test_classification_schema.py` (extra=forbid,
no-tier, coherence rejects); `test_compliance_classify_tool.py` (persists sealed row, supersede-on-change,
idempotent-same-hash, no-tier-tool exists, audit counts/types/IDs only, reject-and-retry); `test_compliance_
classification_read.py` (verdict read + list badge join, 404 unclassified, no internal-field leak); a live
scenario under `tests/agents/scenarios/` (engine issues tier; model provably cannot self-certify).

**DOCS:** ADR-F057 "Implementation notes — AIC-2" addendum; this plan; `HANDOFF.md`; memory
`ai-compliance-module-pivot.md`.

## Verification / DoD (ADR-F005 gate)

- Deterministic suite green with counts quoted (golden engine + presence-gate + schema + router + full
  compliance/agents regression) on a throwaway pgvector DB migrated through **0086**; `ruff check` +
  `ruff format --check` (repo-root config, line-length 100) + `mypy app` clean; `npm run check` 0 errors.
- **Presence gate proven adversarially**: no tool/column writes a tier; facts schema rejects `risk_tier`;
  identical facts ⇒ identical `verdict_hash` (reproducible); changed facts supersede.
- Live masked scenario (OOM-aware; defer the live run if the box is loaded, like prior slices) — the tier
  comes from the engine, not the model.
- Fresh-context adversarial review incl. the mandatory **security + simplification pass**: engine holds no
  key / egresses nothing / calls no LLM; facts injected/validated at the boundary; SQL parameterized; audit
  carries counts/types/IDs not raw facts; no stray files / leaked secrets; dead-code/dup sweep.
- ADR-F057 AIC-2 addendum; HANDOFF + memory updated; stacked PR under the full ADR-F005 gate.
- **Counsel-review gate honoured**: ruleset carries `ruleset_version` + `draft_basis` + a visible "pending
  counsel review — not legal advice" disclaimer; the verdict is not presented as authoritative until a
  lawyer validates ruleset v1.

## Open decisions for the maintainer (recommendations baked in — edit here)

1. **Facts location** — snapshot `ClassificationFactsInput` on the verdict row *(recommend, Option A)* vs
   add fact columns to `ai_systems` (Option B).
2. **Art 6(3) derogation posture** — conservative: honour a claimed condition but set `draft_basis=true` and
   always block on profiling *(recommend)* vs treat derogation as settled.
3. **Deadline hint on the verdict** — defer all dates to AIC-6, cite articles only *(recommend)* vs stamp an
   `obligations_apply_from` now from a tiny date map.
4. **UI depth this slice** — tier badge column only *(recommend)* vs also ship the predicate-trace/
   article-refs detail drawer now.
5. **Counsel review** — who validates ruleset v1 before any verdict is authoritative (ADR-F057 open #8).

## Recommended order

ruleset.py + classify.py (pure, TDD against the golden table) → classification schema + model + migration
0086 (throwaway-DB verify) → `classify_ai_system` tool + presence-gate tests → read API + list join → web
badge + live-wash → deterministic suite + golden eval → live scenario (OOM-aware) → docs/ADR/HANDOFF/memory
→ adversarial review → stacked PR.
