"""Drift guard: migration 0100's derivation twin vs the live service — ADR-F088.

Migrations in this repo are self-contained (none of them imports ``app.*``), so
``0100_matter_reference_and_stamping.py`` restates ``derive_code``/
``uniquify_code`` and the code/reference patterns. If the service's copy ever
changes without the migration's, a re-run of the backfill on a fresh deployment
would mint DIFFERENT area codes from the ones the running code allocates under.
This test fails the build in that case.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from app.matters import reference as svc

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0100_matter_reference_and_stamping.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0100", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration() -> ModuleType:
    return _load_migration()


def test_patterns_and_constants_match(migration: ModuleType) -> None:
    assert migration._CODE_PATTERN == svc.CODE_PATTERN
    assert migration._REFERENCE_PATTERN == svc.REFERENCE_PATTERN
    assert migration._REFERENCE_MAX_CHARS == svc.REFERENCE_MAX_CHARS
    assert migration._DEFAULT_ORG_CODE == svc.DEFAULT_ORG_CODE
    assert migration._GENERIC_AREA_CODE == svc.GENERIC_AREA_CODE
    assert migration._DERIVED_CODE_CHARS == svc.DERIVED_CODE_CHARS
    assert migration._CODE_MIN_CHARS == svc.CODE_MIN_CHARS
    assert migration._CODE_MAX_CHARS == svc.CODE_MAX_CHARS
    assert migration._STANDARD_AREA_CODES == svc.STANDARD_AREA_CODES


@pytest.mark.parametrize(
    "name",
    [
        "Commercial",
        "commercial",
        "M&A",
        "Privacy",
        "Privacy Programme",
        "Disputes",
        "Employment",
        "AI Compliance",
        "3M",
        "A",
        "",
        "   ",
        "!!!",
        "Ärzte & Recht",
        "Extraordinarily Long Practice Area Name",
    ],
)
def test_derive_code_parity(migration: ModuleType, name: str) -> None:
    assert migration._derive_code(name) == svc.derive_code(name)


@pytest.mark.parametrize(
    ("candidate", "taken"),
    [
        ("COM", set[str]()),
        ("COM", {"COM"}),
        ("COM", {"COM", "COM2"}),
        ("ABCDEF", {"ABCDEF"}),
        ("GEN", {"GEN"}),
    ],
)
def test_uniquify_code_parity(migration: ModuleType, candidate: str, taken: set[str]) -> None:
    assert migration._uniquify_code(candidate, set(taken)) == svc.uniquify_code(
        candidate, set(taken)
    )
