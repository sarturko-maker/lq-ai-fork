# EU AI Act self-assessment — LQ.AI (the product), dogfooded through its own engine

**Status: SAAS-0 draft — pending counsel review, same gate as the AIC-2 ruleset (ADR-F057 open
item #8). Not legal advice. To be published on the trust page once counsel-validated.**

Why this exists: we sell an EU-AI-Act compliance module; the first customer demo invites *"what
is your own classification?"*. This records the answer — derived with the fork's own
deterministic engine (`app/aiact/classify`, lands with PR #190) — plus the Art 50 actions and
the GPAI boundary. Roles: once hosted commercially, **we are the provider** of the LQ.AI system;
**customers are deployers**; the underlying LLMs are third-party **GPAI models** we integrate
via the gateway.

## 1. Classification facts (the engine's input vocabulary, `ClassificationFactsInput`)

| Fact | Value | Reasoning on record |
|---|---|---|
| `art5_trigger` | `none` | No prohibited practice: no social scoring, manipulation, RBI, emotion recognition in workplace/education, NCII/CSAM generation, etc. The AUP forbids customer use for Art 5 categories. |
| `annex_i_safety_component` | `false` | Not a safety component of an Annex I regulated product. |
| `requires_third_party_conformity_assessment` | `false` | Only meaningful for an Annex I component (none here). |
| `annex_iii_area` | `none` | The intended purpose is assisting in-house legal professionals (drafting, review, registers). It is not intended for employment decisions about natural persons (Annex III(4)), essential-services eligibility (III(5)), or use *by judicial authorities* in administering justice (III(8) targets courts/ADR bodies — in-house counsel using a drafting aid is neither). Deployer misuse outside the intended purpose is the deployer's re-classification event (Art 25 logic — AIC-3 territory). |
| `profiling_of_natural_persons` | `false` | No Annex III context; the system profiles documents, not people. |
| `art6_3_derogation_condition` | `none` | No Annex III classification to derogate from. |
| `interacts_with_natural_persons` | `true` | Conversational agent UI. |
| `generates_synthetic_content` | `true` | Drafts, redlines, register entries — generated text. |
| `emotion_recognition` / `biometric_categorisation` | `false` | Absent. |
| `is_gpai` (register flag, not a fact) | `false` | We are not a GPAI *model* provider; we are a downstream system provider integrating third-party GPAI (see §3). |

## 2. Expected verdict (to be sealed by running the engine once PR #190 merges)

**Tier: LIMITED · Route: `art50_transparency` · refs: Art 50 · `draft_basis: false`**
(ruleset `2024-1689+omnibus-2026-06-30.v1`). **SAAS-0 ships with the hash deliberately
deferred**: the engine (`app/aiact/`) lives on the unmerged AIC stack (PR #190), which is not on
this branch's base. This one item explicitly carries past SAAS-0 acceptance — seal it as soon as
PR #190 lands on the deployment branch, by running `classify()` on the §1 facts (all fields
pinned above, `is_gpai=False`) and pasting the result: `verdict_hash: TODO`.

## 3. What LIMITED obliges us to do (provider-side Art 50), and the GPAI boundary

1. **Art 50(1) — AI-interaction disclosure.** Users must know they interact with AI. Arguably
   "obvious from context" for a tool marketed as an AI agent to lawyers — but we implement the
   in-product disclosure anyway (cheap, trust-building): agent surfaces labelled as AI, noted in
   onboarding. *(Action: SAAS-6 UI copy.)*
2. **Art 50(2) — synthetic-content marking.** Machine-readable marking on generated output.
   For exports (redline `.docx`, grid exports): embed generator metadata + a visible "AI-drafted,
   review required" note (aligns with the commercial pack's work-product framing). Omnibus note
   (per AIC-2 research, 2026-07-01): the marking obligations carry a transition/grace window to
   2026-12-02 — implement within it, don't rely on it. *(Action: SAAS-6/8A export surfaces.)*
3. **GPAI flow-down (Chapter V sits upstream).** GPAI-provider obligations (model documentation,
   training-data summaries, systemic-risk duties) rest with Anthropic/Mistral/etc. We rely on
   their published documentation through the gateway's provider registry, and surface *which*
   models a tenant's menu uses (trust page + order form). We must pass deployers the information
   they need (Art 13-style transparency via product docs) — our capability panel + gateway
   routing log already expose model identity per run.
4. **Deployer-side note for customers (goes in product docs):** customers deploying LQ.AI for
   their own staff inherit deployer duties (AI-literacy, human oversight of outputs) — our
   work-product framing ("draft requiring qualified review") is aligned by design.

## 4. Caveats

- Same disclaimer as every engine verdict: ruleset v1 is **pending counsel review**; this
  self-assessment is not legal advice and must be counsel-validated before the trust page.
- Re-run on intended-purpose changes (e.g. if a future module *does* target an Annex III area —
  say HR-adjacent review — the verdict must be recomputed and this document superseded).
- The engine's supersede-on-fact-change semantics apply to us too: keep the sealed verdict
  current the same way we ask customers to.
