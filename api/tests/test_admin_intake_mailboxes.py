"""Integration tests for the INTAKE-1 (ADR-F086) admin intake-mailboxes CRUD surface.

Covers ``/api/v1/admin/intake-mailboxes``:

* POST create — validates practice_area_id + owner_user_id both exist
  (404 on either miss); rejects a (provider, inbox_id) collision among
  live rows (409); non-admin → 403.
* GET list — live (non-soft-deleted) rows only, newest first.
* PATCH update — partial update of active/owner_user_id/
  default_budget_profile/max_steps; unknown id → 404; bad owner_user_id
  on update → 404.
* DELETE — soft delete (204); idempotent (already-deleted/missing → 404).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.intake import IntakeMailbox
from app.models.practice_area import PracticeArea
from app.models.user import User
from app.security import create_access_token, hash_password


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


async def _make_user(db_session: AsyncSession, *, email: str, is_admin: bool) -> tuple[User, str]:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password("test-password-123"),
        is_admin=is_admin,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(user_id=user.id, email=user.email, is_admin=user.is_admin)
    return user, token


@pytest_asyncio.fixture
async def admin_client(db_session: AsyncSession) -> AsyncIterator[tuple[AsyncClient, str]]:
    _user, token = await _make_user(db_session, email="admin-mailbox@example.com", is_admin=True)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, token
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def member_client(db_session: AsyncSession) -> AsyncIterator[tuple[AsyncClient, str]]:
    _user, token = await _make_user(db_session, email="member-mailbox@example.com", is_admin=False)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, token
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def owner_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"queue-owner-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("test-password-123"),
        is_admin=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def practice_area(db_session: AsyncSession) -> PracticeArea:
    area = PracticeArea(
        key=f"area-{uuid.uuid4().hex[:8]}",
        name="Commercial (test)",
        unit_label="Matter",
        position=0,
    )
    db_session.add(area)
    await db_session.flush()
    return area


def _create_body(
    *, practice_area_id: uuid.UUID, owner_user_id: uuid.UUID, **overrides: object
) -> dict[str, object]:
    base: dict[str, object] = {
        "provider": "agentmail",
        "inbox_id": f"inbox-{uuid.uuid4().hex[:8]}",
        "address": "legal-intake@example.com",
        "practice_area_id": str(practice_area_id),
        "owner_user_id": str(owner_user_id),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# POST create
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_mailbox_happy_path(
    admin_client: tuple[AsyncClient, str],
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    body = _create_body(
        practice_area_id=practice_area.id,
        owner_user_id=owner_user.id,
        default_budget_profile="economy",
        max_steps=10,
    )
    res = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["provider"] == "agentmail"
    assert out["inbox_id"] == body["inbox_id"]
    assert out["address"] == "legal-intake@example.com"
    assert out["practice_area_id"] == str(practice_area.id)
    assert out["owner_user_id"] == str(owner_user.id)
    assert out["default_budget_profile"] == "economy"
    assert out["max_steps"] == 10
    assert out["active"] is True


@pytest.mark.integration
async def test_create_mailbox_defaults_provider_to_agentmail(
    admin_client: tuple[AsyncClient, str],
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    body = _create_body(practice_area_id=practice_area.id, owner_user_id=owner_user.id)
    del body["provider"]
    res = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["provider"] == "agentmail"


@pytest.mark.integration
async def test_create_mailbox_unknown_practice_area_returns_404(
    admin_client: tuple[AsyncClient, str], owner_user: User
) -> None:
    ac, token = admin_client
    body = _create_body(practice_area_id=uuid.uuid4(), owner_user_id=owner_user.id)
    res = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


@pytest.mark.integration
async def test_create_mailbox_unknown_owner_returns_404(
    admin_client: tuple[AsyncClient, str], practice_area: PracticeArea
) -> None:
    ac, token = admin_client
    body = _create_body(practice_area_id=practice_area.id, owner_user_id=uuid.uuid4())
    res = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


@pytest.mark.integration
async def test_create_mailbox_collision_on_live_row_returns_409(
    admin_client: tuple[AsyncClient, str],
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    body = _create_body(practice_area_id=practice_area.id, owner_user_id=owner_user.id)
    first = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 201

    second = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409


@pytest.mark.integration
async def test_create_mailbox_non_admin_returns_403(
    member_client: tuple[AsyncClient, str],
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = member_client
    body = _create_body(practice_area_id=practice_area.id, owner_user_id=owner_user.id)
    res = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# GET list
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_returns_only_live_rows(
    admin_client: tuple[AsyncClient, str],
    db_session: AsyncSession,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    live = IntakeMailbox(
        provider="agentmail",
        inbox_id="live-inbox",
        address="live@example.com",
        practice_area_id=practice_area.id,
        owner_user_id=owner_user.id,
    )
    deleted = IntakeMailbox(
        provider="agentmail",
        inbox_id="deleted-inbox",
        address="deleted@example.com",
        practice_area_id=practice_area.id,
        owner_user_id=owner_user.id,
        deleted_at=datetime.now(tz=UTC),
    )
    db_session.add_all([live, deleted])
    await db_session.commit()

    res = await ac.get(
        "/api/v1/admin/intake-mailboxes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    inbox_ids = {row["inbox_id"] for row in res.json()}
    assert inbox_ids == {"live-inbox"}


@pytest.mark.integration
async def test_list_non_admin_returns_403(member_client: tuple[AsyncClient, str]) -> None:
    ac, token = member_client
    res = await ac.get(
        "/api/v1/admin/intake-mailboxes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# PATCH update
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_patch_updates_only_provided_fields(
    admin_client: tuple[AsyncClient, str],
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    created = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=_create_body(
            practice_area_id=practice_area.id, owner_user_id=owner_user.id, max_steps=5
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    mailbox_id = created.json()["id"]

    res = await ac.patch(
        f"/api/v1/admin/intake-mailboxes/{mailbox_id}",
        json={"active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["active"] is False
    # Untouched fields survive the partial update.
    assert body["max_steps"] == 5
    assert body["owner_user_id"] == str(owner_user.id)


@pytest.mark.integration
async def test_patch_unknown_owner_returns_404_and_does_not_apply_other_fields(
    admin_client: tuple[AsyncClient, str],
    db_session: AsyncSession,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    created = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=_create_body(practice_area_id=practice_area.id, owner_user_id=owner_user.id),
        headers={"Authorization": f"Bearer {token}"},
    )
    mailbox_id = created.json()["id"]

    res = await ac.patch(
        f"/api/v1/admin/intake-mailboxes/{mailbox_id}",
        json={"active": False, "owner_user_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404

    row = (
        await db_session.execute(
            select(IntakeMailbox).where(IntakeMailbox.id == uuid.UUID(mailbox_id))
        )
    ).scalar_one()
    # The rejected PATCH did not partially apply.
    assert row.active is True


@pytest.mark.integration
async def test_patch_unknown_mailbox_returns_404(admin_client: tuple[AsyncClient, str]) -> None:
    ac, token = admin_client
    res = await ac.patch(
        f"/api/v1/admin/intake-mailboxes/{uuid.uuid4()}",
        json={"active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


@pytest.mark.integration
async def test_patch_non_admin_returns_403(
    member_client: tuple[AsyncClient, str],
) -> None:
    ac, token = member_client
    res = await ac.patch(
        f"/api/v1/admin/intake-mailboxes/{uuid.uuid4()}",
        json={"active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_delete_soft_deletes(
    admin_client: tuple[AsyncClient, str],
    db_session: AsyncSession,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    created = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=_create_body(practice_area_id=practice_area.id, owner_user_id=owner_user.id),
        headers={"Authorization": f"Bearer {token}"},
    )
    mailbox_id = created.json()["id"]

    res = await ac.delete(
        f"/api/v1/admin/intake-mailboxes/{mailbox_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 204
    assert res.content == b""

    row = (
        await db_session.execute(
            select(IntakeMailbox).where(IntakeMailbox.id == uuid.UUID(mailbox_id))
        )
    ).scalar_one()
    assert row.deleted_at is not None


@pytest.mark.integration
async def test_delete_already_deleted_returns_404(
    admin_client: tuple[AsyncClient, str],
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    ac, token = admin_client
    created = await ac.post(
        "/api/v1/admin/intake-mailboxes",
        json=_create_body(practice_area_id=practice_area.id, owner_user_id=owner_user.id),
        headers={"Authorization": f"Bearer {token}"},
    )
    mailbox_id = created.json()["id"]

    first = await ac.delete(
        f"/api/v1/admin/intake-mailboxes/{mailbox_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 204

    second = await ac.delete(
        f"/api/v1/admin/intake-mailboxes/{mailbox_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 404


@pytest.mark.integration
async def test_delete_missing_returns_404(admin_client: tuple[AsyncClient, str]) -> None:
    ac, token = admin_client
    res = await ac.delete(
        f"/api/v1/admin/intake-mailboxes/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


@pytest.mark.integration
async def test_delete_non_admin_returns_403(
    member_client: tuple[AsyncClient, str],
) -> None:
    ac, token = member_client
    res = await ac.delete(
        f"/api/v1/admin/intake-mailboxes/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
