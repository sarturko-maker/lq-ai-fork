# Upstream awareness review — LegalQuants/lq-ai since fork baseline `f91149a`

**Date:** 2026-07-10 · **Reviewer:** automated fan-out (31 agents) + maintainer-lead verification ·
**Scope:** 115 PRs merged + 25 issues opened upstream between 2026-06-07 (`f91149a`, our baseline) and
2026-07-09. Upstream has moved from **v0.4.0 → v0.6.1**, migrations **0047 → ~0065**, and shipped three
feature arcs (legal-research + MCP, fiduciary-grade Citation Ledger, governed matter sessions).

**Governing rule (ADR-F001):** upstream is FROZEN. Nothing here is merged or cherry-picked without the
maintainer's **per-case approval**, and every taken item gets an `UPSTREAM.md` sync-log entry. Because the
fork diverged hard, most upstream *fixes* to shared substrate must be **re-authored** (port the fix *shape*,
not the diff) — the paths and surrounding code have moved. This doc is an **awareness + decision record**,
not a merge plan.

The maintainer's priority for this pass: **fixes over features.** That ordering is reflected below.

---

## TL;DR — the decision

| Bucket | Count | What it is |
|---|---|---|
| **Include now** | 10 | Real defects/gaps live in **our** kept substrate (2 are confirmed security bugs), + 2 cheap ops/quality fixes + 1 small feature |
| **Defer** | 10 | Real but lower blast-radius, or concept-only (reference design for a future ADR'd slice) |
| **Not needed** | 23 | Convergent (we already fixed it), or in code we replaced/deleted |
| **Notable features (awareness)** | 15 | Upstream functionality we deliberately skip; recorded so we know it exists |

**Two of the include-now items are security bugs that upstream's own audit (#288) found and that I
independently confirmed are present at our HEAD** — they were inherited from baseline, not introduced by
us, but they are live in code we still run. They should jump the queue ahead of B-7a.

---

## INCLUDE NOW

Ordered by severity. Each was verified against the fork tree at `main` HEAD — the "Confirmed" line is my
own re-check, not just the agent's.

### 🔴 SEC-1 (was GW-01) — gateway inference/embeddings routes require no key
- **Upstream:** audit issue #288 / #294, fix in their PR #289. **Kind:** security (auth bypass).
- **The bug:** `gateway/app/api/inference.py:114` builds its router with **no** `dependencies=`, so
  `POST /v1/chat/completions`, `POST /v1/embeddings`, `GET /v1/models` are **unauthenticated**. The admin
  router (`gateway/app/api/admin.py:59`) *does* attach `dependencies=[Depends(require_gateway_key)]`.
  `main.py:363` mounts inference with no app-level auth middleware. The gateway is our **sole egress and
  sole key-holder** — so any process that can reach the gateway container (any co-located compose service;
  anything on the tenant's network in a self-host stack) can drive keyed provider egress **for free**.
- **Confirmed at HEAD:** yes — inference router has zero `Depends`; admin router enforces; no middleware
  covers it. `make_require_gateway_key` **auto-disables when the key env var is unset**, so tests and
  keyless dev stacks are unaffected.
- **Fix (re-author, don't cherry-pick):** attach `dependencies=[Depends(make_require_gateway_key())]` to
  the inference router exactly as admin does. Our api client already sends `X-LQ-AI-Gateway-Key` on every
  call (`api/app/clients/gateway.py:155`) and the ingest-worker embeds through the same client — **no
  legitimate caller breaks.** Add a keyed/keyless gateway test pair + a live streaming + ingest-embeddings
  check. **Effort: small.** Security-sensitive path → deeper F005 review.

### 🔴 SEC-2 (was API-01) — `create_chat` project IDOR + unscoped KB load (cross-tenant read)
- **Upstream:** audit issue #288 / #294, fix in their PR #290. **Kind:** security (cross-tenant confidentiality).
- **The bug:** `create_chat` (`api/app/api/chats.py:426`) persists attacker-controlled `payload.project_id`
  with **no ownership check** — `Project.owner_id` is checked **zero times** in the entire file. The chat
  RAG path then loads that project's attached knowledge bases via `_load_attached_kb_ids_for_chat` (filters
  only `project_id`) and `select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))` (`chats.py:867`) —
  **no `owner_id` scope**, though `KnowledgeBase.owner_id` exists. A user attaches a victim's `project_id`
  and pulls the victim's KB text — **un-anonymized** — into their own model context.
- **Confirmed at HEAD:** yes — both halves verified in the live agentic/chat path; `chats.py` changed since
  baseline (SETUP-5b, file-inject) but never gained a project guard.
- **Fix (re-author):** in `create_chat`, fetch the `Project` and 404 if `owner_id != user.id` (our
  cross-user = 404-not-403 rule); defense-in-depth, scope the `KnowledgeBase`/`ProjectKnowledgeBase` loads
  to `owner_id`. Single-file change + regression test. **Effort: small.** Deeper F005 review.

> **SEC-1 + SEC-2 should be one small security slice, done next** — both are localized, both are in kept
> substrate, both are confirmed live. Suggested: `UP-SEC-1` (one PR, two fixes, or two stacked PRs).

### 🟠 Ops / supply-chain (cheap, high-leverage)

- **SHA-pin GitHub Actions in credential-holding workflows** (upstream #296). Our `release.yml`
  (`packages:write` + `id-token:write` + `attestations:write`), `images.yml` (`packages:write`),
  `deploy-staging.yml` (holds `STAGING_SSH_KEY`) still reference third-party actions by **mutable tag**
  (`checkout@v4`, `build-push-action@v5`, `login-action@v3`, `attest-build-provenance@v1`, …). `trivy.yml`
  is only *partially* pinned. A hijacked tag exfiltrates registry-push / deploy creds. `ci.yml` is
  `contents:read` only → low blast radius. **Fix:** pin to commit SHAs. **Effort: small, mechanical.**
- **Root `docker-compose.yml` never forwards `LQ_AI_GATEWAY_MASTER_KEY`** (upstream #278). The gateway env
  block forwards `LQ_AI_GATEWAY_KEY` but not the master key, so the **Fernet runtime key store is silently
  off** and every in-app provider-key set returns `400 failed_precondition`. Same gap confirmed in our root
  compose. **Fix: one line.** (Trivial — but check it doesn't collide with our KV/managed-identity path,
  ADR-F069/F072, which may make it moot for Azure tenants.)
- **Gateway sanitized-config endpoint leaks `api_key_encrypted` ciphertext** (buried in upstream #273). Our
  `_sanitized_config_payload` is a documented **no-op** while `ProviderConfig.api_key_encrypted` (Fernet
  ciphertext of runtime-set keys) exists in baseline config — `GET /admin/v1/config` returns the ciphertext.
  **Fix: strip the field.** Trivial. *(Verify it applies — if the fork never populates
  `api_key_encrypted` because keys come from env/KV, this is latent-not-live; still worth closing.)*

### 🟡 Data-integrity + correctness

- **Ingest parse-timeout strands files in `processing` forever** (upstream #196). A Docling parse exceeding
  arq's `job_timeout` is hard-killed with `CancelledError`, bypassing every `except`, leaving the file row
  stuck in `processing` (UI polls forever). **Fix:** in-job `asyncio.wait_for` **soft** timeout that marks
  the row `failed`, arq hard timeout bumped above it. Kept substrate. **Effort: small.** (We hit adjacent
  ingest hangs in the Commercial UAT — this is the same failure class.)
- **`max_tokens` → `max_completion_tokens` for GPT-5/o-series** (upstream #157). Reasoning deployments
  **hard-400** on `max_tokens` (OpenAI *and* Azure). Upstream added an opt-in **per-provider**
  `use_max_completion_tokens` flag that renames the param in the shared `_to_openai_request` (per-provider,
  not model-heuristic, because Azure deployment ids are opaque). **Directly relevant** to our Azure Foundry
  workstream — if a tenant points at a GPT-5/o-series Azure deployment today, it 400s. **Effort: small.**

### 🟢 Ops-quality + one feature

- **Pin `ruff` exactly** (upstream #168 pinned `0.15.17`). Both our pyprojects still float `ruff>=0.6`,
  which is the **exact recurring pain** in our `ruff-version-drift` memory (dev formats clean, CI's newer
  ruff fails `--check`). **Fix: pin both.** Trivial, removes a whole class of CI churn.
- **Plain `text/markdown` ingest** (upstream #206) — *feature, but cheap and high-value.* A dependency-free
  `parse_text` branch: `.md`/`.txt` flow through the same chunk→embed→cite pipeline, storing decoded bytes
  **verbatim** as the canonical character stream so exact-match citations resolve byte-for-byte; rejects
  non-UTF-8/NUL rather than guessing charsets. In-house legal teams paste `.md`/`.txt` constantly.
  **Effort: small.** Needs adaptation to our reader registry (ADR-F029).

---

## DEFER (real, but lower priority or concept-only)

| Item | Refs | Why defer |
|---|---|---|
| **GW-04 — provider `base_url` has no https/SSRF/allowlist guard** | #288 (their #293) | Real SSRF from the sole-egress component: `base_url` validated as `min_length=1` only. But it requires a **gateway-admin config write** to exploit (operator-trust boundary), so lower than SEC-1/2. Fold into the security slice if cheap. |
| **GW-02/03/05 — anonymization trusts client flags; embeddings bypass; weak Presidio defaults** | #288 | The middleware reads client-set `lq_ai_privileged`/skip verbatim; embeddings skip anonymization+tier; SSN/IBAN/passport/IP recognizers off by default. **Upstream itself deferred these to a committee decision.** Own slice + policy call. |
| **Containers run as root; base images tag-pinned not digest-pinned** | #288, #301 | No `USER` directive in api/gateway/bridge Dockerfiles; `FROM python:3.12-slim` mutable. Squarely on the self-host promise but low severity. Own hardening slice. |
| **Halted runs must still synthesize (empty-answer-at-cap)** | #208, #207, #210 | Upstream's chat loop persisted a 0-char answer at the tool-call cap. **Their file is gone in the fork**, but the *bug shape* transfers to deepagents brakes (R4/R5): does a forced final round carry a synthesis directive? Worth a check, not urgent. |
| **Model numeric args → SQL + zombie-`running` on poisoned AsyncSession** | #239 | Their agentic-loop Critical: `top_k:-1` reached SQL; `DBAPIError` swallowed without `rollback()` poisoned the session → `PendingRollbackError` → zombie `running`. **Two checks for us:** (1) do our retrieval tools bound numeric args? (2) does our run-failure handler `rollback()` before the terminal write? |
| **ADR-0016 structural CI gates** (egress import-allowlist, audit payload-column scanner) | #209 | Cheap structural tests that enforce our *own* invariants (single audited egress, counts-not-payloads audit). Portable, defensive. Small slice when convenient. |
| **Deterministic honesty grade + quote-verification of retrieved content** | #216/#218/#225 | Concept, not code (their ledger tables absent here): char-verify the model's verbatim quotes against already-retrieved source (no LLM cost) + a deterministic per-output verdict. Lands on our Citation Engine substrate — a candidate *concept* for deepagents receipts. Own ADR'd slice. |
| **EUR-Lex authority source (get-by-CELEX)** | #257 | Keyless, quote-verifiable EU legislation + CJEU source with careful redirect/SSRF hardening. **Maps onto our EU practice areas** (Privacy, AI-Act). Attractive later; own slice behind the MCP/tool-egress milestone. |
| **Gateway tool-egress boundary + MCP adapter (ADRs 0014/0015)** | #158/#160/#165 | This is the **reference design** our CLAUDE.md gates the future MCP milestone on — SSRF-guarded egress, counts-only `tool_egress_log`, key-gated transport. Study when we open that milestone; don't build now (MCP is double-gated). |
| **Read-only, audit-logged auditor/compliance role** | #266 | Deployment-wide read-only role; every cross-user read writes an "audit-the-auditor" row; non-owners still 404. **An in-house legal dept is exactly the buyer of this.** Own slice; overlaps our RBAC (ADR-F064). |

---

## SKIP (verified not applicable)

- **DE-358 tool-use hardening (#215)** — maps 1:1 onto things we already built: streaming-`tool_use` bridge
  (AZ-2b) and resume-payload storage (HITL, migs 0093/0094). The two durable ideas (a tools-count cap on
  the bridge; encryption-at-rest for resume payloads) are worth a glance but there's no upstream code to
  take. *Note: resume-payload encryption-at-rest is a legitimate small hardening we could choose to add.*

---

## NOT NEEDED — 23 items (we already did it, or replaced the code)

**Convergences (we fixed the same bug independently — record in `UPSTREAM.md`):**
- **#154** gateway `lq_ai_*` strip → our **GW-STRIP #249** fixed the same Azure-400 class *more* robustly
  (central prefix-strip vs their two-key allowlist).
- **#155** provider-4xx misclassification → our **PR #96** shipped the same `_classify_provider_error` fix
  a day later, incl. the streaming path.
- **#187** governed tool-loop + Anthropic bridge + confirmation gate → **triple convergence**: our AZ-2b
  (unary+streaming bridge) + HITL-1/2/3 (ADR-F071) + deepagents.
- **#193** retire OpenWebUI MCP bypass stub → we deleted the whole husk in **F0-S6 (ADR-F006)** two weeks
  earlier.
- **#198** DOCX-via-Pandoc *proposal* → we already ship DOCX/PPTX/XLSX/EML/MSG via our own reader registry
  (ADR-F029, no GPL Pandoc).
- **#99** paddleocr sidecar unpullable → our compose already removed it.
- **#288 audit subset D-01/API-02/API-03/API-04** (stored-XSS, viewer RBAC, login/MFA rate-limiting) →
  already covered by our DOMPurify render path, `MutatingUser`/ADR-F064, and Redis limiter.
- **#217** `skill_inputs` drop → fixed pre-baseline (DE-328), inherited.

**Replaced/diverged (upstream fix targets code we rebuilt or deleted):** macOS launcher first-run fixes
(#147/#200/#277 — no launcher here), BYOK tenant key UI (#202 — we use env/KV/managed-identity,
ADR-F069/F072), API-side MCP registry + `/admin/mcp` (#166 — MCP double-gated), tool-governance ToolIntents
(#181 — our `guarded_tool_call` serves this), transparency Learn pages (#188/#262), chat tool-gate SSE
frames (#189 — HITL-3 deliberately took the opposite no-new-frame design), sticky-skills toggle (#211/#213
— area bindings do this), Citation Ledger UI (#228), WS-D matter sessions on the legacy executor
(#238/#240 — **upstream converging on our pivot thesis**, but retrofitted into the linear executor),
tabular wizard (#222 — our Grids tool, ADR-F055), inline `@document` refs (#258).

---

## NOTABLE FEATURES we deliberately skip (awareness only)

Recorded so future planning knows they exist upstream: the **macOS consumer launcher** distribution track;
the full **US legal-research authority stack** (CourtListener/GovInfo/EDGAR/EUR-Lex); the **MCP client +
per-user OAuth** implementation (our reference for the future gated milestone); the **Citation Ledger +
fiduciary gate + treatment (KeyCite-analog)** v0.6.0 flagship; **generated-OpenAPI CI drift-guard** (#255 —
borrowable technique, we're code-canonical so lower value); **stack-boot smoke CI** (#297 — catches exactly
our VM-deploy failure surface, backlog-worthy optional ops tooling); **gateway-native quality-escalation
routing** (#224 — maps onto our LLM-judge fan-outs); **auditor role** (already in Defer); **native Vite HMR
dev flow** (#281 — addresses our "rebuild the prebuilt bundle" pain).

---

## Recommended sequencing

1. **`UP-SEC-1` (next slice, before B-7a):** SEC-1 gateway-key enforcement + SEC-2 chat project IDOR/KB
   scoping. Both confirmed live, both small, both security. Fold in GW-04 `base_url` guard + the
   `api_key_encrypted` strip if cheap. One security-focused F005 review.
2. **`UP-OPS-1` (fast, mechanical):** SHA-pin Actions (#296) + exact-pin ruff (#168) + compose master-key
   forward (#278, if not moot under KV). Low-risk hygiene, no behavior change.
3. **`UP-FIX-1`:** ingest parse-timeout → `failed` (#196) + `max_completion_tokens` for GPT-5/o-series
   (#157, ties into Azure Foundry). Small.
4. **`text/markdown` ingest (#206)** — bundle into a "small wins" slice or fold into UP-FIX-1.
5. Everything in **Defer** stays in the backlog; the MCP/authority/ledger reference designs get pulled in
   when we actually open those ADR'd milestones.

Each taken item, on merge, gets one `UPSTREAM.md` sync-log row (ref, what, why) per ADR-F001. Convergences
get an awareness row too (no code taken, but the record shows we reached the same fix independently).
