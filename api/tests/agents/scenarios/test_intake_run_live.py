"""INTAKE-3 live scenarios — the two named end-to-end cases (ADR-F086, plan § Slices).

The plan names two live checks for this slice:

* **spam → ``handled``, the matter closed** — noise must leave no clutter;
* **NDA → ``awaiting_human``** — a counterparty NDA must reach the lawyer, and if the
  agent drafted a reply the run settles ``awaiting_input`` on the STRUCTURAL HITL
  floor (``draft_email_reply`` is interrupt-gated whatever the area policy says).

Both drive the production path through the shared rig (landing handler → worker core
→ composition against the live gateway). Provider-marked; CI skips.

    docker compose run --rm -v "$PWD:/repo" -w /repo/api \\
      -e LQ_AI_GATEWAY_KEY=... api \\
      pytest -q -m provider tests/agents/scenarios/test_intake_run_live.py -s
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.agents.scenarios.intake_pack import (
    load_pack,
    outbound_drafts,
    run_fixture,
    seed_rig,
    teardown_rig,
)

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_MODEL_ALIAS = os.environ.get("LQ_AI_SCENARIO_MODEL", "smart")


async def test_marketing_email_is_filed_and_its_matter_closed(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    rig = await seed_rig(commit_factory)
    try:
        (fixture,) = load_pack(only=["06-vendor-marketing.json"])
        result = await run_fixture(rig, fixture, model_alias=_MODEL_ALIAS)
        drafts = await outbound_drafts(rig, result.thread_id)
    finally:
        await teardown_rig(rig)

    print(f"\nspam scenario: {result}")
    assert result.outcome == "dealt_with", result
    assert result.thread_status == "handled"
    assert result.project_archived
    # Nothing outbound on noise.
    assert drafts == []


async def test_counterparty_nda_reaches_the_lawyer(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    rig = await seed_rig(commit_factory)
    try:
        (fixture,) = load_pack(only=["01-nda-with-attachment.json"])
        result = await run_fixture(rig, fixture, model_alias=_MODEL_ALIAS)
        drafts = await outbound_drafts(rig, result.thread_id)
    finally:
        await teardown_rig(rig)

    print(f"\nNDA scenario: {result}")
    # Closing this away would be the unsafe answer.
    assert result.outcome == "needs_human", result
    assert result.thread_status == "awaiting_human"
    assert not result.project_archived
    if "draft_email_reply" in result.tools_called or drafts:
        # The structural floor: a drafted reply CANNOT execute without a human, so the
        # run settles awaiting_input on the interrupt rather than completing.
        assert result.run_status == "awaiting_input", result
