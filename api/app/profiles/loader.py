"""Walk ``profiles/`` + parse each ``profile.yaml`` + cross-validate → registry.

**Fail-loud policy (ADR-F067 D4).** Unlike the skills loader (which skips a bad
skill with a WARNING and builds the rest), the profile loader raises
:class:`ProfileLoadError` on the *first* problem — a malformed manifest, an
unknown skill/tool binding, a bad roster, or an ineligible HITL name. The
bootstrap lets it bubble out of the lifespan so the process refuses to start,
mirroring the gateway's ``config_loader`` posture: shipped catalog content that
does not validate is an image/authoring bug, and coming up with a silently
dropped profile would mask it. This discharges D4's "refuse unknown kind/key at
LOAD, never at apply-time surprise."

The cross-validation reuses the *same* code the runtime write surface uses —
``build_area_subagents`` (the roster validator; ADR-F010 model-key ban + ADR-F017
skills-subset), ``TOOL_GROUP_REGISTRY`` / ``COMPOSITION_ONLY_GROUP_KEYS`` (tool
bindability), and ``hitl_eligible_tool_names`` — so a manifest can never encode a
binding the apply endpoint would later refuse.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.agents.area_agent import build_area_subagents
from app.agents.capabilities import (
    COMPOSITION_ONLY_GROUP_KEYS,
    TOOL_GROUP_REGISTRY,
    hitl_eligible_tool_names,
)
from app.profiles.registry import ProfileRecord, ProfileRegistry
from app.profiles.schema import ProfileManifest
from app.skills.registry import SkillRegistry

log = logging.getLogger(__name__)

_MANIFEST_FILE = "profile.yaml"
_DOCTRINE_FILE = "doctrine.md"

# Top-level entries under profiles/ that are not profile folders.
_TOP_LEVEL_NON_PROFILES: frozenset[str] = frozenset({"README.md", ".gitignore", ".DS_Store"})


class ProfileLoadError(Exception):
    """Raised (fatally) when a profile manifest cannot be loaded or validated."""

    def __init__(self, profile: str, message: str) -> None:
        super().__init__(f"profile {profile!r}: {message}")
        self.profile = profile


def load_profiles(
    profiles_dir: Path | str,
    *,
    skill_registry: SkillRegistry,
) -> ProfileRegistry:
    """Load every ``profiles/<name>/profile.yaml`` into a :class:`ProfileRegistry`.

    Raises :class:`ProfileLoadError` on the first malformed/invalid manifest, or
    :class:`FileNotFoundError` if ``profiles_dir`` is missing (a shipped dir must
    exist — see :func:`app.profiles.install_profile_registry`).
    """

    base = Path(profiles_dir)
    if not base.is_dir():
        raise FileNotFoundError(
            f"profiles directory does not exist or is not a directory: {base} "
            "(set PROFILES_DIR to the profile manifests location)"
        )

    records: dict[str, ProfileRecord] = {}
    known_skills = set(skill_registry.names())
    seen_area_keys: dict[str, str] = {}  # area_key -> profile name (dup guard)

    for folder in sorted(_iter_profile_folders(base)):
        record = _load_one(folder, known_skills=known_skills)
        name = record.manifest.name
        if name in records:
            raise ProfileLoadError(name, f"duplicate profile name (also in {records[name].folder})")
        if record.manifest.area_key is not None:
            prior = seen_area_keys.get(record.manifest.area_key)
            if prior is not None:
                raise ProfileLoadError(
                    name,
                    f"area_key {record.manifest.area_key!r} is already claimed by profile "
                    f"{prior!r} — two profiles may not target the same area by default",
                )
            seen_area_keys[record.manifest.area_key] = name
        records[name] = record

    log.info("profile registry built: %d profiles loaded from %s", len(records), base)
    return ProfileRegistry(records=records)


def _iter_profile_folders(base: Path) -> Iterator[Path]:
    """Yield each direct subdirectory of ``base`` that contains a ``profile.yaml``."""

    for child in base.iterdir():
        if child.name in _TOP_LEVEL_NON_PROFILES or child.name.startswith("."):
            continue
        if not child.is_dir():
            continue
        if not (child / _MANIFEST_FILE).is_file():
            continue
        yield child


def _load_one(folder: Path, *, known_skills: set[str]) -> ProfileRecord:
    """Parse + cross-validate one profile folder. Raises ProfileLoadError."""

    manifest_path = folder / _MANIFEST_FILE
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileLoadError(folder.name, f"cannot read {_MANIFEST_FILE}: {exc}") from exc

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ProfileLoadError(folder.name, f"{_MANIFEST_FILE} is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProfileLoadError(
            folder.name,
            f"{_MANIFEST_FILE} must be a YAML mapping at the top level "
            f"(got {type(parsed).__name__})",
        )

    try:
        manifest = ProfileManifest.model_validate(parsed)
    except ValidationError as exc:
        raise ProfileLoadError(folder.name, f"manifest failed schema validation:\n{exc}") from exc

    if manifest.name != folder.name:
        raise ProfileLoadError(
            folder.name,
            f"manifest name {manifest.name!r} does not match its folder name {folder.name!r}",
        )

    doctrine: str | None = None
    if manifest.kind == "area":
        doctrine = _load_doctrine(folder)
        _validate_area_bindings(manifest, known_skills=known_skills)

    return ProfileRecord(manifest=manifest, doctrine=doctrine, folder=folder)


def _load_doctrine(folder: Path) -> str:
    """Read the sibling ``doctrine.md`` verbatim (byte-parity with the seeded
    ``practice_areas.profile_md``). Required for an ``area`` profile."""

    doctrine_path = folder / _DOCTRINE_FILE
    if not doctrine_path.is_file():
        raise ProfileLoadError(
            folder.name,
            f"kind='area' profile requires a sibling {_DOCTRINE_FILE} (the doctrine text)",
        )
    try:
        doctrine = doctrine_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileLoadError(folder.name, f"cannot read {_DOCTRINE_FILE}: {exc}") from exc
    if not doctrine.strip():
        # An empty doctrine would apply as profile_md="" → a silently *unconfigured*
        # area from an area profile. Fail loud instead (shipped content is authored).
        raise ProfileLoadError(folder.name, f"{_DOCTRINE_FILE} is empty")
    return doctrine


def _validate_area_bindings(manifest: ProfileManifest, *, known_skills: set[str]) -> None:
    """Cross-check an area manifest's bindings/roster/hitl against the live
    registries — the same checks the apply endpoint enforces at write time."""

    name = manifest.name
    bindings = manifest.bindings
    assert bindings is not None  # kind=='area' guarantees it (schema validator)

    unknown_skills = sorted(s for s in bindings.skills if s not in known_skills)
    if unknown_skills:
        raise ProfileLoadError(
            name,
            f"binds skill(s) not in the skill registry: {unknown_skills}",
        )

    for group_key in bindings.tool_groups:
        if group_key not in TOOL_GROUP_REGISTRY:
            raise ProfileLoadError(name, f"binds unknown tool group {group_key!r}")
        if group_key in COMPOSITION_ONLY_GROUP_KEYS:
            raise ProfileLoadError(
                name,
                f"binds composition-only tool group {group_key!r} — it is never adoptable/bindable",
            )

    # Reuse the runtime roster validator: model-key ban (ADR-F010), required
    # keys, and skills ⊆ the area's bound set (ADR-F017).
    try:
        build_area_subagents(manifest.agent_config, known_skill_names=bindings.skills)
    except ValueError as exc:
        raise ProfileLoadError(name, f"invalid sub-agent roster: {exc}") from exc

    eligible = hitl_eligible_tool_names()
    bad_hitl = sorted(k for k in manifest.hitl if k not in eligible)
    if bad_hitl:
        raise ProfileLoadError(
            name,
            f"hitl policy names tool(s) that are not HITL-eligible: {bad_hitl}",
        )


__all__ = ["ProfileLoadError", "load_profiles"]
