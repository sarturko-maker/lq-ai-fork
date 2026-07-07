# Dev-box OOM shield (local-only, not shipped)

**Status:** applied 2026-07-07 on the maintainer's Crostini dev box only. **Not committed** — lives in
`docker-compose.override.yml`, which `.gitignore` already excludes. Prod is unaffected (it runs with
explicit `-f docker-compose.yml -f docker-compose.prod.yml`, which never loads the override).

## Why
The box has 6.3 GiB RAM and **no swap** (Crostini can't add swap). When the local ONNX embedder loads
during an ingest or an agent run, the ingest/arq workers spike; with no swap cushion the host OOM
killer fires and sometimes kills a **database client** mid-query. That leaves a Postgres backend with a
"broken pipe", which forces Postgres to recycle all connections and replay its WAL — a ~2-second window
where it refuses connections and any in-flight run fails with `CannotConnectNowError: the database
system is not yet accepting connections`.

## The shield (inverted — the direct form is impossible here)
**First attempt (failed): `oom_score_adj: -1000` on `postgres`.** This constrained Crostini Docker
won't let a container *lower* its OOM score below the parent's — that needs `CAP_SYS_RESOURCE`, which
the daemon doesn't grant — so runc refused to start the container (`can't get final child's PID from
pipe: EOF`). Postgres came straight back up on the plain config; no harm.

**What shipped: `oom_score_adj: 1000` on the two memory-hog workers** (`ingest-worker`, `arq-worker`)
via `docker-compose.override.yml`. *Raising* an OOM score is always permitted (no privilege), and it
achieves the same goal from the other side: under memory pressure the kernel picks a worker (badness
maxed by the +1000) as the victim before it ever touches Postgres/api/gateway (all at the default 0).
A killed ingest just retries; an agent run fails cleanly. The database never enters recovery, so other
work is unaffected. It does **not** create memory — under a big enough spike something still gets
killed, just always a restartable worker.

The two workers are the only in-process ONNX-embedder hosts (the reranker is off), so they are the
real spike sources as well as the sacrificial targets — the bias is exactly where the memory goes.

## Not chosen, and why
- **Swap** — impossible on Crostini.
- **Embedder → gateway (F056 Door B)** — would egress confidential document text to OpenAI and require
  re-ingesting the whole corpus (all chunks are embedded locally in the 768-dim column; the 1536-dim
  gateway column is empty). Rejected for a legal tool on privacy + re-ingestion cost.
- **Sequencing ingest vs agent runs** — a fine free habit, but discipline not a fix (background ingest
  has no clear "done" signal; a single heavy op can OOM alone).

## To revert
Delete `docker-compose.override.yml` (or the worker `oom_score_adj` blocks) and
`docker compose up -d ingest-worker arq-worker`.
