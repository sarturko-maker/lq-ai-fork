# F020 — Conversational-link external assessment intake (unauthenticated scoped agent)

- Status: accepted (design of record) — **build DEFERRED; no machine exposure** (see Build status)
- Date: 2026-06-20
- Deciders: maintainer (accepts); drafted from the `priv-a4-understand` multi-agent grounding workflow
  (6 readers mapping auth/token, agent-run scoping, assessment domain, streaming/UI, security surfaces,
  precedent ADRs) + three maintainer design calls (token model, link scope, review state).
- Milestone: PRIV-A4 (Privacy / assessment automation — P1 flagship track; THE differentiator)
- Extends: ADR-F018 (agentic modules = agent proposes → code validates → human owns), ADR-F019 (relational,
  deployment-global Privacy register; single-tenant; agent is sole audited writer), ADR-F027 (assessment
  domain + completion invariant). Bound by: ADR-F002 (one-matter-one-identity; B-class runtime injection),
  ADR-F009 (at-most-once runs; no auto-resume), ADR-F026 (run budget/timeout layering).
- Relates to: ADR-F021 (user permissions — its **invitations** lifecycle is the closest precedent; F021
  already forward-references "tokenized-link prior art … for ADR-F020"). A4's token-bearer is the
  **unauthenticated** sibling of F021's authenticated guest agent.

> **Build status (2026-06-20): DEFERRED — recorded, not implemented.** Per maintainer direction this
> machine is **never exposed to external traffic**. No A4 code is built now: the intake token, the
> unauthenticated public endpoint, the rate-limiter / strict-CSP / serving infra, and the public web page
> are **all deferred** until a separate, explicit decision to expose. This ADR stands as the design of
> record for *when* that decision is taken — accepted so the security contract is settled in advance; if
> implementation later forces changes, **supersede** it (the normal escape hatch). Near-term privacy work
> instead **hardens the existing internal assessment loop (A1–A3) locally** (full Privacy agent: create →
> add risks → complete under the F027 invariant → read in the cockpit; provider-scenario harness, throwaway
> DBs, no exposure). Build plan (also marked deferred):
> `docs/fork/plans/PRIV-A4-conversational-link-intake-decomposition.md`.

## Context

OneTrust and TrustArc both lead with assessment automation, and both intake non-privacy stakeholders
(system owners, vendors, business SMEs) through a **static respondent web-form**: a fixed questionnaire,
conditional show/hide, submit, then back-office mapping into the inventory. PRIV-A1→A3 built our internal
half — the typed assessment domain (F027), the code-validated agent write path (F018), and the read
UI + ROPA write-back. PRIV-A4 is the flagship divergence: **replace the static form with a tokenized,
no-login link to a scoped Privacy agent the SME talks to**, which code-validates what it learns and files
it into the firm's standing assessment record for the firm to own.

This introduces the fork's **first unauthenticated external surface**. The grounding workflow established
the hard facts that force this ADR:

1. **No precedent token.** There is no share / invite / reset / magic-link token in the schema today. The
   only time-boxed single-use token is the MFA challenge (JWT, claims-only, no DB row); the only
   opaque-secret-with-DB-row is the refresh token (bcrypt-hashed in `user_sessions`, revocable). A4's
   intake token is the first general external-access token and sets the pattern.
2. **No rate limiting anywhere.** `RateLimited` (429) is defined but unused; the app has only CORS
   middleware. Brute-force/DoS protection was always "deferred to the edge." For an unauthenticated,
   LLM-backed endpoint this is load-bearing and must be built, not assumed.
3. **The scoping seam is small but must be exact.** `compose_and_execute_run` is the single composition
   point; `guarded_dispatch` + `GuardContext` (R5 halt / R6 grant / audit) is the single tool chokepoint;
   `build_assessment_tools` already splits model-facing A-class args from closure-injected B-class context.
   A scoped agent is a tight grant set + an `assessment_id` closure-injected so the model literally cannot
   name another assessment — *if* composition is made to short-circuit to it and nothing leaks a broader
   toolset.
4. **The conversation UI is not reusable.** `ConversationPanel`/`ChatPanel` require auth, a matters list,
   and the cockpit rail. Only the SSE parser + the polling reducers (ADR-F004: settled rows are truth,
   stream is animation) are auth-agnostic and reusable. The public page must live outside `/lq-ai`, and
   the web bundle is a static SPA (`adapter-static`, no SSR) — so strict CSP is a serving-layer concern.
5. **`agent_runs`/`agent_threads` carry a NOT-NULL `user_id` FK**, and every run/stream read endpoint is
   owner-scoped (`run.user_id == current_user.id`, else 404). An unauthenticated respondent has no user.

Three calls are architectural and recorded here before any code; the rest of the track (A4-1…A4-5) builds
on them.

## Considered Options

