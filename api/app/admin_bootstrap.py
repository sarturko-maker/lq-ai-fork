"""First-run admin bootstrap — Task B2.

If no admin user exists in the database (i.e. the deployment is brand new),
we mint one with a randomly generated password and print the password to
the API container's logs at INFO level. The user is created with
`must_change_password=True`; the `/auth/change-password` endpoint flips
it to False once the operator sets a permanent password.

Race-safety: multiple uvicorn workers may start simultaneously. We use
`INSERT ... ON CONFLICT DO NOTHING` against the email unique constraint
so only one worker actually inserts. The losing worker(s) detect the
conflict (zero rows inserted) and silently skip — they won't print the
password, only the winner does. This avoids advisory locks and keeps the
startup path simple.

The default admin email is `admin@lq.ai`. Operators can override it via
`FIRST_RUN_ADMIN_EMAIL` (config.py's Settings has no ``env_prefix``, so the
env var is the bare field name — NOT ``LQ_AI_``-prefixed); the email never
changes after first-run, only the password is rotated through the
change-password endpoint or the `reset-admin-password` CLI.

Idempotency: subsequent restarts find an existing admin and skip silently
(no log line, no new password generated). The bootstrap is a no-op after
the first successful start.
"""

from __future__ import annotations

import logging
import secrets
import string

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.security import hash_password

log = logging.getLogger(__name__)

# Length and alphabet for the generated initial password. 24 characters of
# the URL-safe alphabet gives ~143 bits of entropy — well above any
# brute-force threshold for the time the operator takes to log in once
# and rotate. We use a mixed letter+digit alphabet rather than full
# URL-safe (which includes `-` and `_`) so the printed password reads
# cleanly in a log tail without quoting concerns.
_PW_LENGTH = 24
_PW_ALPHABET = string.ascii_letters + string.digits


def generate_password(length: int = _PW_LENGTH) -> str:
    """Generate a random password using a CSPRNG.

    Returns a string of `length` characters drawn uniformly from
    `_PW_ALPHABET` using `secrets.choice` (cryptographically secure).
    """
    return "".join(secrets.choice(_PW_ALPHABET) for _ in range(length))


async def ensure_first_run_admin(db: AsyncSession) -> str | None:
    """Create the first-run admin user if none exists.

    Returns the generated plaintext password if a new admin was created,
    or `None` if an admin already exists (no-op). The caller is expected
    to log the returned password at INFO level — we deliberately don't
    log it from inside this function so callers (e.g. tests) can capture
    the value without parsing logs.

    Logging from this function is limited to:
    - INFO line stating that the bootstrap is running and the outcome
      (created vs. already-exists), and
    - WARNING if the insert raises an unexpected error.

    The plaintext password is **only** returned from the function and
    **only** logged by the caller in `main.py`'s lifespan handler — it
    is never persisted anywhere besides the bcrypt hash in
    `users.hashed_password`.
    """
    settings = get_settings()
    admin_email = settings.first_run_admin_email

    # Fast path: an admin already exists. We check by `is_admin=True` rather
    # than email so an operator who renamed the admin (via DB migration or
    # manual update) doesn't trigger a second bootstrap.
    existing = await db.execute(
        select(User.id).where(User.is_admin.is_(True), User.deleted_at.is_(None)).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        log.info("First-run admin bootstrap: admin user already exists; skipping.")
        return None

    plaintext = generate_password()
    hashed = hash_password(plaintext)

    # Race-safe insert: ON CONFLICT DO NOTHING on the unique `email` column.
    # If two workers race here, only one row lands. We use RETURNING id to
    # tell whether THIS call inserted; if it didn't, another worker won and
    # we discard the password we generated (it was never persisted) and
    # treat it as a no-op.
    # `role="admin"` is set in addition to `is_admin=True` to keep the two
    # admin signals in sync. `is_admin` is the legacy boolean (per the
    # User model's history); `role` was introduced by migration 0017
    # (`alembic/versions/0017_user_role.py`) and is the canonical field
    # the frontend reads. If we only set `is_admin=True`, the user is an
    # admin to the authorization layer but reports `role="member"` to the
    # UI — subtle inconsistency that produces wrong role badges and
    # conditional-nav decisions. Always seed both.
    stmt = (
        pg_insert(User)
        .values(
            email=admin_email,
            display_name="LQ.AI Administrator",
            hashed_password=hashed,
            is_admin=True,
            role="admin",
            mfa_enabled=False,
            must_change_password=True,
        )
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(User.id)
    )
    result = await db.execute(stmt)
    inserted_id = result.scalar_one_or_none()

    if inserted_id is None:
        # Another worker won the race, OR a non-admin user already owned
        # this email (unlikely on first start but possible if the operator
        # pre-seeded one). Either way: we are not the writer, so the
        # plaintext we generated is dropped on the floor.
        log.info(
            "First-run admin bootstrap: %s already exists (lost race or pre-seeded); skipping.",
            admin_email,
        )
        await db.rollback()
        return None

    await db.commit()
    log.info("First-run admin bootstrap: created admin user %s.", admin_email)
    return plaintext


async def ensure_first_run_operator(db: AsyncSession) -> str | None:
    """Create the first-run operator (platform) account if configured — SETUP-3a.

    The operator owns the gateway-proxy surfaces (model aliases, provider keys,
    gateway config, tier-policy writes, tier-floor override) behind the
    ``OperatorUser`` fence (ADR-F061 D3/D4). Unlike the admin bootstrap — which
    always mints ``admin@lq.ai`` — the operator is created ONLY when
    ``FIRST_RUN_OPERATOR_EMAIL`` is set, so a self-host deployment with no
    separate operator simply never gets one.

    Returns the generated plaintext password if a new operator was created, or
    ``None`` when the feature is unconfigured OR an operator already exists (the
    caller logs the returned password at WARNING, exactly once, like the admin
    bootstrap). Idempotent + race-safe via ``ON CONFLICT DO NOTHING`` on email.

    The account is minted with ``role='operator'`` AND ``is_admin=True`` — the
    operator is a superset of the org-admin, so it also passes every
    ``AdminUser`` surface. ``must_change_password=True`` forces a first-login
    rotation. This is the ONLY path that mints an operator; the org-admin role
    endpoint can never promote to operator (ADR-F061 D3 escalation guard).
    """
    settings = get_settings()
    operator_email = settings.first_run_operator_email
    if not operator_email:
        # No operator configured for this deployment — clean no-op.
        return None

    # Fast path: an operator already exists (idempotent on restart).
    existing = await db.execute(
        select(User.id).where(User.role == "operator", User.deleted_at.is_(None)).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        log.info("First-run operator bootstrap: operator already exists; skipping.")
        return None

    plaintext = generate_password()
    hashed = hash_password(plaintext)

    stmt = (
        pg_insert(User)
        .values(
            email=operator_email,
            display_name="LQ.AI Operator",
            hashed_password=hashed,
            is_admin=True,
            role="operator",
            mfa_enabled=False,
            must_change_password=True,
        )
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(User.id)
    )
    result = await db.execute(stmt)
    inserted_id = result.scalar_one_or_none()

    if inserted_id is None:
        # Lost the race, or a non-operator user already owns this email.
        log.info(
            "First-run operator bootstrap: %s already exists (lost race or pre-seeded); skipping.",
            operator_email,
        )
        await db.rollback()
        return None

    await db.commit()
    log.info("First-run operator bootstrap: created operator user %s.", operator_email)
    return plaintext
