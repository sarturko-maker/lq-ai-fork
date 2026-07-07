"""C4 commercial_tools integration tests (ADR-F031/F035).

Drives ``_apply_redline`` through a real test DB with a real ``RedlineService``
(Adeu) and storage monkeypatched to a known ``.docx`` — covering the orchestration
(validate → fetch → gate → dry-run → apply → persist), the matter-scope boundary
(a document in another matter is not found — 404-conflated), and the audit receipt
(counts/types/IDs, never clause text).
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents import commercial_tools
from app.agents.commercial_tools import (
    COMMERCIAL_TOOL_NAMES,
    _apply_redline,
    _extract_counterparty_position,
    _preview_redline,
    _reconcile_positions,
    _redlined_filename,
    _render_state_of_play,
    _respond_to_counterparty,
    _response_filename,
    build_commercial_tools,
)
from app.agents.deal_changes import DealChangeLedger
from app.agents.negotiation_service import StateOfPlay, TrackedChange, read_state_of_play
from app.agents.redline_render import reconstruct_redline_text
from app.agents.redline_service import (
    ProposedEdit,
    RedlineApplyResult,
    RedlinePreview,
    RedlineService,
)
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.file import File
from app.models.project import MatterMemoryEntry, MatterParticipant, Project
from app.models.user import User
from app.pipeline.readers._base import OOXML_DOCX_MIME
from app.security import hash_password

pytestmark = pytest.mark.integration

CAP = (
    "The Vendor's aggregate liability arising out of or in connection with this "
    "Agreement shall not exceed the total fees paid by the Customer in the three (3) "
    "months preceding the claim."
)
_RATIONALE = (
    "Align the cap measurement period to the house twelve-month fee floor so the "
    "customer's standard liability position is preserved across this deal."
)


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _make_matter_file(
    factory: async_sessionmaker[AsyncSession], *, filename: str = "contract.docx"
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a user + matter + a .docx File (no Document — the tool falls back to
    DocxReader). Returns (user_id, project_id, file_id)."""
    async with factory() as db:
        user = User(
            email=f"comm-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Commercial User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="SecureScan Deal",
            slug=f"deal-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
        )
        db.add(project)
        await db.flush()
        file = File(
            owner_id=user.id,
            project_id=project.id,
            filename=filename,
            mime_type=OOXML_DOCX_MIME,
            size_bytes=1234,
            hash_sha256="0" * 64,
            storage_path=str(uuid.uuid4()),
            ingestion_status="ready",
        )
        db.add(file)
        await db.commit()
        return user.id, project.id, file.id


async def _make_run(
    factory: async_sessionmaker[AsyncSession], *, user_id: uuid.UUID, project_id: uuid.UUID
) -> uuid.UUID:
    """Seed a thread + run so a redlined File can carry a valid ``created_by_run_id``
    FK (ADR-F046). Returns the run id."""
    async with factory() as db:
        thread = AgentThread(user_id=user_id, project_id=project_id, title="redline")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user_id,
            thread_id=thread.id,
            project_id=project_id,
            prompt="redline the MSA",
        )
        db.add(run)
        await db.commit()
        return run.id


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="SecureScan Deal",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