**1 — Token model**

A. **Stateless JWT (`typ=intake`)**, assessment_id + expiry in the claims, no DB row — simplest, no
   migration; mirrors the MFA token. But a leaked link **cannot be revoked** before expiry, there is no
   per-link cost ceiling, and audit/usage cannot be tied to a link.
B. **Opaque token + DB row (chosen)** — a long random token returned once, only its **bcrypt hash** stored
   in a new `assessment_intake_tokens` row carrying `assessment_id`, `created_by`, `expires_at`,
   `revoked_at`, and a **cost cap**. Mirrors the refresh-token pattern. Revocable, spend-bounded, auditable
   per link. Costs one table + migration — accepted, because the security mandate (revoke, cost-cap,
   audit-every-turn) all *require* a row.

**2 — What the link grants the scoped agent**

A. **Link can create a new assessment** — the SME starts blank; the agent proposes a fresh assessment +
   risks. More self-serve, but it widens the unauthenticated write surface (mint records, not just append)
   and complicates "human owns."
B. **Per-assessment, firm-created shell (chosen)** — a firm user creates the draft assessment and issues a
   link **scoped to that one `assessment_id`**. The external agent may **only add risk findings into that
   assessment** — no create, no link-to-activity, no register enumeration, no completion. Tightest possible
   blast radius on an unauthenticated surface.

**3 — Review / ownership workflow**

A. **Explicit `externally_submitted → firm_accepted` state now** — add `respondent_id` / `review_status` /
   `firm_reviewer_id` / `reviewed_at` (migration + backfill) and a firm accept-gate UI. Stronger
   provenance, but a bigger migration and more UI up front.
B. **Defer; review in the A3 cockpit (chosen)** — no review-workflow migration in this track. "Human owns"
   is satisfied structurally: the external agent has **no `complete_assessment` tool**, so it can never
   sign off; the firm reads the contributed risks in the existing Assessments cockpit (A3) and runs
   completion (which re-validates the F027 invariant). Revisit (A4-5) only if a formal accept gate proves
   necessary in practice.

## Decision Outcome

**Token: option 1B — opaque token + DB row.** New `assessment_intake_tokens` (id, `assessment_id` FK
CASCADE, `token_hash` bcrypt, `created_by` FK users, `created_at`, `expires_at`, `revoked_at?`,
`max_cost_usd`, `cumulative_cost_usd` default 0, optional `label`/`respondent_hint`). The plaintext token is
returned **once** at issuance and never stored or logged. Validation = look up by hash + bcrypt verify +
`now() < expires_at` + `revoked_at IS NULL` + `cumulative_cost_usd < max_cost_usd`; any failure → **401
opaque** ("link invalid or expired") with no detail that distinguishes the failure (no enumeration).
Issuance/list/revoke are **authenticated** firm-user endpoints under the assessment (A4-1); the public
surface only ever *consumes* a token.

**Scope: option 2B — per-assessment, firm-created shell.** The scoped agent's grant set is the tight subset
`{add_risk}` (a deliberate floor; widen only by a recorded amendment). It is built by a new
`build_assessment_scoped_tools(assessment_id, …)` that **closure-injects `assessment_id`** as B-class
context, so the model-facing signature carries **no** assessment id and cannot target another. The run
carries an intake-scope discriminator; `compose_and_execute_run` checks it **first** and short-circuits —
an intake run is **never** handed the matter/ROPA/full-assessment toolset, regardless of practice area.
The scoped grant is built **directly from the token's `assessment_id`** — a second, deliberate
grant-construction path beside the area-keyed one, because an intake run has **no matter binding** from
which to resolve a practice area (F002/F021 area-keying does not apply); F019's sole-writer guarantee still
holds because the write goes through `guarded_dispatch`, and the assessment is Privacy-domain by
construction (it is an assessment record). Errors from the tools are opaque (no "assessment X not found"
id-probing). The agent reaches the LLM only
through the Inference Gateway (unchanged sole egress + sole key-holder); A4 adds **no** new provider path.

**Review: option 3B — deferred.** No `review_status`/`respondent` migration in this track. The scoped agent
cannot complete; the firm owns completion in the A3 cockpit. The Article 30 export and the "DPIA on file"
write-back are unaffected (they already gate on `status == completed`, which only the firm can reach).

