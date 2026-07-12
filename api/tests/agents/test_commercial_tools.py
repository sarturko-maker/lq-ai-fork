"""C4 commercial_tools integration tests (ADR-F031/F035).

Drives ``_apply_redline`` through a real test DB with a real ``RedlineService``
(Adeu) and storage monkeypatched to a known ``.docx`` — covering the orchestration
(validate → fetch → gate → dry-run → apply → persist), the matter-scope boundary
(a document in another matter is not found — 404-conflated), and the audit receipt
(counts/types/IDs, never clause text).
"""

from __future__ import annotations

import hashlib
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
    _lawyer_draft_filename,
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


def _patch_storage(
    monkeypatch: pytest.MonkeyPatch, *, source: bytes | list[bytes]
) -> dict[str, object]:
    """Fake the four storage calls the redline persist paths make.

    ``source`` may be a LIST of byte strings: successive downloads pop from it
    (the last entry repeats) — this is how a test stages a concurrent-writer
    race between the render download and the wedge-aware CAS's re-download
    (ADR-F081). ``uploads``/``copies``/``deletes`` record every call in order;
    the flat ``path``/``body`` keys keep last-write semantics for the
    create-path tests.
    """
    captured: dict[str, object] = {"uploads": [], "copies": [], "deletes": []}
    downloads = list(source) if isinstance(source, list) else [source]

    @asynccontextmanager
    async def fake_download(*, storage_path: str) -> AsyncIterator[AsyncIterator[bytes]]:
        data = downloads.pop(0) if len(downloads) > 1 else downloads[0]

        async def _gen() -> AsyncIterator[bytes]:
            yield data

        yield _gen()

    async def fake_upload(*, storage_path: str, body: bytes, content_type: str) -> None:
        captured["path"] = storage_path
        captured["body"] = body
        captured["content_type"] = content_type
        captured["uploads"].append((storage_path, body))  # type: ignore[union-attr]

    async def fake_copy(*, source_path: str, dest_path: str) -> None:
        captured["copies"].append((source_path, dest_path))  # type: ignore[union-attr]

    async def fake_delete(*, storage_path: str) -> None:
        captured["deletes"].append(storage_path)  # type: ignore[union-attr]

    monkeypatch.setattr(commercial_tools.storage, "stream_download", fake_download)
    monkeypatch.setattr(commercial_tools.storage, "upload_bytes", fake_upload)
    monkeypatch.setattr(commercial_tools.storage, "copy_object", fake_copy)
    monkeypatch.setattr(commercial_tools.storage, "delete_object", fake_delete)
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
        # adversarial_review rides this grant set (ADR-F084) but is built by its own
        # builder (build_adversarial_review_tools) — build_commercial_tools' closures
        # above stay the five redline/negotiation tools.
        "adversarial_review",
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


