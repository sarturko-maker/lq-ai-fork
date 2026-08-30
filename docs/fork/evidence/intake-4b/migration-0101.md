# Migration 0101 — `intake_messages.send_error` (INTAKE-4b, ADR-F087)

Verified `up → down → up` on a **throwaway** `pgvector/pgvector:pg16` container
(`lq-test-pg-4b`, database `mig0101`), never against the dev DB (CLAUDE.md
dev-environment hard rules). `api/` and `skills/` mounted; alembic run inside the
`lq-ai-api-dev` image.

## 1. `alembic upgrade head` (0099 → 0100 → 0101)

```
INFO  [alembic.runtime.migration] Running upgrade 0099 -> 0100, INTAKE-4a — matter reference (ORG-AREA-NNNN) + email stamping substrate (ADR-F088)
INFO  [alembic.runtime.migration] Running upgrade 0100 -> 0101, INTAKE-4b — intake_messages.send_error (ADR-F087)
```

`\d intake_messages` (relevant rows only):

```
 send_error           | text                     |           |          |
Check constraints:
    "chk_intake_messages_send_error_len" CHECK (send_error IS NULL OR char_length(send_error) >= 1 AND char_length(send_error) <= 100)
```

## 2. `alembic downgrade 0100`

```
INFO  [alembic.runtime.migration] Running downgrade 0101 -> 0100, INTAKE-4b — intake_messages.send_error (ADR-F087)
```

Both the column and the CHECK are gone, and the stamp is back at 0100:

```
select count(*) from information_schema.columns
  where table_name='intake_messages' and column_name='send_error';        -> 0
select count(*) from pg_constraint
  where conname='chk_intake_messages_send_error_len';                     -> 0
select version_num from alembic_version;                                  -> 0100
```

## 3. `alembic upgrade head` again

```
INFO  [alembic.runtime.migration] Running upgrade 0100 -> 0101, INTAKE-4b — intake_messages.send_error (ADR-F087)
```

```
send_error|YES|text
CHECK (((send_error IS NULL) OR ((char_length(send_error) >= 1) AND (char_length(send_error) <= 100))))
0101
```

Additive and nullable, so existing rows need no backfill and the downgrade is
lossless for every row the previous schema could hold.
