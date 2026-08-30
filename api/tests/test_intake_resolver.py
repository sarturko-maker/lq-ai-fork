"""INTAKE-4a (ADR-F088) — the inbound resolver's trust ladder, end to end.

Table-driven over ``POST /api/v1/internal/intake/emails``: a message that opens a
NEW provider thread either lands on an EXISTING matter (layers 2/3) or opens a
new one, and the two must never be confusable by a stranger.

What is being defended here:

* **Layer 2 attaches, layer 3 does not — on its own.** ``References``/
  ``In-Reply-To`` naming a message we hold is strong (they were actually in a
  conversation with this inbox). A ``[ORG-AREA-NNNN]`` subject tag, or a
  plus-tagged recipient, is text a stranger types; it attaches ONLY when the
  sender is already on that matter's roster.
* **Weak layers never auto-merge.** A spoofed tag opens a NEW matter and leaves
  a ``claimed_reference`` note for the agent — nothing is merged into a matter
  that may hold privileged material.
* **No existence leak.** A tag naming another user's matter behaves EXACTLY like
  a tag naming nothing: same response, same new matter, same note. The 404-class
  silence of the rest of this codebase, applied to references.
* **The agent conversation continues.** An attached thread inherits the matter's
  ``agent_thread_id`` (INTAKE-3's reuse property) rather than forking.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.main import app
from app.matters.reference import is_valid_reference
from app.models.agent_run import AgentThread
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.practice_area import PracticeArea
from app.models.project import MatterParticipant, Project
from app.models.user import User
from app.security import hash_password
from tests.test_storage_streaming import FakeS3Client

pytestmark = pytest.mark.integration

BRIDGE_TOKEN = "intake-resolver-bridge-token"
INBOX_ID = "legal-intake-resolver"
ROSTER_SENDER = "jane@counterparty.example"
STRANGER = "stranger@elsewhere.example"


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def configured_settings(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("LQ_AI_BRIDGE_TOKEN", BRIDGE_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, configured_settings: None) -> AsyncIterator[AsyncClient]:
    fake_s3 = FakeS3Client()

    @asynccontextmanager
    async def _ctx() -> AsyncIterator[FakeS3Client]:
        yield fake_s3

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    with patch("app.storage.s3_client", _ctx):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.pop(get_db, None)


async def _user(db_session: AsyncSession) -> User:
    row = User(
        email=f"resolver-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("test-password-123"),
        is_admin=False,
        must_change_password=False,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def owner_user(db_session: AsyncSession) -> User:
    return await _user(db_session)


@pytest_asyncio.fixture
async def practice_area(db_session: AsyncSession) -> PracticeArea:
    row = PracticeArea(
        key=f"area-{uuid.uuid4().hex[:8]}",
        name="Xenon resolver area",
        unit_label="Matter",
        position=0,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def mailbox(
    db_session: AsyncSession, owner_user: User, practice_area: PracticeArea
) -> IntakeMailbox:
    row = IntakeMailbox(
        provider="agentmail",
        inbox_id=INBOX_ID,
        address="legal-intake@example.com",
        practice_area_id=practice_area.id,
        owner_user_id=owner_user.id,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _seed_existing_matter(
    db_session: AsyncSession,
    *,
    mailbox: IntakeMailbox,
    owner: User,
    practice_area: PracticeArea,
    reference: str,
    outbound_message_id: str = "our-outbound-1",
    roster_email: str | None = ROSTER_SENDER,
    roster_trust: str = "confirmed",
    roster_aliases: list[str] | None = None,
    inbound_message_id: str | None = None,
) -> tuple[Project, IntakeThread, AgentThread]:
    """One matter that already exists, with an intake thread, an agent conversation,
    one outbound message we sent, and (optionally) a roster entry."""

    project = Project(
        owner_id=owner.id,
        practice_area_id=practice_area.id,
        name="Existing matter",
        slug=f"existing-{uuid.uuid4().hex[:8]}",
        intake_state="candidate",
        reference=reference,
    )
    db_session.add(project)
    await db_session.flush()

    agent_thread = AgentThread(user_id=owner.id, project_id=project.id, title="Intake")
    db_session.add(agent_thread)
    await db_session.flush()

    thread = IntakeThread(
        mailbox_id=mailbox.id,
        provider_thread_id=f"provider-thread-{uuid.uuid4().hex[:8]}",
        subject="Original subject",
        project_id=project.id,
        agent_thread_id=agent_thread.id,
        message_count=1,
    )
    db_session.add(thread)
    await db_session.flush()

    db_session.add(
        IntakeMessage(
            thread_id=thread.id,
            provider_message_id=outbound_message_id,
            direction="out",
            from_addr="legal-intake@example.com",
            to_addrs=[ROSTER_SENDER],
            subject=f"Re: Original subject [{reference}]",
            body_text="Our reply.",
        )
    )
    if inbound_message_id is not None:
        db_session.add(
            IntakeMessage(
                thread_id=thread.id,
                provider_message_id=inbound_message_id,
                direction="in",
                from_addr=ROSTER_SENDER,
                to_addrs=["legal-intake@example.com"],
                subject="Original subject",
                body_text="Their first message.",
            )
        )
    if roster_email is not None or roster_aliases is not None:
        aliases = (
            roster_aliases if roster_aliases is not None else ["Jane Counterparty", roster_email]
        )
        db_session.add(
            MatterParticipant(
                project_id=project.id,
                user_id=owner.id,
                display_name="Jane Counterparty",
                aliases=aliases,
                side="counterparty",
                trust=roster_trust,
            )
        )
    await db_session.flush()
    return project, thread, agent_thread


def _envelope(
    *,
    provider_thread_id: str,
    subject: str = "A brand new thread",
    provider_message_id: str | None = None,
    from_addr: str = STRANGER,
    to: list[str] | None = None,
    headers: dict[str, str] | None = None,
    inbox_id: str = INBOX_ID,
) -> dict[str, Any]:
    return {
        "provider": "agentmail",
        "inbox_id": inbox_id,
        "thread": {"provider_thread_id": provider_thread_id, "subject": subject},
        "message": {
            "provider_message_id": provider_message_id or f"msg-{uuid.uuid4().hex[:8]}",
            "from_addr": from_addr,
            "to": to if to is not None else ["legal-intake@example.com"],
            "cc": [],
            "timestamp": "2026-08-30T12:00:00Z",
            "text": "Body text.",
            "headers": headers or {},
            "auth_state": "pass",
            "attachments": [],
        },
    }


async def _post(client: AsyncClient, body: dict[str, Any]):
    return await client.post(
        "/api/v1/internal/intake/emails",
        json=body,
        headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"},
    )


async def _thread_for(db_session: AsyncSession, thread_id: uuid.UUID) -> IntakeThread:
    row = await db_session.get(IntakeThread, thread_id)
    assert row is not None
    return row


# ---------------------------------------------------------------------------
# Layer 2 — References / In-Reply-To
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"References": "<our-outbound-1>"}, id="references"),
        pytest.param({"In-Reply-To": "<our-outbound-1>"}, id="in-reply-to"),
        pytest.param(
            {"References": "<someone@else> <our-outbound-1>", "In-Reply-To": "<unknown@x>"},
            id="references-chain",
        ),
    ],
)
async def test_layer2_attaches_to_the_matter_and_keeps_the_agent_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
    headers: dict[str, str],
) -> None:
    project, _thread, agent_thread = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0001",
    )

    res = await _post(
        client,
        _envelope(provider_thread_id=f"new-{uuid.uuid4().hex[:8]}", headers=headers),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] == str(project.id)

    landed = await _thread_for(db_session, uuid.UUID(body["thread_id"]))
    assert landed.project_id == project.id
    assert landed.agent_thread_id == agent_thread.id
    assert landed.claimed_reference is None


async def test_layer2_ignores_an_id_from_another_mailbox(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    other_owner = await _user(db_session)
    other_mailbox = IntakeMailbox(
        provider="agentmail",
        inbox_id=f"other-inbox-{uuid.uuid4().hex[:8]}",
        address="other@example.com",
        practice_area_id=practice_area.id,
        owner_user_id=other_owner.id,
    )
    db_session.add(other_mailbox)
    await db_session.flush()
    other_project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=other_mailbox,
        owner=other_owner,
        practice_area=practice_area,
        reference="NWT-XEN-0009",
        outbound_message_id="their-outbound-1",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            headers={"References": "<their-outbound-1>"},
        ),
    )
    assert res.status_code == 200
    assert res.json()["project_id"] != str(other_project.id)


async def test_layer2_ignores_a_matter_owned_by_someone_else(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    practice_area: PracticeArea,
) -> None:
    """A matter on THIS mailbox but owned by another user is not attachable.

    Belt and braces behind the mailbox fence: a mailbox re-bound to a different
    owner must not let new mail file into the previous owner's matters.
    """

    previous_owner = await _user(db_session)
    stale, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=previous_owner,
        practice_area=practice_area,
        reference="NWT-XEN-0012",
        outbound_message_id="previous-owner-out-1",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            headers={"References": "<previous-owner-out-1>"},
        ),
    )
    assert res.status_code == 200
    assert res.json()["project_id"] != str(stale.id)


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"References": "not-angle-bracketed"}, id="malformed"),
        pytest.param({"References": "<>"}, id="empty-id"),
        pytest.param({"References": "<no-such-id@nowhere>"}, id="unknown-id"),
        pytest.param({}, id="absent"),
    ],
)
async def test_layer2_does_not_attach_on_unusable_headers(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
    headers: dict[str, str],
) -> None:
    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0002",
    )

    res = await _post(
        client,
        _envelope(provider_thread_id=f"new-{uuid.uuid4().hex[:8]}", headers=headers),
    )
    assert res.status_code == 200
    assert res.json()["project_id"] != str(project.id)


async def test_layer2_does_not_attach_on_an_INBOUND_id(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    """Quoting back an id the SENDER minted proves nothing — no attach.

    Only ids WE issued (``direction='out'``) show that the sender actually
    received something from this inbox. An inbound id is the sender's own
    choice, so matching it would let anyone who ever wrote in re-quote their
    earlier id and be filed into the matter it opened, with layer-2 privileges
    (no Roster check). Layer 3 still applies afterwards — with no tag here,
    that means a new matter.
    """

    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0013",
        outbound_message_id=f"out-{uuid.uuid4().hex[:6]}",
        inbound_message_id="their-own-inbound-1",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            headers={"References": "<their-own-inbound-1>"},
            from_addr=ROSTER_SENDER,
        ),
    )
    assert res.status_code == 200
    assert res.json()["project_id"] != str(project.id)


async def test_layer2_matches_our_outbound_id_at_the_end_of_a_long_chain(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    """A 12-hop ``References`` chain still carries our id — it is the NEWEST.

    Senders append, so our reply's id sits at the END. The header cap trims from
    the head for exactly this reason; at the old 500-char cap this chain lost its
    tail and the attach silently stopped working on long threads.
    """

    ours = "our-reply-on-a-long-thread@fixture.example.com"
    project, _t, agent_thread = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0014",
        outbound_message_id=ours,
    )

    chain = [f"<hop-{i:02d}-{'x' * 30}@meridian-supply-group.example>" for i in range(11)]
    chain.append(f"<{ours}>")
    header = " ".join(chain)
    assert len(header) > 500, "the fixture must exceed the ORIGINAL cap to be meaningful"

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            headers={"References": header},
        ),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] == str(project.id)
    landed = await _thread_for(db_session, uuid.UUID(body["thread_id"]))
    assert landed.agent_thread_id == agent_thread.id


async def test_threading_headers_are_persisted_for_later_matching(
    client: AsyncClient, db_session: AsyncSession, mailbox: IntakeMailbox
) -> None:
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            provider_message_id=message_id,
            headers={"In-Reply-To": "<parent@x>", "References": "<root@x> <parent@x>"},
        ),
    )
    assert res.status_code == 200
    row = (
        await db_session.execute(
            select(IntakeMessage).where(IntakeMessage.provider_message_id == message_id)
        )
    ).scalar_one()
    assert row.in_reply_to == "<parent@x>"
    assert row.references_header == "<root@x> <parent@x>"


# ---------------------------------------------------------------------------
# Layer 3 — subject tag / plus-tagged recipient, gated on the Roster
# ---------------------------------------------------------------------------


async def test_layer3_tagged_reply_from_a_roster_sender_attaches(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    project, _t, agent_thread = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0003",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Fwd: Original subject [NWT-XEN-0003]",
            # Same person, different capitalisation and a display name.
            from_addr=f"Jane Counterparty <{ROSTER_SENDER.upper()}>",
        ),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] == str(project.id)
    landed = await _thread_for(db_session, uuid.UUID(body["thread_id"]))
    assert landed.agent_thread_id == agent_thread.id
    assert landed.claimed_reference is None


async def test_layer3_plus_tagged_recipient_from_a_roster_sender_attaches(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0004",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="No tag in the subject at all",
            from_addr=ROSTER_SENDER,
            # The provider lower-cases the stored recipient (probed live).
            to=["legal-intake+nwt-xen-0004@example.com"],
        ),
    )
    assert res.status_code == 200
    assert res.json()["project_id"] == str(project.id)


async def test_layer3_does_not_match_a_display_name_alias(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    """A roster alias that is a NAME, not an address, can never gate an attach.

    ADR-F048 aliases are tracked-change author strings, routinely display names.
    A sender whose address happened to normalise to such a string must not pass
    an identity check.
    """

    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0015",
        roster_aliases=["Legal", "J. Smith", "Jane Counterparty"],
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Re: something [NWT-XEN-0015]",
            from_addr="Legal",
        ),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] != str(project.id)
    landed = await _thread_for(db_session, uuid.UUID(body["thread_id"]))
    assert landed.claimed_reference == "NWT-XEN-0015"


async def test_layer3_does_not_accept_an_agent_inferred_roster_row(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    """``trust='inferred'`` cannot open the gate — it came from untrusted metadata.

    The agent infers roster rows from document author strings, which an attacker
    supplies. If an inferred row authorised an attach, the loop closes: send a
    .docx whose author string you chose, then quote the reference.
    """

    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0016",
        roster_trust="inferred",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Re: something [NWT-XEN-0016]",
            from_addr=ROSTER_SENDER,
        ),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] != str(project.id)
    landed = await _thread_for(db_session, uuid.UUID(body["thread_id"]))
    assert landed.claimed_reference == "NWT-XEN-0016"


async def test_layer3_accepts_the_same_person_once_a_human_confirms_them(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    """The mirror of the test above: confirmed is exactly what unlocks it."""

    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0017",
        roster_trust="confirmed",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Re: something [NWT-XEN-0017]",
            from_addr=ROSTER_SENDER,
        ),
    )
    assert res.status_code == 200
    assert res.json()["project_id"] == str(project.id)


async def test_layer3_tag_from_a_stranger_opens_a_new_matter_and_records_the_claim(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0005",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Re: your matter [NWT-XEN-0005]",
            from_addr=STRANGER,
        ),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] != str(project.id)
    landed = await _thread_for(db_session, uuid.UUID(body["thread_id"]))
    assert landed.claimed_reference == "NWT-XEN-0005"


async def test_layer3_tag_naming_another_users_matter_is_silent(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    """Another owner's reference must be indistinguishable from a nonexistent one.

    Same status, same "new matter" outcome, same recorded claim — nothing an
    outsider could use to probe whether a reference exists (404-class silence).
    """

    other_owner = await _user(db_session)
    other_project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=other_owner,
        practice_area=practice_area,
        reference="NWT-XEN-0006",
        outbound_message_id=f"other-out-{uuid.uuid4().hex[:6]}",
        # Even ON the roster: the matter is not this queue's to attach to.
        roster_email=STRANGER,
    )

    tagged = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Re: [NWT-XEN-0006]",
            from_addr=STRANGER,
        ),
    )
    unknown = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Re: [NWT-XEN-9999]",
            from_addr=STRANGER,
        ),
    )

    assert tagged.status_code == unknown.status_code == 200
    assert tagged.json()["project_id"] != str(other_project.id)
    assert tagged.json()["project_id"] != unknown.json()["project_id"]

    tagged_thread = await _thread_for(db_session, uuid.UUID(tagged.json()["thread_id"]))
    unknown_thread = await _thread_for(db_session, uuid.UUID(unknown.json()["thread_id"]))
    assert tagged_thread.claimed_reference == "NWT-XEN-0006"
    assert unknown_thread.claimed_reference == "NWT-XEN-9999"


@pytest.mark.parametrize(
    "subject",
    [
        pytest.param("Re: [nwt-xen-0007]", id="lowercase-spoof"),
        pytest.param("Re: [NWT-XEN-007]", id="under-padded"),
        pytest.param("Re: NWT-XEN-0007", id="no-brackets"),
        pytest.param("Re: [NWT-[XEN]-0007]", id="nested-brackets"),
    ],
)
async def test_layer3_malformed_tags_neither_attach_nor_record_a_claim(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
    subject: str,
) -> None:
    project, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0007",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject=subject,
            from_addr=ROSTER_SENDER,
        ),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] != str(project.id)
    landed = await _thread_for(db_session, uuid.UUID(body["thread_id"]))
    assert landed.claimed_reference is None


async def test_layer2_wins_over_a_tag_naming_a_different_matter(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    owner_user: User,
    practice_area: PracticeArea,
) -> None:
    strong, _t, _a = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0010",
        outbound_message_id="strong-out-1",
    )
    weak, _t2, _a2 = await _seed_existing_matter(
        db_session,
        mailbox=mailbox,
        owner=owner_user,
        practice_area=practice_area,
        reference="NWT-XEN-0011",
        outbound_message_id="weak-out-1",
    )

    res = await _post(
        client,
        _envelope(
            provider_thread_id=f"new-{uuid.uuid4().hex[:8]}",
            subject="Re: something [NWT-XEN-0011]",
            from_addr=ROSTER_SENDER,
            headers={"References": "<strong-out-1>"},
        ),
    )
    assert res.status_code == 200
    assert res.json()["project_id"] == str(strong.id)
    assert res.json()["project_id"] != str(weak.id)


# ---------------------------------------------------------------------------
# The intake-born matter carries a reference like any other
# ---------------------------------------------------------------------------


async def test_a_new_intake_matter_gets_a_reference(
    client: AsyncClient, db_session: AsyncSession, mailbox: IntakeMailbox
) -> None:
    res = await _post(client, _envelope(provider_thread_id=f"new-{uuid.uuid4().hex[:8]}"))
    assert res.status_code == 200
    project = await db_session.get(Project, uuid.UUID(res.json()["project_id"]))
    assert project is not None
    assert project.reference is not None
    assert is_valid_reference(project.reference)
    assert project.reference.split("-")[1] == "XEN"