**Actor model.** An intake run is **owned by the issuing firm user** (`run.user_id = token.created_by`) so
the existing NOT-NULL FKs, lease fencing (F009), and checkpointing hold with no schema surgery on
`agent_runs`/`agent_threads`. The **external respondent is the token, not a user**: the `GuardContext`
additionally carries `intake_token_id` + `assessment_id`, and every dispatch audits `(token_id,
assessment_id, tool, outcome, result_chars)` — counts/types/IDs only, never the respondent's free-text.
Because the run is firm-owned, the existing owner-scoped run/stream/thread reads stay closed to the public;
A4-3 adds **separate token-scoped** public read/stream endpoints. **The token-bearer's authz posture is
fixed here** (it is not punted to F021): a token-bearer is **not** a `user`, **not** a
`user_practice_areas` member, and carries no area scope. Its reads gate on an **`intake_token_id` +
`assessment_id` match** — a **deliberate, documented exception** to F021's `can(actor,…)` /
`visible_filter(actor,kind)` seam (which is for authenticated users/areas) — and still return **404** on a
missing/expired/revoked token (never 403, no existence leak, per the house rule). Its *writes* are gated by
the frozen scoped grant set (R6), not by the policy seam. When the F021 authz seam lands it must **absorb
`TokenBearer` as a distinct actor kind** (assessment-scoped, read-limited) reflecting exactly this posture,
not re-derive intake as a user.

**Security envelope (the unauthenticated-surface contract — every item is a gate, not a nicety):**

- **Rate limiting** — a reusable Redis token-bucket limiter (A4-2), keyed per token **and** per client IP,
  on every public route. First real limiter in the app; pays down the codebase-wide gap.
- **Request-body cap** — a small fixed ceiling on the public message endpoint (defense vs payload DoS;
  today only file upload is capped).
- **Per-link cost cap** — `cumulative_cost_usd` accrues from the gateway routing-log cost per turn; a run
  is refused once a link reaches `max_cost_usd`. Bounds LLM spend on an open surface (complements R4).
- **Strict CSP + security headers** — `default-src 'none'`-style CSP, HSTS, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` on the public page, enforced at the
  serving layer; the page is authored CSP-clean (no inline script/eval). Token travels in the request
  body/header, **never** the URL query (no Referer/history/log leak).
- **Audit every turn** — via the existing `guarded_dispatch` audit, extended with `(token_id,
  assessment_id)`; issuance/revocation/access also audited.
- **No exfil** — the `{add_risk}` floor + `assessment_id` injection + opaque errors mean the agent cannot be
  steered to read other assessments, matters, documents, or memory. The system prompt is fixed
  (intake-only) and never built from respondent input.
- **No auto-resume** — F009 carries unchanged: a lost run costs the respondent one resend, never a
  duplicate write.

## Consequences

- **`assessment_intake_tokens` is the fork's reusable external-token pattern.** Future external intakes
  (DSAR, breach/incident) would get their **own** token variant + ADR, not a parameterized god-endpoint —
  scope creep into a general public agent is an explicit non-goal.
- **A genuinely new trust boundary.** Respondent free-text is the most untrusted input the system has taken
  (CLAUDE.md already treats retrieved docs/memory as injection-risky). The defense is structural (tight
  grant + closure-injected scope + parameterized SQL + fixed prompt), not a content filter; it must be
  proven by an **adversarial exfil-refusal scenario test** (A4-3) before the surface goes live.
- **The rate-limiter and the serving-layer CSP are reusable assets**, not A4-local — once landed they are
  *available* to cover other sensitive routes, but **A4 applies them only to the public intake surface**;
  retrofitting existing routes (e.g. chat) is explicitly out of scope here (recorded so they're mistaken
  neither for one-off intake plumbing nor for an A4 obligation to retrofit).
- **Token-bearer is a new actor kind the future authz seam must absorb.** F020 fixes its own posture (above:
  token-scoped, not a user/area member; reads = token+assessment match → 404-no-leak; writes = the frozen
  grant set). When ADR-F021's `can(actor,…)` seam is built it reconciles by adding `TokenBearer`, not by
  re-deriving intake — flagged so the two ADRs converge rather than drift (the HANDOFF already tracks an
  F021 fold-in).
- **Single-tenant is load-bearing (ADR-F019).** A token scopes to one deployment's one assessment. If
  multi-tenancy ever lands, tokens must carry `org_id` from issuance or a retrofit re-issues every link —
  flagged now so it is a known cost, not a surprise.
- **Cost cap depends on the gateway routing-log** as the cost source of truth; if a turn's cost is unknown
  (null), the cap counts it as a turn-unit so an open link can never bill unbounded.
- **Firm-owned runs mean an issuing user's deletion must revoke their live links** (FK + a revoke-on-delete
  step), else an intake run references a soft-deleted owner. Handled in A4-1.
- **Deferred-review is reversible** — A4-5 can add the explicit `submitted → accepted` state later without
  reworking A4-1…A4-4 (the columns are additive; the scoped agent already can't complete).
- This ADR is the **gate** the rest of the sub-track hangs off; A4-1…A4-4 each carry the full DoD and the
  deeper security-review pass mandated for an unauthenticated path. Decomposition:
  `docs/fork/plans/PRIV-A4-conversational-link-intake-decomposition.md`.
