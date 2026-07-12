"""ADV-1 adversarial-review tests (ADR-F084) — the hostile-reader tool.

Drives, through the real test DB and a STUB gateway (no egress):

* the grant set (one tool, riding the redlining group's names; narrow builder grant),
* the happy path: load the matter docx → one gateway call → validated findings →
  severity-ordered checklist + counts-only audit row,
* reject paths: unknown document (fix-and-retry), malformed model JSON, over-cap
  findings, gateway failure, truncated (finish_reason='length') output — all reject,
  never crash, and NOTHING is written,
* input truncation: an oversize document is cut with an HONEST notice in the render,
* the audit row carries counts only — never clause or finding text.

The gateway is the injected ``gateway_factory`` seam (build_adversarial_review_tools);
no test touches a provider.
"""

from __future__ import annotations

import io
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents import adversarial_review as adv
from app.agents.adversarial_review import (
    ADVERSARIAL_REVIEW_TOOL_NAME,
    build_adversarial_review_tools,
)
from app.agents.commercial_tools import COMMERCIAL_TOOL_NAMES
from app.agents.tools import MatterBinding
from app.models.audit import AuditLog
from app.models.file import File
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration


def build_docx(paragraphs: list[str]) -> bytes:
    """A minimal real .docx (the corpus-test pattern) — the review pass parses real OOXML."""
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Stub gateway
# --------------------------------------------------------------------------- #


@dataclass
class _Message:
    content: str | None


@dataclass
class _Choice:
    message: _Message
    finish_reason: str = "stop"


@dataclass
class _Response:
    choices: list[_Choice]


@dataclass
class _StubGateway:
    """Canned-response gateway double; records the requests it receives."""

    content: str | None = None
    finish_reason: str = "stop"
    error: Exception | None = None
    requests: list[Any] = field(default_factory=list)

    async def chat_completion(self, request: Any) -> _Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return _Response(
            choices=[
                _Choice(message=_Message(content=self.content), finish_reason=self.finish_reason)
            ]
        )


