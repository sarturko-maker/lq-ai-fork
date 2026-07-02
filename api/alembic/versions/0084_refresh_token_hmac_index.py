"""Replace the bcrypt refresh-token hash with a deterministic HMAC index — SAAS-2 (ADR-F059)

``/auth/refresh`` previously scanned EVERY active ``user_sessions`` row and
bcrypt-compared each (a per-row salt makes a bcrypt column unindexable) — a
CPU-DoS that reached tens of seconds under accumulated sessions and amplified
under a bad-token flood. Refresh tokens are 32 bytes of CSPRNG output (~256
bits), so they are not brute-forceable offline; a deterministic HMAC-SHA256 is a
sufficient at-rest verifier and turns the lookup into ONE indexed equality query
(ADR-F059). bcrypt stays for PASSWORDS only.

Schema change:
  * DROP column ``refresh_token_hash`` (bcrypt) — its partial index
    ``idx_user_sessions_token_hash`` (0001) is cascade-dropped with the column.
  * ADD column ``refresh_token_hmac`` (VARCHAR(64), NOT NULL) + a UNIQUE index.

Existing rows CANNOT be backfilled: the HMAC is over the token plaintext, which
was never stored (only the bcrypt hash was), so there is no way to derive the new
verifier from an old row. This migration therefore DELETES all ``user_sessions``
rows first — every currently-logged-in user must log in once more. Impact is
dev-only in practice (no production tenants exist yet) and cosmetic (one
re-login); refresh-token rotation already assumes sessions are disposable.

Downgrade is destructive in the same way (bcrypt hashes are gone): it deletes all
sessions, drops the HMAC column + index, and restores ``refresh_token_hash``.

Revision ID: 0084
Revises: 0083
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_user_sessions_refresh_token_hmac"


def upgrade() -> None:
    # Existing bcrypt rows have no recoverable plaintext to re-derive the HMAC
    # from — clear them so the NOT NULL column can be added on an empty table and
    # no stale, unusable session lingers.
    op.execute("DELETE FROM user_sessions")
    op.add_column(
        "user_sessions",
        sa.Column("refresh_token_hmac", sa.String(length=64), nullable=False),
    )
    op.create_index(
        _INDEX_NAME,
        "user_sessions",
        ["refresh_token_hmac"],
        unique=True,
    )
    # Dropping the column cascade-drops its 0001 partial index
    # (idx_user_sessions_token_hash WHERE revoked_at IS NULL).
    op.drop_column("user_sessions", "refresh_token_hash")


def downgrade() -> None:
    # Symmetrically destructive: HMAC verifiers cannot become bcrypt hashes.
    op.execute("DELETE FROM user_sessions")
    op.add_column(
        "user_sessions",
        sa.Column("refresh_token_hash", sa.Text(), nullable=False),
    )
    # Restore the original 0001 partial index over the bcrypt column.
    op.execute(
        "CREATE INDEX idx_user_sessions_token_hash "
        "ON user_sessions (refresh_token_hash) WHERE revoked_at IS NULL"
    )
    op.drop_index(_INDEX_NAME, table_name="user_sessions")
    op.drop_column("user_sessions", "refresh_token_hmac")
