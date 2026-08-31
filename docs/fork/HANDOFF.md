# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## State

- Branch: `intake-sec-hardening` — **INTAKE security-hardening pass; PR pending**. A fresh-context
  adversarial security review of the whole email-intake series (#290–#300) + verified fixes (F1–F7).
  **No migration** (auth_state column/CHECK already admit pass/fail/unknown). Report + live evidence:
  `docs/fork/evidence/intake-security-review/` (README = findings + not-prod-ready list; f3-live-proof).
- Prior: INTAKE 0..4b + 5 plan + 5a + 5a.1 (#290–#300). Next feature slice remains **INTAKE-5b**
  (human attach, ADR-F089) — unchanged by this pass.
- Fixes: F1 stamp-before-enqueue (finishes the #300 P1); F2 remove layer-2 sibling-guess (fail closed);
  F3 honest auth_state (DMARC parse, method-anchored, never fake "pass"); F4 Trojan-Source neutralise
  name/label/note; F5 webhook body streaming cap; F6 drop dead /send attachments + cap; F7 six small
  correctness/contract fixes. Documented-not-fixed: rate limiting / work amplification, injection
  blast radius on writes (HITL-gate record_intake_outcome), dedicated send token, dead-letter, full
  authserv-id AR parsing, layer-2 forward/CC transferability, prod webhook never run.
- Verified: full api `-m "not provider"` (counts in PR); mail-bridge 123; mypy api 259 + mail-bridge
  --strict clean; ruff clean; F3 proven live vs captured provider payload; two fresh-context diff
  reviewers (caught+fixed F3 DMARC-forgery regex, F2 dead code, F7c agent-subject asymmetry in-slice).

## Next slice — INTAKE-5b — human attach (1 day)

Plan #298 ruling 4 + ADR-F089 to draft: `POST /intake/threads/{id}/attach {project_id}` moves
thread + `agent_threads.project_id` + the thread's ingested files onto an OPEN owned matter
(cross-owner 404); 409 while `is_conversation_in_flight`; clears `claimed_reference`; archives
an intake-born now-empty source matter (note "merged into <ref>"); audit ids/counts only.
Web: "Attach to matter…" + `AttachToMatterDialog`. Live script: stranger's tagged email → stub
with claim → attach → stub archived → sender's next reply continues the SAME conversation.
Then INTAKE-6 acceptance; demo-prep pass (seed pack + reply signature/tone doctrine) is on
offer to the maintainer before or after 5b.

## Pick up exactly here

1. Merge PR #300 when CI is green (gate evidence in the PR body; wait for green — repo has NO
   required checks, `--auto` merges instantly).
2. Draft ADR-F089 + build INTAKE-5b, review, live, merge.
Working model: Sonnet easy / Opus implement+review+fix / Fable orchestrate, design, live-verify,
merge.

## Gotchas

- **`gh pr merge --auto` merges IMMEDIATELY here** (no required checks). Wait for CI green.
- **Prod rebuilds overwrite `lq-ai-api`** → dev image tag `lq-ai-api-dev` + override file
  (`services.api.image: lq-ai-api-dev`, `build: !reset null`); run compose from the MAIN
  checkout (worktrees lack `.env`), and remember the Bash cwd PERSISTS between commands.
- **`&` backgrounds the whole preceding `&&` chain** — a `git checkout && … && setsid … &`
  backgrounds the checkout too (a rebuild once built `main` silently). Verify `git log -1`
  before building; `--force-recreate` after a wrong-image `up`.
- **Async-ORM trap (bit twice):** never read an ORM attribute after a failed flush or
  rollback — capture scalars first. A lost `uq_agent_runs_thread_running` race must surface
  as AgentThreadBusy/defer, never thread `error`.
- **`pgrep -f`/`pkill -f` match your own shell** — anchor (`^/bin/bash <script>`).
- Long jobs: `setsid nohup <script> >> log & disown` + Monitor; `sleep` is blocked — use
  until-loops in Monitor/background Bash. Python run by path doesn't put cwd on sys.path —
  `docker compose exec -e PYTHONPATH=/app api python /tmp/x.py`.
- Requeue surgery: pending = inbound `run_id IS NULL`; un-stamp + `enqueue_intake_email_job
  (thread_id, provider_message_id=…)`; arq job id deterministic per message, `keep_result=0`.
- Synthesising inbound mail: python INSIDE mail-bridge container (`LQ_AI_BRIDGE_TOKEN` stays
  in its env) → `POST /api/v1/internal/intake/emails` with `InboundEmailEnvelope`.
- Headless shots: puppeteer-core + `/usr/bin/chromium`, `lq_ai_auth` localStorage token
  (minted in the api container to a file; expires — re-mint per session).
- Many threads share ONE conversation → `live_ask` true on every sibling while paused;
  `waiting_on` names the ask's thread. Sent `intake_messages` rows have NO
  `provider_timestamp` (coalesce created_at). Summarise pass: marker column, not arq payload.
- `ruff` from repo root with `--no-cache` (`.ruff_cache` is root-owned). Bare `pytest` in the
  api container runs provider tests — `-m "not provider"`. `docker compose exec` supports `-w`.
- AgentMail traps: `reply()` takes no subject; plus-addressing → base inbox; provider
  lowercases addresses; provider `message_id` canonical.
- INTAKE tripwires: `draft_email_reply` hitl-gated UNCONDITIONALLY, execution IS the send, no
  retries; weak stamps never auto-merge; AgentMail creds never in `api`; summaries/titles are
  agent text about untrusted mail — text interpolation only, sizes capped, bidi rejected.
