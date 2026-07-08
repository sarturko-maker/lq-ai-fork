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
from app.models.deployment_branding import (
    HEX_COLOR_RE,
    PRODUCT_NAME_MAX,
    DeploymentBranding,
    contains_control_chars,
)
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


# ---------------------------------------------------------------------------
# First-run branding seed — BRAND-1a (ADR-F068)
# ---------------------------------------------------------------------------

# The seeder validates env-originated values against the SAME rules the PUT
# boundary enforces — imported from app/models/deployment_branding (single
# source, so the two boundaries cannot drift). An invalid accent/name is
# warned about and SKIPPED, never rewritten.


def _blend_hex(fg: str, bg: str, alpha: float) -> str:
    """Blend ``fg`` over ``bg`` at ``alpha`` opacity — both ``#RRGGBB``.

    Pure integer channel math (no image/colour dependency); used only to
    derive a sane ``status_running_wash`` from a seeded accent (ADR-F068).
    """

    def channel(i: int) -> int:
        f = int(fg[1 + 2 * i : 3 + 2 * i], 16)
        b = int(bg[1 + 2 * i : 3 + 2 * i], 16)
        return round(f * alpha + b * (1 - alpha))

    return "#" + "".join(f"{channel(i):02x}" for i in range(3))


def _accent_fan_out(accent: str, theme: str) -> dict[str, str]:
    """Fan one accent out into the brandable token family (ADR-F068).

    ``brand = ring = sidebar_ring = status_running = chart_1 = accent``;
    ``brand_foreground`` is white on light / ink on dark (matching the
    shipped defaults' pairing); the wash is the accent blended into the
    theme's canvas (8% over white / 16% over #111111) — a quiet pill
    background in the accent's hue, like the shipped #eef4ff / #14233a.
    """

    if theme == "light":
        foreground = "#ffffff"
        wash = _blend_hex(accent, "#ffffff", 0.08)
    else:
        foreground = "#111111"
        wash = _blend_hex(accent, "#111111", 0.16)
    return {
        "brand": accent,
        "brand_foreground": foreground,
        "ring": accent,
        "sidebar_ring": accent,
        "status_running": accent,
        "status_running_wash": wash,
        "chart_1": accent,
    }


async def ensure_first_run_branding(db: AsyncSession) -> bool:
    """Seed the deployment-branding singleton from BRAND_* env — BRAND-1a.

    Inserts ONLY when the ``deployment_branding`` table is empty AND at
    least one valid ``BRAND_*`` setting is configured — so an admin's
    in-app edits (which create/keep the row) always win over the env on
    every later restart. Returns True when THIS call inserted the row.

    Env values are validated with the same rules the PUT boundary applies
    (name ≤80 chars, no control characters; accents ``#RRGGBB``); an
    invalid value is logged at WARNING and skipped — never sanitized,
    never a boot crash (the lifespan's degrade-not-crash posture).
    Race-safe via ``ON CONFLICT DO NOTHING`` against the singleton index.
    """

    settings = get_settings()

    product_name = settings.brand_product_name or ""
    if product_name and (
        len(product_name) > PRODUCT_NAME_MAX or contains_control_chars(product_name)
    ):
        log.warning(
            "First-run branding: BRAND_PRODUCT_NAME is invalid "
            "(max %d chars, no control characters); ignoring it.",
            PRODUCT_NAME_MAX,
        )
        product_name = ""

    palette: dict[str, dict[str, str]] = {}
    for theme, accent in (
        ("light", settings.brand_accent_light),
        ("dark", settings.brand_accent_dark),
    ):
        if not accent:
            continue
        if not HEX_COLOR_RE.fullmatch(accent):
            log.warning(
                "First-run branding: BRAND_ACCENT_%s is not a #RRGGBB hex colour; ignoring it.",
                theme.upper(),
            )
            continue
        palette[theme] = _accent_fan_out(accent, theme)

    if not product_name and not palette:
        # Nothing (valid) configured for this deployment — clean no-op.
        return False

    # Fast path: a row exists (admin-written or previously seeded) — the env
    # NEVER overwrites it (idempotent on restart; admin edits win).
    existing = await db.execute(select(DeploymentBranding.id).limit(1))
    if existing.scalar_one_or_none() is not None:
        log.info("First-run branding: a branding row already exists; skipping seed.")
        return False

    # Race-safe insert: the partial unique index on ((true)) (migration 0090)
    # makes any concurrent second insert conflict; DO NOTHING without a target
    # covers it, mirroring the admin/operator bootstraps above.
    stmt = (
        pg_insert(DeploymentBranding)
        .values(product_name=product_name, palette=palette)
        .on_conflict_do_nothing()
        .returning(DeploymentBranding.id)
    )
    result = await db.execute(stmt)
    inserted_id = result.scalar_one_or_none()

    if inserted_id is None:
        # Another worker won the race — clean no-op for this one.
        log.info("First-run branding: lost the seed race; skipping.")
        await db.rollback()
        return False

    await db.commit()
    # Counts/lengths only — never the configured values themselves.
    log.info(
        "First-run branding: seeded singleton (name_length=%d, themes=%d).",
        len(product_name),
        len(palette),
    )
    return True