def _patch_storage(monkeypatch: pytest.MonkeyPatch, *, source: bytes) -> dict[str, object]:
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_download(*, storage_path: str) -> AsyncIterator[AsyncIterator[bytes]]:
        async def _gen() -> AsyncIterator[bytes]:
            yield source

        yield _gen()

    async def fake_upload(*, storage_path: str, body: bytes, content_type: str) -> None:
        captured["path"] = storage_path
        captured["body"] = body
        captured["content_type"] = content_type

    monkeypatch.setattr(commercial_tools.storage, "stream_download", fake_download)
    monkeypatch.setattr(commercial_tools.storage, "upload_bytes", fake_upload)
    return captured


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """A committed user+matter+.docx File, torn down after the test.

    commit_factory bypasses the per-test rollback, so these rows MUST be cleaned
    up or they leak into the shared DB (File.owner_id is ON DELETE RESTRICT, so a
    leftover file breaks other tests' user deletes + row-count assertions).
    """
    user_id, project_id, _ = await _make_matter_file(commit_factory)
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(File).where(File.owner_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


def test_build_commercial_tools_grants_redline_tools() -> None:
    factory = async_sessionmaker()  # not used; the closure captures it
    tools = build_commercial_tools(
        factory,
        run_id=uuid.uuid4(),
        binding=_binding(uuid.uuid4(), uuid.uuid4()),
        redline_service=RedlineService(),
    )
    assert [t.__name__ for t in tools] == [
        "apply_redline",
        "preview_redline",
        "extract_counterparty_position",
        "respond_to_counterparty",
        "reconcile_positions",
    ]
    assert sorted(COMMERCIAL_TOOL_NAMES) == [
        "apply_redline",
        "extract_counterparty_position",
        "preview_redline",
        "reconcile_positions",
        "respond_to_counterparty",
    ]


async def test_apply_redline_rejects_noop_edit(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[{"target_text": "the claim", "new_text": "the claim"}],
            service=RedlineService(),
            run_id=uuid.uuid4(),  # rejected → no File row → FK never exercised
        )
    assert "rejected" in out.lower()
    assert "no change" in out.lower()


async def test_apply_redline_document_in_another_matter_not_found(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, _project_id = matter
    other_project = uuid.uuid4()  # a matter that doesn't own the file
    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, other_project),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
            run_id=uuid.uuid4(),  # not found → no File row → FK never exercised
        )
    assert "No document named" in out  # matter-scope: invisible across matters


async def test_preview_redline_renders_without_persisting(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """preview_redline returns the rendered tracked changes but writes nothing —
    no upload, no new File row (the self-review primitive, ADR-F041)."""
    user_id, project_id = matter
    captured = _patch_storage(monkeypatch, source=_docx_bytes(CAP))

    async with commit_factory() as db:
        out = await _preview_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
        )
        await db.commit()

    # the rendered tracked changes come back to the agent...
    assert "[+twelve" in out and "[-three" in out
    assert "NOTHING has been saved" in out
    # ...but nothing was uploaded and no redlined File was created.
    assert "body" not in captured
    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx"}


async def test_preview_redline_rejects_noop_edit(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    async with commit_factory() as db:
        out = await _preview_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[{"target_text": "the claim", "new_text": "the claim"}],
            service=RedlineService(),
        )
    assert "rejected" in out.lower()
    assert "no change" in out.lower()


