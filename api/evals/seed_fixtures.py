"""Idempotent seeder for the F0-S9 qualification fixtures.

Writes the two eval matters (``evals.fixtures``) straight into the
target database as already-ingested documents — files, documents, and
paragraph chunks — bypassing the ingest pipeline so the fixture text is
byte-deterministic across re-seeds (``content_tsv`` is a generated
column; FTS just works). All ids are uuid5 of the fixture name, so
re-running converges instead of duplicating; existing rows are replaced
to pick up fixture-text changes.

Run inside the api image against the dev stack:

    docker run --rm --network lq-ai_default \\
      -v $PWD/api:/work -w /work -e PYTHONPATH=/work \\
      -e DATABASE_URL=postgresql+asyncpg://<user>:<pw>@postgres:5432/<db> \\
      --entrypoint python lq-ai-api:latest -m evals.seed_fixtures

The owner is looked up by email (``LQAI_EVAL_USER_EMAIL``, default
``admin@lq.ai``) — the harness authenticates as the same user.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.document import Document, DocumentChunk
from app.models.file import File
from app.models.project import Project
from app.models.user import User
from evals.fixtures import ALL_MATTERS, DocFixture, MatterFixture

_NS = uuid.UUID("3f3c5f5e-9d51-4c2a-8f60-46a52d5b9e01")  # fixed namespace, fork-local


def _uid(kind: str, name: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"s9-eval:{kind}:{name}")


def _chunks(content: str) -> list[tuple[int, str, int, int]]:
    """Paragraph chunks as (index, text, char_start, char_end)."""
    out: list[tuple[int, str, int, int]] = []
    cursor = 0
    index = 0
    for para in content.split("\n\n"):
        start = content.index(para, cursor)
        end = start + len(para)
        cursor = end
        if para.strip():
            out.append((index, para, start, end))
            index += 1
    return out


async def _seed_matter(session: object, owner_id: uuid.UUID, matter: MatterFixture) -> None:
    db = session  # typed loosely; this is a script, not app code
    project_id = _uid("matter", matter.name)

    existing = await db.get(Project, project_id)  # type: ignore[attr-defined]
    if existing is None:
        db.add(  # type: ignore[attr-defined]
            Project(
                id=project_id,
                owner_id=owner_id,
                name=matter.name,
                slug=matter.slug,
                description=matter.description,
            )
        )
    else:
        existing.owner_id = owner_id
        existing.name = matter.name
        existing.archived_at = None

    for doc in matter.documents:
        await _seed_document(db, owner_id=owner_id, project_id=project_id, doc=doc)


async def _seed_document(
    db: object, *, owner_id: uuid.UUID, project_id: uuid.UUID, doc: DocFixture
) -> None:
    file_id = _uid("file", doc.filename)
    document_id = _uid("document", doc.filename)
    body = doc.content.encode()

    # Replace, never accrete: chunk text must match fixtures.py exactly.
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))  # type: ignore[attr-defined]
    await db.execute(delete(Document).where(Document.id == document_id))  # type: ignore[attr-defined]
    await db.execute(delete(File).where(File.id == file_id))  # type: ignore[attr-defined]

    db.add(  # type: ignore[attr-defined]
        File(
            id=file_id,
            owner_id=owner_id,
            project_id=project_id,  # upload-time membership column (F0-S4 union)
            filename=doc.filename,
            mime_type="text/plain",
            size_bytes=len(body),
            hash_sha256=hashlib.sha256(body).hexdigest(),
            storage_path=f"s9-eval/{doc.filename}",  # never fetched; reads use normalized_content
            ingestion_status="ready",
        )
    )
    # Explicit flush per dependency level: the ORM models don't declare
    # the FK edges these tables enforce, so the unit-of-work's insert
    # ordering is undefined without it (documents-before-files violated
    # fk_documents_file_id on first run).
    await db.flush()  # type: ignore[attr-defined]
    db.add(  # type: ignore[attr-defined]
        Document(
            id=document_id,
            file_id=file_id,
            parser="s9-eval-seed",
            page_count=1,
            character_count=len(doc.content),
            normalized_content=doc.content,
            ingest_status="ok",
            processed_at=datetime.now(UTC),
        )
    )
    await db.flush()  # type: ignore[attr-defined]
    for index, text, start, end in _chunks(doc.content):
        db.add(  # type: ignore[attr-defined]
            DocumentChunk(
                id=_uid("chunk", f"{doc.filename}:{index}"),
                document_id=document_id,
                chunk_index=index,
                content=text,
                page_start=1,
                page_end=1,
                char_offset_start=start,
                char_offset_end=end,
            )
        )


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    owner_email = os.environ.get("LQAI_EVAL_USER_EMAIL", "admin@lq.ai")

    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            owner_id = (
                await db.execute(select(User.id).where(User.email == owner_email))
            ).scalar_one_or_none()
            if owner_id is None:
                raise SystemExit(f"no user with email {owner_email!r} — create the admin first")
            for matter in ALL_MATTERS:
                await _seed_matter(db, owner_id, matter)
            await db.commit()
        for matter in ALL_MATTERS:
            print(
                f"seeded: {matter.name} ({_uid('matter', matter.name)}) — {len(matter.documents)} doc(s)"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
