# INTAKE security review — verified findings (2026-08-30)

Scope: the whole email-intake series, PRs #290–#300 (`803364b0..origin/main`), across
`api/`, `mail-bridge/`, and `web/`. Method: five fresh-context adversarial reviewers, one per
trust boundary (mail-bridge ingress/egress; ingestion + prompt-injection; read-API authz/IDOR;
agent composition + matter isolation; web XSS + secrets + supply-chain). **Every finding below
was re-verified against the actual code by the orchestrating session before it was recorded here** —
reviewer claims that did not survive that check are omitted or corrected.

This is a review of an IN-HOUSE v1 that is explicitly *not yet claimed production-ready*. The point
of the exercise is to be precise about which safety properties genuinely hold, which defects are
real, and which gaps are known-and-deferred rather than overlooked.

## What held up under attack (verified)

- **HITL send floor is structural, not prompted.** `draft_email_reply ∈ ALWAYS_INTERRUPT_TOOL_NAMES`,
  unioned in `_with_structural_floor` *after* policy compilation (un-removable by a malformed/empty
  `hitl_policy`), carried into every subagent spec by `stamp_subagent_opt_out`. The bridge is
  reply-only by construction — recipients derived from the replied-to message, never from the model's
  `to` — so even an approved *injected* reply can only reach the original sender. No auto-send path
  exists. The runner refuses to arm without a checkpointer, so there is no "ungated because
  persistence is off" path. (Traced independently by two reviewers.)
- **Prompt-injection fence.** Per-run `secrets.token_hex(8)` nonce; every 5+-dash run neutralised in
  every rendered field; one-line fields collapse line breaks; `single_line_neutralised` shared between
  the prompt and the Inbox read API. Fence-escape / injection corpus (`21-fence-escape`,
  `17-injection-attempt`) defeated structurally.
- **Matter-reference spoofing cannot cross owner.** Layer 2 matches only ids WE minted
  (`direction='out'`) + mailbox + owner fences; layer 3 requires a human-confirmed, active,
  address-form roster member compared in Python, and a cross-owner reference resolves to silence
  (same 200, no prompt/log distinction) — the 404-class posture applied to references.
- **Authz.** Owner fence in the SQL WHERE (not post-filter), cross-user 404 never 403, single
  statement shared by list/detail/summarise so they cannot drift, resume is IDOR-safe, admin routes
  `AdminUser`-gated. No string-built SQL anywhere; roster aliases matched in Python.
- **Secrets & web.** Bridge is sole holder of the AgentMail key; `hmac.compare_digest` /
  `secrets.compare_digest` both directions; presigned-URL log/span suppression verified; zero new
  `{@html}`, every sender/agent string text-interpolated; no leaked credentials or stray `.env*` in
  the diff; only new supply-chain surface is `agentmail` (pinned) + `svix`.

## Real defects (fixed in the `intake-sec-hardening` slice)