def test_lawyer_draft_filename() -> None:
    """The ADR-F081 human-bytes snapshot name — the mirror of WOPI's "(agent
    draft)": stable, extension-preserving, docx-appended for a bare name."""
    assert _lawyer_draft_filename("contract (redlined).docx") == (
        "contract (redlined) (lawyer draft).docx"
    )
    assert _lawyer_draft_filename("noext") == "noext (lawyer draft).docx"


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
    hash_sha256: str = "1" * 64,
    created_by_run_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed a prior redline output as a lineage child of the matter's contract.docx.

    ``hash_sha256`` must match the bytes the storage fake serves for the ADR-F081
    converge path to pass its CAS guard (a mismatch IS the drift-rejection case).
    ``created_by_run_id`` None = human-authored head (snapshot branch); set = the
    agent's own untouched output (plain overwrite branch).

    Returns (source_file_id, child_file_id)."""
    async with factory() as db:
        source = (await db.execute(select(File).where(File.owner_id == user_id))).scalar_one()
        child = File(
            owner_id=user_id,
            project_id=project_id,
            filename="contract (redlined).docx",
            mime_type=OOXML_DOCX_MIME,
            size_bytes=1234,
            hash_sha256=hash_sha256,
            storage_path=str(uuid.uuid4()),
            ingestion_status="ready",
            parent_file_id=source.id,
            created_by_run_id=created_by_run_id,
        )
        db.add(child)
        await db.commit()
        return source.id, child.id


async def test_apply_redline_converges_on_working_head_and_snapshots_human_bytes(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """By default a follow-up apply_redline resolves the named document to the
    latest working version and UPDATES IT IN PLACE (ADR-F081) — same row, same
    filename, same storage key — so the matter keeps one living redlined
    document. A human-authored head (created_by_run_id NULL: the lawyer edited
    it since the agent last wrote) is preserved first as an immutable
    ``(lawyer draft)`` snapshot, mirroring WOPI PutFile's authorship-boundary
    snapshot."""
    user_id, project_id = matter
    source_bytes = _docx_bytes(CAP)
    captured = _patch_storage(monkeypatch, source=source_bytes)
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    prior_hash = hashlib.sha256(source_bytes).hexdigest()
    _, child_id = await _seed_redlined_child(
        commit_factory, user_id=user_id, project_id=project_id, hash_sha256=prior_hash
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
        )
        # NO commit here — the converge path commits INSIDE the tool body
        # (ADR-F081: the guard's failed-audit rollback must not be able to
        # discard row metadata for already-overwritten bytes). The fresh-session
        # assertions below pin that in-body commit.

    # transparency: the result names the resolved working version, says it was
    # updated in place, mentions the preserved lawyer draft + the escape hatch
    assert 'Continuing from your latest working version "contract (redlined).docx"' in out
    assert 'updated "contract (redlined).docx" in place' in out
    assert "lawyer draft" in out
    assert "start_fresh=true" in out

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        by_name = {f.filename: f for f in files}
        # exactly: the original, the living head, and one snapshot — no v2 sibling
        assert set(by_name) == {
            "contract.docx",
            "contract (redlined).docx",
            "contract (redlined) (lawyer draft).docx",
        }
        head = by_name["contract (redlined).docx"]
        assert head.id == child_id  # the SAME row, mutated
        assert head.created_by_run_id == run_id
        assert head.updated_at is not None  # resolver leaf pick + WOPI 1010 backstop
        body = captured["body"]
        assert isinstance(body, bytes)
        assert head.hash_sha256 == hashlib.sha256(body).hexdigest()
        assert head.size_bytes == len(body)
        assert head.is_snapshot is False
        # the overwrite landed at the head's OWN storage key (no orphaned object)
        assert captured["path"] == head.storage_path
        # the lawyer's prior bytes survive as an immutable snapshot of the head
        snap = by_name["contract (redlined) (lawyer draft).docx"]
        assert snap.is_snapshot is True
        assert snap.parent_file_id == head.id
        assert snap.hash_sha256 == prior_hash
        assert snap.created_by_run_id is None  # the preserved bytes are the lawyer's
        assert snap.storage_path == str(snap.id)  # ADR 0005 key == row id
        assert captured["copies"] == [(head.storage_path, str(snap.id))]

        # audit receipt: in-place semantics recorded, counts/IDs only
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
        details = audit[0].details
        assert details["updated_in_place"] is True
        assert details["snapshot_file_id"] == str(snap.id)
        assert details["redlined_sha256"] == head.hash_sha256
        assert "twelve" not in str(details) and "three" not in str(details)


async def test_apply_redline_agent_head_overwrites_without_snapshot(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """An agent-authored head (created_by_run_id set — the agent's own untouched
    output) is overwritten with NO snapshot: tracked changes are additive, so the
    prior round is recoverable by rejecting the newest change regions (ADR-F081).
    Provenance follows to the newest run."""
    user_id, project_id = matter
    source_bytes = _docx_bytes(CAP)
    _patch_storage(monkeypatch, source=source_bytes)
    run_1 = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    run_2 = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    _, child_id = await _seed_redlined_child(
        commit_factory,
        user_id=user_id,
        project_id=project_id,
        hash_sha256=hashlib.sha256(source_bytes).hexdigest(),
        created_by_run_id=run_1,
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
            run_id=run_2,
        )
        # no commit — pins the tool-body commit (see the converge test)

    assert 'updated "contract (redlined).docx" in place' in out
    assert "lawyer draft" not in out  # no snapshot on agent-over-agent

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx", "contract (redlined).docx"}
        head = next(f for f in files if f.filename == "contract (redlined).docx")
        assert head.id == child_id
        assert head.created_by_run_id == run_2  # the run that last wrote the bytes
        assert not any(f.is_snapshot for f in files)


async def test_apply_redline_cas_rejects_a_genuine_race(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A GENUINE race: the storage bytes (and the row hash) moved on after the
    render — the wedge-aware CAS re-downloads, sees storage ≠ what was rendered
    over, and rejects with NOTHING written (ADR-F081: never clobber a
    concurrent write)."""
    user_id, project_id = matter
    rendered_over = _docx_bytes(CAP)
    interloper = _docx_bytes(CAP + " Amended by a concurrent save.")
    # first download (the render) sees the old bytes; the CAS re-download sees
    # the interloper's bytes, which match the row the interloper committed
    captured = _patch_storage(monkeypatch, source=[rendered_over, interloper])
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    interloper_hash = hashlib.sha256(interloper).hexdigest()
    await _seed_redlined_child(
        commit_factory, user_id=user_id, project_id=project_id, hash_sha256=interloper_hash
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
        )

    assert "changed while this redline was being prepared" in out
    assert captured["uploads"] == [] and captured["copies"] == []  # nothing written

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx", "contract (redlined).docx"}
        head = next(f for f in files if f.filename == "contract (redlined).docx")
        assert head.hash_sha256 == interloper_hash  # untouched
        assert head.created_by_run_id is None


