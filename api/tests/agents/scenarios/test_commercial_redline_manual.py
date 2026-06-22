"""C9 manual, Claude-judged redline harness (provider-marked, CI-skipped).

C8's eval used DeepSeek as its own craft-judge — a weak signal (same model). The
maintainer's C9 steer: **a stronger judge**. This harness drives DeepSeek to
redline vendor-favoured agreements under *purposive* instruction, then captures
every produced ``.docx`` + a readable reconstruction + the accept-to-clean text
into an evidence dir. **Claude (the agent) then judges** each produced redline for
lawyer-like craft and writes the verdicts — this file deliberately does NOT call
an automated craft judge.

The corpus spans contract types AND complexity, because the *real* surgical test
(maintainer steer) is dense, multi-limb clauses where most language must be LEFT
ALONE — not short clauses that are trivially replaceable:

  moderate (short-clause) — ids are the LQ_AI_C9_ONLY keys:
    1. SecureScan SaaS MSA            (``securescan_saas_msa``)
    2. DataBridge software licence    (``databridge_licence``)
    3. Aegis "mutual" NDA            (``aegis_mutual_nda``)
    4. Northwind DPA                  (``northwind_dpa``)
    5. Meridian professional-services (``meridian_services_sow``)
  complex (dense, multi-limb — the hard surgical case):
    6. Helios master SaaS+services    (``helios_master_agreement``)
    7. Orion software dev + licence    (``orion_dev_licence``)

Per scenario it writes ``c9/<id>/`` (the original + redlined ``.docx``, the
reconstruction, the accepted-clean text) and merges a ``manifest.json``. Set
``LQ_AI_C9_ONLY=<id>[,<id>]`` to run a subset without clobbering the others
(DeepSeek is stochastic; a run can occasionally produce no redline).

``LQ_AI_SCENARIO_MODEL`` selects the gateway alias: ``deepseek`` (deepseek-v4-flash)
is the baseline; re-run the same scenarios with ``deepseek-pro`` (deepseek-v4-pro)
to isolate a model limitation from a method limitation when craft falls short
(maintainer steer). Point ``UX_B1_EVIDENCE_DIR`` at a model-specific dir so the two
runs do not overwrite each other.

Run against the live dev stack:

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c9/flash \\
    pytest -m provider tests/agents/scenarios/test_commercial_redline_manual.py -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.redline_render import bare_text, docx_text, reconstruct_redline_text
from app.agents.redline_service import RedlineService
from app.skills import SkillRegistry, load_registry
from tests.agents.scenarios.aegis_mutual_nda import (
    NDA_FILENAME,
    build_nda_docx,
    nda_normalized_text,
)
from tests.agents.scenarios.commercial_redline_lib import (
    RedlineScenarioDoc,
    capture_redline,
    seed_doc_matter,
)
from tests.agents.scenarios.databridge_license import (
    LICENSE_FILENAME,
    build_license_docx,
    license_normalized_text,
)
from tests.agents.scenarios.harness import run_scenario
from tests.agents.scenarios.helios_master_agreement import (
    HELIOS_FILENAME,
    build_helios_docx,
    helios_normalized_text,
)
from tests.agents.scenarios.meridian_services_sow import (
    SOW_FILENAME,
    build_sow_docx,
    sow_normalized_text,
)
from tests.agents.scenarios.northwind_dpa import (
    DPA_FILENAME,
    build_dpa_docx,
    dpa_normalized_text,
)
from tests.agents.scenarios.orion_dev_licence import (
    ORION_FILENAME,
    build_orion_docx,
    orion_normalized_text,
)
from tests.agents.scenarios.scenarios import Scenario
from tests.agents.scenarios.securescan_msa import (
    MSA_FILENAME,
    build_msa_docx,
    msa_normalized_text,
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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c9"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_ONLY = {s.strip() for s in os.environ.get("LQ_AI_C9_ONLY", "").split(",") if s.strip()}
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}
_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)


def _purposive_prompt(role: str, filename: str, heads: tuple[str, ...]) -> str:
    """A purposive redline instruction tailored to one instrument.

    The maintainer's C9 steer is that Claude *instructs DeepSeek purposively* —
    so each prompt names our side, the instrument, and the specific one-sided
    heads to rebalance, while leaving the surgical *technique* to the bound
    ``surgical-redline`` skill (we measure whether the agent applies it)."""
    bullets = "\n".join(f"  - {h}" for h in heads)
    return (
        f"You are our in-house commercial counsel and {role}. Review the attached "
        f'agreement "{filename}" and redline it with tracked changes (apply_redline) to '
        "protect us. Read the whole agreement first, then work through every clause that is "
        "one-sided against us — in particular:\n"
        f"{bullets}\n"
        "Make balanced, defensible edits a partner would accept. Apply ALL your edits in a "
        "SINGLE apply_redline call (it re-redlines the original on each call, so one call must "
        "cover everything)."
    )


CORPUS: list[RedlineScenarioDoc] = [
    RedlineScenarioDoc(
        id="securescan_saas_msa",
        filename=MSA_FILENAME,
        build_docx=build_msa_docx,
        normalized_text=msa_normalized_text,
        prompt=_purposive_prompt(
            "we are the CUSTOMER",
            MSA_FILENAME,
            (
                "the unilateral fee increase and non-refundable fees",
                "the auto-renewal and no-termination-for-convenience term",
                "the IP assignment of deliverables and feedback to the Vendor",
                "the perpetual Customer Data licence",
                'the "as is" warranty disclaimer',
                "the one-sided indemnity (make it reciprocal; add Vendor IP cover)",
                "the one-month liability cap (carve out confidentiality, IP and gross "
                "negligence; raise the period)",
            ),
        ),
        boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
    ),
    RedlineScenarioDoc(
        id="databridge_licence",
        filename=LICENSE_FILENAME,
        build_docx=build_license_docx,
        normalized_text=license_normalized_text,
        prompt=_purposive_prompt(
            "we are the LICENSEE",
            LICENSE_FILENAME,
            (
                "the suspension-at-sole-discretion-without-notice right",
                "the unilateral fee increase and non-refundable fees",
                "the IP vesting of configurations and feedback in the Licensor",
                "the perpetual Licensee Content licence (especially model training)",
                'the "as is" warranty disclaimer',
                "the one-sided indemnity (make it reciprocal; add Licensor IP cover)",
                "the three-month liability cap (carve out confidentiality, IP and data)",
                "the auto-renewal and no-termination-for-convenience term",
            ),
        ),
        boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
    ),
    RedlineScenarioDoc(
        id="aegis_mutual_nda",
        filename=NDA_FILENAME,
        build_docx=build_nda_docx,
        normalized_text=nda_normalized_text,
        prompt=_purposive_prompt(
            "we are the RECIPIENT",
            NDA_FILENAME,
            (
                "make the obligations genuinely mutual (it is one-directional despite the title)",
                "add the standard exclusions (public domain, already known, independently "
                "developed, required by law)",
                "cap the perpetual confidentiality term to a fixed period",
                "allow retention of backup and legally-required copies on return",
                "make the injunctive-relief and no-bond right reciprocal",
                "narrow or mutualise the one-sided indemnity",
            ),
        ),
        boilerplate_bare=(
            "shall hold in strict confidence",
            "shall indemnify, defend and hold harmless",
        ),
    ),
    RedlineScenarioDoc(
        id="northwind_dpa",
        filename=DPA_FILENAME,
        build_docx=build_dpa_docx,
        normalized_text=dpa_normalized_text,
        prompt=_purposive_prompt(
            "we are the CONTROLLER",
            DPA_FILENAME,
            (
                "require processing only on the Controller's documented instructions",
                "strike the Processor's own-purpose use and model-training rights",
                "require prior authorisation and flow-down for sub-processors, with the "
                "Processor remaining liable",
                "require appropriate technical and organisational measures to the risk",
                "shorten breach notification to without undue delay and add assistance",
                "add a Controller audit right",
                "require transfer safeguards (e.g. SCCs) for international transfers",
                "require deletion or return on termination with no open-ended retention",
            ),
        ),
        boilerplate_bare=("The Processor shall implement",),
    ),
    RedlineScenarioDoc(
        id="meridian_services_sow",
        filename=SOW_FILENAME,
        build_docx=build_sow_docx,
        normalized_text=sow_normalized_text,
        prompt=_purposive_prompt(
            "we are the CUSTOMER",
            SOW_FILENAME,
            (
                "add a real acceptance right with correction at the Supplier's cost and a "
                "longer review window",
                "the uncapped time-and-materials fees and unilateral rate increases",
                "the IP vesting of deliverables in the Supplier (assign bespoke deliverables "
                "to us or grant a broad licence)",
                'the "as is" warranty (warrant conformance to spec; re-perform at no cost)',
                "the free personnel substitution (add key-person protection)",
                "the one-sided indemnity (make it reciprocal; add Supplier IP cover)",
                "the one-month liability cap (carve out confidentiality, IP and gross "
                "negligence; raise the period)",
                "the one-sided termination for convenience (give us the same right; pay only "
                "for work performed)",
            ),
        ),
        boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
    ),
    # --- complex tier: dense, multi-limb clauses (the hard surgical test) ----
    RedlineScenarioDoc(
        id="helios_master_agreement",
        filename=HELIOS_FILENAME,
        build_docx=build_helios_docx,
        normalized_text=helios_normalized_text,
        prompt=_purposive_prompt(
            "we are the CUSTOMER",
            HELIOS_FILENAME,
            (
                "§2 the mid-term unilateral fee increase (the renewal increase and our "
                "good-faith withholding right are fine)",
                "§3 the blanket warranty disclaimer (the express service warranty and the "
                "correct-or-refund remedy are fine)",
                "§4 the Deliverables/configurations vesting in the Provider (we should own or "
                "have a broad licence to what we pay to have built; background IP and feedback "
                "are fine)",
                "§5 the over-broad Customer indemnity and the indemnifying party's right to "
                "settle in its sole discretion (the notice / control-of-defence / cooperation "
                "procedure is fine)",
                "§6 the liability cap and exclusions: add confidentiality, data protection and "
                "IP infringement to the excluded matters, treat loss of Customer Data as a "
                "direct loss, lengthen the six-month cap period and the six-month claim time-bar "
                "(the indirect-loss exclusion list and the death/personal-injury and fraud "
                "carve-outs are fine)",
            ),
        ),
        boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
        complexity="complex",
    ),
    RedlineScenarioDoc(
        id="orion_dev_licence",
        filename=ORION_FILENAME,
        build_docx=build_orion_docx,
        normalized_text=orion_normalized_text,
        prompt=_purposive_prompt(
            "we are the CLIENT",
            ORION_FILENAME,
            (
                "§2 the five-day deemed-acceptance window and pay-on-delivery-regardless, and add "
                "a right to reject a Deliverable with material defects (the delivery → test → "
                "re-deliver procedure is fine)",
                "§3 the bespoke developments we commission and pay for vesting in the Developer "
                "(we should own them or have a broad licence; the Background-IP split and the "
                "licence grant are fine)",
                "§4 the service credits as our sole and exclusive remedy, and add a right to exit "
                "for chronic SLA failure (the availability target, response time and credit "
                "mechanics are fine)",
                "§5 the escrow release events (add the Developer ceasing to support the Software)",
                "§6 the over-broad Client indemnity and add a settlement-consent proviso (the "
                "indemnification procedure is fine)",
                "§7 the liability cap and exclusions: add confidentiality, data and IP "
                "infringement to the excluded matters and lengthen the three-month cap period "
                "(the indirect-loss exclusion and the death/PI and fraud carve-outs are fine)",
                "§8 the one-sided termination for convenience (give us the same right)",
            ),
        ),
        boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
        complexity="complex",
    ),
]


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _run_once(
    factory: async_sessionmaker[AsyncSession],
    doc: RedlineScenarioDoc,
    registry: SkillRegistry,
) -> dict[str, object]:
    """Seed → run DeepSeek → capture the produced .docx + reconstruction.

    Writes the deliverables Claude will judge into ``c9/<id>/``; returns the
    manifest row. No automated judge here — Claude reads the artifacts and judges.
    """
    out_dir = _EVIDENCE_DIR / doc.id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"original-{doc.filename}").write_bytes(doc.build_docx())

    seeded = await seed_doc_matter(factory, doc)
    row: dict[str, object] = {
        "doc": doc.id,
        "filename": doc.filename,
        "complexity": doc.complexity,
        "prompt": doc.prompt,
    }
    try:
        scenario = Scenario(
            id=f"redline_manual_{doc.id}",
            title=f"Claude-judged redline — {doc.id}",
            note="DeepSeek redlines under purposive instruction; Claude judges the craft.",
            prompt=doc.prompt,
            expect_tools=("apply_redline",),
            step_bound=100,
        )
        receipt = await run_scenario(
            scenario, seeded, skill_registry=registry, model_alias=_MODEL, max_steps=100
        )
        row["status"] = receipt.status
        row["model_turns"] = receipt.model_turns
        row["tools_called"] = receipt.tools_called

        captured = await capture_redline(factory, seeded.user_id, seeded.project_id)
        if captured is None:
            row["redlined"] = False
            return row
        redlined_bytes, redlined_name = captured
        redline_view = reconstruct_redline_text(redlined_bytes)
        accepted = docx_text(RedlineService().accept_all(redlined_bytes))
        (out_dir / redlined_name).write_bytes(redlined_bytes)
        (out_dir / "reconstruction.txt").write_text(redline_view, encoding="utf-8")
        (out_dir / "accepted-clean.txt").write_text(accepted, encoding="utf-8")
        row["redlined"] = True
        row["redlined_file"] = f"{doc.id}/{redlined_name}"
        # Deterministic structure note (informational; Claude judges the craft).
        row["boilerplate_bare"] = all(
            phrase in bare_text(redline_view) for phrase in doc.boilerplate_bare
        )
        return row
    finally:
        await seeded.cleanup()


def _merge_manifest(out_dir: Path, rows: list[dict[str, object]]) -> dict[str, object]:
    """Merge this run's rows into any existing manifest so a single-instrument
    re-run (``LQ_AI_C9_ONLY``) does not clobber the other instruments' records."""
    path = out_dir / "manifest.json"
    existing: dict[str, object] = {}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    by_doc: dict[str, object] = {}
    prior = existing.get("instruments")
    if isinstance(prior, list):
        by_doc = {str(r.get("doc")): r for r in prior if isinstance(r, dict)}
    for row in rows:
        by_doc[str(row["doc"])] = row
    return {"model": _MODEL, "instruments": [by_doc[k] for k in sorted(by_doc)]}


async def test_commercial_redline_manual(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    registry = load_registry(_SKILLS_DIR)  # activates the bound surgical-redline skill
    corpus = [d for d in CORPUS if not _ONLY or d.id in _ONLY]
    assert corpus, f"LQ_AI_C9_ONLY={_ONLY} matched no instrument"

    rows = [await _run_once(commit_factory, doc, registry) for doc in corpus]
    manifest = _merge_manifest(_EVIDENCE_DIR, rows)
    (_EVIDENCE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Rig assertions only (ADR-F015): every run reached a terminal state and turned
    # the model. Whether the redline is lawyer-like is Claude's manual judgement,
    # recorded in c9/verdicts/ — never a hard gate on model quality here.
    assert rows, "no manual runs executed"
    for r in rows:
        assert r.get("status") in _TERMINAL, r
