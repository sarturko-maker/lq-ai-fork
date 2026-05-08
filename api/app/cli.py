"""LQ.AI backend CLI — operational commands for the API service.

Usage (from inside the API container; matches docs/quickstart.md):

    docker compose exec api python -m app.cli reset-admin-password [--email EMAIL]

Subcommands:
    reset-admin-password
        Reset the admin user's password. Generates a fresh random
        password, prints it to stdout, marks `must_change_password=True`
        on the user, and revokes all active sessions. Used by an
        operator who has lost access to the deployment.

The CLI shares the runtime configuration (DATABASE_URL, BCRYPT_ROUNDS,
etc.) from `app.config`, so it works against the same Postgres the API
service uses.

This module does NOT depend on the running FastAPI app — it constructs
its own engine/session and disposes it cleanly. It is safe to run while
the API is up.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.admin_bootstrap import generate_password
from app.config import get_settings
from app.models.user import User, UserSession
from app.security import hash_password

log = logging.getLogger("app.cli")


async def _reset_admin_password(email: str | None) -> int:
    """Reset the admin password and return a CLI exit code.

    If `email` is None, target the user with `is_admin=True`. If multiple
    admins exist, fail loudly and tell the operator which to target via
    --email.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session:
            target: User | None
            if email is not None:
                result = await session.execute(
                    select(User).where(User.email == email, User.deleted_at.is_(None))
                )
                target = result.scalar_one_or_none()
                if target is None:
                    print(f"error: no user found with email {email}", file=sys.stderr)
                    return 2
            else:
                result = await session.execute(
                    select(User).where(User.is_admin.is_(True), User.deleted_at.is_(None))
                )
                admins = result.scalars().all()
                if not admins:
                    print(
                        "error: no admin user exists yet. Start the API service "
                        "to trigger first-run admin creation.",
                        file=sys.stderr,
                    )
                    return 2
                if len(admins) > 1:
                    addresses = ", ".join(sorted(a.email for a in admins))
                    print(
                        "error: multiple admin users found "
                        f"({addresses}). Pass --email to disambiguate.",
                        file=sys.stderr,
                    )
                    return 2
                target = admins[0]

            new_password = generate_password()
            target.hashed_password = hash_password(new_password)
            target.must_change_password = True

            # Revoke any active sessions so a stolen refresh token from before
            # the reset can't be used.
            await session.execute(
                update(UserSession)
                .where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(tz=UTC)),
            )

            await session.commit()

            # Print to stdout so the operator can capture it in a pipeline.
            print(f"Reset password for {target.email}: {new_password}")
            print(
                "must_change_password is now true; the user will be forced to "
                "set a new password on next login."
            )
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a CLI exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="LQ.AI backend operational CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    reset = sub.add_parser(
        "reset-admin-password",
        help="Reset the admin password and force a change on next login.",
    )
    reset.add_argument(
        "--email",
        default=None,
        help=(
            "Specific email to reset. Omit to target the single existing "
            "admin user; required if multiple admins exist."
        ),
    )

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "reset-admin-password":
        return asyncio.run(_reset_admin_password(args.email))

    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable; argparse exits


if __name__ == "__main__":  # pragma: no cover - module-runner entry
    sys.exit(main())
