"""Unit tests for the org-skill propose synthesis + strict validation core (B-2a, ADR-F067 D2/D3).

Pure, no-DB tests: :mod:`app.skills.org_proposal` takes plain dicts/dataclasses in and out, so
these exercise it directly against a bare (unpersisted) :class:`~app.models.user_skill.UserSkill`
instance and hand-built frontmatter dicts. The DB-backed harness (migration constraints,
endpoint status codes, audit rows) is covered elsewhere (``tests/test_migrations.py``,
``tests/test_org_skill_harness_api.py``).
"""

from __future__ import annotations

import hashlib
import re

import pytest

from app.api.skills import _skill_from_user_skill
from app.models.org_skill import OrgSkillVersion
from app.models.user_skill import UserSkill
from app.skills.loader import _FRONTMATTER_RE
from app.skills.org_proposal import (
    ALLOWED_LQ_AI,
    ALLOWED_TOP_LEVEL,
    ORG_SKILL_MAX_BYTES,
    render_provenance_banner,
    served_skill_md,
    synthesize_org_skill,
    validate_org_frontmatter,
)


def _make_user_skill(**overrides: object) -> UserSkill:
    """A bare (unpersisted) UserSkill row — enough attributes for the synthesizer, nothing
    touches the DB so id/timestamps/server-defaults are left unset."""
    defaults: dict[str, object] = {
        "scope": "user",
        "slug": "contract-qa",
        "display_name": "Contract QA",
        "description": "Reviews a contract for common risk flags.",
        "version": "1.2.0",
        "tags": ["contracts", "review"],
        "frontmatter_extra": {},
        "body": "# Contract QA\n\nWalk the document and flag risky clauses.",
    }
    defaults.update(overrides)
    return UserSkill(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# synthesize_org_skill — shape parity with the gateway synthesizer
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_synthesize_org_skill_frontmatter_matches_skill_from_user_skill() -> None:
    """The synthesized frontmatter dict is byte-identical in SHAPE to what
    ``api.skills._skill_from_user_skill`` already produces for the same row (parsed back out of
    its ``content_yaml``) — same top-level keys, same ``lq_ai`` nesting, same precedence."""
    row = _make_user_skill(frontmatter_extra={"jurisdiction": "us", "output_format": "markdown"})

    content = synthesize_org_skill(row)

    import yaml

    gateway_payload = _skill_from_user_skill(row)
    gateway_frontmatter = yaml.safe_load(gateway_payload["content_yaml"])

    assert content.frontmatter == gateway_frontmatter
    assert content.frontmatter == {
        "name": "contract-qa",
        "description": "Reviews a contract for common risk flags.",
        "lq_ai": {
            "title": "Contract QA",
            "version": "1.2.0",
            "tags": ["contracts", "review"],
            "jurisdiction": "us",
            "output_format": "markdown",
        },
    }


@pytest.mark.unit
def test_synthesize_org_skill_omits_tags_when_row_has_none() -> None:
    row = _make_user_skill(tags=[])
    content = synthesize_org_skill(row)
    assert "tags" not in content.frontmatter["lq_ai"]


@pytest.mark.unit
def test_synthesize_org_skill_lq_ai_wins_on_conflict_with_frontmatter_extra() -> None:
    """``frontmatter_extra`` never overrides an already-set ``lq_ai`` key (title/version) —
    mirrors ``_skill_from_user_skill``'s ``key not in lq_ai`` precedence."""
    row = _make_user_skill(frontmatter_extra={"version": "9.9.9", "title": "Ignored"})
    content = synthesize_org_skill(row)
    assert content.frontmatter["lq_ai"]["version"] == "1.2.0"
    assert content.frontmatter["lq_ai"]["title"] == "Contract QA"


@pytest.mark.unit
def test_synthesize_org_skill_drops_none_valued_frontmatter_extra() -> None:
    row = _make_user_skill(frontmatter_extra={"jurisdiction": None, "author": "A. Lawyer"})
    content = synthesize_org_skill(row)
    assert "jurisdiction" not in content.frontmatter["lq_ai"]
    assert content.frontmatter["lq_ai"]["author"] == "A. Lawyer"


@pytest.mark.unit
def test_synthesize_org_skill_raw_yaml_has_no_trailing_newline() -> None:
    row = _make_user_skill()
    content = synthesize_org_skill(row)
    assert not content.raw_yaml.endswith("\n")
    assert content.raw_yaml.startswith("name:")


@pytest.mark.unit
def test_synthesize_org_skill_hash_is_stable_and_hex() -> None:
    row = _make_user_skill()
    first = synthesize_org_skill(row)
    second = synthesize_org_skill(row)
    assert first.content_hash == second.content_hash
    assert re.fullmatch(r"[0-9a-f]{64}", first.content_hash)

    # Hash matches an independent sha256 over the reconstructed text.
    from app.agents.skill_backend import reconstruct_skill_md

    expected = hashlib.sha256(
        reconstruct_skill_md(first.raw_yaml, first.body).encode("utf-8")
    ).hexdigest()
    assert first.content_hash == expected


@pytest.mark.unit
def test_synthesize_org_skill_size_bytes_boundary() -> None:
    """size_bytes is the UTF-8 byte length of the reconstructed SKILL.md text — exactly at
    ORG_SKILL_MAX_BYTES passes the caller's cap check, one byte over fails it. This module does
    not enforce the cap itself (the propose endpoint does); this test only pins the arithmetic
    the endpoint relies on."""
    from app.agents.skill_backend import reconstruct_skill_md

    row = _make_user_skill(body="x")
    content = synthesize_org_skill(row)
    reconstructed = reconstruct_skill_md(content.raw_yaml, content.body)
    assert content.size_bytes == len(reconstructed.encode("utf-8"))

    # Pad the body so the reconstructed text lands exactly at the cap.
    header_len = len(reconstruct_skill_md(content.raw_yaml, "").encode("utf-8"))
    pad_len = ORG_SKILL_MAX_BYTES - header_len
    assert pad_len > 0
    at_cap_row = _make_user_skill(body="a" * pad_len)
    at_cap = synthesize_org_skill(at_cap_row)
    assert at_cap.size_bytes == ORG_SKILL_MAX_BYTES

    over_cap_row = _make_user_skill(body="a" * (pad_len + 1))
    over_cap = synthesize_org_skill(over_cap_row)
    assert over_cap.size_bytes == ORG_SKILL_MAX_BYTES + 1


# ---------------------------------------------------------------------------
# validate_org_frontmatter — F067 D3.3 closed allowlist
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_org_frontmatter_accepts_maximal_legal_frontmatter() -> None:
    frontmatter = {
        "name": "contract-qa",
        "description": "Reviews a contract for common risk flags.",
        "lq_ai": {
            "title": "Contract QA",
            "version": "1.0.0",
            "author": "A. Lawyer",
            "tags": ["contracts"],
            "jurisdiction": "us",
            "output_format": "markdown",
            "trigger_examples": ["review this NDA"],
        },
    }
    assert validate_org_frontmatter(frontmatter) == []


@pytest.mark.unit
def test_validate_org_frontmatter_accepts_minimal_frontmatter() -> None:
    assert validate_org_frontmatter({"name": "x", "description": "y"}) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "denied_key",
    [
        "allowed-tools",
        "minimum_inference_tier",
        "ensemble_verification",
        "inputs",
        "columns",
        "use_organization_profile",
        "is_organization_profile",
        "self_improvement",
        "api_key",
    ],
)
def test_validate_org_frontmatter_reports_denied_lq_ai_keys(denied_key: str) -> None:
    """Every F067 D3.3-denied key (and anything else outside the allowlist) is reported at its
    dotted path when nested under ``lq_ai`` — including when it arrived via
    ``frontmatter_extra`` (synthesize_org_skill puts unknown extras straight into ``lq_ai``, so
    this is the exact shape a hostile/careless propose would produce)."""
    frontmatter = {
        "name": "x",
        "description": "y",
        "lq_ai": {"title": "X", denied_key: "danger"},
    }
    offending = validate_org_frontmatter(frontmatter)
    assert offending == [f"lq_ai.{denied_key}"]