class _DryRunRaises(RedlineService):
    def dry_run(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlinePreview:
        raise RuntimeError("simulated editor failure")


class _ApplyRaises(RedlineService):
    def apply(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlineApplyResult:
        raise RuntimeError("simulated editor failure")


async def test_apply_redline_editor_exception_is_rejected_not_propagated(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """If the Adeu editor raises on a pathological edit (a real batch CAN — e.g. a
    zero-width insertion), the tool returns fix-and-retry guidance and persists
    nothing — never propagates the exception (untrusted input, ADR-F041)."""
    user_id, project_id = matter
    _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    valid = [{"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}]

    for svc in (_DryRunRaises(), _ApplyRaises()):
        async with commit_factory() as db:
            out = await _apply_redline(
                db,
                _binding(user_id, project_id),
                document_name="contract.docx",
                edits=valid,
                service=svc,
                run_id=uuid.uuid4(),  # editor failure → no File row → FK never exercised
            )
            await db.commit()
        assert "could not be placed by the editor" in out

    # neither attempt persisted a redlined file
    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx"}


async def test_apply_redline_happy_path_persists_redlined_file(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    captured = _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)

    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
            run_id=run_id,
        )
        await db.commit()

    assert "Applied" in out and "redlined" in out.lower()

    # the redlined .docx was uploaded + carries native tracked changes
    body = captured["body"]
    assert isinstance(body, bytes)
    redline = reconstruct_redline_text(body)
    assert "[+twelve" in redline and "[-three" in redline

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        names = {f.filename for f in files}
        assert "contract.docx" in names
        assert "contract (redlined).docx" in names
        redlined = next(f for f in files if f.filename == "contract (redlined).docx")
        assert redlined.project_id == project_id
        assert redlined.mime_type == OOXML_DOCX_MIME
        assert redlined.ingestion_status == "ready"
        # work-product provenance (ADR-F046): the output is tied to the run
        assert redlined.created_by_run_id == run_id
        # document lineage (ADR-F066): the output points at its source; a working
        # version, never a snapshot
        source = next(f for f in files if f.filename == "contract.docx")
        assert redlined.parent_file_id == source.id
        assert redlined.is_snapshot is False

        # audit receipt: counts/types/IDs only, never clause text
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "commercial.redline_applied",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1
        details = str(audit[0].details)
        assert "twelve" not in details and "three" not in details


# --------------------------------------------------------------------------- #
# R-1 (ADR-F066) — redline continuity: working-version default + start_fresh
# --------------------------------------------------------------------------- #


def test_redlined_filename_version_bumps() -> None:
    """Base case unchanged; a chained output bumps to v2, v3, … (ADR-F066)."""
    assert _redlined_filename("contract.docx") == "contract (redlined).docx"
    assert _redlined_filename("contract (redlined).docx") == "contract (redlined v2).docx"
    assert _redlined_filename("contract (redlined v2).docx") == "contract (redlined v3).docx"


def test_response_filename_version_bumps() -> None:
    assert _response_filename("contract.docx") == "contract (response).docx"
    assert _response_filename("contract (response).docx") == "contract (response v2).docx"
    assert _response_filename("contract (response v7).docx") == "contract (response v8).docx"


def test_versioned_filename_survives_pathological_version_digits() -> None:
    """An adversarial upload named with a huge version digit run must not crash
    the run at persist time (Python's ~4300-digit int() conversion limit): past
    the bound it degrades to a plain "(label)" suffix instead of bumping."""
    hostile = "x (redlined v" + "9" * 5000 + ").docx"
    assert _redlined_filename(hostile) == hostile[: -len(".docx")] + " (redlined).docx"
    # The bound itself still bumps (8 digits is far beyond any real chain).
    assert _redlined_filename("x (redlined v99999999).docx") == "x (redlined v100000000).docx"


async def _seed_redlined_child(
    factory: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed a prior redline output as a lineage child of the matter's contract.docx.

    Returns (source_file_id, child_file_id)."""
    async with factory() as db:
        source = (await db.execute(select(File).where(File.owner_id == user_id))).scalar_one()
        child = File(
            owner_id=user_id,
            project_id=project_id,
            filename="contract (redlined).docx",
            mime_type=OOXML_DOCX_MIME,
            size_bytes=1234,
            hash_sha256="1" * 64,
            storage_path=str(uuid.uuid4()),
            ingestion_status="ready",
            parent_file_id=source.id,
        )
        db.add(child)
        await db.commit()
        return source.id, child.id


async def test_apply_redline_default_continues_from_working_version(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """By default a follow-up apply_redline resolves the named document to the
    agent's latest working version (the lineage leaf), says so in the result,
    chains the new output onto that leaf, and version-bumps the name (ADR-F066)."""
    user_id, project_id = matter
    _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    _, child_id = await _seed_redlined_child(commit_factory, user_id=user_id, project_id=project_id)

    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
            run_id=run_id,
        )
        await db.commit()

    # transparency: the result names the resolved working version + the escape hatch
    assert 'Continued from your latest working version "contract (redlined).docx"' in out
    assert "start_fresh=true" in out

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        new = next(f for f in files if f.created_by_run_id == run_id)
        assert new.filename == "contract (redlined v2).docx"  # version-aware naming
        assert new.parent_file_id == child_id  # chained onto the working version


async def test_apply_redline_start_fresh_hits_the_named_row(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """start_fresh=True pins the literally-named original even when a redlined
    child exists on the lineage chain (the explicit restart, ADR-F066)."""
    user_id, project_id = matter
    _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    source_id, _ = await _seed_redlined_child(
        commit_factory, user_id=user_id, project_id=project_id
    )

    async with commit_factory() as db:
        out = await _apply_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
            run_id=run_id,
            start_fresh=True,
        )
        await db.commit()

    assert "Continued from" not in out

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        new = next(f for f in files if f.created_by_run_id == run_id)
        assert new.filename == "contract (redlined).docx"  # named from the original
        assert new.parent_file_id == source_id  # chained onto the original


async def test_preview_redline_default_notes_working_version(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The preview carries the same continuity note (and still saves nothing)."""
    user_id, project_id = matter
    captured = _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    await _seed_redlined_child(commit_factory, user_id=user_id, project_id=project_id)

    async with commit_factory() as db:
        out = await _preview_redline(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            edits=[
                {"target_text": "three (3)", "new_text": "twelve (12)", "rationale": _RATIONALE}
            ],
            service=RedlineService(),
        )

    assert 'Continued from your latest working version "contract (redlined).docx"' in out
    assert "NOTHING has been saved" in out
    assert "body" not in captured  # still a pure dry run


# --------------------------------------------------------------------------- #
# C5a — negotiation rounds: extract + respond + the no-silent-action gate (ADR-F032)
# --------------------------------------------------------------------------- #

_NEG_BASE = (
    "The Vendor shall indemnify the Customer for all losses arising from the Services. "
    "The term of this Agreement is three (3) years from the Effective Date. "
    "Liability is capped at fees paid in the prior twelve (12) months."
)


def _counterparty_docx() -> bytes:
    """A .docx with 3 counterparty tracked changes + 1 anchored comment (their markup)."""
    from adeu import ModifyText, RedlineEngine

    doc = _docx_bytes(_NEG_BASE)
    eng = RedlineEngine(io.BytesIO(doc), author="Opposing Counsel")
    eng.apply_edits(
        [
            ModifyText(
                target_text="all losses",
                new_text="direct losses only",
                comment="Cap our exposure to direct losses please.",
            ),
            ModifyText(target_text="three (3)", new_text="five (5)"),
            ModifyText(target_text="twelve (12)", new_text="twenty-four (24)"),
        ]
    )
    out = eng.save_to_stream()
    return out.getvalue() if hasattr(out, "getvalue") else bytes(out)


def _full_coverage_decisions(source: bytes) -> list[dict[str, object]]:
    """One decision per change/comment ref in ``source`` — accept/reject/counter/reply."""
    state = read_state_of_play(source)
    decisions: list[dict[str, object]] = []
    for c in state.changes:
        if c.kind == "modify" and c.inserted_text == "twenty-four (24)":
            decisions.append(
                {
                    "ref": c.ref,
                    "verdict": "counter",
                    "target_text": "twenty-four (24)",
                    "new_text": "eighteen (18)",
                    "rationale": (
                        "Eighteen months is the house fallback for the liability survival "
                        "window; twenty-four exceeds our standard position on this deal."
                    ),
                }
            )
        elif c.kind == "modify" and c.inserted_text == "five (5)":
            decisions.append(
                {
                    "ref": c.ref,
                    "verdict": "reject",
                    "rationale": "Five years is too long; revert to three.",
                }
            )
        elif c.kind == "modify" and c.inserted_text == "direct losses only":
            # The comment is anchored to THIS change; we reply to that comment below, so we
            # must not accept/reject this change (that would wipe the reply — C5b-1). Leave
            # it open: a recorded decision that keeps the thread (and our reply) alive.
            decisions.append(
                {
                    "ref": c.ref,
                    "verdict": "leave_open",
                    "rationale": "Parking the indemnity scope pending the reply on their comment.",
                }
            )
        else:
            decisions.append({"ref": c.ref, "verdict": "accept", "rationale": "Acceptable."})
    for cm in state.comments:
        if cm.parent_id is None and not cm.is_ours:
            decisions.append(
                {
                    "ref": cm.ref,
                    "verdict": "reply",
                    "reply_text": "Noted — see our counter on the cap period.",
                }
            )
    return decisions


async def test_extract_counterparty_position_lists_changes_and_comments(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    _patch_storage(monkeypatch, source=_counterparty_docx())

    async with commit_factory() as db:
        out = await _extract_counterparty_position(
            db, _binding(user_id, project_id), document_name="contract.docx"
        )
        await db.commit()

    assert "provenance=counterparty" in out
    assert "TRACKED CHANGES" in out and "[C1]" in out and "[C2]" in out and "[C3]" in out
    assert "[Com:" in out  # the anchored comment is surfaced
    assert "respond_to_counterparty" in out

    # audit receipt: counts only, no clause text
    async with commit_factory() as db:
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "commercial.counterparty_extracted",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1
        assert "losses" not in str(audit[0].details)


def _np(name: str, side: str, *, aliases: list[str] | None = None) -> MatterParticipant:
    """An in-memory roster row for the pure render tests (classify reads name/aliases/side)."""
    return MatterParticipant(display_name=name, side=side, aliases=aliases or [], trust="inferred")


def _tc(ref: str, author: str, *, deleted: str = "a", inserted: str = "b") -> TrackedChange:
    return TrackedChange(
        ref=ref,
        kind="modify",
        deleted_text=deleted,
        inserted_text=inserted,
        author=author,
        context="",
        adeu_ids=(),
    )


def _sop(changes: list[TrackedChange]) -> StateOfPlay:
    return StateOfPlay(
        changes=changes,
        comments=[],
        clean_view="CLEAN",
        marked_view="MARKED",
        clean_text_full="CLEAN",
    )


def test_render_state_of_play_groups_by_roster_side() -> None:
    """ADR-F048 Slice 2: the negotiation render groups changes by side, keeping every ref.

    Coverage parity is preserved — every change ref still appears in the "decide one
    verdict per ref" list — while our side / a third party are grouped distinctly from
    the counterparty so the agent doesn't negotiate against itself or mis-read a third party.
    """
    ours, third = "Our Associate", "Escrow Agent"
    state = _sop(
        [
            _tc("C1", ours),  # ours
            _tc("C2", "Mark Counsel"),  # not on roster → assumed counterparty
            _tc("C3", third),  # known third party
        ]
    )
    roster = [_np(ours, "ours"), _np(third, "other")]
    out = _render_state_of_play("nda.docx", state, roster)
    # Every ref is still required (the coverage gate is unchanged).
    assert "[C1]" in out and "[C2]" in out and "[C3]" in out
    assert "respond_to_counterparty" in out
    # Grouped distinctly.
    assert "Your side" in out
    assert "third party" in out.lower()
    assert "counterparty" in out.lower()


def test_render_state_of_play_empty_roster_assumes_counterparty() -> None:
    """Backward-compatible: with no placed authors, everyone is the other side (no groups)."""
    out = _render_state_of_play("nda.docx", _sop([_tc("C1", "Anyone")]), [])
    assert "[C1]" in out and "respond_to_counterparty" in out
    assert "Your side" not in out  # no 'ours' subsection when nobody classifies ours
    # The unplaced author is assumed counterparty on this document (C5a loop preserved).


async def test_extract_counterparty_position_other_matter_not_found(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, _project_id = matter
    async with commit_factory() as db:
        out = await _extract_counterparty_position(
            db, _binding(user_id, uuid.uuid4()), document_name="contract.docx"
        )
    assert "No document named" in out  # matter-scope: 404-conflated across matters


async def test_respond_rejects_incomplete_coverage(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The no-silent-action gate: omit one ref → the whole batch is rejected, nothing
    is written (a silent accept is impossible)."""
    user_id, project_id = matter
    source = _counterparty_docx()
    _patch_storage(monkeypatch, source=source)
    decisions = _full_coverage_decisions(source)[:-2]  # drop the last change + the comment

    async with commit_factory() as db:
        out = await _respond_to_counterparty(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            decisions=decisions,
            run_id=uuid.uuid4(),  # rejected pre-write → no File → FK never exercised
        )
        await db.commit()

    assert "UNADDRESSED" in out
    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx"}  # nothing written


async def test_respond_counter_violating_surgical_gate_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A counter is held to the same surgical gate as apply_redline — a substantive
    change with no rationale is rejected (and nothing is written)."""
    user_id, project_id = matter
    source = _counterparty_docx()
    _patch_storage(monkeypatch, source=source)
    decisions = _full_coverage_decisions(source)
    for d in decisions:
        if d["verdict"] == "counter":
            d["rationale"] = "no"  # too short for a substantive (number) change → D2 fail

    async with commit_factory() as db:
        out = await _respond_to_counterparty(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            decisions=decisions,
            run_id=uuid.uuid4(),
        )
        await db.commit()

    assert "ejected" in out  # "Rejected"/"rejected"
    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx"}


async def test_respond_full_coverage_persists_and_audits(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    source = _counterparty_docx()
    captured = _patch_storage(monkeypatch, source=source)
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    decisions = _full_coverage_decisions(source)

    async with commit_factory() as db:
        out = await _respond_to_counterparty(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            decisions=decisions,
            run_id=run_id,
        )
        await db.commit()

    assert "Responded to all" in out and "coverage verified" in out

    # the response .docx was uploaded with native tracked changes + comments
    body = captured["body"]
    assert isinstance(body, bytes)
    redline = reconstruct_redline_text(body)
    assert "[+" in redline or "[-" in redline  # our layered tracked changes

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        names = {f.filename for f in files}
        assert "contract (response).docx" in names
        response = next(f for f in files if f.filename == "contract (response).docx")
        assert response.project_id == project_id
        assert response.mime_type == OOXML_DOCX_MIME
        assert response.created_by_run_id == run_id  # work-product provenance (ADR-F046)
        # document lineage (ADR-F066): the response derives from the counterparty doc
        source = next(f for f in files if f.filename == "contract.docx")
        assert response.parent_file_id == source.id
        assert response.is_snapshot is False

        # domain audit receipt — counts/types/IDs only, never clause text
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "commercial.counterparty_responded",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1
        details = str(audit[0].details)
        assert "losses" not in details and "eighteen" not in details

        # matter-memory receipt fact for round-to-round continuity
        facts = (
            (
                await db.execute(
                    select(MatterMemoryEntry).where(
                        MatterMemoryEntry.project_id == project_id,
                        MatterMemoryEntry.kind == "fact",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any("Counterparty round" in f.body_md for f in facts)


async def test_respond_records_each_verdict_into_the_deal_change_ledger(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """C5b-3 (ADR-F032): a verified+saved round records one verdict per decision into
    the run-scoped ledger (ref + verdict only), which the runner drains into the live
    chips. One entry per decision, refs/verdicts match the proposal."""
    user_id, project_id = matter
    source = _counterparty_docx()
    _patch_storage(monkeypatch, source=source)
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    decisions = _full_coverage_decisions(source)
    ledger = DealChangeLedger()

    async with commit_factory() as db:
        out = await _respond_to_counterparty(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            decisions=decisions,
            run_id=run_id,
            change_ledger=ledger,
        )
        await db.commit()

    assert "Responded to all" in out
    drained = ledger.drain()
    assert {(c.ref, c.verdict) for c in drained} == {(d["ref"], d["verdict"]) for d in decisions}
    assert len(drained) == len(decisions)  # one chip per decision, no dupes


async def test_respond_rejection_records_nothing_into_the_deal_change_ledger(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """C5b-3: a chip can never fire on a silent/rejected round — incomplete coverage is
    rejected pre-write, so nothing is recorded (mirrors 'record only on a real change')."""
    user_id, project_id = matter
    source = _counterparty_docx()
    _patch_storage(monkeypatch, source=source)
    decisions = _full_coverage_decisions(source)[:-2]  # drop refs → coverage gate rejects
    ledger = DealChangeLedger()

    async with commit_factory() as db:
        out = await _respond_to_counterparty(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            decisions=decisions,
            run_id=uuid.uuid4(),
            change_ledger=ledger,
        )
        await db.commit()

    assert "UNADDRESSED" in out
    assert ledger.drain() == []  # nothing recorded on a rejected round


async def test_respond_rejects_reply_on_accepted_anchored_change(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """C5b-1 comment-wipe gate: replying to a comment while accepting the change it is
    anchored to would silently delete the reply — the batch is rejected up front and
    nothing is written (full coverage holds, so this is the anchoring gate, not coverage)."""
    user_id, project_id = matter
    source = _counterparty_docx()
    _patch_storage(monkeypatch, source=source)

    state = read_state_of_play(source)
    com_ref = next(iter(state.open_comment_refs))
    anchored_ref = state.comment_anchors[com_ref]  # the change the comment sits on
    decisions: list[dict[str, object]] = [
        {"ref": c.ref, "verdict": "accept", "rationale": "Acceptable."} for c in state.changes
    ]
    # accept the anchored change AND reply to its comment → the wipe combination
    decisions.append({"ref": com_ref, "verdict": "reply", "reply_text": "We want full indemnity."})

    async with commit_factory() as db:
        out = await _respond_to_counterparty(
            db,
            _binding(user_id, project_id),
            document_name="contract.docx",
            decisions=decisions,
            run_id=uuid.uuid4(),  # rejected pre-write → no File → FK never exercised
        )
        await db.commit()

    assert "anchored to" in out and anchored_ref in out  # the gate names the offending change
    assert "Responded to all" not in out
    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx"}  # nothing written
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "commercial.counterparty_responded",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert not audit  # no response receipt


# ----------------------- C7b reconcile_positions (ADR-F034) ------------------ #


async def test_reconcile_positions_records_receipt_and_audits(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A consistent (or fully-resolved) reconciliation records one counts-only receipt
    + audit row — never position text — and returns the reconciled position per head."""
    user_id, project_id = matter
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    positions = [
        {"head": "liability", "position": "uncapped", "source": "clause-drafter"},
        {"head": "liability", "position": "cap at fees", "source": "clause-reviewer"},
        {"head": "indemnity", "position": "mutual, IP carve-out", "source": "clause-drafter"},
    ]
    resolutions = {"liability": "super-cap at 2x fees, data/IP uncapped"}

    async with commit_factory() as db:
        out = await _reconcile_positions(
            db,
            _binding(user_id, project_id),
            positions=positions,
            resolutions=resolutions,
            run_id=run_id,
        )
        await db.commit()

    assert "Reconciled" in out and "1 divergence(s) resolved" in out
    assert "super-cap" in out  # the reconciled position is handed back to the lead

    async with commit_factory() as db:
        facts = (
            (
                await db.execute(
                    select(MatterMemoryEntry).where(
                        MatterMemoryEntry.project_id == project_id,
                        MatterMemoryEntry.kind == "fact",
                    )
                )
            )
            .scalars()
            .all()
        )
        receipt = [f for f in facts if "Reconciled" in f.body_md]
        assert len(receipt) == 1
        assert receipt[0].fact_type == "open_point"
        assert receipt[0].run_id == run_id
        # the receipt names the heads (continuity) but never the position text
        assert "liability" in receipt[0].body_md
        assert "super-cap" not in receipt[0].body_md and "uncapped" not in receipt[0].body_md

        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "commercial.positions_reconciled",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1
        details = str(audit[0].details)
        assert "super-cap" not in details and "uncapped" not in details  # counts only
        assert "liability" not in details and "indemnity" not in details


async def test_reconcile_positions_unresolved_divergence_records_nothing(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A head where the drafts diverge with no resolution is rejected — nothing recorded."""
    user_id, project_id = matter
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    positions = [
        {"head": "liability", "position": "uncapped", "source": "clause-drafter"},
        {"head": "liability", "position": "cap at fees", "source": "clause-reviewer"},
    ]

    async with commit_factory() as db:
        out = await _reconcile_positions(
            db,
            _binding(user_id, project_id),
            positions=positions,
            resolutions={},
            run_id=run_id,
        )
        await db.commit()

    assert "Reconciliation rejected" in out and "liability" in out

    async with commit_factory() as db:
        facts = (
            (
                await db.execute(
                    select(MatterMemoryEntry).where(
                        MatterMemoryEntry.project_id == project_id,
                        MatterMemoryEntry.kind == "fact",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert not [f for f in facts if "Reconciled" in f.body_md]
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "commercial.positions_reconciled",
                        AuditLog.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert not audit  # no receipt on a rejected reconciliation


async def test_reconcile_positions_malformed_input_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """An empty batch returns a fix-and-retry string (reject, don't crash); nothing written."""
    user_id, project_id = matter
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    async with commit_factory() as db:
        out = await _reconcile_positions(
            db,
            _binding(user_id, project_id),
            positions=[],
            resolutions={},
            run_id=run_id,
        )
        await db.commit()
    assert "Rejected" in out and "reconcile_positions" in out
