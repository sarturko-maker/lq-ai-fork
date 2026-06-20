# Privacy module — TODO / backlog (living)

**Purpose.** The single place the Privacy practice-area's outstanding work is parked, so the team can
switch to another practice area (e.g. Commercial) and return without losing context. Updated whenever a
Privacy slice ships or a new item is found. **Date last curated:** 2026-06-21. Compass for *what's worth
building* (and the reaffirmed non-goals): `PRIV-onetrust-to-lqai-functionality-map.md`.

## Shipped (one-line snapshot — the module is at ~OneTrust/TrustArc parity on the inventory axis)

ROPA spine + read UI + Article 30 export (PRIV-1/3/4a) · vendors + transfers (PRIV-5) · personal-data
taxonomy, closes Article 30(1) (PRIV-6a) · programme dashboard (PRIV-6b) · **data-flow / node-link map**
(PRIV-6c, ADR-F022) · ROPA population from a notice (PRIV-7) · **change verbs** soft-retire/unlink + the
live mixpanel→hotjar swap (PRIV-8a/b, ADR-F023) · **co-visible cockpit** + run-lock + changed-row highlight
+ cross-process streaming (PRIV-9a/b, ADR-F024/F025) · **assessment track** PIA/DPIA/LIA/TIA spine + agent
write path + read UI + ROPA write-back, **build→complete→read loop proven live** (PRIV-A1/A2/A3 + the
hardening proof, ADR-F018/F019/F027). ADRs accepted: F018/F019/F022/F023/F024/F025/F027; **F020 accepted
but BUILD-DEFERRED**; F021 proposed.

---

## TODO

### Tier 1 — ready now (no decision, no machine exposure, small)

1. **Default-binding skill migration.** Bind `pia-generation`, `ropa-population`, `ropa-maintenance` to the
   Privacy practice area via a migration (the migration `0056` pattern). **All three are bound test-only
   today** (dev-DB only for the live tests) — so production Privacy matters don't get them. The live proofs
   show they're load-bearing/valuable (`ropa-population`/`-maintenance` are load-bearing on flash;
   `pia-generation` keeps the assessment agent focused enough to finish+report). Small, high-value.
   *Where:* `skills/{pia-generation,ropa-population,ropa-maintenance}/SKILL.md`; the 0056 migration.

2. **PRIV-7 find-or-create DEADLOCK (HIGH).** Under parallel tool calls the category find-or-create path can
   deadlock, surfacing as a `failed` run. Fix with consistent lock ordering / a Postgres advisory lock /
   bounded retry. *Where:* `api/app/agents/ropa_tools.py` `_find_or_create_category` (the `begin_nested`
   SAVEPOINT path). Flagged in the PRIV-7 follow-ups.

3. **`special_category=false`-but-sensitive invariant gap.** The write-path invariant only enforces
   `special_category=true ⇒ art9_condition`, not the inverse — a sensitive activity marked
   `special_category=false` with no Art 9 condition passes `integrity_ok=true`. Add the inverse heuristic
   (flag likely-special-category content marked false). *Where:* the ROPA write-path validation; PRIV-7
   substantive-audit finding (`docs/fork/evidence/priv-7/` FINDINGS).

4. **ROPA `updated_at` carried debt.** The ROPA tables shipped without `onupdate` (known-deferred across
   PRIV-3→6; A1 fixed it for the assessment tables). Add `onupdate=now()` to the mutable ROPA tables (a
   small migration) or formally accept it. *Where:* `api/app/models/ropa.py` + a migration.

### Tier 2 — needs a decision or a prereq

5. **PRIV-6e geographic cross-border transfer map** ("the map", geo half). Apache **ECharts** geo-arcs
   (Apache-2.0; runner-up d3-geo; amCharts disqualified = proprietary). Beats incumbents by showing the
   **Chapter-V mechanism on arc-click + flagging restricted-without-mechanism**. **Prereq:**
   `transfer.destination` is free-text → geocode at projection time (additive; controlled vocabulary later).
   **Decision:** approve the new dep (→ ADR + NOTICES, the ADR-F022 precedent). *Plan:*
   `docs/fork/plans/PRIV-6e-geographic-transfer-map.md`. Independent — slot anytime.

6. **PRIV-6d Legal-Entity scope.** Scope the ROPA to legal entities (multi-entity controllers). **Needs a
   migration** + a data-model decision. Was a named pickup option off PRIV-6c.

7. **Substantive legal-quality track (PRIV-7 audit verdict: "C+ first-draft, not sign-off-ready").** The
   structural "9/9 linked" ≠ legal quality. Red-pen items a privacy lawyer flagged: **transfers often 0**
   (Art 30(1)(e)/(f) under-captured — most serious), recipient-role over-use of `processor`, generic
   boilerplate risk. A skill/method-improvement + scenario-eval track. **Decision:** scope/priority.
   *Where:* `docs/fork/evidence/priv-7/` FINDINGS § Substantive quality audit.

### Tier 3 — deferred behind an explicit gate

8. **PRIV-A4 — conversational-link external intake. DEFERRED — resume ONLY on an explicit decision to
   EXPOSE this machine to external traffic.** This is the flagship differentiator (replace OneTrust/TrustArc's
   static respondent web-form with a scoped agent the SME talks to), but it is the fork's first
   unauthenticated external surface. **ADR-F020 is accepted as the design of record** (opaque-token+DB-row;
   per-assessment firm-created shell; scoped `{add_risk}` agent; deferred-review; the security envelope; the
   token-bearer authz posture). The whole build — intake token + issuance, the rate-limiter (the app's
   first), the `get_intake_token` dependency, the unauthenticated endpoint, the scoped agent, strict
   CSP/serving infra, the `/intake/[token]` web page, and A4-5 (firm review surface + respondent
   provenance) — waits for the expose decision. *Plan:*
   `docs/fork/plans/PRIV-A4-conversational-link-intake-decomposition.md` (A4-1…A4-5). *ADR:*
   `docs/adr/F020-conversational-link-external-assessment-intake.md`.

### Cross-cutting / dependencies

9. **ADR-F021 Authorization (proposed).** When picked up it touches Privacy: the deployment-global register
   read-filter flips to **area-scoped** (the PRIV-6a "confused-deputy" fix), plus guest agents. Privacy
   modules are built flip-ready (reads through the seam, deny→404). **Fold in when F021 lands:** the
   ADR-F020 **token-bearer** actor type (a `TokenBearer` actor in `can(actor,…)`), and the in-flight
   collaboration-workflow output (`wajbzaq82`) into the guest-agent mechanism + Phase 5.

10. **Operational — gateway aliases (local, uncommitted).** `smart`/`fast`/`budget` are repointed
    `minimax/MiniMax-M3 → deepseek/deepseek-v4-flash` on the LOCAL gateway (MiniMax out of quota; survives
    restarts via the `gateway-config` volume). Revert when MiniMax quota returns, or formalize the provider
    choice. *Not Privacy-specific* — recorded so a live UI run on `smart` isn't a surprise.

---

## Reaffirmed non-goals (do NOT build — from the gap analysis)

Consent / CMP; cookie scanner; a data-store connector fleet; licensed regulatory-content RAG. Our edge is the
**ADR-F018 validated-write loop** + (when exposed) the **conversational-link intake** — *not* matching every
incumbent SKU. See `PRIV-onetrust-to-lqai-functionality-map.md` § Update 2026-06-19.
