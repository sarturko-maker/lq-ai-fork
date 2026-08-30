"""INTAKE-4a — matter reference (ORG-AREA-NNNN) + email stamping substrate (ADR-F088)

Five additive schema items plus one backfill:

* ``organization_profile.org_code`` — the tenant's own short code (``NWT``),
  nullable, CHECK ``^[A-Z0-9]{2,6}$``. The admin sets it once (setup wizard /
  House Brief page). NULL = not set yet; the runtime falls back to the neutral
  placeholder ``ORG`` (``app.matters.reference.DEFAULT_ORG_CODE``) so a fresh
  deployment still mints unique, immutable references.

* ``practice_areas.area_code`` — the area's short code (``COM``), nullable with
  the same CHECK and a UNIQUE index over the non-NULL values. Backfilled here
  from the shipped defaults (``commercial`` → ``COM``, ``privacy`` → ``PRV``,
  … — the same map the profile manifests carry as ``code:``), else derived from
  the area's display name, uniquified on collision.

* ``matter_reference_counters(area_code, next_value)`` — one row per area CODE,
  taken with ``SELECT … FOR UPDATE``. Keyed by the code rather than the area id
  because the code is what appears in the string: if a code were ever re-minted
  on a different area, an id-keyed counter would restart at 1 and collide with
  references already issued. Matters filed under no area allocate under the
  ``GEN`` code (no practice-area row is created for it).

* ``projects.reference`` — the matter reference, globally UNIQUE (this
  deployment is single-tenant — there is no ``org_id`` anywhere — so global IS
  per-org) with a format CHECK. Backfilled for every non-sandbox project in
  ``created_at`` order per area, so the oldest matter in an area is ``-0001``.
  Sandboxes are deliberately skipped: a sandbox is not a matter (see
  ``chk_projects_sandbox_no_area``), so it gets no reference.

* ``intake_messages.in_reply_to`` / ``.references_header`` — the two RFC 5322
  threading headers the bridge already forwards inside the envelope's
  allowlisted ``headers`` map (``ALLOWED_HEADER_KEYS``). INTAKE-1 dropped them
  on the floor; the layer-2 resolver needs them persisted so a reply that
  arrives on a NEW provider thread can still be matched to a message we already
  hold. Bounds mirror the boundary cap in ``app.schemas.intake``.

* ``intake_threads.claimed_reference`` — an untrusted reference a sender put in
  a subject tag (or a plus-addressed recipient) that did NOT earn an attach
  (unknown reference, or a sender who is not on that matter's roster). Rendered
  into the intake prompt through the existing sanitisers so the agent can say
  "someone claims this belongs to X" without any code having merged anything.

**The derivation logic is duplicated, not imported.** Migrations in this repo
are self-contained (no migration imports ``app.*``); ``derive_code`` here is a
byte-for-byte behavioural twin of ``app.matters.reference.derive_code`` and
``tests/matters/test_reference_migration_parity.py`` fails the build if the two
ever disagree.

Downgrade is symmetric and drops only what this migration added.

Revision ID: 0100
Revises: 0099
Create Date: 2026-08-30
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

# --- mirrors of app.matters.reference (drift-guarded by a test) -------------
_CODE_PATTERN = "^[A-Z0-9]{2,6}$"
_REFERENCE_PATTERN = "^[A-Z0-9]{2,6}-[A-Z0-9]{2,6}-[0-9]{4,}$"
_REFERENCE_MAX_CHARS = 40
_DEFAULT_ORG_CODE = "ORG"
_GENERIC_AREA_CODE = "GEN"
_DERIVED_CODE_CHARS = 3
_CODE_MIN_CHARS = 2
_CODE_MAX_CHARS = 6
_STANDARD_AREA_CODES = {
    "commercial": "COM",
    "disputes": "DIS",
    "m-and-a": "MNA",
    "privacy": "PRV",
    "employment": "EMP",
    "ai-compliance": "AIC",
}

_NON_CODE_CHARS = re.compile(r"[^A-Z0-9]+")
_CODE_RE = re.compile(_CODE_PATTERN)


def _derive_code(name: str, *, chars: int = _DERIVED_CODE_CHARS) -> str | None:
    """Twin of ``app.matters.reference.derive_code`` — keep the two identical."""

    candidate = _NON_CODE_CHARS.sub("", name.upper())[:chars]
    if len(candidate) < _CODE_MIN_CHARS:
        return None
    return candidate


def _uniquify_code(candidate: str, taken: set[str]) -> str:
    """Twin of ``app.matters.reference.uniquify_code``."""

    if candidate not in taken:
        return candidate
    for suffix in range(2, 1000):
        tail = str(suffix)
        stem = candidate[: max(1, _CODE_MAX_CHARS - len(tail))]
        variant = f"{stem}{tail}"
        if _CODE_RE.match(variant) and variant not in taken:
            return variant
    raise RuntimeError("no free area code remains")  # pragma: no cover


def upgrade() -> None:
    conn = op.get_bind()

    # --- org code -----------------------------------------------------------
    op.add_column("organization_profile", sa.Column("org_code", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_organization_profile_org_code",
        "organization_profile",
        f"org_code IS NULL OR org_code ~ '{_CODE_PATTERN}'",
    )

    # --- area code ----------------------------------------------------------
    op.add_column("practice_areas", sa.Column("area_code", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_practice_areas_area_code",
        "practice_areas",
        f"area_code IS NULL OR area_code ~ '{_CODE_PATTERN}'",
    )
    op.create_index(
        "uq_practice_areas_area_code",
        "practice_areas",
        ["area_code"],
        unique=True,
        postgresql_where=sa.text("area_code IS NOT NULL"),
    )

    # ``GEN`` is reserved for area-less matters, so no real area may claim it.
    taken: set[str] = {_GENERIC_AREA_CODE}
    areas = conn.execute(
        sa.text("SELECT id, key, name FROM practice_areas ORDER BY position, created_at, id")
    ).all()
    for area_id, key, name in areas:
        candidate = (
            _STANDARD_AREA_CODES.get(str(key))
            or _derive_code(str(name))
            or (_derive_code(str(key)) or _GENERIC_AREA_CODE)
        )
        code = _uniquify_code(candidate, taken)
        taken.add(code)
        conn.execute(
            sa.text("UPDATE practice_areas SET area_code = :code WHERE id = :id"),
            {"code": code, "id": area_id},
        )

    # --- counter table ------------------------------------------------------
    op.create_table(
        "matter_reference_counters",
        sa.Column("area_code", sa.Text(), nullable=False),
        sa.Column("next_value", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("area_code", name="pk_matter_reference_counters"),
        sa.CheckConstraint(
            f"area_code ~ '{_CODE_PATTERN}'", name="chk_matter_reference_counters_area_code"
        ),
        sa.CheckConstraint("next_value >= 1", name="chk_matter_reference_counters_next_value"),
    )

    # --- projects.reference -------------------------------------------------
    op.add_column("projects", sa.Column("reference", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_projects_reference_format",
        "projects",
        f"reference IS NULL OR (reference ~ '{_REFERENCE_PATTERN}' "
        f"AND char_length(reference) <= {_REFERENCE_MAX_CHARS})",
    )
    op.create_index(
        "uq_projects_reference",
        "projects",
        ["reference"],
        unique=True,
        postgresql_where=sa.text("reference IS NOT NULL"),
    )

    org_code = conn.execute(
        sa.text("SELECT org_code FROM organization_profile WHERE org_code IS NOT NULL LIMIT 1")
    ).scalar()
    if not (isinstance(org_code, str) and _CODE_RE.match(org_code)):
        org_code = _DEFAULT_ORG_CODE

    # Backfill in creation order per area so the oldest matter in an area is -0001.
    # Sandboxes are not matters and get no reference.
    rows = conn.execute(
        sa.text(
            "SELECT p.id, COALESCE(a.area_code, :generic) AS code "
            "FROM projects p LEFT JOIN practice_areas a ON a.id = p.practice_area_id "
            "WHERE p.is_sandbox = false "
            "ORDER BY COALESCE(a.area_code, :generic), p.created_at, p.id"
        ),
        {"generic": _GENERIC_AREA_CODE},
    ).all()
    counters: dict[str, int] = {}
    for project_id, code in rows:
        area_code = str(code)
        number = counters.get(area_code, 0) + 1
        counters[area_code] = number
        conn.execute(
            sa.text("UPDATE projects SET reference = :ref WHERE id = :id"),
            {"ref": f"{org_code}-{area_code}-{number:04d}", "id": project_id},
        )
    for area_code, used in counters.items():
        conn.execute(
            sa.text(
                "INSERT INTO matter_reference_counters (area_code, next_value) "
                "VALUES (:code, :next) ON CONFLICT (area_code) DO NOTHING"
            ),
            {"code": area_code, "next": used + 1},
        )

    # --- intake threading headers + the untrusted claimed reference ---------
    op.add_column("intake_messages", sa.Column("in_reply_to", sa.Text(), nullable=True))
    op.add_column("intake_messages", sa.Column("references_header", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_intake_messages_in_reply_to_len",
        "intake_messages",
        "in_reply_to IS NULL OR char_length(in_reply_to) <= 500",
    )
    op.create_check_constraint(
        "chk_intake_messages_references_len",
        "intake_messages",
        "references_header IS NULL OR char_length(references_header) <= 2000",
    )
    op.create_index(
        "ix_intake_messages_provider_message_id",
        "intake_messages",
        ["provider_message_id"],
    )

    op.add_column("intake_threads", sa.Column("claimed_reference", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_intake_threads_claimed_reference",
        "intake_threads",
        "claimed_reference IS NULL OR "
        f"(char_length(claimed_reference) <= {_REFERENCE_MAX_CHARS} "
        f"AND claimed_reference ~ '{_REFERENCE_PATTERN}')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_intake_threads_claimed_reference", "intake_threads", type_="check")
    op.drop_column("intake_threads", "claimed_reference")

    op.drop_index("ix_intake_messages_provider_message_id", table_name="intake_messages")
    op.drop_constraint("chk_intake_messages_references_len", "intake_messages", type_="check")
    op.drop_constraint("chk_intake_messages_in_reply_to_len", "intake_messages", type_="check")
    op.drop_column("intake_messages", "references_header")
    op.drop_column("intake_messages", "in_reply_to")

    op.drop_index("uq_projects_reference", table_name="projects")
    op.drop_constraint("chk_projects_reference_format", "projects", type_="check")
    op.drop_column("projects", "reference")

    op.drop_table("matter_reference_counters")

    op.drop_index("uq_practice_areas_area_code", table_name="practice_areas")
    op.drop_constraint("chk_practice_areas_area_code", "practice_areas", type_="check")
    op.drop_column("practice_areas", "area_code")

    op.drop_constraint("chk_organization_profile_org_code", "organization_profile", type_="check")
    op.drop_column("organization_profile", "org_code")
