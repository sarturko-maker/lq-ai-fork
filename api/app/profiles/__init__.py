"""Shipped agent-profile manifests — ADR-F067 D4 (B-7a).

Public surface:

* :class:`ProfileManifest` / :class:`ProfileBindings` — the ``profile.yaml`` schema.
* :class:`ProfileRegistry` / :class:`ProfileRecord` — the in-memory (shipped-static)
  registry installed at ``app.state.profile_registry``.
* :func:`load_profiles` / :class:`ProfileLoadError` — the fail-loud loader.
* :func:`install_profile_registry` / :func:`resolve_profiles_dir` — the API-process
  bootstrap (wired in the ``app/main.py`` lifespan, after the skill registry).
"""

from __future__ import annotations

from app.profiles.bootstrap import install_profile_registry, resolve_profiles_dir
from app.profiles.loader import ProfileLoadError, load_profiles
from app.profiles.registry import ProfileRecord, ProfileRegistry
from app.profiles.schema import ProfileBindings, ProfileKind, ProfileManifest, UnitLabel

__all__ = [
    "ProfileBindings",
    "ProfileKind",
    "ProfileLoadError",
    "ProfileManifest",
    "ProfileRecord",
    "ProfileRegistry",
    "UnitLabel",
    "install_profile_registry",
    "load_profiles",
    "resolve_profiles_dir",
]
