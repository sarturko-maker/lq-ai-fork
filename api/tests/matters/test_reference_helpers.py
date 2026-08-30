"""Pure helpers behind ``ORG-AREA-NNNN`` — INTAKE-4a (ADR-F088).

No DB, no I/O. The allocator's transactional half lives in
``test_reference_allocator.py``.
"""

from __future__ import annotations

import pytest

from app.matters.reference import (
    CODE_MAX_CHARS,
    DEFAULT_ORG_CODE,
    GENERIC_AREA_CODE,
    REFERENCE_MAX_CHARS,
    STANDARD_AREA_CODES,
    derive_code,
    format_reference,
    is_valid_code,
    is_valid_reference,
    uniquify_code,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Commercial", "COM"),
        ("commercial", "COM"),
        ("M&A", "MA"),
        ("Privacy Programme", "PRI"),
        ("  Disputes  ", "DIS"),
        ("AI Compliance", "AIC"),
        ("Ärzte & Recht", "RZT"),  # non-ASCII letters are not [A-Z0-9] and drop out
        ("A", None),  # one usable char is not a code
        ("", None),
        ("   ", None),
        ("!!!", None),
        ("é", None),
        ("3M", "3M"),  # digits are legal code characters
    ],
)
def test_derive_code(name: str, expected: str | None) -> None:
    assert derive_code(name) == expected


def test_derive_code_never_exceeds_the_code_bounds() -> None:
    assert derive_code("Extraordinarily Long Practice Area Name") == "EXT"


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("COM", True),
        ("AB", True),
        ("ABCDEF", True),
        ("A1B2C3", True),
        ("A", False),
        ("ABCDEFG", False),
        ("com", False),
        ("CO-M", False),
        ("CO M", False),
        ("", False),
    ],
)
def test_is_valid_code(value: str, valid: bool) -> None:
    assert is_valid_code(value) is valid


def test_shipped_area_codes_are_valid_and_distinct() -> None:
    codes = list(STANDARD_AREA_CODES.values())
    assert all(is_valid_code(c) for c in codes)
    assert len(set(codes)) == len(codes)
    # GEN is reserved for area-less matters and must not be a real area's code.
    assert GENERIC_AREA_CODE not in codes
    assert is_valid_code(GENERIC_AREA_CODE)
    assert is_valid_code(DEFAULT_ORG_CODE)


def test_uniquify_code_returns_the_candidate_when_free() -> None:
    assert uniquify_code("COM", set()) == "COM"


def test_uniquify_code_suffixes_on_collision() -> None:
    assert uniquify_code("COM", {"COM"}) == "COM2"
    assert uniquify_code("COM", {"COM", "COM2", "COM3"}) == "COM4"


def test_uniquify_code_keeps_the_result_within_bounds() -> None:
    variant = uniquify_code("ABCDEF", {"ABCDEF"})
    assert len(variant) <= CODE_MAX_CHARS
    assert is_valid_code(variant)


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "NWT-COM-0001"),
        (42, "NWT-COM-0042"),
        (9999, "NWT-COM-9999"),
        (10_000, "NWT-COM-10000"),  # grows past 4 digits, never wraps
        (1_234_567, "NWT-COM-1234567"),
    ],
)
def test_format_reference(number: int, expected: str) -> None:
    rendered = format_reference("NWT", "COM", number)
    assert rendered == expected
    assert is_valid_reference(rendered)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("NWT-COM-0001", True),
        ("AB-CD-0001", True),
        ("ABCDEF-ABCDEF-999999", True),
        ("nwt-com-0001", False),
        ("NWT-COM-001", False),  # under-padded
        ("NWT-COM", False),
        ("NWT--0001", False),
        ("NWT-COM-0001 ", False),
        (" NWT-COM-0001", False),
        ("NWT-COM-0001\nX", False),
        ("A" * (REFERENCE_MAX_CHARS + 10), False),
    ],
)
def test_is_valid_reference(value: str, valid: bool) -> None:
    assert is_valid_reference(value) is valid
