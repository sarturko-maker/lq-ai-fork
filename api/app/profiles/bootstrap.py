"""Profile-registry bootstrap for the API process (ADR-F067 D4, B-7a).

Installed ONLY on the FastAPI app (``app/main.py`` lifespan) — the arq worker
never applies profiles, so unlike ``install_skill_registry`` this is not wired
into the worker's ``on_startup`` (justified divergence; ADR-F067 B-7a addendum).
It runs *after* the skill registry is installed, because the profile loader
cross-validates each manifest's skill bindings against the live skill corpus.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.profiles.loader import load_profiles

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.config import Settings
    from app.profiles.registry import ProfileRegistry
    from app.skills.registry import SkillRegistry


def resolve_profiles_dir(settings: Settings) -> Path:
    """Resolve the profiles directory from settings (relative to CWD).

    Mirrors ``resolve_skill_dirs``: the API container's WORKDIR is ``/app`` and
    the default ``../profiles`` anchors there → ``/profiles`` (the Dockerfile
    ``COPY`` target and the dev bind mount).
    """
    return Path(settings.profiles_dir).resolve()


def install_profile_registry(
    app: FastAPI,
    settings: Settings,
    *,
    skill_registry: SkillRegistry,
) -> ProfileRegistry:
    """Build the profile registry and install it at ``app.state.profile_registry``.

    Fail-loud: a missing directory raises :class:`FileNotFoundError`; a malformed
    manifest raises :class:`app.profiles.loader.ProfileLoadError`. Both bubble out
    of the lifespan so the process refuses to boot rather than serving a silently
    incomplete profile catalog (ADR-F067 D4).
    """
    profiles_dir = resolve_profiles_dir(settings)
    registry = load_profiles(profiles_dir, skill_registry=skill_registry)
    app.state.profile_registry = registry
    return registry


__all__ = ["install_profile_registry", "resolve_profiles_dir"]