async def test_apply_redline_repairs_a_stale_row_wedge(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The WEDGE: a prior apply's step-2 commit failed after the overwrite, so
    the row hash disagrees with the head's OWN storage bytes. The render is
    over the true current bytes, so the apply must PROCEED and repair the row —
    a blind CAS rejection here would wedge the living document forever
    (review should-fix, ADR-F081)."""
    user_id, project_id = matter
    source_bytes = _docx_bytes(CAP)
    captured = _patch_storage(monkeypatch, source=source_bytes)
    run_old = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    run_new = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    # row hash is stale garbage; storage (the fake) serves the real bytes — the
    # exact state a step-2 commit failure leaves behind
    _, child_id = await _seed_redlined_child(
        commit_factory,
        user_id=user_id,
        project_id=project_id,
        hash_sha256="1" * 64,
        created_by_run_id=run_old,
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
            run_id=run_new,
        )

    assert 'updated "contract (redlined).docx" in place' in out

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx", "contract (redlined).docx"}
        head = next(f for f in files if f.filename == "contract (redlined).docx")
        assert head.id == child_id
        body = captured["body"]
        assert isinstance(body, bytes)
        assert head.hash_sha256 == hashlib.sha256(body).hexdigest()  # row repaired
        assert head.created_by_run_id == run_new


async def test_apply_redline_never_converges_on_a_response_document(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A "(response)" document is the per-round OUTBOUND record — even when the
    resolver lands on it as the newest working leaf, apply_redline must branch a
    NEW row rather than mutate it (ADR-F081 redline-name anchor; review catch)."""
    user_id, project_id = matter
    _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    async with commit_factory() as db:
        source = (await db.execute(select(File).where(File.owner_id == user_id))).scalar_one()
        response = File(
            owner_id=user_id,
            project_id=project_id,
            filename="contract (response).docx",
            mime_type=OOXML_DOCX_MIME,
            size_bytes=1234,
            hash_sha256="2" * 64,
            storage_path=str(uuid.uuid4()),
            ingestion_status="ready",
            parent_file_id=source.id,
        )
        db.add(response)
        await db.commit()
        response_id = response.id

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
        await db.commit()  # create path defers to the caller's commit, as before

    assert "Applied" in out

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        untouched = next(f for f in files if f.id == response_id)
        assert untouched.hash_sha256 == "2" * 64  # the outbound record is immutable
        assert untouched.updated_at is None
        new = next(f for f in files if f.created_by_run_id == run_id)
        assert new.id != response_id
        assert new.parent_file_id == response_id  # chained, not converged
        assert new.filename == "contract (response) (redlined).docx"


async def test_apply_redline_snapshot_commit_failure_cleans_up_and_writes_nothing(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Step-1 failure discipline (mirrors WOPI): if the snapshot row's commit
    fails, the orphan snapshot OBJECT is deleted, the live object is untouched,
    no snapshot row survives, and the error propagates (ADR-F081)."""
    user_id, project_id = matter
    source_bytes = _docx_bytes(CAP)
    captured = _patch_storage(monkeypatch, source=source_bytes)
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    prior_hash = hashlib.sha256(source_bytes).hexdigest()
    await _seed_redlined_child(
        commit_factory, user_id=user_id, project_id=project_id, hash_sha256=prior_hash
    )

    async with commit_factory() as db:
        real_commit = db.commit

        async def failing_commit() -> None:
            monkeypatch.setattr(db, "commit", real_commit)  # fail only the first
            raise RuntimeError("simulated step-1 commit failure")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError, match="simulated step-1 commit failure"):
            await _apply_redline(
                db,
                _binding(user_id, project_id),
                document_name="contract.docx",
                edits=[
                    {
                        "target_text": "three (3)",
                        "new_text": "twelve (12)",
                        "rationale": _RATIONALE,
                    }
                ],
                service=RedlineService(),
                run_id=run_id,
            )

    # the snapshot copy was made, then deleted as an orphan; nothing was uploaded
    copies = captured["copies"]
    assert isinstance(copies, list) and len(copies) == 1
    assert captured["deletes"] == [copies[0][1]]
    assert captured["uploads"] == []

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        assert {f.filename for f in files} == {"contract.docx", "contract (redlined).docx"}
        head = next(f for f in files if f.filename == "contract (redlined).docx")
        assert head.hash_sha256 == prior_hash  # untouched
        assert head.created_by_run_id is None  # the flip rolled back with the commit


async def test_apply_redline_head_deleted_between_render_and_persist(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The deleted-head guard: if the resolved row vanishes before persist, the
    tool reports it and writes nothing (ADR-F081 behavior matrix)."""
    from types import SimpleNamespace

    user_id, project_id = matter
    captured = _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)

    real_render = commercial_tools._render_redline

    async def render_then_ghost(*args: object, **kwargs: object) -> object:
        rendered = await real_render(*args, **kwargs)  # type: ignore[arg-type]
        assert not isinstance(rendered, str)
        # simulate the row disappearing after the render resolved it
        ghost_row = SimpleNamespace(file_id=uuid.uuid4(), filename=rendered.row.filename)
        return commercial_tools._RenderedRedline(
            row=ghost_row,  # type: ignore[arg-type]
            proposal=rendered.proposal,
            redlined=rendered.redlined,
            result=rendered.result,
            source_sha256=rendered.source_sha256,
            continuity_note=rendered.continuity_note,
        )

    monkeypatch.setattr(commercial_tools, "_render_redline", render_then_ghost)

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

    assert "was deleted while the redline was being prepared" in out
    assert captured["uploads"] == [] and captured["copies"] == []


async def test_apply_redline_start_fresh_hits_the_named_row(
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """start_fresh=True pins the literally-named original even when a redlined
    child exists on the lineage chain (the explicit restart, ADR-F066). The new
    branch is a NEW row (never an in-place update) with a matter-unique name —
    the living head already holds "contract (redlined).docx" (ADR-F081)."""
    user_id, project_id = matter
    _patch_storage(monkeypatch, source=_docx_bytes(CAP))
    run_id = await _make_run(commit_factory, user_id=user_id, project_id=project_id)
    source_id, child_id = await _seed_redlined_child(
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

    assert "Continuing from" not in out

    async with commit_factory() as db:
        files = (await db.execute(select(File).where(File.owner_id == user_id))).scalars().all()
        new = next(f for f in files if f.created_by_run_id == run_id)
        assert new.id != child_id  # a fresh branch, not an in-place update
        assert new.filename == "contract (redlined v2).docx"  # matter-unique name
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

    assert 'Continuing from your latest working version "contract (redlined).docx"' in out
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
