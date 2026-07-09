"""Pure-core tests for the org-playbook propose/freeze machinery (ADR-F067 B-4).

No DB. Covers canonicalization determinism (the byte-pin story), totality over malformed
untrusted ``fallback_tiers``, the size-cap input, and the rehydration + provenance banner the
render seam consumes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.agents.playbook_proposal import (
    content_size_bytes,
    freeze_playbook_snapshot,
    frozen_playbook_from_version,
)

pytestmark = pytest.mark.unit


def _pos(**kw: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "issue": "Confidentiality",
        "description": "",
        "standard_language": "Each party keeps the other's info secret.",
        "fallback_tiers": [],
        "redline_strategy": "",
        "severity_if_missing": "high",
        "detection_keywords": [],
        "detection_examples": [],
        "position_order": 0,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _playbook(
    positions: list[SimpleNamespace],
    *,
    name: str = "House NDA",
    contract_type: str = "NDA",
    description: str = "d",
    version: str = "1.0.0",
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        contract_type=contract_type,
        description=description,
        version=version,
        positions=positions,
    )


def _version_like(content: object) -> SimpleNamespace:
    c = content
    return SimpleNamespace(
        name=c.name,  # type: ignore[attr-defined]
        contract_type=c.contract_type,  # type: ignore[attr-defined]
        description=c.description,  # type: ignore[attr-defined]
        playbook_version=c.playbook_version,  # type: ignore[attr-defined]
        positions=c.positions,  # type: ignore[attr-defined]
    )


def test_freeze_produces_hash_size_and_count() -> None:
    content = freeze_playbook_snapshot(_playbook([_pos(), _pos(issue="Term", position_order=1)]))
    assert content.position_count == 2
    assert content.content_hash and len(content.content_hash) == 64
    assert content.size_bytes > 0
    assert content.name == "House NDA" and content.playbook_version == "1.0.0"


def test_hash_stable_across_reordered_semantically_equal_input() -> None:
    """Shuffled positions (by order) + shuffled fallback_tiers (by rank) + differing key
    insertion order → identical content_hash (the byte-pin determinism story)."""
    a = _playbook(
        [
            _pos(
                issue="A",
                position_order=0,
                fallback_tiers=[{"rank": 2, "description": "y"}, {"rank": 1, "description": "x"}],
            ),
            _pos(issue="B", position_order=1),
        ]
    )
    b = _playbook(
        [
            _pos(issue="B", position_order=1),
            _pos(
                issue="A",
                position_order=0,
                fallback_tiers=[{"description": "x", "rank": 1}, {"description": "y", "rank": 2}],
            ),
        ]
    )
    assert freeze_playbook_snapshot(a).content_hash == freeze_playbook_snapshot(b).content_hash


def test_hash_deterministic_with_colliding_position_order() -> None:
    """Two positions sharing position_order=0 canonicalize deterministically (content tiebreak),
    so byte-identical input hashes identically regardless of input order."""
    a = _playbook([_pos(issue="A", position_order=0), _pos(issue="B", position_order=0)])
    b = _playbook([_pos(issue="B", position_order=0), _pos(issue="A", position_order=0)])
    assert freeze_playbook_snapshot(a).content_hash == freeze_playbook_snapshot(b).content_hash


def test_hash_changes_when_content_changes() -> None:
    a = _playbook([_pos(standard_language="X")])
    b = _playbook([_pos(standard_language="Y")])
    assert freeze_playbook_snapshot(a).content_hash != freeze_playbook_snapshot(b).content_hash


def test_canonicalize_total_over_malformed_fallback_tiers() -> None:
    """A hostile/garbage ``fallback_tiers`` shape must NOT raise and must hash deterministically
    (non-dict tiers skipped, mirroring the render path)."""
    pb = _playbook(
        [_pos(fallback_tiers=["not a dict", 42, {"rank": 1, "description": "ok"}, None])]
    )
    content = freeze_playbook_snapshot(pb)  # must not raise
    assert content.positions[0]["fallback_tiers"] == [{"rank": 1, "description": "ok"}]
    assert freeze_playbook_snapshot(pb).content_hash == content.content_hash


def test_canonicalize_non_list_fallback_tiers_becomes_empty() -> None:
    content = freeze_playbook_snapshot(_playbook([_pos(fallback_tiers={"rank": 1})]))
    assert content.positions[0]["fallback_tiers"] == []


def test_content_size_bytes_matches_freeze() -> None:
    content = freeze_playbook_snapshot(_playbook([_pos()]))
    assert content_size_bytes(_version_like(content)) == content.size_bytes


def test_frozen_playbook_from_version_carries_banner_and_positions() -> None:
    content = freeze_playbook_snapshot(
        _playbook([_pos(issue="Confidentiality", standard_language="keep secret")])
    )
    version = SimpleNamespace(
        name=content.name,
        contract_type=content.contract_type,
        description=content.description,
        playbook_version=content.playbook_version,
        positions=content.positions,
        reviewed_at=datetime(2026, 7, 9, tzinfo=UTC),
        author_user_id=None,
        reviewed_by=None,
    )
    frozen = frozen_playbook_from_version(version, author_label="a@x.com", approver_label="b@x.com")
    assert frozen.name == "House NDA"
    assert frozen.provenance_banner is not None and "2026-07-09" in frozen.provenance_banner
    assert frozen.positions[0].issue == "Confidentiality"
    assert frozen.positions[0].standard_language == "keep secret"