def _findings_json(n: int = 2) -> str:
    findings = [
        {
            "severity": "high" if i == 0 else "low",
            "kind": "under_protection" if i == 0 else "gap",
            "clause": f"clause anchor {i}",
            "issue": f"issue {i}",
            "suggestion": f"suggestion {i}",
        }
        for i in range(n)
    ]
    return json.dumps({"findings": findings, "overall": "Needs work before it goes out."})


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    async with commit_factory() as db:
        user = User(
            email=f"adv-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Adversarial Review User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="ADV Matter",
            slug=f"adv-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
        )
        db.add(project)
        await db.commit()
        user_id, project_id = user.id, project.id
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(File).where(File.owner_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="ADV Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


async def _seed_docx(
    commit_factory: async_sessionmaker[AsyncSession],
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    filename: str,
    paragraphs: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seed a matter .docx row + patch storage download to return its bytes."""
    data = build_docx(paragraphs)
    async with commit_factory() as db:
        db.add(
            File(
                owner_id=owner_id,
                project_id=project_id,
                filename=filename,
                mime_type=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                size_bytes=len(data),
                hash_sha256="f" * 64,
                storage_path=uuid.uuid4().hex,
                ingestion_status="ready",
            )
        )
        await db.commit()

    class _Stream:
        async def __aenter__(self) -> Any:
            async def gen() -> Any:
                yield data

            return gen()

        async def __aexit__(self, *args: Any) -> None:
            return None

    from app.agents import tools as agent_tools

    monkeypatch.setattr(agent_tools.storage, "stream_download", lambda *, storage_path: _Stream())


# --------------------------------------------------------------------------- #
# Grant set
# --------------------------------------------------------------------------- #


def test_tool_rides_the_redlining_grant_set() -> None:
    assert ADVERSARIAL_REVIEW_TOOL_NAME in COMMERCIAL_TOOL_NAMES
    tools = build_adversarial_review_tools(
        async_sessionmaker(),
        run_id=uuid.uuid4(),
        binding=_binding(uuid.uuid4(), uuid.uuid4()),
        gateway_factory=_StubGateway,
    )
    assert [t.__name__ for t in tools] == ["adversarial_review"]


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


async def test_happy_path_renders_severity_ordered_checklist_and_audits_counts_only(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, project_id = matter
    await _seed_docx(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="draft MSA.docx",
        paragraphs=["Liability is unlimited.", "Termination for convenience."],
        monkeypatch=monkeypatch,
    )
    gateway = _StubGateway(content=_findings_json())
    run_id = uuid.uuid4()

    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=run_id,
            gateway=gateway,
            model_alias="smart",
            document_name="draft MSA.docx",
            focus="liability",
        )
        await db.commit()

    assert "HOSTILE-READER FINDINGS" in out
    assert out.index("[HIGH") < out.index("[LOW")  # severity-ordered
    assert "OVERALL: Needs work" in out
    # The single gateway request carried the purpose + the document + the focus.
    assert len(gateway.requests) == 1
    req = gateway.requests[0]
    assert req.lq_ai_purpose == "adversarial_review"
    assert "Liability is unlimited." in req.messages[1].content
    assert "liability" in req.messages[1].content

    async with commit_factory() as db:
        rows = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.user_id == user_id, AuditLog.action == "review.adversarial"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    details = rows[0].details
    assert details["findings"] == 2 and details["high"] == 1 and details["low"] == 1
    # Counts only — no clause/finding text anywhere in the audit payload.
    assert "clause anchor" not in json.dumps(details)


# --------------------------------------------------------------------------- #
# Reject paths — never crash, nothing written
# --------------------------------------------------------------------------- #


async def test_unknown_document_is_fix_and_retry(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    gateway = _StubGateway(content=_findings_json())
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="Nope.docx",
            focus="",
        )
    assert "No document named" in out
    assert gateway.requests == []  # no spend on a missing document


async def test_gateway_failure_rejects_cleanly(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, project_id = matter
    await _seed_docx(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="d.docx",
        paragraphs=["Body."],
        monkeypatch=monkeypatch,
    )
    gateway = _StubGateway(error=RuntimeError("boom"))
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="d.docx",
            focus="",
        )
    assert "model service was unavailable" in out


async def test_malformed_json_rejects_with_bounded_reason(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, project_id = matter
    await _seed_docx(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="d.docx",
        paragraphs=["Body."],
        monkeypatch=monkeypatch,
    )
    gateway = _StubGateway(content="I think the contract is fine, no JSON for you")
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="d.docx",
            focus="",
        )
    assert "rejected" in out and "Try again" in out


async def test_length_truncated_output_is_a_diagnosable_reject(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, project_id = matter
    await _seed_docx(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="d.docx",
        paragraphs=["Body."],
        monkeypatch=monkeypatch,
    )
    gateway = _StubGateway(content='{"findings": [', finish_reason="length")
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="d.docx",
            focus="",
        )
    assert "too large" in out and "narrower focus" in out


async def test_overlong_focus_is_rejected_before_any_load(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    gateway = _StubGateway(content=_findings_json())
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="d.docx",
            focus="x" * 1_000,
        )
    assert "focus is too long" in out
    assert gateway.requests == []


async def test_textless_document_is_rejected_before_any_spend(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review fix (PR #272): an OOXML-valid docx with no extractable text (scanned/
    image-only) rejects BEFORE the gateway call — no spend, no false clearance."""
    user_id, project_id = matter
    await _seed_docx(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="scan.docx",
        paragraphs=[],  # no text runs
        monkeypatch=monkeypatch,
    )
    gateway = _StubGateway(content=_findings_json())
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="scan.docx",
            focus="",
        )
    assert "no extractable text" in out and "Nothing was reviewed" in out
    assert gateway.requests == []


async def test_focus_is_fenced_and_echoed_in_the_render(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review fix (PR #272): the system prompt fences focus as a topic steer that never
    suppresses findings, and a steered pass is VISIBLY steered in the render."""
    user_id, project_id = matter
    await _seed_docx(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="d.docx",
        paragraphs=["Body."],
        monkeypatch=monkeypatch,
    )
    gateway = _StubGateway(content=_findings_json(1))
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="d.docx",
            focus="liability and indemnity",
        )
        await db.commit()
    system = gateway.requests[0].messages[0].content
    assert "never suppresses findings" in system
    assert "FOCUS APPLIED" in out and "liability and indemnity" in out


async def test_oversize_document_is_truncated_with_honest_notice(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, project_id = matter
    # ~40 paragraphs of 2k chars ≈ 80k chars > the 60k cap.
    await _seed_docx(
        commit_factory,
        owner_id=user_id,
        project_id=project_id,
        filename="huge.docx",
        paragraphs=["y" * 2_000 for _ in range(40)],
        monkeypatch=monkeypatch,
    )
    gateway = _StubGateway(content=_findings_json(1))
    async with commit_factory() as db:
        out = await adv._adversarial_review(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=gateway,
            model_alias="smart",
            document_name="huge.docx",
            focus="",
        )
        await db.commit()
    # The prompt told the model, and the render tells the lead — no fake full coverage.
    assert "TRUNCATED" in gateway.requests[0].messages[1].content
    assert "coverage is PARTIAL" in out
