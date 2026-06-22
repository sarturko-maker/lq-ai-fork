"""Shared scaffolding for the live Commercial-redline scenarios — C4/C8.

Both the single canonical evidence run (``test_commercial_redline_scenario.py``)
and the multi-repetition surgical-craft **eval** (``test_commercial_redline_eval.py``)
need the same machinery: seed a Commercial matter with a real vendor ``.docx`` in
object storage (so ``apply_redline`` fetches the actual bytes), capture the
redlined output the agent produced, and judge its *craft* with an adversarial
critic. Kept here so neither test duplicates it — and so the seeded rows are torn
down via a **real** cleanup (the C4 ``_noop_cleanup`` leak, fixed in C8).

Provider-only helpers (they drive the live gateway); imported by provider-marked
tests, never run in CI.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import storage
from app.agents.factory import build_gateway_chat_model, build_gateway_http_client
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.audit import AuditLog
from app.models.document import Document, DocumentChunk
from app.models.file import File
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.user import User
from app.pipeline.readers._base import OOXML_DOCX_MIME
from app.security import hash_password
from tests.agents.scenarios.harness import SeededMatter


@dataclass(frozen=True)
class RedlineScenarioDoc:
    """One vendor-favoured contract the eval/scenario redlines.

    ``boilerplate_bare`` lists recognisable phrases a SURGICAL redline must leave
    untouched (verb phrases like "shall indemnify, defend and hold harmless") —
    used by the eval to score structure-preservation deterministically, alongside
    the model judge.
    """

    id: str
    filename: str
    build_docx: Callable[[], bytes]
    normalized_text: Callable[[], str]
    prompt: str
    boilerplate_bare: tuple[str, ...] = ()
    # C9: "moderate" (short-clause) vs "complex" (dense, multi-limb clauses where
    # the surgical "leave language alone" test bites). Recorded in the manifest so
    # the evidence foregrounds the hard cases the maintainer cares about.
    complexity: str = "moderate"


async def seed_doc_matter(
    factory: async_sessionmaker[AsyncSession], doc: RedlineScenarioDoc
) -> SeededMatter:
    """User + Commercial matter + the real ``.docx`` (File+Document+chunks+storage).

    Returns a ``SeededMatter`` whose ``cleanup`` deletes every seeded row by user
    (File→Document→chunk cascade drops with the File) — call it in a ``finally``.
    """
    docx_bytes = doc.build_docx()
    text = doc.normalized_text()
    storage_key = str(uuid.uuid4())
    await storage.upload_bytes(
        storage_path=storage_key, body=docx_bytes, content_type=OOXML_DOCX_MIME
    )

    async with factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        user = User(
            email=f"redline-eval-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Redline Eval User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name=f"{doc.id} — redline eval",
            slug=f"commercial-{uuid.uuid4().hex[:6]}",
            privileged=True,
            minimum_inference_tier=4,
            practice_area_id=area_id,
        )
        db.add(project)
        await db.flush()
        file = File(
            owner_id=user.id,
            project_id=project.id,
            filename=doc.filename,
            mime_type=OOXML_DOCX_MIME,
            size_bytes=len(docx_bytes),
            hash_sha256=uuid.uuid4().hex,
            storage_path=storage_key,
            ingestion_status="ready",
        )
        db.add(file)
        await db.flush()
        document = Document(
            file_id=file.id,
            parser="redline-eval-fixture",
            page_count=1,
            character_count=len(text),
            normalized_content=text,
        )
        db.add(document)
        await db.flush()
        offset = 0
        for idx, para in enumerate(text.split("\n")):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=idx,
                    content=para,
                    page_start=1,
                    page_end=1,
                    char_offset_start=offset,
                    char_offset_end=offset + len(para),
                )
            )
            offset += len(para) + 1
        await db.commit()
        user_id, project_id = user.id, project.id

    async def cleanup() -> None:
        async with factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            run_ids = (
                (await db.execute(select(AgentRun.id).where(AgentRun.user_id == user_id)))
                .scalars()
                .all()
            )
            if run_ids:
                await db.execute(delete(AgentRunStep).where(AgentRunStep.run_id.in_(run_ids)))
            await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
            await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
            await db.execute(delete(File).where(File.owner_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()

    return SeededMatter(
        factory=factory,
        user_id=user_id,
        project_id=project_id,
        practice_area_id=area_id,
        cleanup=cleanup,
    )


async def capture_redline(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, project_id: uuid.UUID
) -> tuple[bytes, str] | None:
    """Download the redlined output File the agent produced (most recent), scoped to
    the matter (owner + project) per the ADR-F035 matter-scope convention."""
    async with factory() as db:
        row = (
            await db.execute(
                select(File.storage_path, File.filename)
                .where(
                    File.owner_id == user_id,
                    File.project_id == project_id,
                    File.filename.like("%(redlined)%"),
                )
                .order_by(File.created_at.desc())
            )
        ).first()
    if row is None:
        return None
    chunks: list[bytes] = []
    async with storage.stream_download(storage_path=row.storage_path) as stream:
        async for chunk in stream:
            chunks.append(chunk)
    return b"".join(chunks), row.filename


@dataclass(frozen=True)
class CraftVerdict:
    """Parsed craft judgement — the unit the eval aggregates into a rate."""

    verdict: str  # STRONG | ADEQUATE | WEAK | UNKNOWN
    surgical: bool  # the judge's structure-preservation call
    text: str  # the full critic response (for evidence)

    @property
    def is_surgical_pass(self) -> bool:
        """A run counts toward the surgical-craft rate when the judge calls it
        surgical AND at least adequate (the maintainer's bar: good craft, reliably)."""
        return self.surgical and self.verdict in {"STRONG", "ADEQUATE"}


_VERDICT_RE = re.compile(r"VERDICT:\s*(STRONG|ADEQUATE|WEAK)", re.IGNORECASE)
_SURGICAL_RE = re.compile(r"SURGICAL:\s*(yes|no|true|false)", re.IGNORECASE)


async def craft_judge(
    model_alias: str, original_text: str, redline_view: str, accepted_text: str
) -> CraftVerdict:
    """Adversarial redline-CRAFT critic (sharpened §5.1 rubric).

    Asks for two machine-readable header lines (``VERDICT:`` / ``SURGICAL:``) then
    bullets, so the eval can compute a surgical-craft rate while keeping the prose
    for evidence. Per ADR-F015 this is a finding, never a runtime gate.
    """
    http = build_gateway_http_client()
    try:
        model = build_gateway_chat_model(
            model_alias=model_alias,
            purpose="commercial_redline_craft_judge",
            http_async_client=http,
            project_minimum_inference_tier=None,
            privileged=False,
        )
        sys = SystemMessage(
            content=(
                "You are a senior commercial lawyer grading a junior's tracked-changes "
                "redline of a vendor-favoured SaaS MSA, acting for the CUSTOMER. Judge CRAFT, "
                "discounting model intelligence:\n"
                "- SURGICAL: are changes NARROW edits (a party swap, a narrowed trigger, an "
                "inserted carve-out), with recognisable boilerplate (e.g. 'shall indemnify, "
                "defend and hold harmless', 'shall not exceed') left BARE — NOT whole clauses "
                "struck and retyped?\n"
                "- BALANCE: does it weave protection via the right mechanism (carve-outs from the "
                "cap, deemed-direct losses, super-cap, mutual indemnity, IP licence-back) rather "
                "than just bumping numbers?\n"
                "- COHERENCE / over- or under-protection.\n\n"
                "Respond EXACTLY in this shape:\n"
                "VERDICT: STRONG|ADEQUATE|WEAK\n"
                "SURGICAL: yes|no\n"
                "then 3-6 terse bullets. SURGICAL is 'no' if ANY material clause was "
                "struck-and-retyped wholesale instead of edited narrowly."
            )
        )
        human = HumanMessage(
            content=(
                "ORIGINAL:\n" + original_text[:8000] + "\n\n"
                "THE REDLINE ([-deleted-][+inserted+]):\n" + redline_view[:16000] + "\n\n"
                "ACCEPTED RESULT:\n" + accepted_text[:10000]
            )
        )
        resp = await model.ainvoke([sys, human])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    finally:
        await http.aclose()

    vm = _VERDICT_RE.search(text)
    sm = _SURGICAL_RE.search(text)
    verdict = vm.group(1).upper() if vm else "UNKNOWN"
    surgical = bool(sm) and sm.group(1).lower() in {"yes", "true"}
    return CraftVerdict(verdict=verdict, surgical=surgical, text=text)
