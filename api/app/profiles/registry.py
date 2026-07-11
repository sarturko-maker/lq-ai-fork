"""In-memory registry of shipped profile manifests (ADR-F067 D4, B-7a).

Unlike the skills registry, profiles are **shipped-static**: they are code,
loaded once at boot and never reloaded on a running process. So there is no
``Mutable*`` holder and no SIGHUP wiring — the API installs a single frozen
:class:`ProfileRegistry` on ``app.state.profile_registry`` and reads it
per-request. (Justified divergence from ``MutableSkillRegistry``; recorded in
the ADR-F067 B-7a addendum.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.profiles.schema import ProfileManifest


@dataclass(frozen=True)
class ProfileRecord:
    """One loaded profile: its parsed manifest plus the doctrine read verbatim
    from the sibling ``doctrine.md`` (``None`` for a ``blank`` profile, which
    ships no doctrine)."""

    manifest: ProfileManifest
    doctrine: str | None
    folder: Path


@dataclass(frozen=True)
class ProfileRegistry:
    """Immutable snapshot of all loaded profiles, keyed by ``name``."""

    records: dict[str, ProfileRecord]

    def names(self) -> list[str]:
        return sorted(self.records.keys())

    def get(self, name: str) -> ProfileRecord | None:
        return self.records.get(name)

    def list_records(self) -> list[ProfileRecord]:
        """Every record, sorted by name (stable order for the wizard picker)."""
        return [self.records[name] for name in self.names()]


__all__ = ["ProfileRecord", "ProfileRegistry"]
