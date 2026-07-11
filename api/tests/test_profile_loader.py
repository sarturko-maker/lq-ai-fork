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
    _write(tmp_path, _mutate(name="gadgets", area_key="widgets"))  # same area_key
    with pytest.raises(ProfileLoadError, match="already claimed"):
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
