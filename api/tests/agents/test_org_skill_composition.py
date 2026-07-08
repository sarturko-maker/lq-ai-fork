"""Org-skill composition proofs — the B-2a runtime seam end to end (ADR-F067 D2/D3).

The three milestone-core properties, exercised at the integration level over REAL DB rows
(``users`` + ``user_skills`` + an approved ``org_skill_versions`` snapshot) driven through the
actual runtime pieces — the composition helper ``_resolve_org_skill_files`` (batched author/
approver email resolution + the no-shadowing filter), ``build_area_inventory`` (availability),
and ``build_area_skill_wiring`` (served bytes). Nothing is monkeypatched; a duck-typed registry
stands in for the filesystem catalog exactly as the pure tests do.

1. **Snapshot bytes, not the live row.** approve → adopt → bind → compose serves the immutable
   snapshot (author bytes + the D3.5 provenance banner), never the mutable ``user_skills`` row.
2. **Post-approval edit is inert.** editing the ``user_skills`` row after approval does NOT change
   the served text — the snapshot is a byte copy taken at propose time.
3. **Revoke fail-closes.** flipping the snapshot's state off ``approved`` drops the skill from both
   the inventory (with the ``skill_unresolved_skipped`` warning) and the wiring (backend None).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.capabilities import build_area_inventory
from app.agents.composition import _resolve_org_skill_files
from app.agents.skill_backend import SKILLS_ROOT, build_area_skill_wiring
from app.models.org_skill import OrgSkillVersion
from app.models.user import User
from app.models.user_skill import UserSkill
from app.security import hash_password
from app.skills.org_proposal import render_provenance_banner, synthesize_org_skill

pytestmark = pytest.mark.integration

_SLUG = "house-nda-clause"
_APPROVED_ON = datetime(2026, 7, 8, tzinfo=UTC)


class _FakeRegistry:
    """A duck-typed skill registry that knows only an explicit name set — the org slug is
    deliberately absent, so the snapshot is the sole resolution source (the common case)."""

    def __init__(self, known: dict[str, Any] | None = None) -> None:
        self._known = known or {}

    def get(self, name: str) -> Any | None:
        return self._known.get(name)


def _lib(kind: str, key: str) -> SimpleNamespace:
    return SimpleNamespace(capability_kind=kind, capability_key=key)


async def _new_user(db: AsyncSession, *, is_admin: bool) -> User:
    user = User(
        email=f"org-skill-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Approver" if is_admin else "Author",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=is_admin,
        mfa_enabled=False,
        must_change_password=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_approved_org_skill(
    db: AsyncSession, *, snapshot_body: str, live_body: str
) -> tuple[OrgSkillVersion, User, User, UserSkill]:
    """Create author + approver users, a source ``user_skills`` row, and an APPROVED snapshot.

    The snapshot is synthesized while the source row still holds ``snapshot_body`` (approval
    pins those bytes); the source row is then edited to ``live_body`` so the two genuinely
    differ — the fixture for "snapshot ≠ live row"."""
    author = await _new_user(db, is_admin=False)
    approver = await _new_user(db, is_admin=True)

    skill_row = UserSkill(
        scope="user",
        owner_user_id=author.id,
        slug=_SLUG,
        display_name="House NDA clause",
        description="Our standard NDA clause.",
        version="1.0.0",
        tags=[],
        frontmatter_extra={},
        body=snapshot_body,
    )
    db.add(skill_row)
    await db.flush()

    content = synthesize_org_skill(skill_row)  # pins snapshot_body as author bytes
    version = OrgSkillVersion(
        slug=_SLUG,
        version_no=1,
        raw_yaml=content.raw_yaml,
        body=content.body,
        frontmatter=content.frontmatter,
        content_hash=content.content_hash,
        source_user_skill_id=skill_row.id,
        author_user_id=author.id,
        state="approved",
        reviewed_by=approver.id,
        reviewed_at=_APPROVED_ON,
    )
    db.add(version)
    await db.flush()

    # The live row drifts after approval — the snapshot must NOT follow it.
    skill_row.body = live_body
    await db.flush()

    return version, author, approver, skill_row


async def test_compose_serves_snapshot_bytes_with_banner_not_live_row(
    db_session: AsyncSession,
) -> None:
    """Proof 1: approve → adopt → bind → compose resolves the SNAPSHOT bytes (author body +
    provenance banner), never the live, edited ``user_skills`` row."""
    version, author, approver, _ = await _seed_approved_org_skill(
        db_session,
        snapshot_body="# House NDA\nApproved wording, section 4.2.",
        live_body="# House NDA\nEDITED-AFTER-APPROVAL wording.",
    )
    registry = _FakeRegistry()  # does not know the org slug

    # Availability: the snapshot is adopted + bound, so it becomes a skill entry.
    inv = build_area_inventory(
        bound_skill_names=[_SLUG],
        registry=registry,
        area_playbooks=[],
        tool_group_keys=[],
        library_entries=[_lib("skill", _SLUG)],
        org_skill_snapshots={_SLUG: version},
    )
    (entry,) = [e for e in inv.entries if e.kind == "skill"]
    assert entry.key == _SLUG and entry.label == "House NDA clause"

    # Served bytes: banner (author + approver EMAILS + approval date) prefixed to author body.
    files = await _resolve_org_skill_files(db_session, {_SLUG: version}, [_SLUG], registry)
    served = files[_SLUG]
    banner = render_provenance_banner(author.email, approver.email, "2026-07-08")
    assert f"> {banner}" in served
    assert "Approved wording, section 4.2." in served  # the snapshot's author body
    assert "EDITED-AFTER-APPROVAL" not in served  # NOT the live user_skills row

    # And it rides the real backend verbatim to the agent.
    wiring = build_area_skill_wiring(
        registry, area_skill_names=[_SLUG], subagents=[], org_skill_files=files
    )
    assert wiring.backend is not None
    read = wiring.backend.read(f"{SKILLS_ROOT}/{_SLUG}/SKILL.md")
    assert read.file_data is not None and read.file_data["content"] == served


async def test_post_approval_edit_does_not_change_served_text(
    db_session: AsyncSession,
) -> None:
    """Proof 2: editing the ``user_skills`` row after approval is inert — the served text is a
    frozen snapshot copy, independent of the live row."""
    version, _, _, skill_row = await _seed_approved_org_skill(
        db_session,
        snapshot_body="# House NDA\nApproved wording.",
        live_body="# House NDA\nFirst edit.",
    )
    registry = _FakeRegistry()

    before = (await _resolve_org_skill_files(db_session, {_SLUG: version}, [_SLUG], registry))[
        _SLUG
    ]

    # Edit the live row again (and re-synthesize to prove the LIVE row really changed).
    skill_row.body = "# House NDA\nSecond, totally different edit."
    await db_session.flush()
    assert synthesize_org_skill(skill_row).body == "# House NDA\nSecond, totally different edit."

    after = (await _resolve_org_skill_files(db_session, {_SLUG: version}, [_SLUG], registry))[_SLUG]
    assert after == before  # snapshot bytes unchanged
    assert "Second, totally different edit." not in after


async def test_revoke_drops_skill_fail_closed_with_warning(
    db_session: AsyncSession, caplog: Any
) -> None:
    """Proof 3: revoking (a state flip off ``approved``) removes the skill from the approved
    snapshot set, so it drops from BOTH the inventory (fail-closed, warning logged) and the
    wiring (backend None) — the F067 D3.8 revoke chokepoint."""
    version, _, _, _ = await _seed_approved_org_skill(
        db_session,
        snapshot_body="# House NDA\nApproved wording.",
        live_body="# House NDA\nApproved wording.",
    )
    registry = _FakeRegistry()

    # Revoke: the runtime only ever reads state='approved', so the production load excludes it.
    version.state = "revoked"
    await db_session.flush()
    approved = (
        (
            await db_session.execute(
                select(OrgSkillVersion).where(OrgSkillVersion.state == "approved")
            )
        )
        .scalars()
        .all()
    )
    org_snapshots = {v.slug: v for v in approved}
    assert org_snapshots == {}  # nothing approved survives the revoke

    # Inventory: still adopted + bound, but resolves nowhere → dropped + fail-close warning.
    with caplog.at_level(logging.WARNING):
        inv = build_area_inventory(
            bound_skill_names=[_SLUG],
            registry=registry,
            area_playbooks=[],
            tool_group_keys=[],
            library_entries=[_lib("skill", _SLUG)],
            org_skill_snapshots=org_snapshots,
        )
    assert all(e.kind != "skill" for e in inv.entries)
    dropped = [r for r in caplog.records if getattr(r, "event", None) == "skill_unresolved_skipped"]
    assert dropped and dropped[0].keys == [_SLUG]

    # Wiring: no served bytes, backend None (the agent cannot reach the revoked skill).
    files = await _resolve_org_skill_files(db_session, org_snapshots, [_SLUG], registry)
    assert files == {}
    wiring = build_area_skill_wiring(
        registry, area_skill_names=[_SLUG], subagents=[], org_skill_files=files
    )
    assert wiring.backend is None