| # | Sev | File(s) | Defect | Fix |
|---|-----|---------|--------|-----|
| F1 | HIGH | `api/app/workers/intake_worker.py:244,311` | Run is enqueued before `message.run_id` is stamped; in that window a multi-thread conversation binds the run to the wrong sibling (the #300 P1 class — same wrong-sibling bind that failed live twice). The summarise path already fixed this with `_mark_then_enqueue`; the main path did not. | Stamp `message.run_id` inside an enqueue-wrapper callback, before the real enqueue — mirroring `_mark_then_enqueue`. |
| F2 | MED | `api/app/agents/intake_tools.py:404` | Layer-2 conversation-lineage heuristic runs for ANY stampless run, not only historic rows as its docstring claims; a modern stampless run (F1 window, or a lawyer-typed follow-up on the intake conversation) guesses a sibling. | Fail closed for post-0103 stampless runs; run the legacy heuristic only for historic rows. |
| F3 | HIGH | `mail-bridge/app/normalize.py:275` | `auth_state` hardcoded `"pass"` — false "Sender check passed" to model + UI; the model's caution branch is dead code; the real `Authentication-Results` verdict is dropped by the header allowlist. | Default `"unknown"` (honest); parse the receiver-prepended `Authentication-Results` DMARC verdict into pass/fail only when confidently present. UI already has an honest `unknown` branch. |
| F4 | MED | `api/app/api/intake_threads.py:316`, `api/app/schemas/intake.py:371` | Trojan-Source: subject-derived matter name rendered un-neutralised (though the adjacent subject IS); `label`/`note` skip the control+bidi rejection `matter_title`/`summary` enforce. | Neutralise the name at the read boundary; switch `label`/`note` to reject control+bidi. |
| F5 | MED | `mail-bridge/app/main.py:292` | `await request.body()` buffers a chunked (no-Content-Length) webhook body unbounded before the size check — pre-auth memory DoS. | Stream `request.stream()` with a running-total cap and abort. |
| F6 | MED | `mail-bridge/app/schemas.py` | `/send` admits ~350 MB base64 decoded inside validators (OOM the 6 GiB box) via a DEAD unused `attachments` field. | Drop the field; add the webhook's pre-read content-length cap to `/send`. |
| F7a | LOW | `api/app/api/admin_intake_mailboxes.py:197` | `PATCH {"active": null}` writes None into a NOT NULL column → 500 + poisoned session. | `_reject_explicit_null` on `IntakeMailboxUpdate.active`. |
| F7b | LOW | `api/app/schemas/intake.py:167` | `content_type` is plain `str`, contradicting the module's stated NUL-reject contract. | `_NulFreeStr`. |
| F7c | LOW | `api/app/schemas/agent_runs.py` | Edited-reply `subject` permits `\n` — latent SMTP header injection the moment subject reaches the bridge. | Reject `\n` in subject. |
| F7d | LOW | `api/app/api/intake_threads.py:646` | Summarise enqueue bypasses the per-user concurrent-run flood brake chat has. | Apply the `_MAX_CONCURRENT_RUNS_PER_USER` check (429). |
| F7e | LOW | `api/app/api/intake_threads.py:217` | `waiting_on` lateral has no owner fence of its own (leaks one sibling subject after an admin mailbox-owner reassignment). | Fence the lateral with the same owner predicate. |
| F7f | LOW | `api/app/config.py` | `lq_ai_mail_bridge_url` defaults to a live hostname, so an unconfigured deploy would POST the bridge token to whatever answers at `mail-bridge`. | Default `""`; let compose supply it (matches the client's "not configured ⇒ None" contract). |

## Genuinely not production-ready — documented, deferred, NOT silently patched

These are design-level gaps a prod cutover must close. They are recorded here rather than fixed
because each needs a product/trust-model decision, an ADR consequence line, or its own slice.

1. **No rate limiting / work amplification.** The intake address is public by design; nothing caps
   messages, new matters, reference-counter consumption, storage, or billed LLM runs per sender or
   per mailbox. ADR-F086 accepts per-thread inference cost for legitimate mail and defers a spam
   pre-filter as a cost optimisation; the *adversarial* case (someone chooses to send 10,000 emails)
   is unaddressed. RECOMMEND: a per-mailbox arrival budget (messages/hour, new-matters/hour) enforced
   before the project/reference/enqueue work, plus an admin-visible "pause this mailbox" switch.
2. **Injection blast radius on the writable tool surface.** An intake run holds the area's whole
   matter-write surface (matter memory, `apply_redline`, ROPA/assessment writes, grids); only the
   *send* has a structural HITL floor. Prompt injection in an inbound email can therefore drive
   un-approved matter-memory writes, a redline, or `record_intake_outcome("dealt_with")` (which sets
   `archived_at` — a counterparty could talk the agent into closing a live matter; soft/recoverable,
   but no human in that loop). Deliberate per ADR-F086 Ruling 1 (an ordinary run), but it is the
   largest remaining injection surface. RECOMMEND: an area policy that HITL-gates
   `record_intake_outcome`/`apply_redline` on intake-heavy areas, and an ADR consequence line.
3. **Sender-authentication is not really measured (F3's deeper half).** Even after the honest-floor
   fix, robust SPF/DKIM/DMARC requires parsing `Authentication-Results` from the trusted authserv-id
   (a sender can inject a forged AR header; only the receiver-prepended one is trustworthy). Until
   that lands, layer-3 roster attach trusts a `From:` it cannot authenticate — so a spoofed roster
   member + a guessable reference attaches into a matter. RECOMMEND: a real AR parse, then gate
   layer-3 attach on `auth_state == "pass"` (a failed/unknown claim falls to "new matter + note").
4. **Shared bridge token = send-as-the-company.** `LQ_AI_BRIDGE_TOKEN` (also held by slack/teams
   bridges, inbound-only) is now also the `/send` outbound capability. RECOMMEND a dedicated
   `LQ_AI_MAIL_SEND_TOKEN` held only by api + arq-worker.
5. **No dead-letter.** A deterministically-failing envelope (e.g. an attachment over a hardened
   upload cap) rolls back its idempotency claim and retries forever via Svix / reconciliation.
   RECOMMEND: commit an `error` claim state so redelivery short-circuits, surfaced in the Inbox.
6. **Layer-2 forward/CC transferability.** Layer 2 attaches on "you received our reply" — true of
   everyone CC'd or forwarded. Fenced by owner/mailbox so not cross-tenant; RECOMMEND confirming a
   layer-2 attach from a new sender address rather than merging silently.
7. **Prod webhook has never run.** No `mail-bridge` service or `/agentmail/webhook` route exists in
   `docker-compose.prod.yml` / `.private.yml`; the Svix-verified ingress is exercised only by unit
   tests. The only battle-tested ingress today is the dev websocket. Know this before first cutover.
8. **Containers run as root** (`mail-bridge/Dockerfile`, no `USER`) — matches every other service in
   the repo, so repo-wide hygiene debt, not an intake regression. RECOMMEND a repo-wide non-root pass.

## Adversarial review OF the fixes (in-slice, before merge)

The hardening diff was itself put through two fresh-context adversarial reviewers (api-side;
mail-bridge-side) plus a hand review. All fixes verified functionally correct; three issues were
caught and fixed IN this slice (not deferred):

- **F3 DMARC regex was forgeable (caught, fixed).** The first cut used `\bdmarc\s*=` — but an
  Authentication-Results value places attacker-controlled tokens (`envelope-from=`, `helo=` — the
  SMTP MAIL FROM local-part and HELO) BEFORE the real `dmarc=`, so `re.search` matched a forged
  `envelope-from=dmarc=pass@evil.com` first and upgraded a genuine `fail` to `"pass"`. Fixed by
  anchoring to a method boundary (`(?:^|;)\s*dmarc=`) + a regression test with the forgery string.
  (Full trust still needs the receiver's authserv-id — deferred item 3.)
- **F2 left the legacy layer-2 heuristic as dead code behind a guard (caught, simplified).** The
  first cut gated the sibling-guessing heuristic behind an `any_stamped` probe; review showed the
  guard made it unreachable, so the dead code was removed outright — binding now covers layers
  0/1/1b (marker / own stamp / resume lineage) and otherwise binds only the unambiguous single
  working thread, failing closed. Clearer intent, same (safe) behaviour.
- **F7c hardened only the human-edited subject, not the agent-drafted one (caught, extended).** The
  agent drafts the reply subject FROM untrusted mail and it renders in the outbound row, so it now
  takes the same control+bidi rejection as label/note/summary (`DraftEmailReplyInput.subject` →
  `_PlainLineStr`). The inaccurate "SMTP header injection" rationale on the human-edit validator was
  corrected to "display-only, defence-in-depth".

Verification: mail-bridge 123 passed, mypy --strict clean, ruff clean; api mypy 259 files clean,
ruff clean; full api suite `-m "not provider"` green (counts in the PR); no migration (auth_state
column/CHECK already admit pass/fail/unknown).
