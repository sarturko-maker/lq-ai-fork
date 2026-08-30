"""The neutral matter reference ``ORG-AREA-NNNN`` — INTAKE-4a (ADR-F088).

Every matter — cockpit-created or intake-born — carries a short, sayable,
human-quotable reference:

    ``NWT-COM-0042``   org code · home practice-area code · per-area counter

Three deliberate properties (maintainer rulings 2026-08-30, plan
``docs/fork/plans/INTAKE-4-plan.md`` § Maintainer rulings):

* **Neutral.** Nothing in the string names this product. The codes are the
  tenant's own: ``ORG`` is set once by the admin (setup wizard / House Brief
  page), ``AREA`` is the practice area's own admin-editable code.
* **Home-area only.** ``AREA`` is the area that OWNS the matter
  (``projects.practice_area_id``). When a future milestone lets a second area
  help on a matter, the matter keeps this one reference — "which areas touch
  this matter" is a separate future relation, never a second reference.
* **Immutable.** Allocated once at matter creation and never rewritten; no
  PUT/PATCH path accepts it. The counter never reuses a number.

**Why a counter table and not a sequence.** ``matter_reference_counters`` is
an ordinary row per area code taken with ``SELECT … FOR UPDATE``: per-tenant
stacks stay migration-simple (no per-area DDL), the allocation participates in
the caller's transaction (a rolled-back matter creation rolls back its number
too, so the series has no holes), and a self-host dump/restore carries the
counters as data.

**Why the counter is keyed by the CODE, not the area id.** The code is what
appears in the string, so keying on it is what actually guarantees the string
is unique: if an area's code were later reused by a different area (renamed
away and re-minted elsewhere), an id-keyed counter would restart at 1 and
collide with references already issued under that code. Matters with no
practice area — legacy/unfiled rows — allocate under :data:`GENERIC_AREA_CODE`,
which is a code, not an area (no row is created for them).

Single-tenant note: this deployment has no ``org_id`` anywhere (CLAUDE.md
blocker #5; the SaaS posture is stack-per-tenant), so "unique per org" is
enforced as a plain global UNIQUE on ``projects.reference`` and the counter
table needs no org column.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_profile import OrganizationProfile
from app.models.practice_area import PracticeArea
from app.models.project import MatterReferenceCounter

# --- the code vocabulary ---------------------------------------------------

#: A short code — 2 to 6 characters, uppercase letters and digits only. The SQL
#: mirror of this pattern is the CHECK on ``organization_profile.org_code`` and
#: ``practice_areas.area_code`` (migration 0100). Keep the three in sync.
CODE_PATTERN = r"^[A-Z0-9]{2,6}$"
CODE_RE = re.compile(CODE_PATTERN)

CODE_MIN_CHARS = 2
CODE_MAX_CHARS = 6

#: How many characters a derived code takes from a name (``Commercial`` → ``COM``).
DERIVED_CODE_CHARS = 3

#: Used when the admin has not set an org code yet. Deliberately neutral: this
#: schema stores no company *name* to derive from (``organization_profile`` is a
#: single Markdown body), and the deployment's branding text is not the legal
#: entity's name — so the fallback is a placeholder the admin replaces, never a
#: guess and never a product name.
DEFAULT_ORG_CODE = "ORG"

#: The area code used by matters that file under no practice area. No practice
#: area row is created for it — it exists only as a counter key and a segment.
GENERIC_AREA_CODE = "GEN"

#: Shipped defaults for the standard/seeded areas, keyed by ``practice_areas.key``.
#: The shipped profile manifests (``profiles/<name>/profile.yaml`` ``code:``) are
#: the source of truth for the areas that HAVE a manifest; this map additionally
#: covers the areas migration 0053 seeds without one. A drift-guard test
#: (``tests/test_profile_loader.py``) asserts the two agree.
STANDARD_AREA_CODES: dict[str, str] = {
    "commercial": "COM",
    "disputes": "DIS",
    "m-and-a": "MNA",
    "privacy": "PRV",
    "employment": "EMP",
    "ai-compliance": "AIC",
}

#: The full reference. Segment bounds mirror :data:`CODE_PATTERN`; the counter is
#: zero-padded to 4 digits and simply grows past 4 (``…-10000``) — it is never
#: truncated and never wraps.
REFERENCE_PATTERN = r"^[A-Z0-9]{2,6}-[A-Z0-9]{2,6}-[0-9]{4,}$"
REFERENCE_RE = re.compile(REFERENCE_PATTERN)

COUNTER_PAD = 4

#: Longest reference this can ever produce for a sane counter — used to bound the
#: DB column and the untrusted ``claimed_reference`` we store from a subject line.
REFERENCE_MAX_CHARS = 40

_NON_CODE_CHARS = re.compile(r"[^A-Z0-9]+")


def derive_code(name: str, *, chars: int = DERIVED_CODE_CHARS) -> str | None:
    """Derive a candidate short code from a display name.

    ``"Commercial"`` → ``"COM"``, ``"M&A"`` → ``"MA"``, ``"Privacy Programme"``
    → ``"PRI"``. Non-alphanumerics are dropped, everything is upper-cased, and
    the first ``chars`` survivors are taken. Returns ``None`` when the name
    yields fewer than :data:`CODE_MIN_CHARS` usable characters — the caller
    decides the fallback rather than getting a silently wrong code.

    Pure and deterministic: migration 0100 restates this logic (migrations in
    this repo are self-contained by convention) and
    ``tests/matters/test_reference_migration_parity.py`` guards the two against
    drift.
    """

    condensed = _NON_CODE_CHARS.sub("", name.upper())
    candidate = condensed[:chars]
    if len(candidate) < CODE_MIN_CHARS:
        return None
    return candidate


def is_valid_code(value: str) -> bool:
    """Whether ``value`` is a well-formed short code (2 to 6 chars, ``[A-Z0-9]``)."""

    return CODE_RE.match(value) is not None


def format_reference(org_code: str, area_code: str, number: int) -> str:
    """Render ``ORG-AREA-NNNN`` (zero-padded to 4, growing past 4 digits)."""

    return f"{org_code}-{area_code}-{number:0{COUNTER_PAD}d}"


def is_valid_reference(value: str) -> bool:
    """Whether ``value`` is a well-formed matter reference."""

    return len(value) <= REFERENCE_MAX_CHARS and REFERENCE_RE.match(value) is not None


def uniquify_code(candidate: str, taken: set[str]) -> str:
    """Return ``candidate`` or the first non-colliding numeric variant of it.

    ``COM`` → ``COM2`` → ``COM3`` … Truncates the stem when appending would push
    the code past :data:`CODE_MAX_CHARS`, so the result is always a valid code.
    Falls back to a 6-digit numeric code in the (absurd) event every variant is
    taken.
    """

    if candidate not in taken:
        return candidate
    for suffix in range(2, 1000):
        tail = str(suffix)
        stem = candidate[: max(1, CODE_MAX_CHARS - len(tail))]
        variant = f"{stem}{tail}"
        if is_valid_code(variant) and variant not in taken:
            return variant
    for n in range(10, 1_000_000):  # pragma: no cover - unreachable in practice
        variant = f"A{n:05d}"[:CODE_MAX_CHARS]
        if variant not in taken:
            return variant
    raise RuntimeError("no free area code remains")  # pragma: no cover


# --- runtime resolution ----------------------------------------------------


async def resolve_org_code(session: AsyncSession) -> str:
    """The deployment's org code, or :data:`DEFAULT_ORG_CODE` when unset.

    Read straight off the ``organization_profile`` singleton. A blank/absent
    value is not an error — a fresh deployment has no profile row at all — so
    the placeholder stands in until an admin sets one, and every reference
    minted meanwhile is still unique and immutable.
    """

    value = await session.scalar(
        select(OrganizationProfile.org_code)
        .where(OrganizationProfile.org_code.is_not(None))
        .limit(1)
    )
    if isinstance(value, str) and is_valid_code(value):
        return value
    return DEFAULT_ORG_CODE


async def _taken_area_codes(session: AsyncSession) -> set[str]:
    rows = (
        await session.execute(
            select(PracticeArea.area_code).where(PracticeArea.area_code.is_not(None))
        )
    ).scalars()
    return {str(code) for code in rows} | {GENERIC_AREA_CODE}


async def assign_area_code(session: AsyncSession, *, area_id: uuid.UUID) -> str:
    """Return the area's code, deriving and persisting one if it has none.

    The lazy write is the single choke point that keeps every area code-bearing
    however it was created (admin API, profile apply, a future seed migration).
    ``FOR UPDATE`` on the area row serialises two concurrent first-allocations
    on the same area, so only one derived code is written.
    """

    area = (
        await session.execute(
            select(PracticeArea).where(PracticeArea.id == area_id).with_for_update()
        )
    ).scalar_one_or_none()
    if area is None:
        return GENERIC_AREA_CODE
    if isinstance(area.area_code, str) and is_valid_code(area.area_code):
        return area.area_code

    taken = await _taken_area_codes(session)
    code = uniquify_code(derive_code(area.name) or GENERIC_AREA_CODE, taken)
    # Set through the ORM (not a Core UPDATE) so an area already loaded in THIS
    # session sees its new code — a caller that goes on to serialise the area
    # would otherwise render a stale NULL.
    area.area_code = code
    await session.flush()
    return code


async def next_counter_value(session: AsyncSession, *, area_code: str) -> int:
    """Claim the next number for ``area_code`` under a row lock.

    Insert-if-absent then ``SELECT … FOR UPDATE``: a concurrent allocator either
    blocks on the unique index (its insert becomes a no-op) or on the row lock,
    so two concurrent callers get consecutive numbers and never the same one.
    The lock is held to the caller's COMMIT — deliberately: the number and the
    matter row it lands on settle together.
    """

    await session.execute(
        pg_insert(MatterReferenceCounter)
        .values(area_code=area_code, next_value=1)
        .on_conflict_do_nothing(constraint="pk_matter_reference_counters")
    )
    value = await session.scalar(
        select(MatterReferenceCounter.next_value)
        .where(MatterReferenceCounter.area_code == area_code)
        .with_for_update()
    )
    if value is None:  # pragma: no cover - the insert above guarantees the row
        raise RuntimeError(f"matter reference counter for {area_code!r} vanished")
    await session.execute(
        update(MatterReferenceCounter)
        .where(MatterReferenceCounter.area_code == area_code)
        .values(next_value=MatterReferenceCounter.next_value + 1, updated_at=func.now())
    )
    return int(value)


async def allocate_reference(
    session: AsyncSession,
    *,
    practice_area_id: uuid.UUID | None,
) -> str:
    """Allocate the next matter reference for a matter under ``practice_area_id``.

    ADR-F088. Called from EVERY matter-creation path inside that path's own
    transaction: the reference commits with the matter or not at all.
    ``practice_area_id=None`` (a legacy/unfiled matter) allocates under
    :data:`GENERIC_AREA_CODE`.
    """

    org_code = await resolve_org_code(session)
    area_code = (
        GENERIC_AREA_CODE
        if practice_area_id is None
        else await assign_area_code(session, area_id=practice_area_id)
    )
    number = await next_counter_value(session, area_code=area_code)
    return format_reference(org_code, area_code, number)


__all__ = [
    "CODE_MAX_CHARS",
    "CODE_MIN_CHARS",
    "CODE_PATTERN",
    "CODE_RE",
    "DEFAULT_ORG_CODE",
    "DERIVED_CODE_CHARS",
    "GENERIC_AREA_CODE",
    "REFERENCE_MAX_CHARS",
    "REFERENCE_PATTERN",
    "REFERENCE_RE",
    "STANDARD_AREA_CODES",
    "allocate_reference",
    "assign_area_code",
    "derive_code",
    "format_reference",
    "is_valid_code",
    "is_valid_reference",
    "next_counter_value",
    "resolve_org_code",
    "uniquify_code",
]