@pytest.mark.unit
def test_validate_org_frontmatter_reports_unknown_top_level_keys() -> None:
    frontmatter = {"name": "x", "description": "y", "extra_top_level": "nope"}
    assert validate_org_frontmatter(frontmatter) == ["extra_top_level"]


@pytest.mark.unit
def test_validate_org_frontmatter_reports_multiple_offenses_sorted() -> None:
    frontmatter = {
        "name": "x",
        "description": "y",
        "z_unknown": 1,
        "lq_ai": {"allowed-tools": ["read_file"], "b_unknown": 2},
    }
    assert validate_org_frontmatter(frontmatter) == [
        "lq_ai.allowed-tools",
        "lq_ai.b_unknown",
        "z_unknown",
    ]


@pytest.mark.unit
def test_validate_org_frontmatter_rejects_non_dict_lq_ai() -> None:
    frontmatter = {"name": "x", "description": "y", "lq_ai": "not-a-dict"}
    assert validate_org_frontmatter(frontmatter) == ["lq_ai"]


@pytest.mark.unit
def test_validate_org_frontmatter_rejects_non_string_name_and_description() -> None:
    frontmatter = {"name": 123, "description": None}
    assert validate_org_frontmatter(frontmatter) == ["description", "name"]


@pytest.mark.unit
def test_validate_org_frontmatter_allowlists_are_the_documented_closed_sets() -> None:
    assert {"name", "description", "lq_ai"} == ALLOWED_TOP_LEVEL
    assert {
        "title",
        "version",
        "author",
        "tags",
        "jurisdiction",
        "output_format",
        "trigger_examples",
    } == ALLOWED_LQ_AI


