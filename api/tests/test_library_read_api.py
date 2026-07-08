"""Member-readable Org Library read model — STORE-2 D-B (ADR-F065).

``GET /api/v1/library`` returns every capability the org adopted, joined to
catalog display metadata, for ANY active user — not just admins. These prove:

* member AND viewer both get 200 (``ActiveUser`` surface, not ``AdminUser``),
* unauthenticated is 401,
* only adopted entries are returned, with catalog metadata (label/description/
  source/author/version) resolved the same way the admin catalog does,
* a dangling entry (adopted, then the underlying catalog entry vanished)
  returns ``label=None`` (and the rest of the catalog fields ``None`` too),
* canonical ordering: kind (tool -> skill -> playbook -> knowledge), then label
  (case-insensitive, ``None`` last), then key,
* ``adopted_by`` never appears on the wire (member-visible surface, no
  cross-user identifiers).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.knowledge import KnowledgeBase
from app.models.playbook import Playbook
from app.models.practice_area import OrgLibraryEntry
from app.models.user import User
from app.skills import load_registry
from app.skills.registry import MutableSkillRegistry
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

_URL = "/api/v1/library"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def member(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="library-member")


@pytest_asyncio.fixture
async def viewer(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="library-viewer")
    u.role = "viewer"
    await db_session.flush()
    return u


@pytest_asyncio.fixture(autouse=True)
async def _empty_library(db_session: AsyncSession) -> AsyncIterator[None]:
    """Start each test from an empty Library.

    The test DB seeds ``org_library_entries`` once, session-scoped, from
    migration 0088's ``_seed`` (every default-bound skill/tool — see
    ``conftest.py``). These tests need exact control over what's adopted for
    the ordering/dangling assertions, so clear the seeded rows inside this
    test's isolated (SAVEPOINT-rolled-back) transaction before each test.
    """
    await db_session.execute(delete(OrgLibraryEntry))
    await db_session.flush()
    yield


@pytest_asyncio.fixture
async def fixture_registry() -> AsyncIterator[None]:
    """Install the C1 loader test fixtures as the live skill registry.

    Restores whatever was installed before (mirrors
    ``test_org_library_api.test_adopt_skill_with_registry_204``).
    """
    prior = getattr(app.state, "skill_registry", None)
    app.state.skill_registry = MutableSkillRegistry(load_registry(_FIXTURES_DIR))
    try:
        yield
    finally:
        if prior is None:
            delattr(app.state, "skill_registry")
        else:
            app.state.skill_registry = prior


async def _adopt(db: AsyncSession, kind: str, key: str) -> None:
    db.add(OrgLibraryEntry(capability_kind=kind, capability_key=key))
    await db.flush()


async def _make_playbook(db: AsyncSession, *, name: str = "Lib NDA playbook") -> Playbook:
    pb = Playbook(name=name, contract_type="NDA", description="A playbook.")
    db.add(pb)
    await db.flush()
    return pb


async def _make_kb(
    db: AsyncSession, owner: User, *, name: str = "Lib knowledge collection"
) -> KnowledgeBase:
    kb = KnowledgeBase(owner_id=owner.id, name=name, description="A knowledge collection.")
    db.add(kb)
    await db.flush()
    return kb


# --- authz ---------------------------------------------------------------------
async def test_member_gets_200(client: AsyncClient, member: User) -> None:
    resp = await client.get(_URL, headers=_bearer(member))
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


async def test_viewer_gets_200(client: AsyncClient, viewer: User) -> None:
    resp = await client.get(_URL, headers=_bearer(viewer))
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


async def test_unauthenticated_is_401(client: AsyncClient) -> None:
    resp = await client.get(_URL)
    assert resp.status_code == 401


# --- catalog metadata ------------------------------------------------------
async def test_returns_only_adopted_entries_with_catalog_metadata(
    client: AsyncClient, member: User, db_session: AsyncSession, fixture_registry: None
) -> None:
    await _adopt(db_session, "tool", "redlining")
    await _adopt(db_session, "skill", "alpha-test-skill")
    # NOT adopted — must not appear.
    resp = await client.get(_URL, headers=_bearer(member))
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 2

    tool_entry = next(e for e in entries if e["kind"] == "tool")
    assert tool_entry["key"] == "redlining"
    assert tool_entry["label"] == "Redlining"
    assert tool_entry["source"] == "built-in"
    assert tool_entry["author"] is None
    assert tool_entry["version"] is None

    skill_entry = next(e for e in entries if e["kind"] == "skill")
    assert skill_entry["key"] == "alpha-test-skill"
    assert skill_entry["label"] == "Alpha Test Skill"
    assert skill_entry["author"] == "LQ.AI tests"
    assert skill_entry["version"] == "1.0.0"


async def test_playbook_entry_metadata(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session)
    await _adopt(db_session, "playbook", str(pb.id))
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["kind"] == "playbook"
    assert entries[0]["key"] == str(pb.id)
    assert entries[0]["label"] == "Lib NDA playbook (NDA)"
    assert entries[0]["description"] == "A playbook."
    assert entries[0]["source"] is None  # playbooks carry no provenance field (D-A)


async def test_knowledge_entry_metadata(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    kb = await _make_kb(db_session, member)
    await _adopt(db_session, "knowledge", str(kb.id))
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["kind"] == "knowledge"
    assert entries[0]["key"] == str(kb.id)
    assert entries[0]["label"] == "Lib knowledge collection"
    assert entries[0]["description"] == "A knowledge collection."
    # source stays None: knowledge collections carry no provenance field either (D-A);
    # adoption + binding IS the control (ADR-F067 D1).
    assert entries[0]["source"] is None


# --- dangling entries --------------------------------------------------------
async def test_dangling_skill_has_null_label(
    client: AsyncClient, member: User, db_session: AsyncSession, fixture_registry: None
) -> None:
    await _adopt(db_session, "skill", "no-longer-a-real-skill")
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["label"] is None
    assert entries[0]["description"] is None
    assert entries[0]["source"] is None


async def test_dangling_tool_has_null_label(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    await _adopt(db_session, "tool", "not-a-real-group")
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert entries[0]["label"] is None


async def test_dangling_playbook_has_null_label(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    # Adopted, but no such playbook row exists (deleted after adoption).
    import uuid

    await _adopt(db_session, "playbook", str(uuid.uuid4()))
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert entries[0]["label"] is None


async def test_dangling_knowledge_has_null_label_when_unknown(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    # Adopted, but no such collection row exists (deleted after adoption).
    import uuid

    await _adopt(db_session, "knowledge", str(uuid.uuid4()))
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert entries[0]["label"] is None


async def test_dangling_knowledge_has_null_label_when_archived(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    # Adopted, then archived — archived collections drop out of the catalog too
    # (same drift-drop posture as a deleted playbook).
    kb = await _make_kb(db_session, member)
    kb.archived_at = datetime.now(UTC)
    await db_session.flush()
    await _adopt(db_session, "knowledge", str(kb.id))
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert entries[0]["label"] is None


async def test_skill_dangling_when_no_registry_installed(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    # No registry installed in the ASGI test app ⇒ every skill degrades to dangling.
    prior = getattr(app.state, "skill_registry", None)
    if prior is not None:
        delattr(app.state, "skill_registry")
    try:
        await _adopt(db_session, "skill", "anything")
        resp = await client.get(_URL, headers=_bearer(member))
        entries = resp.json()["entries"]
        assert entries[0]["label"] is None
    finally:
        if prior is not None:
            app.state.skill_registry = prior


# --- ordering -----------------------------------------------------------------
async def test_canonical_ordering(
    client: AsyncClient, member: User, db_session: AsyncSession, fixture_registry: None
) -> None:
    pb = await _make_playbook(db_session, name="Zeta playbook")
    await _adopt(db_session, "tool", "redlining")  # label "Redlining"
    await _adopt(db_session, "tool", "tabular")  # label "Grids"
    await _adopt(db_session, "skill", "gamma-tagged")  # label "Gamma Tagged"
    await _adopt(db_session, "skill", "alpha-test-skill")  # label "Alpha Test Skill"
    await _adopt(db_session, "playbook", str(pb.id))

    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    ordering = [(e["kind"], e["key"]) for e in entries]
    assert ordering == [
        ("tool", "tabular"),  # "Grids" < "Redlining"
        ("tool", "redlining"),
        ("skill", "alpha-test-skill"),  # "Alpha Test Skill" < "Gamma Tagged"
        ("skill", "gamma-tagged"),
        ("playbook", str(pb.id)),
    ]


async def test_dangling_entries_sort_last_within_their_kind(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    await _adopt(db_session, "tool", "redlining")  # real, label "Redlining"
    await _adopt(db_session, "tool", "not-a-real-group")  # dangling, label None
    resp = await client.get(_URL, headers=_bearer(member))
    entries = resp.json()["entries"]
    assert [e["key"] for e in entries] == ["redlining", "not-a-real-group"]


# --- no cross-user identifiers on the wire ------------------------------------
async def test_adopted_by_not_serialized(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session)
    await _adopt(db_session, "playbook", str(pb.id))
    resp = await client.get(_URL, headers=_bearer(member))
    assert "adopted_by" not in resp.text
    for entry in resp.json()["entries"]:
        assert "adopted_by" not in entry
