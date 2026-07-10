"""Shared advisory-lock key for Alembic migrations (HS-1).

Kept in its own tiny module rather than in ``alembic/env.py`` because importing
``env.py`` has the side effect of *running migrations* (its module tail calls
``run_migrations_online()``), so the key could not otherwise be imported by
tests or other code without triggering a migration run.

The key coordinates concurrent ``alembic upgrade head`` runners — e.g. multiple
``api`` replicas each running migrations on boot in a Kubernetes deployment.
Without it, they race the same DDL and all but one crash ("tuple concurrently
updated" / duplicate-object errors). See ``api/alembic/env.py`` for the
acquire/release seam and ``docs/fork/plans/ENTERPRISE-AZURE-K8S-phase1.md``
(§ Horizontal-scale blocker ledger, HS-1) for the finding.
"""

from __future__ import annotations

# Arbitrary-but-stable 32-bit value: 0x4C51_4149 == b"LQAI". Comfortably fits
# the ``bigint`` that ``pg_advisory_lock(bigint)`` takes. Never change it — a
# different value would stop coordinating with runners on the old value during
# a rolling upgrade.
MIGRATION_ADVISORY_LOCK_KEY = 0x4C51_4149
