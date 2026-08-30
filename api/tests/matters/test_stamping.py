"""Email stamping + threading parsers — INTAKE-4a (ADR-F088).

Pure functions, hostile inputs included: a subject line and a recipient
address are whatever a stranger types, and neither may crash, blow up, or
smuggle a tag past the strict pattern.
"""

from __future__ import annotations

import pytest

from app.matters.stamping import (
    MAX_PARSED_SUBJECT_CHARS,
    MAX_PARSED_TAGS,
    has_reference_tag,
    normalise_address,
    parse_plus_tag,
    parse_plus_tags,
    parse_reference_tags,
    parse_references_header,
    parse_threading_headers,
    tag_subject,
)

REF = "NWT-COM-0042"


# ---------------------------------------------------------------------------
# tag_subject
# ---------------------------------------------------------------------------


def test_tag_subject_appends_prefix_and_tag() -> None:
    assert tag_subject("NDA review", REF) == f"Re: NDA review [{REF}]"


def test_tag_subject_is_idempotent() -> None:
    once = tag_subject("NDA review", REF)
    assert tag_subject(once, REF) == once
    assert tag_subject(tag_subject(once, REF), REF) == once


@pytest.mark.parametrize("prefix", ["Re:", "RE:", "re:", "AW:", "SV:", "Antw:"])
def test_tag_subject_does_not_double_the_reply_prefix(prefix: str) -> None:
    stamped = tag_subject(f"{prefix} NDA review", REF)
    assert stamped == f"{prefix} NDA review [{REF}]"


def test_tag_subject_on_empty_subject() -> None:
    assert tag_subject("", REF) == f"Re: [{REF}]"
    assert tag_subject("   ", REF) == f"Re: [{REF}]"


def test_tag_subject_trims_the_subject_not_the_tag() -> None:
    stamped = tag_subject("x" * 5000, REF)
    assert stamped.endswith(f"[{REF}]")
    assert len(stamped) <= MAX_PARSED_SUBJECT_CHARS
    assert has_reference_tag(stamped, REF)


def test_tag_subject_adds_its_own_tag_beside_a_different_matters_tag() -> None:
    stamped = tag_subject("Re: something [NWT-PRV-0007]", REF)
    assert "[NWT-PRV-0007]" in stamped
    assert f"[{REF}]" in stamped


def test_tag_subject_handles_unicode() -> None:
    stamped = tag_subject("Überprüfung — 契約 review 😀", REF)
    assert stamped == f"Re: Überprüfung — 契約 review 😀 [{REF}]"


# ---------------------------------------------------------------------------
# parse_reference_tags
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        (f"Re: NDA [{REF}]", [REF]),
        (f"[{REF}] leading tag", [REF]),
        (f"Fwd: Re: [{REF}] forwarded", [REF]),
        (f"[{REF}] and [{REF}] again", [REF]),  # de-duplicated
        (f"[{REF}] then [NWT-PRV-0007]", [REF, "NWT-PRV-0007"]),
        ("no tag at all", []),
        ("[nwt-com-0042]", []),  # lowercase spoof is NOT a tag
        ("[NwT-CoM-0042]", []),
        ("[NWT-COM-042]", []),  # under-padded
        ("[NWT-COM-0042", []),  # unterminated
        ("NWT-COM-0042]", []),
        ("[[NWT-COM-0042]]", [REF]),  # the inner well-formed tag still matches
        ("[NWT-[COM]-0042]", []),  # nested brackets cannot form a tag
        ("[TOOLONGCODE-COM-0042]", []),
        ("[NWT-COM-0042extra]", []),
        ("", []),
    ],
)
def test_parse_reference_tags(subject: str, expected: list[str]) -> None:
    assert parse_reference_tags(subject) == expected


def test_parse_reference_tags_is_bounded() -> None:
    many = " ".join(f"[NWT-COM-{i:04d}]" for i in range(1, 40))
    assert len(parse_reference_tags(many)) == MAX_PARSED_TAGS


def test_parse_reference_tags_ignores_a_tag_past_the_line_limit() -> None:
    huge = ("x" * (MAX_PARSED_SUBJECT_CHARS + 100)) + f" [{REF}]"
    assert parse_reference_tags(huge) == []


# ---------------------------------------------------------------------------
# plus-addressing (probed live 2026-08-30 — the provider lower-cases recipients)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("intake+NWT-COM-0042@example.com", REF),
        ("oscar-lq+nwt-com-0042@agentmail.to", REF),
        ("Legal <intake+nwt-com-0042@example.com>", REF),
        ("intake@example.com", None),
        ("intake+notareference@example.com", None),
        ("intake+nwt-com-042@example.com", None),
        ("intake+nwt-com-0042", None),  # no domain
        ("intake+nwt-com-0042@example.com extra", None),
        ("", None),
        ("a" * 400 + "+nwt-com-0042@example.com", None),  # over the address bound
    ],
)
def test_parse_plus_tag(address: str, expected: str | None) -> None:
    assert parse_plus_tag(address) == expected


def test_parse_plus_tags_over_a_recipient_list() -> None:
    assert parse_plus_tags(
        [
            "legal-intake@example.com",
            "intake+nwt-com-0042@example.com",
            "intake+NWT-COM-0042@example.com",
            "someone@else.com",
        ]
    ) == [REF]


# ---------------------------------------------------------------------------
# threading headers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<a@x>", ["a@x"]),
        ("<a@x> <b@y>", ["a@x", "b@y"]),
        ("<a@x>,<b@y>", ["a@x", "b@y"]),
        ("<a@x> <a@x>", ["a@x"]),
        ("a@x", []),  # bare ids are not RFC-shaped and are ignored
        ("<>", []),
        ("<<a@x>>", ["a@x"]),
        ("garbage", []),
        (None, []),
        ("", []),
    ],
)
def test_parse_references_header(value: str | None, expected: list[str]) -> None:
    assert parse_references_header(value) == expected


def test_parse_references_header_is_bounded() -> None:
    many = " ".join(f"<id{i}@x>" for i in range(100))
    assert len(parse_references_header(many)) == 20


def test_parse_threading_headers_puts_the_immediate_parent_first() -> None:
    assert parse_threading_headers("<c@x>", "<a@x> <b@x> <c@x>") == ["c@x", "b@x", "a@x"]


def test_parse_threading_headers_without_in_reply_to() -> None:
    assert parse_threading_headers(None, "<a@x> <b@x>") == ["b@x", "a@x"]


# ---------------------------------------------------------------------------
# normalise_address
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Jane Doe <Jane@Example.COM>", "jane@example.com"),
        ("  JANE@EXAMPLE.COM  ", "jane@example.com"),
        ("jane@example.com", "jane@example.com"),
        ("", ""),
    ],
)
def test_normalise_address(value: str, expected: str) -> None:
    assert normalise_address(value) == expected
