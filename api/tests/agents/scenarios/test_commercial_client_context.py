"""C-CLIENT — does the injected company/client tier change the agent's run?

Provider-marked (CI skips — no gateway key). Run against the live dev stack:

    DATABASE_URL=postgresql+asyncpg://lq_ai:lq_ai@localhost:5432/lq_ai \\
    LQ_AI_GATEWAY_KEY=<dev key> \\
    pytest -m provider tests/agents/scenarios/test_commercial_client_context.py -s

The proof is an **A/B**: the SAME Commercial matter and the SAME prompt, run
with the operator's Organization Profile (the synthetic Zendesk house context,
ADR-F030) **OFF then ON**. With it ON the agent should act FOR Zendesk —
recognise which side we are on, hold the house cap position, escalate an
uncapped demand to the GC, and (when buying) require a DPA — none of which is in
the matter document. Per ADR-F015 this is NOT a model pass/fail gate: the
house-context "signals" are recorded as findings in the committed report; the
hard assertions only confirm the RIG turned the model on both legs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.agents.org_profile_fixtures import clear_org_profile, set_org_profile
from tests.agents.scenarios.harness import Receipt, run_scenario, seed_multi_doc_matter
from tests.agents.scenarios.zendesk_client import (
    CUSTOMER_PROCUREMENT,
    SUPPLIER_UNCAPPED,
    ZENDESK_PROFILE_MD,
    build_zendesk_msa,
)

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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c-client"
)

_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

# House-derived signals — phrasings that can only come from the injected house
# context, not from the matter document (which has no GC, no escalation rule, no
# procurement posture). Reported as findings, never hard-asserted (ADR-F015).
_SUPPLIER_HOUSE_SIGNALS = (
    "escalat",  # escalate / escalation
    "general counsel",
    "hard no",
    "2x annual",
    "super-cap",
    "supercap",
)
_PROCUREMENT_HOUSE_SIGNALS = (
    "dpa",
    "data processing addendum",
    "processor",
    "data processing terms",
    "vendor",
)


def _signals_present(answer: str | None, signals: tuple[str, ...]) -> list[str]:
    lower = (answer or "").lower()
    return [s for s in signals if s in lower]


def _leg(label: str, receipt: Receipt, signals: tuple[str, ...]) -> dict[str, object]:
    found = _signals_present(receipt.final_answer, signals)
    return {
        "leg": label,
        **receipt.to_dict(),
        "house_signals_found": found,
        "house_signal_present": bool(found),
    }


def _write_report(legs: list[dict[str, object]]) -> None:
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (_EVIDENCE_DIR / "zendesk-org-profile.md").write_text(ZENDESK_PROFILE_MD, encoding="utf-8")
    (_EVIDENCE_DIR / "ab-report.json").write_text(
        json.dumps({"legs": legs}, indent=2), encoding="utf-8"
    )

    lines = [
        "# C-CLIENT live verification — injected client/house context (DeepSeek)",
        "",
        "Slice **C-CLIENT** (ADR-F030): the operator's Organization Profile (the company/",
        "client memory tier) is injected read-only at the composition seam. Proof is an A/B —",
        "the same Commercial matter and prompt, profile **OFF then ON** — using a synthetic",
        "Zendesk house context (`zendesk-org-profile.md`). Per ADR-F015 the house-context",
        "signals are findings, not a pass/fail gate.",
        "",
    ]
    for leg in legs:
        lines += [
            f"## {leg['leg']} — `{leg['id']}` · {leg['status']} · {leg['step_count']} steps",
            "",
            f"**Prompt:** {leg['prompt']}",
            "",
            f"**Tools:** {leg['tools_called']}  ·  "
            f"**House signals:** {leg['house_signals_found'] or 'none'}",
            "",
            "**Answer:**",
            "",
            "> " + (str(leg["final_answer_excerpt"]).replace("\n", "\n> ")),
            "",
        ]
    (_EVIDENCE_DIR / "ab-report.md").write_text("\n".join(lines), encoding="utf-8")


async def test_client_context_ab(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[build_zendesk_msa()],
        matter_name="Northwind — Master Services Agreement",
    )
    legs: list[dict[str, object]] = []
    try:
        # Leg 1: profile OFF (default no-row state) — the baseline.
        await clear_org_profile(commit_factory)
        off = await run_scenario(SUPPLIER_UNCAPPED, seeded)
        legs.append(_leg("supplier · profile OFF", off, _SUPPLIER_HOUSE_SIGNALS))

        # Leg 2: profile ON — same matter, same prompt.
        await set_org_profile(commit_factory, ZENDESK_PROFILE_MD)
        on = await run_scenario(SUPPLIER_UNCAPPED, seeded)
        legs.append(_leg("supplier · profile ON", on, _SUPPLIER_HOUSE_SIGNALS))

        # Leg 3: profile ON, the procurement flip (ON only — a finding).
        proc = await run_scenario(CUSTOMER_PROCUREMENT, seeded)
        legs.append(_leg("procurement · profile ON", proc, _PROCUREMENT_HOUSE_SIGNALS))
    finally:
        await clear_org_profile(commit_factory)
        await seeded.cleanup()

    _write_report(legs)

    # Rig assertions only (ADR-F015): the loop turned the model on every leg and
    # nothing stranded at 'running'. The house-context EFFECT is in the report.
    assert len(legs) == 3
    assert all(leg["status"] in _TERMINAL for leg in legs), [
        (leg["id"], leg["status"]) for leg in legs
    ]
    assert all(int(leg["model_turns"]) > 0 for leg in legs), "a leg never turned the model"
