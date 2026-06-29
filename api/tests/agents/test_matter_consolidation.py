"""C3b-2 matter_consolidation tests (ADR-F043) — the gateway-routed consolidation/Lint.

Drives the consolidation tool through the real test DB with a STUBBED gateway (no live
model). Covers:

* the grant set (one tool; DISJOINT from the wiki / fact-ledger / ROPA / assessment /
  commercial grants — confinement),
* the egress contract: exactly ONE gateway call with the right purpose / anonymize /
  token cap, and the module makes no direct-provider call,
* 0 live facts ⇒ NO gateway call (a free lower bound on egress),
* the supersede-only apply: ``retire`` closes a window (no replacement), ``replace``
  inserts the consolidated fact and closes+links the priors; the wiki is snapshotted +
  rewritten,
* reject-not-write (all-or-nothing): an op naming a correction / unknown / duplicated id,
  a too-early ``valid_from``, a blank/oversize wiki, malformed JSON, an empty response,
  and a gateway transport failure — each leaves the matter untouched (and a pinned
  correction survives every path),
* the guard audit receipt carries counts/IDs only — never a fact/wiki body.
"""

from __future__ import annotations

import ast
import inspect
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.agents.matter_consolidation as consolidation_mod
from app.agents.assessment_tools import ASSESSMENT_TOOL_NAMES
from app.agents.commercial_tools import COMMERCIAL_TOOL_NAMES
from app.agents.matter_consolidation import (
    _CONSOLIDATION_MAX_TOKENS,
    MATTER_CONSOLIDATION_TOOL_NAMES,
    _consolidate_matter_memory,
    build_matter_consolidation_tools,
)
from app.agents.matter_conversation_tools import MATTER_CONVERSATION_TOOL_NAMES
from app.agents.matter_fact_tools import MATTER_FACT_TOOL_NAMES, live_facts
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.matter_read_tools import MATTER_READ_TOOL_NAMES
from app.agents.ropa_tools import ROPA_TOOL_NAMES
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.project import MatterMemoryEntry, Project
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2026, 3, 1, tzinfo=UTC)
_FUTURE = datetime(2099, 1, 1, tzinfo=UTC)  # a fact not yet in effect (valid_at > now)


# --------------------------------------------------------------------------- #
# Stub gateway — mirrors tests/test_easy_playbook_extractor.py::_StubGateway
# --------------------------------------------------------------------------- #


@dataclass
class _StubMessage:
    content: str


@dataclass
class _StubChoice:
    message: _StubMessage


@dataclass
class _StubResponse:
    choices: list[_StubChoice]


