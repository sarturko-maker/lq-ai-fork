# F1-S1 live verification — dev stack, MiniMax-M3, 2026-06-12

Stack rebuilt on slice code (api + arq-worker + ingest-worker images
together; DB auto-migrated to 0052 on api boot). All times UTC.

## Scenario A — kill -9 the worker mid-run → sweep settles → thread continues

1. Run `f2c56c9b` created 202 on matter "S9 Eval — Single Doc 9001"
   (thread `84ab8268`); worker claimed it (`claimed_by
   cef806b8ba56:1:c18a4253`), steps appearing.
2. `docker kill -s KILL lq-ai-arq-worker-1` at **08:10:18**; run row
   frozen: `running`, heartbeat_at **08:10:16**.
3. Worker restarted 08:10:35 (fresh boot tag). Run stays `running`
   through the 08:11:30 sweep (heartbeat not yet stale — correct).
4. **08:12:30 cron sweep settles it**: `failed`, error
   `orphaned: worker heartbeat stale (claimed_by cef806b8ba56:1:c18a4253)`
   — 2m12s after the kill (threshold 120s + cron cadence). Audit row
   `agent_run.orphan_settled {"reason": "stale_heartbeat"}`.
5. Thread detail: `continuable: true`. Follow-up run on the same thread:
   202 → **completed**, grounded answer quoting the MSA's twelve-month
   cap — the checkpoint survived (durability=sync), the dangling
   tool call was repaired pre-invoke, and the model retained the
   interrupted run's context ("From the MSA document I just read").

Logs: `/tmp/f1s1-live-A-start.log`, `/tmp/f1s1-live-A-followup.log`
(session-local; key lines quoted above and in the worker log excerpt).

## Scenario B — cancel mid-run

1. Run `d1247aac` on "S9 Eval — Batch Fanout 9002" (thread `14fb158c`),
   3+ steps live.
2. `POST /runs/{id}/cancel` → **200 `cancelled` in 0.53s** (settle-first).
3. Second cancel → 200 `cancelled` (idempotent no-op, no extra audit row).
4. Worker log: `12.04s ⊘ agent-run:d1247aac…:agent_run_job aborted` —
   arq Job.abort delivered, no zombie spend.
5. Thread detail after cancel: `continuable: true`.
6. Audit row `agent_run.cancel {"from_status": "running"}`.

## Scenario C — thread delete removes checkpoint state

1. `DELETE /threads/14fb158c` → **204**; GET after → **404**.
2. `agent_runs` row cascaded with the thread (SQL count 0).
3. Library tables for the thread id:
   `checkpoints 0 · checkpoint_blobs 0 · checkpoint_writes 0`.
4. Audit row `agent_thread.delete {"runs_deleted": 1}`.

## Worker log excerpt (timeline)

```
08:08:09 Starting worker for 9 functions: …, agent_run_job,
         cron:agent_run_orphan_sweep, cron:checkpoint_gc_job
08:09:56 → agent-run:f2c56c9b…:agent_run_job
08:10:18 [docker kill -s KILL]
08:10:35 Starting worker (restart)
08:11:30 ← cron:agent_run_orphan_sweep ● {'swept': 0}   (not yet stale)
08:12:30 → cron:agent_run_orphan_sweep                   (settles f2c56c9b)
08:13:33 → agent-run:d1247aac…:agent_run_job
08:13:45 12.04s ⊘ agent-run:d1247aac…:agent_run_job aborted
```

Plus: migration `0052` confirmed via `alembic_version` and `\d agent_runs`
(claimed_by / claimed_at / lease_token / heartbeat_at present); idle-stack
sweep ticks return `{'swept': 0}`.

## Post-review-fix deployment spot check (final images, c0f8405)

The adversarial review's 35 confirmed findings were fixed and all three
services rebuilt. Spot check on the final images: matter-bound run
`018102cc` completed with a cited answer (Excluded Claims list,
`msa-vendor-services.txt, p. 1`); a second run cancelled mid-flight
(200 `cancelled`). The kill -9 / sweep scenario above exercised the
stale-heartbeat rule (120s, unchanged by the fixes); the unclaimed
grace changed 300s → 1200s after the review showed 300s could falsely
fail runs queued behind 900s legacy jobs.
