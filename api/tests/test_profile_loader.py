"""B-7a: the profile-manifest loader (ADR-F067 D4).

Unlike the skills loader (skip-and-warn), the profile loader is FAIL-LOUD: any
malformed/invalid manifest raises :class:`ProfileLoadError`. These tests pin that
posture over a tmp corpus + a fixture skill registry, then assert the real
shipped ``profiles/`` load cleanly against the real ``skills/`` registry.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.config import get_settings
from app.matters.reference import GENERIC_AREA_CODE, STANDARD_AREA_CODES, is_valid_code
from app.profiles.bootstrap import resolve_profiles_dir
from app.profiles.loader import ProfileLoadError, load_profiles
from app.skills.bootstrap import resolve_skill_dirs
from app.skills.loader import load_registry

pytestmark = pytest.mark.unit

_SKILL_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "skills"

# A valid area manifest binding fixture-corpus skills (alpha-test-skill,
# beta-minimal, gamma-tagged) + a real tool group.
_GOOD_AREA: dict[str, Any] = {
    "name": "widgets",
    "kind": "area",
    "display_name": "Widgets",
    "description": "A test area profile.",
    "area_key": "widgets",
    "code": "WID",
    "unit_label": "Matter",
    "default_tier_floor": None,
    "default_budget_profile": None,
    "bindings": {"skills": ["alpha-test-skill", "beta-minimal"], "tool_groups": ["redlining"]},
    "agent_config": {
        "subagents": [
            {
                "name": "helper",
                "description": "d",
                "system_prompt": "p",
                "skills": ["alpha-test-skill"],
            }
        ]
    },
    "hitl": {},
}
_GOOD_BLANK: dict[str, Any] = {
    "name": "scratch",
    "kind": "blank",
    "display_name": "Scratch",
    "description": "A blank profile.",
}
_DOCTRINE = "You are a widgets lawyer.\n\nBe surgical."


@pytest.fixture(scope="module")
def skill_registry() -> Any:
    return load_registry(_SKILL_FIXTURES)


def _write(
    base: Path,
    manifest: dict[str, Any],
    *,
    doctrine: str | None = _DOCTRINE,
    folder_name: str | None = None,
) -> Path:
    folder = base / (folder_name or manifest["name"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "profile.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if doctrine is not None and manifest.get("kind") == "area":
        (folder / "doctrine.md").write_text(doctrine, encoding="utf-8")
    return folder


def _mutate(**overrides: Any) -> dict[str, Any]:
    m = copy.deepcopy(_GOOD_AREA)
    m.update(overrides)
    return m


def test_loads_good_area_and_blank(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, _GOOD_AREA)
    _write(tmp_path, _GOOD_BLANK)
    reg = load_profiles(tmp_path, skill_registry=skill_registry)
    assert reg.names() == ["scratch", "widgets"]
    area = reg.get("widgets")
    assert area is not None and area.manifest.kind == "area"
    assert area.doctrine == _DOCTRINE
    blank = reg.get("scratch")
    assert blank is not None and blank.manifest.kind == "blank"
    assert blank.doctrine is None


def test_readme_and_hidden_are_skipped(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, _GOOD_BLANK)
    (tmp_path / "README.md").write_text("# not a profile", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    reg = load_profiles(tmp_path, skill_registry=skill_registry)
    assert reg.names() == ["scratch"]


def test_missing_dir_raises_filenotfound(tmp_path: Path, skill_registry: Any) -> None:
    with pytest.raises(FileNotFoundError):
        load_profiles(tmp_path / "does-not-exist", skill_registry=skill_registry)


# Each mutation is INVALID and must fail the whole load (fail-loud).
_BAD_CASES: list[tuple[dict[str, Any], str]] = [
    (_mutate(bogus_field="x"), "schema validation"),  # extra=forbid
    (
        _mutate(bindings={"skills": ["nope"], "tool_groups": ["redlining"]}),
        "not in the skill registry",
    ),
    (
        _mutate(bindings={"skills": ["alpha-test-skill"], "tool_groups": ["nope-group"]}),
        "unknown tool group",
    ),
    (
        _mutate(bindings={"skills": ["alpha-test-skill"], "tool_groups": ["knowledge"]}),
        "composition-only",
    ),
    (
        _mutate(
            agent_config={
                "subagents": [
                    {
                        "name": "h",
                        "description": "d",
                        "system_prompt": "p",
                        "skills": ["gamma-tagged"],
                    }
                ]
            }
        ),
        "roster",
    ),  # roster skill ∉ bindings (ADR-F017)
    (
        _mutate(
            agent_config={
                "subagents": [
                    {"name": "h", "description": "d", "system_prompt": "p", "model": "gpt"}
                ]
            }
        ),
        "roster",
    ),  # model key (ADR-F010)
    (_mutate(hitl={"not_a_real_tool": True}), "HITL-eligible"),
    (_mutate(unit_label="Deal"), "schema validation"),  # not in the closed Literal
    (_mutate(bindings=None), "schema validation"),  # area missing bindings
]


@pytest.mark.parametrize(("manifest", "msg"), _BAD_CASES)
def test_bad_manifest_fails_loud(
    tmp_path: Path, skill_registry: Any, manifest: dict[str, Any], msg: str
) -> None:
    _write(tmp_path, manifest)
    with pytest.raises(ProfileLoadError) as exc:
        load_profiles(tmp_path, skill_registry=skill_registry)
    assert msg in str(exc.value)


def test_area_missing_doctrine_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, _GOOD_AREA, doctrine=None)  # no doctrine.md written
    with pytest.raises(ProfileLoadError, match="doctrine"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_area_empty_doctrine_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, _GOOD_AREA, doctrine="   \n")  # present but blank
    with pytest.raises(ProfileLoadError, match="empty"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_folder_name_mismatch_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, _GOOD_AREA, folder_name="not-widgets")
    with pytest.raises(ProfileLoadError, match="does not match its folder"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_duplicate_area_key_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, _GOOD_AREA)
    _write(tmp_path, _mutate(name="gadgets", area_key="widgets", code="GAD"))  # same area_key
    with pytest.raises(ProfileLoadError, match="already claimed"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_duplicate_area_code_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    """INTAKE-4a (ADR-F088): two areas sharing a code could mint the same
    matter reference — refused at LOAD, like every other manifest cross-check."""
    _write(tmp_path, _GOOD_AREA)
    _write(tmp_path, _mutate(name="gadgets", area_key="gadgets"))  # same code "WID"
    with pytest.raises(ProfileLoadError, match="already claimed"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_reserved_generic_area_code_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    """``GEN`` belongs to area-less matters; no real area may claim it."""
    _write(tmp_path, _mutate(code="GEN"))
    with pytest.raises(ProfileLoadError, match="already claimed"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_area_without_a_code_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    bad = _mutate()
    bad.pop("code")
    _write(tmp_path, bad)
    with pytest.raises(ProfileLoadError, match="schema validation"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_blank_with_a_code_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, dict(_GOOD_BLANK, code="SCR"), doctrine=None)
    with pytest.raises(ProfileLoadError, match="schema validation"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_lowercase_area_code_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    _write(tmp_path, _mutate(code="wid"))
    with pytest.raises(ProfileLoadError, match="schema validation"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_blank_with_area_field_fails_loud(tmp_path: Path, skill_registry: Any) -> None:
    bad_blank = dict(_GOOD_BLANK, area_key="scratch")
    _write(tmp_path, bad_blank, doctrine=None)
    with pytest.raises(ProfileLoadError, match="schema validation"):
        load_profiles(tmp_path, skill_registry=skill_registry)


def test_real_shipped_profiles_load_clean() -> None:
    """The shipped ``profiles/`` corpus validates against the real ``skills/``
    registry (mirrors test_capabilities.py's real-corpus health check)."""
    settings = get_settings()
    skills_dir, community_dir = resolve_skill_dirs(settings)
    profiles_dir = resolve_profiles_dir(settings)
    if not skills_dir.is_dir() or not profiles_dir.is_dir():
        pytest.skip("shipped skills/ or profiles/ not present in this run layout")
    real_skills = load_registry(skills_dir, community_skills_dir=community_dir)
    reg = load_profiles(profiles_dir, skill_registry=real_skills)
    assert reg.names() == ["blank", "commercial", "privacy"]
    commercial = reg.get("commercial")
    assert commercial is not None
    assert commercial.doctrine and "commercial" in commercial.doctrine.lower()
    assert commercial.manifest.bindings is not None
    assert "surgical-redline" in commercial.manifest.bindings.skills


def test_shipped_manifests_carry_unique_valid_area_codes() -> None:
    """Drift guard — INTAKE-4a (ADR-F088).

    Every shipped ``area`` manifest declares a well-formed, unique matter-reference
    code, none of them takes the reserved ``GEN``, and each agrees with the
    service's ``STANDARD_AREA_CODES`` map (which additionally covers the areas
    migration 0053 seeds without a manifest, and which the 0100 backfill uses).
    """
    settings = get_settings()
    skills_dir, community_dir = resolve_skill_dirs(settings)
    profiles_dir = resolve_profiles_dir(settings)
    if not skills_dir.is_dir() or not profiles_dir.is_dir():
        pytest.skip("shipped skills/ or profiles/ not present in this run layout")
    real_skills = load_registry(skills_dir, community_skills_dir=community_dir)
    reg = load_profiles(profiles_dir, skill_registry=real_skills)

    codes: list[str] = []
    for record in reg.list_records():
        manifest = record.manifest
        if manifest.kind != "area":
            assert manifest.code is None
            continue
        assert manifest.code is not None
        assert is_valid_code(manifest.code), manifest.name
        assert manifest.code != GENERIC_AREA_CODE
        codes.append(manifest.code)
        assert manifest.area_key is not None
        assert STANDARD_AREA_CODES.get(manifest.area_key) == manifest.code, (
            f"manifest {manifest.name!r} code {manifest.code!r} disagrees with "
            "app.matters.reference.STANDARD_AREA_CODES"
        )
    assert len(set(codes)) == len(codes)