@dataclass
class _StubGateway:
    """One queued response per call. A dict is JSON-serialised; a str is verbatim
    (malformed-JSON tests); an Exception is raised (transport-failure tests)."""

    payloads: list[Any] = field(default_factory=list)
    calls_received: list[Any] = field(default_factory=list)

    async def chat_completion(self, request: Any) -> _StubResponse:
        self.calls_received.append(request)
        if not self.payloads:
            return _StubResponse(choices=[_StubChoice(message=_StubMessage(content=""))])
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        if isinstance(payload, str):
            return _StubResponse(choices=[_StubChoice(message=_StubMessage(content=payload))])
        return _StubResponse(
            choices=[_StubChoice(message=_StubMessage(content=json.dumps(payload)))]
        )


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_matter(
    factory: async_sessionmaker[AsyncSession], *, wiki: str = ""
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        user = User(
            email=f"mc-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Matter Consolidation User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Consolidation Matter",
            slug=f"cons-{uuid.uuid4().hex[:6]}",
            privileged=False,
            minimum_inference_tier=None,
            context_md=wiki or None,
        )
        db.add(project)
        await db.commit()
        return user.id, project.id


def _binding(user_id: uuid.UUID, project_id: uuid.UUID) -> MatterBinding:
    return MatterBinding(
        project_id=project_id,
        user_id=user_id,
        name="Consolidation Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


@pytest_asyncio.fixture
async def matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    user_id, project_id = await _seed_matter(commit_factory)
    try:
        yield user_id, project_id
    finally:
        async with commit_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
            await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def _seed_fact(
    factory: async_sessionmaker[AsyncSession],
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    body: str,
    fact_type: str,
    valid_at: datetime = _T0,
    source: str | None = None,
) -> uuid.UUID:
    async with factory() as db:
        f = MatterMemoryEntry(
            project_id=project_id,
            user_id=user_id,
            kind="fact",
            body_md=body,
            trust="normal",
            author="agent",
            fact_type=fact_type,
            source_citation=source,
            valid_at=valid_at,
        )
        db.add(f)
        await db.commit()
        return f.id


async def _seed_correction(
    factory: async_sessionmaker[AsyncSession],
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    body: str,
) -> uuid.UUID:
    async with factory() as db:
        c = MatterMemoryEntry(
            project_id=project_id,
            user_id=user_id,
            kind="correction",
            body_md=body,
            trust="human-pinned",
        )
        db.add(c)
        await db.commit()
        return c.id


async def _facts(db: AsyncSession, project_id: uuid.UUID) -> list[MatterMemoryEntry]:
    rows = await db.execute(
        select(MatterMemoryEntry)
        .where(MatterMemoryEntry.project_id == project_id, MatterMemoryEntry.kind == "fact")
        .order_by(MatterMemoryEntry.created_at, MatterMemoryEntry.id)
    )
    return list(rows.scalars().all())


async def _wiki(db: AsyncSession, project_id: uuid.UUID) -> str | None:
    proj = await db.get(Project, project_id)
    assert proj is not None
    return proj.context_md


def _retire(fact_id: uuid.UUID, reason: str = "stale") -> dict[str, Any]:
    return {"op": "retire", "fact_id": str(fact_id), "reason": reason}


def _replace(
    supersedes: list[uuid.UUID],
    *,
    fact: str,
    fact_type: str,
    reason: str = "merge duplicates",
    source: str | None = None,
    valid_from: str | None = None,
) -> dict[str, Any]:
    op: dict[str, Any] = {
        "op": "replace",
        "supersedes": [str(s) for s in supersedes],
        "fact": fact,
        "fact_type": fact_type,
        "reason": reason,
    }
    if source is not None:
        op["source"] = source
    if valid_from is not None:
        op["valid_from"] = valid_from
    return op


def _result(
    operations: list[dict[str, Any]], new_wiki: str, lint_notes: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {"operations": operations, "new_wiki": new_wiki}
    if lint_notes is not None:
        out["lint_notes"] = lint_notes
    return out


async def _run(
    factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    stub: _StubGateway,
) -> str:
    """Call the impl directly (bypasses the guard, like the C3b-1 unit tests)."""
    async with factory() as db:
        out = await _consolidate_matter_memory(
            db,
            _binding(user_id, project_id),
            run_id=uuid.uuid4(),
            gateway=stub,  # type: ignore[arg-type]  # duck-typed stub
            model_alias="test-model",
        )
        await db.commit()
    return out


# --------------------------------------------------------------------------- #
# Grant set + confinement
# --------------------------------------------------------------------------- #


def test_build_grants_exactly_one_tool() -> None:
    tools = build_matter_consolidation_tools(
        async_sessionmaker(), run_id=uuid.uuid4(), binding=_binding(uuid.uuid4(), uuid.uuid4())
    )
    assert [t.__name__ for t in tools] == ["consolidate_matter_memory"]
    assert sorted(MATTER_CONSOLIDATION_TOOL_NAMES) == ["consolidate_matter_memory"]


def test_grant_set_disjoint_from_other_grants() -> None:
    """Confinement: the consolidation tool shares no tool name with the wiki / fact /
    ROPA / assessment / commercial grants."""
    assert MATTER_CONSOLIDATION_TOOL_NAMES.isdisjoint(MATTER_MEMORY_TOOL_NAMES)
    assert MATTER_CONSOLIDATION_TOOL_NAMES.isdisjoint(MATTER_FACT_TOOL_NAMES)
    assert MATTER_CONSOLIDATION_TOOL_NAMES.isdisjoint(MATTER_READ_TOOL_NAMES)
    assert MATTER_CONSOLIDATION_TOOL_NAMES.isdisjoint(MATTER_CONVERSATION_TOOL_NAMES)
    assert MATTER_CONSOLIDATION_TOOL_NAMES.isdisjoint(ROPA_TOOL_NAMES)
    assert MATTER_CONSOLIDATION_TOOL_NAMES.isdisjoint(ASSESSMENT_TOOL_NAMES)
    assert MATTER_CONSOLIDATION_TOOL_NAMES.isdisjoint(COMMERCIAL_TOOL_NAMES)


def test_module_has_no_direct_provider_egress() -> None:
    """ADR-F010: the only model access is the injected gateway — no provider SDK and
    no direct HTTP client imported in the consolidation path. Parses the actual
    imports (robust to the docstring, which legitimately *names* api.openai.com)."""
    tree = ast.parse(inspect.getsource(consolidation_mod))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    roots = {m.split(".")[0] for m in modules}
    # No provider SDK, no raw HTTP client — the only egress is the injected gateway.
    assert {"openai", "anthropic", "httpx", "requests", "urllib", "aiohttp"}.isdisjoint(roots)
    # Positive control: it routes through the gateway client.
    assert "app.clients.gateway" in modules


# --------------------------------------------------------------------------- #
# Egress contract
# --------------------------------------------------------------------------- #


async def test_no_live_facts_skips_gateway_call(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    stub = _StubGateway(payloads=[_result([], "unused")])
    out = await _run(commit_factory, user_id, project_id, stub)
    assert stub.calls_received == []  # no facts ⇒ no egress
    assert "nothing to consolidate" in out.lower()


async def test_gateway_request_carries_purpose_anonymize_and_token_cap(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_fact(
        commit_factory, project_id, user_id, body="We act for the buyer.", fact_type="party"
    )
    correction = "We are the BUYER, not the seller."
    await _seed_correction(commit_factory, project_id, user_id, body=correction)

    stub = _StubGateway(payloads=[_result([], "Parties: buyer = us.")])
    await _run(commit_factory, user_id, project_id, stub)

    assert len(stub.calls_received) == 1
    req = stub.calls_received[0]
    assert req.lq_ai_purpose == "consolidate_matter_memory"
    assert req.anonymize is False
    assert req.max_tokens == _CONSOLIDATION_MAX_TOKENS
    assert req.model == "test-model"
    # The pinned correction is injected into the prompt as read-only ground truth.
    user_msg = next(m.content for m in req.messages if m.role == "user")
    assert correction in user_msg


# --------------------------------------------------------------------------- #
# Supersede-only apply + wiki rewrite (the happy path)
# --------------------------------------------------------------------------- #


async def test_consolidation_supersedes_and_rewrites_wiki(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, project_id = await _seed_matter(commit_factory, wiki="old wiki body")
    try:
        f1 = await _seed_fact(
            commit_factory, project_id, user_id, body="We act for the buyer.", fact_type="party"
        )
        f2 = await _seed_fact(
            commit_factory, project_id, user_id, body="Acting for the buyer.", fact_type="party"
        )
        f3 = await _seed_fact(
            commit_factory, project_id, user_id, body="Cap is 1 month (draft).", fact_type="term"
        )

        stub = _StubGateway(
            payloads=[
                _result(
                    [
                        _replace(
                            [f1, f2],
                            fact="We act for the buyer (Northwind Trading Ltd).",
                            fact_type="party",
                            source="matter brief",
                        ),
                        _retire(f3, reason="superseded by the agreed cap"),
                    ],
                    "Parties: buyer = Northwind. Cap: under negotiation.",
                    lint_notes="merged 2 duplicate party facts; retired the stale draft cap",
                )
            ]
        )
        out = await _run(commit_factory, user_id, project_id, stub)
        assert "merged 2 fact(s) into 1" in out
        assert "retired 1 stale fact(s)" in out
        assert "rewrote the wiki" in out

        async with commit_factory() as db:
            facts = await _facts(db, project_id)
            by_id = {f.id: f for f in facts}
            # The new consolidated fact is live, tool-fixed provenance.
            new_facts = [f for f in facts if f.id not in {f1, f2, f3}]
            assert len(new_facts) == 1
            new = new_facts[0]
            assert new.body_md == "We act for the buyer (Northwind Trading Ltd)."
            assert new.author == "agent" and new.trust == "normal"
            assert new.fact_type == "party" and new.source_citation == "matter brief"
            assert new.invalid_at is None and new.superseded_by is None
            # f1, f2 closed + forward-linked to the new fact.
            for old in (f1, f2):
                assert by_id[old].invalid_at is not None
                assert by_id[old].superseded_by == new.id
            # f3 retired with NO replacement.
            assert by_id[f3].invalid_at is not None
            assert by_id[f3].superseded_by is None
            # Wiki rewritten + prior snapshotted.
            assert (
                await _wiki(db, project_id) == "Parties: buyer = Northwind. Cap: under negotiation."
            )
            snaps = (
                (
                    await db.execute(
                        select(MatterMemoryEntry).where(
                            MatterMemoryEntry.project_id == project_id,
                            MatterMemoryEntry.kind == "wiki_snapshot",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert [s.body_md for s in snaps] == ["old wiki body"]
            # Only the new fact remains live.
            assert [f.id for f in await live_facts(db, project_id)] == [new.id]
    finally:
        async with commit_factory() as db:
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def test_noop_result_unchanged_wiki_writes_nothing(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """operations=[] + a new_wiki identical to the current one ⇒ no supersede, no
    snapshot, a benign receipt."""
    user_id, project_id = await _seed_matter(commit_factory, wiki="current one-pager")
    try:
        await _seed_fact(commit_factory, project_id, user_id, body="One fact.", fact_type="fact")
        stub = _StubGateway(payloads=[_result([], "current one-pager")])
        out = await _run(commit_factory, user_id, project_id, stub)
        assert "no changes were needed" in out.lower()
        async with commit_factory() as db:
            assert await _wiki(db, project_id) == "current one-pager"
            snaps = (
                (
                    await db.execute(
                        select(MatterMemoryEntry).where(
                            MatterMemoryEntry.project_id == project_id,
                            MatterMemoryEntry.kind == "wiki_snapshot",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert snaps == []
            facts = await _facts(db, project_id)
            assert len(facts) == 1 and facts[0].invalid_at is None
    finally:
        async with commit_factory() as db:
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


# --------------------------------------------------------------------------- #
# Reject-not-write (all-or-nothing); a pinned correction survives every path
# --------------------------------------------------------------------------- #


async def test_op_targeting_a_correction_is_rejected_no_writes(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The single most important B2 guarantee: a consolidation op can never reach a
    human-pinned correction (it is not a live kind='fact' row)."""
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="A live fact.", fact_type="fact"
    )
    pin = await _seed_correction(commit_factory, project_id, user_id, body="We are the BUYER.")

    stub = _StubGateway(payloads=[_result([_retire(pin)], "rewritten")])
    out = await _run(commit_factory, user_id, project_id, stub)
    assert "not a live fact" in out.lower()

    async with commit_factory() as db:
        survived = await db.get(MatterMemoryEntry, pin)
        assert survived is not None
        assert survived.body_md == "We are the BUYER." and survived.trust == "human-pinned"
        assert survived.invalid_at is None and survived.superseded_by is None
        # The live fact and the wiki are untouched (all-or-nothing).
        assert (await db.get(MatterMemoryEntry, f1)).invalid_at is None  # type: ignore[union-attr]
        assert await _wiki(db, project_id) is None


async def test_op_referencing_unknown_fact_is_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="A live fact.", fact_type="fact"
    )
    stub = _StubGateway(payloads=[_result([_retire(uuid.uuid4())], "rewritten")])
    out = await _run(commit_factory, user_id, project_id, stub)
    assert "not a live fact" in out.lower()
    async with commit_factory() as db:
        assert (await db.get(MatterMemoryEntry, f1)).invalid_at is None  # type: ignore[union-attr]


async def test_duplicate_fact_reference_is_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="A live fact.", fact_type="fact"
    )
    # The same id in two ops — no double-supersede.
    stub = _StubGateway(
        payloads=[_result([_retire(f1), _replace([f1], fact="x", fact_type="fact")], "rewritten")]
    )
    out = await _run(commit_factory, user_id, project_id, stub)
    assert "more than one operation" in out.lower()
    async with commit_factory() as db:
        assert (await db.get(MatterMemoryEntry, f1)).invalid_at is None  # type: ignore[union-attr]
        assert len(await _facts(db, project_id)) == 1  # no new fact written


async def test_replace_valid_from_before_prior_is_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="Cap agreed.", fact_type="term", valid_at=_T1
    )
    stub = _StubGateway(
        payloads=[
            _result(
                [_replace([f1], fact="Cap 12 months.", fact_type="term", valid_from="2026-01-01")],
                "rewritten",
            )
        ]
    )
    out = await _run(commit_factory, user_id, project_id, stub)
    assert "later than" in out.lower()
    async with commit_factory() as db:
        assert (await db.get(MatterMemoryEntry, f1)).invalid_at is None  # type: ignore[union-attr]
        assert len(await _facts(db, project_id)) == 1


async def test_retire_of_future_dated_fact_is_rejected_not_crash(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """A retire closes the window at now; a future-dated fact (valid_at > now) would make
    invalid_at <= valid_at and violate the bi-temporal CHECK. The validation pass must
    reject-and-retry (the no-crash contract), never let it reach a flush IntegrityError."""
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="Launch date.", fact_type="date", valid_at=_FUTURE
    )
    stub = _StubGateway(payloads=[_result([_retire(f1)], "rewritten")])
    out = await _run(commit_factory, user_id, project_id, stub)  # must NOT raise
    assert "not yet in effect" in out.lower()
    async with commit_factory() as db:
        survived = await db.get(MatterMemoryEntry, f1)
        assert survived is not None and survived.invalid_at is None  # untouched


@pytest.mark.parametrize(
    "new_wiki",
    ["", "   ", "x" * 16_001],  # blank / whitespace / over the 16 KiB wiki budget
)
async def test_blank_or_oversize_wiki_is_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
    new_wiki: str,
) -> None:
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="A live fact.", fact_type="fact"
    )
    stub = _StubGateway(payloads=[_result([_retire(f1)], new_wiki)])
    out = await _run(commit_factory, user_id, project_id, stub)
    assert "rejected" in out.lower()
    async with commit_factory() as db:
        assert (await db.get(MatterMemoryEntry, f1)).invalid_at is None  # type: ignore[union-attr]
        assert await _wiki(db, project_id) is None


async def test_malformed_json_is_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="A live fact.", fact_type="fact"
    )
    stub = _StubGateway(payloads=["not valid json {[}"])
    out = await _run(commit_factory, user_id, project_id, stub)
    assert "rejected" in out.lower() and "nothing was changed" in out.lower()
    async with commit_factory() as db:
        assert (await db.get(MatterMemoryEntry, f1)).invalid_at is None  # type: ignore[union-attr]


async def test_empty_response_is_rejected(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    await _seed_fact(commit_factory, project_id, user_id, body="A live fact.", fact_type="fact")
    stub = _StubGateway(payloads=[""])  # blank content
    out = await _run(commit_factory, user_id, project_id, stub)
    assert "no usable output" in out.lower()


async def test_gateway_failure_returns_reject_not_crash(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    f1 = await _seed_fact(
        commit_factory, project_id, user_id, body="A live fact.", fact_type="fact"
    )
    stub = _StubGateway(payloads=[ConnectionError("gateway down")])
    out = await _run(commit_factory, user_id, project_id, stub)  # must NOT raise
    assert "unavailable" in out.lower() and "nothing was changed" in out.lower()
    async with commit_factory() as db:
        assert (await db.get(MatterMemoryEntry, f1)).invalid_at is None  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Guard audit receipt — counts/IDs only (drive the guarded path)
# --------------------------------------------------------------------------- #


async def test_guard_audit_carries_no_body(
    commit_factory: async_sessionmaker[AsyncSession],
    matter: tuple[uuid.UUID, uuid.UUID],
) -> None:
    user_id, project_id = matter
    marker = "GIRAFFE-MARKER-do-not-leak"
    await _seed_fact(commit_factory, project_id, user_id, body="A live fact.", fact_type="fact")
    async with commit_factory() as db:
        thread = AgentThread(user_id=user_id, project_id=project_id, title="mc guard")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user_id,
            thread_id=thread.id,
            project_id=project_id,
            status="running",
            prompt="consolidate",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    stub = _StubGateway(payloads=[_result([], f"Wiki mentioning {marker}.", lint_notes=marker)])
    [consolidate_matter_memory] = build_matter_consolidation_tools(
        commit_factory,
        run_id=run_id,
        binding=_binding(user_id, project_id),
        gateway_factory=lambda: stub,  # type: ignore[arg-type,return-value]
    )
    out = await consolidate_matter_memory()
    assert "Consolidated this matter's memory" in out

    async with commit_factory() as db:
        rows = (
            (await db.execute(select(AuditLog).where(AuditLog.user_id == user_id))).scalars().all()
        )
    assert [r.action for r in rows] == ["agent_run.tool_call"]
    details = str(rows[0].details)
    assert "consolidate_matter_memory" in details
    assert "success" in details
    assert marker not in details  # neither the wiki body nor lint notes reach the audit row
