# SETUP-3a isolated live smoke — 2026-07-03

Throwaway pgvector+redis, worktree api under real uvicorn (dev image), NO dev-stack contact.
Note: the two 'FAIL' lines are smoke-harness assertion bugs (change-password correctly
returns 204 No Content, harness expected 200) — proven by the subsequent re-logins passing.

```
bootstrap: admin + operator passwords scraped
FAIL admin forced password change (want 200 got 204)
FAIL operator forced password change (want 200 got 204)
OK   fence: admin GET /admin/aliases denied (403)
OK   fence: operator passes /admin/aliases (503 — gateway absent, fence cleared)
OK   GET tier-policy stays admin-readable (503)
OK   escalation: invite role=operator refused (422)
OK   invite created, email_sent=false, accept_url present
OK   accept-invite creates the user (201)
OK   invited member can log in
OK   invite token is single-use (400)
OK   member denied /admin/aliases (403)
OK   reset-request uniform for real vs ghost ({"status":"ok"}|202)
OK   admin disables member (200)
OK   disabled member's live token 401s (401)
OK   disabled-login byte-identical to wrong-password
OK   admin re-enables member (200)
OK   re-enabled member logs in again
OK   admin cannot disable the operator (403)
OK   admin cannot demote the operator (403)
==============================
SMOKE RESULT: 17 passed, 2 failed
api-log lines containing 'token=': 0 (should be 0 — no token leaks in logs)
```