# ---------------------------------------------------------------------------
# render_provenance_banner / served_skill_md — F067 D3.5 provenance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_provenance_banner_exact_text() -> None:
    banner = render_provenance_banner("author@example.com", "admin@example.com", "2026-07-08")
    assert banner == (
        "Provenance: org-authored by author@example.com, approved by admin@example.com "
        "on 2026-07-08 — your company's own material, not LQ-shipped."
    )


@pytest.mark.unit
def test_served_skill_md_starts_with_frontmatter_delimiter_and_parses() -> None:
    row = _make_user_skill()
    content = synthesize_org_skill(row)
    version = OrgSkillVersion(
        slug=row.slug,
        version_no=1,
        raw_yaml=content.raw_yaml,
        body=content.body,
        frontmatter=content.frontmatter,
        content_hash=content.content_hash,
    )
    from datetime import UTC, datetime

    version.reviewed_at = datetime(2026, 7, 8, tzinfo=UTC)

    served = served_skill_md(
        version, author_label="author@example.com", approver_label="admin@example.com"
    )

    assert served.startswith("---\n")
    match = _FRONTMATTER_RE.match(served)
    assert match is not None
    body = match.group("body")
    assert body.startswith(
        "> Provenance: org-authored by author@example.com, approved by "
        "admin@example.com on 2026-07-08 — your company's own material, not LQ-shipped.\n\n"
    )
    assert row.body in body


@pytest.mark.unit
def test_served_skill_md_falls_back_to_unknown_date_when_unreviewed() -> None:
    row = _make_user_skill()
    content = synthesize_org_skill(row)
    version = OrgSkillVersion(
        slug=row.slug,
        version_no=1,
        raw_yaml=content.raw_yaml,
        body=content.body,
        frontmatter=content.frontmatter,
        content_hash=content.content_hash,
    )
    served = served_skill_md(version, author_label="author@example.com", approver_label="unknown")
    assert "on unknown —" in served


@pytest.mark.unit
def test_served_skill_md_does_not_mutate_stored_body_or_hash() -> None:
    """The banner rides in the SERVED text only — the version's stored ``body``/``content_hash``
    never change (the hash was computed over author bytes only, at propose time)."""
    row = _make_user_skill()
    content = synthesize_org_skill(row)
    version = OrgSkillVersion(
        slug=row.slug,
        version_no=1,
        raw_yaml=content.raw_yaml,
        body=content.body,
        frontmatter=content.frontmatter,
        content_hash=content.content_hash,
    )
    served_skill_md(version, author_label="a", approver_label="b")
    assert version.body == content.body
    assert version.content_hash == content.content_hash


# ---------------------------------------------------------------------------
# OrgSkillVersion helper properties (title / description / tags read self.frontmatter)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_org_skill_version_title_description_tags_properties() -> None:
    row = _make_user_skill()
    content = synthesize_org_skill(row)
    version = OrgSkillVersion(
        slug=row.slug,
        version_no=1,
        raw_yaml=content.raw_yaml,
        body=content.body,
        frontmatter=content.frontmatter,
        content_hash=content.content_hash,
    )
    assert version.title == "Contract QA"
    assert version.description == "Reviews a contract for common risk flags."
    assert version.tags == ["contracts", "review"]


@pytest.mark.unit
def test_org_skill_version_properties_default_safely_on_sparse_frontmatter() -> None:
    version = OrgSkillVersion(
        slug="x",
        version_no=1,
        raw_yaml="name: x\ndescription: y",
        body="body",
        frontmatter={"name": "x", "description": "y"},
        content_hash="hash",
    )
    assert version.title is None
    assert version.description == "y"
    assert version.tags == []
