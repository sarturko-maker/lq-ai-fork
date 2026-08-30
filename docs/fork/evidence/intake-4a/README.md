# INTAKE-4a — migration 0100 up→down→up evidence (ADR-F088)

Migration `0100_matter_reference_and_stamping.py` BACKFILLS: it writes a matter
reference onto every existing non-sandbox project and an `area_code` onto every
existing practice area. The half worth proving is therefore what it does to rows
that already exist — which no unit test observes, because the test database is
migrated to head before a single row is inserted.

`migration_0100_probe.py` is that check. **Throwaway container only** — it writes
rows, and CLAUDE.md forbids running alembic against the dev database.

## Recipe

```bash
docker network create mig0100net
docker run -d --name mig0100pg --network mig0100net \
  -e POSTGRES_PASSWORD=throwaway -e POSTGRES_USER=lq_ai -e POSTGRES_DB=lq_ai \
  pgvector/pgvector:pg16

run() {  # the api dev image, repo mounted, pointed at the throwaway DB
  docker run --rm --network mig0100net -v "$PWD":/repo -w /repo/api \
    -e DATABASE_URL="postgresql+asyncpg://lq_ai:throwaway@mig0100pg:5432/lq_ai" \
    lq-ai-api "$@"
}

run alembic upgrade 0099
run python ../docs/fork/evidence/intake-4a/migration_0100_probe.py seed
run alembic upgrade head
run python ../docs/fork/evidence/intake-4a/migration_0100_probe.py check
run alembic downgrade -1
run python ../docs/fork/evidence/intake-4a/migration_0100_probe.py gone
run alembic upgrade head
run python ../docs/fork/evidence/intake-4a/migration_0100_probe.py check

docker rm -f mig0100pg && docker network rm mig0100net
```

## Recorded run (2026-08-30)

Seeded at 0099: two Commercial matters (created a second apart), one matter with
no practice area, one sandbox.

```
=== UP to head (0100) ===
Running upgrade 0099 -> 0100, INTAKE-4a — matter reference (ORG-AREA-NNNN) + email stamping substrate (ADR-F088)
0100 (head)
=== backfill result ===
  project 'Older commercial'   sandbox=False reference=ORG-COM-0001
  project 'Newer commercial'   sandbox=False reference=ORG-COM-0002
  project 'Unfiled'            sandbox=False reference=ORG-GEN-0001
  project 'Try-it sandbox'     sandbox=True  reference=None
  area 'commercial'     code=COM
  area 'disputes'       code=DIS
  area 'm-and-a'        code=MNA
  area 'privacy'        code=PRV
  area 'employment'     code=EMP
  counter COM next=3
  counter GEN next=2
  organization_profile rows=0
=== DOWN one (0100 -> 0099) ===
Running downgrade 0100 -> 0099, …
0099
downgrade clean: every 0100 column/table dropped, 4 projects intact
=== UP again ===
0100 (head)
=== backfill result after re-up ===
  (byte-identical to the first run — same references, same codes, same counters)
```

What this proves:

- references are assigned in `created_at` order **per area**, so the oldest
  matter in an area is `-0001`;
- a matter with no practice area falls to the reserved `GEN` series;
- a **sandbox gets no reference** (a sandbox is not a matter);
- area codes come from the shipped defaults (`COM`/`PRV`/…), not from a
  re-derivation that could disagree with the profile manifests;
- the counters are seeded PAST the backfill, so the first runtime allocation
  cannot collide with a backfilled row;
- the downgrade drops every column and the counter table and **keeps the
  projects**, and a re-upgrade reproduces the identical series (idempotent).

`org_code` is unset here (no `organization_profile` row on a fresh deployment),
so the references render with the neutral `ORG` placeholder — the admin sets the
real code on the House Brief page or in the setup wizard, and references minted
before that stay valid and unique.
