"""Migration-0100 up→down→up probe (a script, NOT a pytest module).

Evidence tooling for INTAKE-4a, kept out of ``api/tests/`` so nothing collects
or imports it. It exists because the interesting half of a BACKFILL migration is
what it does to rows that already exist, which no unit test can observe: seed
matters at 0099, upgrade, read the series back, downgrade, confirm nothing but
the new columns went away, upgrade again, confirm the series is identical.

**Run it against a THROWAWAY pgvector container only** — never the dev database
(CLAUDE.md § Dev-environment hard rules). It writes rows. See ``README.md`` in
this directory for the full recipe and the recorded run.

    DATABASE_URL=... python migration_0100_probe.py seed   # while at 0099
    DATABASE_URL=... python migration_0100_probe.py check  # after 0100
    DATABASE_URL=... python migration_0100_probe.py gone   # after the downgrade
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

URL = os.environ["DATABASE_URL"]


async def seed() -> None:
    engine = create_async_engine(URL)
    async with engine.begin() as conn:
        user_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password) "
                "VALUES (:id, :email, 'x') ON CONFLICT DO NOTHING"
            ),
            {"id": user_id, "email": f"probe-{uuid.uuid4().hex[:6]}@example.com"},
        )
        area_id = (
            await conn.execute(text("SELECT id FROM practice_areas WHERE key = 'commercial'"))
        ).scalar_one()
        for n, (name, area) in enumerate(
            [("Older commercial", area_id), ("Newer commercial", area_id), ("Unfiled", None)]
        ):
            await conn.execute(
                text(
                    "INSERT INTO projects (owner_id, practice_area_id, name, slug, created_at) "
                    "VALUES (:owner, :area, :name, :slug, now() + make_interval(secs => :n))"
                ),
                {
                    "owner": user_id,
                    "area": area,
                    "name": name,
                    "slug": f"probe-{n}-{uuid.uuid4().hex[:6]}",
                    "n": float(n),
                },
            )
        # A sandbox row: must be skipped by the backfill (a sandbox is not a matter).
        await conn.execute(
            text(
                "INSERT INTO projects (owner_id, name, slug, is_sandbox) "
                "VALUES (:owner, 'Try-it sandbox', :slug, true)"
            ),
            {"owner": user_id, "slug": f"__sandbox__{uuid.uuid4().hex[:6]}"},
        )
    await engine.dispose()
    print("seeded 3 matters + 1 sandbox at 0099")


async def check() -> None:
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT name, reference, is_sandbox FROM projects "
                    "ORDER BY is_sandbox, reference NULLS LAST"
                )
            )
        ).all()
        for name, reference, is_sandbox in rows:
            print(f"  project {name!r:20} sandbox={is_sandbox} reference={reference}")
        areas = (
            await conn.execute(text("SELECT key, area_code FROM practice_areas ORDER BY position"))
        ).all()
        for key, code in areas:
            print(f"  area {key!r:16} code={code}")
        counters = (
            await conn.execute(
                text("SELECT area_code, next_value FROM matter_reference_counters ORDER BY 1")
            )
        ).all()
        for code, nxt in counters:
            print(f"  counter {code} next={nxt}")
        org = (await conn.execute(text("SELECT count(*) FROM organization_profile"))).scalar_one()
        print(f"  organization_profile rows={org}")
    await engine.dispose()


async def gone() -> None:
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        for table, column in (
            ("projects", "reference"),
            ("practice_areas", "area_code"),
            ("organization_profile", "org_code"),
            ("intake_threads", "claimed_reference"),
            ("intake_messages", "in_reply_to"),
            ("intake_messages", "references_header"),
        ):
            present = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c"
                    ),
                    {"t": table, "c": column},
                )
            ).scalar_one()
            assert present == 0, f"{table}.{column} survived the downgrade"
        tables = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'matter_reference_counters'"
                )
            )
        ).scalar_one()
        assert tables == 0, "matter_reference_counters survived the downgrade"
        projects = (await conn.execute(text("SELECT count(*) FROM projects"))).scalar_one()
    await engine.dispose()
    print(f"downgrade clean: every 0100 column/table dropped, {projects} projects intact")


if __name__ == "__main__":
    asyncio.run({"seed": seed, "check": check, "gone": gone}[sys.argv[1]]())
