"""PRIV-7 — unit tests for the pure ROPA-eval helpers (run in CI, no provider).

The live scenario in ``test_ropa_population_scenario.py`` is provider- and
notice-gated (skips in CI). These cover the deterministic substrate it relies on:
the notice→document chunker (fidelity invariant) and the coverage scorer.
"""

from __future__ import annotations

from pathlib import Path

from tests.agents.scenarios.ropa_eval import (
    ActivityView,
    RegisterSnapshot,
    _split_sections,
    load_notice_document,
    score_coverage,
)

_NOTICE = """# A Notice

Preamble line before any heading.

## 1. Activities

We process customer contact details for support.

## 2. Transfers

Data goes to the US under standard contractual clauses.
"""


def _activity(
    name: str,
    *,
    systems: list[str] | None = None,
    recipients: list[str] | None = None,
    ds: list[str] | None = None,
    dc: list[str] | None = None,
    transfers: list[dict] | None = None,
    special: bool = False,
    art9: str | None = None,
) -> ActivityView:
    return ActivityView(
        name=name,
        purpose_excerpt="purpose",
        lawful_basis="legitimate_interests",
        controller_role="controller",
        retention="24 months",
        special_category=special,
        art9_condition=art9,
        system_names=systems or [],
        vendor_names=recipients or [],
        data_subject_categories=ds or [],
        data_categories=dc or [],
        transfers=transfers or [],
    )


def test_split_sections_keeps_preamble_and_splits_on_headings() -> None:
    sections = _split_sections(_NOTICE)
    # Preamble (title + line) is section 1; each '## ' heading starts a new one.
    assert [page for page, _ in sections] == [1, 2, 3]
    assert sections[0][1].startswith("# A Notice")
    assert sections[1][1].startswith("## 1. Activities")
    assert "standard contractual clauses" in sections[2][1]


def test_load_notice_document_preserves_chunk_fidelity(tmp_path: Path) -> None:
    path = tmp_path / "notice.txt"
    path.write_text(_NOTICE, encoding="utf-8")
    doc = load_notice_document(path, filename="Notice.txt")
    assert doc.filename == "Notice.txt"
    assert len(doc.chunks) == 3
    # The Citation-Engine fidelity invariant: each chunk slices back exactly.
    for chunk in doc.chunks:
        assert (
            doc.normalized_content[chunk.char_offset_start : chunk.char_offset_end] == chunk.content
        )


def test_score_coverage_counts_and_linkage() -> None:
    snap = RegisterSnapshot(
        activities=[
            _activity(
                "Support",
                systems=["Zendesk Support"],
                recipients=["AWS"],
                ds=["Customers"],
                dc=["Contact details"],
                transfers=[
                    {
                        "destination": "United States",
                        "restricted": True,
                        "mechanism": "standard_contractual_clauses",
                        "recipient": "AWS",
                    }
                ],
            ),
            _activity("Marketing", recipients=["Ad partner"]),  # partially linked
        ],
        systems=[{"name": "Zendesk Support", "system_type": "support", "ai_usage": False}],
        vendors=[
            {"name": "AWS", "vendor_role": "processor", "dpa_status": "in_place", "country": "US"}
        ],
    )
    cov = score_coverage(snap)
    assert cov["counts"]["activities"] == 2
    assert cov["counts"]["transfers"] == 1
    assert cov["counts"]["restricted_transfers"] == 1
    assert cov["counts"]["distinct_data_categories"] == 1
    # Only "Support" is fully linked across all four axes.
    assert cov["activities_fully_linked"] == 1
    assert cov["linkage_axis_fractions"]["has_recipient"] == 1.0
    assert cov["linkage_axis_fractions"]["has_system"] == 0.5
    assert cov["integrity_ok"] is True


def test_score_coverage_flags_inconsistent_special_category() -> None:
    # A special_category activity with no Article 9 condition is incoherent
    # (the write path would reject it) — the scorer must flag it.
    snap = RegisterSnapshot(activities=[_activity("Health", special=True, art9=None)])
    assert score_coverage(snap)["integrity_ok"] is False


def test_score_coverage_empty_register() -> None:
    cov = score_coverage(RegisterSnapshot())
    assert cov["counts"]["activities"] == 0
    assert cov["activities_fully_linked"] == 0
    assert cov["integrity_ok"] is True
