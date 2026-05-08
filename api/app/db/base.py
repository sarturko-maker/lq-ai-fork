"""SQLAlchemy declarative base.

Per docs/db-schema.md:
- snake_case for all identifiers; pluralized table names; singular column names
- TIMESTAMPTZ everywhere; created_at and updated_at on entity tables
- UUID v7 where supported, falling back to UUID v4 (gen_random_uuid())

We use UUID v4 throughout v1 — Postgres 16 has gen_random_uuid() built into
the pgcrypto extension and we don't want to take on the pg_uuidv7 third-party
extension dependency. Time-ordered insert ordering is a small optimization
that's not worth the supply-chain footprint for v1. A future migration can
swap to UUID v7 if we need it.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every ORM model in the api/ subsystem."""

    pass
