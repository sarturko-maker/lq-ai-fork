"""Deployment Branding ORM model — BRAND-1a (fork, ADR-F068).

Backs the singleton ``deployment_branding`` table per migration 0090.
Deployment branding is the tenant's white-label surface: a product name
shown in the UI chrome and email subjects, a validated accent palette
(the ADR-F013 "scarce blue" token family), and an optional raster logo.
Option-A stack-per-tenant (ADR-F058) means deployment-level == tenant-
level, so this is a singleton like ``organization_profile`` — no org
scoping, no per-org rows.

Singleton constraint enforced at the DB layer via the partial unique
index on ``((true))`` (see migration 0090); the endpoints keep the row
in place by upserting rather than inserting.

The logo lives as BYTEA in the row (≤512 KB, magic-byte-sniffed raster
only — ADR-F068): it must be readable on the UNAUTH branding surface
(the login page shows it), which rules out the auth-gated, user-owned
``files`` + S3 path. ``logo_content_type`` stores the SNIFFED type,
never the client-declared upload header.

This module is also the SINGLE SOURCE of the brand-validation rules
(name length cap, hex-colour shape, control-character predicate, palette
allowlist): the PUT boundary (:mod:`app.api.branding`), the first-boot
env seeder (:mod:`app.admin_bootstrap`) and the email composer's
belt-and-braces strip (:mod:`app.lifecycle_email`) all import them from
here, so the three surfaces cannot drift apart. Defined on the model
(not the router) so app-core modules never import from the API layer.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# ---------------------------------------------------------------------------
# Shared brand-validation rules (ADR-F068) — single source, no drift.
# ---------------------------------------------------------------------------

PRODUCT_NAME_MAX = 80
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Palette allowlist — the ADR-F013 "scarce blue" token family. CLOSED set:
# unknown themes/tokens are rejected, never stored. `--primary` is ink (#111)
# by design and stays non-brandable.
ALLOWED_PALETTE_THEMES = frozenset({"light", "dark"})
ALLOWED_PALETTE_TOKENS = frozenset(
    {
        "brand",
        "brand_foreground",
        "ring",
        "sidebar_ring",
        "status_running",
        "status_running_wash",
        "chart_1",
    }
)

# Characters that never belong in a product name: C0/C1 controls incl. CR/LF
# and DEL (category Cc — the name lands in SMTP subject headers, a header-
# injection surface), format characters (Cf — e.g. the U+202E RTL override
# used for display spoofing), and the Unicode line/paragraph separators
# (Zl/Zp — U+2028/U+2029).
_FORBIDDEN_NAME_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def contains_control_chars(value: str) -> bool:
    """True when ``value`` carries control/format/line-separator characters.

    Boundary predicate: the PUT validator and the env seeder REJECT (never
    sanitize) on it, per the CLAUDE.md boundary rule.
    """
    return any(unicodedata.category(ch) in _FORBIDDEN_NAME_CATEGORIES for ch in value)


def strip_control_chars(value: str) -> str:
    """``value`` with control/format/line-separator characters removed.

    For the email composer's belt-and-braces strip ONLY — the write
    boundaries reject via :func:`contains_control_chars` instead.
    """
    return "".join(ch for ch in value if unicodedata.category(ch) not in _FORBIDDEN_NAME_CATEGORIES)


class DeploymentBranding(Base):
    """The deployment's singleton white-label branding row.

    ``product_name`` empty means "default brand" (LQ.AI Oscar Edition);
    the web client and the email composer fall back to the shipped
    identity. ``palette`` is the validated brandable-token subset
    (``{"light": {token: "#RRGGBB", ...}, "dark": {...}}``) — the CLOSED
    allowlist is enforced at the PUT boundary (ADR-F068), never trusted
    from storage alone.

    ``updated_by`` is the admin who last wrote the row. Nullable and
    ``ON DELETE SET NULL`` — informational, survives the user's deletion
    (same posture as ``organization_profile.updated_by``).
    """

    __tablename__ = "deployment_branding"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_name: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("''"))
    palette: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    logo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_deployment_branding_updated_by"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<DeploymentBranding id={self.id} "
            f"name_len={len(self.product_name or '')} "
            f"has_logo={self.logo_bytes is not None} updated_at={self.updated_at}>"
        )
