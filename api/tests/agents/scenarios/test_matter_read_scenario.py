"""C3c-1 live matter-memory read + revert — the agent recalls; a human reverts
(ADR-F044, provider-marked, CI-skipped).

Drives the production agent loop against a real model (DeepSeek on the dev stack) to
confirm the read surface works end to end:

* We seed a matter whose ledger has a SUPERSEDED draft cap + a live agreed cap + an
  undated party fact, a pinned correction, and a wiki, then ask the agent to recall what
  it knows now and what it believed at an earlier date.
* We confirm it reaches for the read tools (``search_matter_memory`` /
  ``matter_facts_as_of``), the run settles, and we capture the actual tool digests it
  would see (proving live-only search + the bi-temporal as-of).
* We then exercise the human-authenticated REST surface against the same app:
  ``GET /memory`` (composite) → ``POST /memory/wiki/revert`` (restore a chosen version,
  snapshotting current first) → ``GET /memory`` again (the reverted wiki + a new version).

Per ADR-F015 the model's craft (exactly which tool it picks) is a recorded finding, not a
gate; the hard assertions confirm the SYSTEM worked (the loop turned, settled, a read
tool was granted + dispatched; the REST read/revert round-trips correctly).

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c3c \\
    pytest -m provider tests/agents/scenarios/test_matter_read_scenario.py -s
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.matter_read_tools import _matter_facts_as_of, _search_matter_memory
from app.agents.tools import MatterBinding
from app.db.session import get_db
from app.main import app
from app.models.project import MatterMemoryEntry, Project
from app.models.user import User
from app.security import create_access_token
from app.skills import load_registry
from tests.agents.scenarios.harness import run_scenario, seed_commercial_matter
from tests.agents.scenarios.scenarios import Scenario

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_EVIDENCE_DIR = (
    Path(os.environ["UX_B1_EVIDENCE_DIR"])
    if os.environ.get("UX_B1_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c3c"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_SKILLS_DIR = os.environ.get("LQ_AI_SKILLS_DIR", "/skills")
_READ_TOOLS = {"search_matter_memory", "matter_facts_as_of"}

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2026, 3, 1, tzinfo=UTC)

_RECALL_PROMPT = (
    "Before reading any documents, recall what this matter already knows. First use "
    "search_matter_memory to look up the liability cap and which side we act for. Then use "
    "matter_facts_as_of to tell me what we believed the liability cap was on 2026-02-01. "
    "Summarise both findings briefly."
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_drifted_memory(
    factory: async_sessionmaker[AsyncSession], project_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """A superseded draft cap + a live agreed cap + an undated party fact + a pin + wiki."""
    async with factory() as db:
        proj = await db.get(Project, project_id)
        assert proj is not None
        proj.context_md = "Deal: Acme acquires Cirrus. Liability cap: 12 months' fees."
        db.add_all(
            [
                MatterMemoryEntry(
                    project_id=project_id,
                    user_id=user_id,
                    kind="fact",
                    body_md="Liability cap is 1 month of fees (from the draft).",
                    trust="normal",
                    author="agent",
                    fact_type="term",
                    source_citation="draft MSA §9",
                    valid_at=_T0,
                    invalid_at=_T1,  # superseded — live-only search must NOT surface it
                ),
                MatterMemoryEntry(
                    project_id=project_id,
                    user_id=user_id,
                    kind="fact",
                    body_md="Liability cap is 12 months' fees.",
                    trust="normal",
                    author="agent",
                    fact_type="term",
                    source_citation="Cirrus MSA §9",
                    valid_at=_T1,
                ),
                MatterMemoryEntry(
                    project_id=project_id,
                    user_id=user_id,
                    kind="fact",
                    body_md="We act for the buyer.",
                    trust="normal",
                    author="agent",
                    fact_type="party",
                ),
                MatterMemoryEntry(
                    project_id=project_id,
                    user_id=user_id,
                    kind="correction",
                    body_md="Counterparty counsel is Smith Crowell.",
                    trust="human-pinned",
                ),
            ]
        )
        await db.commit()


def _override_get_db(factory: async_sessionmaker[AsyncSession]):
    async def _override():
        async with factory() as session:
            yield session

    return _override


async def test_agent_reads_matter_memory_and_human_reverts_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = load_registry(Path(_SKILLS_DIR))
    seeded = await seed_commercial_matter(commit_factory)
    await _seed_drifted_memory(commit_factory, seeded.project_id, seeded.user_id)
    binding = MatterBinding(
        project_id=seeded.project_id,
        user_id=seeded.user_id,
        name="Read Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=seeded.practice_area_id,
    )
    evidence: dict[str, object] = {"model": _MODEL}
    try:
        # --- 1. Live: does the agent reach for the read tools? ---------------------
        scenario = Scenario(
            id="matter_read",
            title="Recall the matter's memory",
            note="Does the agent reach for search_matter_memory / matter_facts_as_of?",
            prompt=_RECALL_PROMPT,
            expect_tools=("search_matter_memory", "matter_facts_as_of"),
            step_bound=10,
        )
        receipt = await run_scenario(
            scenario, seeded, skill_registry=registry, max_steps=40, model_alias=_MODEL
        )
        read_called = sorted(_READ_TOOLS.intersection(receipt.tools_called))
        evidence["run"] = {
            "status": receipt.status,
            "tools_called": receipt.tools_called,
            "read_tools_called": read_called,
        }

        # Capture the actual digests the agent would see (deterministic, illustrative).
        async with commit_factory() as db:
            evidence["sample_search_output"] = await _search_matter_memory(
                db, binding, query="liability cap"
            )
            evidence["sample_as_of_2026_02_01"] = await _matter_facts_as_of(
                db, binding, as_of_date="2026-02-01"
            )
            evidence["sample_as_of_2026_04_01"] = await _matter_facts_as_of(
                db, binding, as_of_date="2026-04-01"
            )

        # --- 2. REST: GET → revert (chosen version) → GET (deterministic) ----------
        # Plant a clean wiki + a prior snapshot so the revert demo is independent of
        # whatever the agent did to the wiki during the run.
        async with commit_factory() as db:
            proj = await db.get(Project, seeded.project_id)
            assert proj is not None
            proj.context_md = "REVERT-DEMO: current wiki (v2)."
            db.add(
                MatterMemoryEntry(
                    project_id=seeded.project_id,
                    user_id=seeded.user_id,
                    kind="wiki_snapshot",
                    body_md="REVERT-DEMO: prior wiki (v1).",
                    trust="normal",
                )
            )
            user = await db.get(User, seeded.user_id)
            assert user is not None
            email = user.email
            await db.commit()

        token = create_access_token(seeded.user_id, email, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        base = f"/api/v1/matters/{seeded.project_id}/memory"
        app.dependency_overrides[get_db] = _override_get_db(commit_factory)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                get1 = await ac.get(base, headers=headers)
                composite = get1.json()
                snap_id = next(e["id"] for e in composite["log"] if e["kind"] == "wiki_snapshot")
                rev = await ac.post(
                    f"{base}/wiki/revert", json={"snapshot_id": snap_id}, headers=headers
                )
                get2 = await ac.get(base, headers=headers)
        finally:
            app.dependency_overrides.pop(get_db, None)

        evidence["api_get"] = {
            "status_code": get1.status_code,
            "wiki": composite["wiki"],
            "live_facts": [f["body_md"] for f in composite["facts"]],
            "corrections": [c["body_md"] for c in composite["corrections"]],
            "log_total": composite["log_total"],
        }
        evidence["api_revert"] = {"status_code": rev.status_code, "body": rev.json()}
        evidence["api_get_after_revert"] = {
            "status_code": get2.status_code,
            "wiki": get2.json()["wiki"],
        }

        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (_EVIDENCE_DIR / "live-matter-read-revert.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )

        # --- Hard assertions: the SYSTEM worked (craft is a finding, ADR-F015) -----
        assert receipt.status == "completed", receipt.error
        assert read_called, receipt.tools_called  # at least one read tool was dispatched
        # Live-only search surfaces the AGREED cap, never the superseded draft.
        assert "12 months" in str(evidence["sample_search_output"])
        assert "1 month" not in str(evidence["sample_search_output"])
        # As-of reconstructs history across the supersede boundary.
        assert "1 month" in str(evidence["sample_as_of_2026_02_01"])
        assert "12 months" in str(evidence["sample_as_of_2026_04_01"])
        # REST round-trip: revert restored the chosen version + snapshotted current.
        assert get1.status_code == 200 and rev.status_code == 200 and get2.status_code == 200
        assert rev.json()["wiki"]["content_md"] == "REVERT-DEMO: prior wiki (v1)."
        assert get2.json()["wiki"]["content_md"] == "REVERT-DEMO: prior wiki (v1)."
        assert get2.json()["wiki"]["version_count"] >= 2  # new snapshot of the pre-revert wiki
    finally:
        await seeded.cleanup()
