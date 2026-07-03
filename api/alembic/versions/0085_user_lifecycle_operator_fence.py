"""User lifecycle tokens + operator fence — SETUP-3a (ADR-F061)

Three additive changes that back the invite / password-reset / disable
lifecycle and the operator-role fence (ADR-F058 §5, ADR-F061):

1. ``user_auth_tokens`` — ONE table for both single-use lifecycle tokens
   (``purpose`` ∈ ``invite`` | ``password_reset``). Only the domain-separated
   HMAC-SHA256 verifier (``token_hmac``, VARCHAR(64) UNIQUE) is stored — never
   the plaintext (ADR-F059 token-at-rest pattern). ``email`` (CITEXT) is the
   invite target; ``user_id`` (CASCADE) is the reset target; ``role`` is the
   invited role. ``consumed_at`` / ``revoked_at`` enforce single-use + revoke.

2. ``users.disabled_at`` + ``users.email_verified_at`` (TIMESTAMPTZ NULL) —
   admin disable/re-enable is a timestamp, not a boolean (D5); invite-accept
   stamps ``email_verified_at`` (verification IS the accept step).

3. The 0017 ``chk_users_role_enum`` CHECK is dropped and recreated to add the
   ``operator`` value: ``role IN ('admin','member','viewer','operator')``. The
   operator role is minted ONLY by the first-run bootstrap and never transits
   the org-admin role endpoint (ADR-F061 D3 escalation guard).

Reversible: ``downgrade()`` drops the table + the two columns and restores the
three-value role CHECK. (Any ``operator`` rows must be reclassified before a
downgrade or the restored CHECK will reject them — acceptable for a role that
only the bootstrap mints.)

Revision ID: 0085
Revises: 0084
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

_ROLE_CHECK = "chk_users_role_enum"


def upgrade() -> None:
    # --- 1. user_auth_tokens ------------------------------------------------
    op.create_table(
        "user_auth_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("purpose", sa.Text(), nullable=False),
        # Invite target (case-insensitive email). NULL for password_reset.
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        # Reset target. NULL for invite. CASCADE so deleting the user clears
        # any outstanding reset token.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_auth_tokens_user_id"),
            nullable=True,
        ),
        # Invited role (NULL for password_reset). 'operator' is intentionally
        # NOT allowed — operator accounts are bootstrap-only (ADR-F061 D3).
        sa.Column("role", sa.Text(), nullable=True),
        # Domain-separated HMAC-SHA256 hex verifier (64 chars); the plaintext is
        # never stored (ADR-F059). Unique so a redeem is one indexed lookup.
        sa.Column("token_hmac", sa.String(length=64), nullable=False),
        # Admin who created the token (provenance). SET NULL if that admin is
        # later removed — the token record survives for audit.
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_user_auth_tokens_created_by"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('invite', 'password_reset')",
            name="chk_user_auth_tokens_purpose",
        ),
        # Role enum only constrains non-NULL values (NULL passes the IN check).
        sa.CheckConstraint(
            "role IS NULL OR role IN ('admin', 'member', 'viewer')",
            name="chk_user_auth_tokens_role",
        ),
        # Shape integrity: an invite carries its target email + role; a reset
        # carries its target user_id. Reject malformed rows at the boundary.
        sa.CheckConstraint(
            "(purpose = 'invite' AND email IS NOT NULL AND role IS NOT NULL) "
            "OR (purpose = 'password_reset' AND user_id IS NOT NULL)",
            name="chk_user_auth_tokens_shape",
        ),
    )
    op.create_index(
        "ix_user_auth_tokens_token_hmac",
        "user_auth_tokens",
        ["token_hmac"],
        unique=True,
    )
    # Speeds the pending-invite lookup (WHERE email=? AND purpose='invite' AND
    # consumed_at IS NULL AND revoked_at IS NULL).
    op.create_index(
        "ix_user_auth_tokens_email",
        "user_auth_tokens",
        ["email"],
    )
    op.create_index(
        "ix_user_auth_tokens_user_id",
        "user_auth_tokens",
        ["user_id"],
    )

    # --- 2. users.disabled_at + users.email_verified_at ---------------------
    op.add_column(
        "users",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- 3. widen the role CHECK to admit 'operator' ------------------------
    op.drop_constraint(_ROLE_CHECK, "users", type_="check")
    op.create_check_constraint(
        _ROLE_CHECK,
        "users",
        "role IN ('admin', 'member', 'viewer', 'operator')",
    )


def downgrade() -> None:
    # Restore the three-value role CHECK first (fails loudly if any operator
    # rows still exist — reclassify before downgrading).
    op.drop_constraint(_ROLE_CHECK, "users", type_="check")
    op.create_check_constraint(
        _ROLE_CHECK,
        "users",
        "role IN ('admin', 'member', 'viewer')",
    )

    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "disabled_at")

    op.drop_index("ix_user_auth_tokens_user_id", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_email", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_token_hmac", table_name="user_auth_tokens")
    op.drop_table("user_auth_tokens")
