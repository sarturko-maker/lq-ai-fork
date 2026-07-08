"""Registry-backed virtual skills backend — UX-B-3/UX-B-4 (fork, ADR-F016/F017).

deepagents' ``SkillsMiddleware`` discovers skills by ``ls``-ing a *source*
directory in a :class:`~deepagents.backends.protocol.BackendProtocol` and
``download``-ing each ``SKILL.md``; the model then reads a skill's full
instructions on demand via the builtin ``read_file`` tool, which also goes
through the backend. This adapter presents the in-memory
:class:`~app.skills.registry.SkillRegistry` as such a backend — but exposes
**only explicit allow-lists of skill names**, never the whole library.

Why a backend over the registry instead of pointing deepagents at the
``/skills`` directory (ADR-F016, maintainer-ruled): one library, no
duplication (areas reference skills by name; nothing is copied per area),
**least privilege** (the builtin ``read_file``/``ls`` are NOT wrapped by the
``guarded_dispatch`` chokepoint — extending the guard to the full tool
universe is F1 — so the backend is the boundary: it is read-only, serves only
the allow-listed names, reaches no host filesystem and no matter data), and
**zero-copy per run** (the registry is already resident).

UX-B-4 (ADR-F017): the backend is **multi-source**. deepagents gives each
subagent its OWN ``SkillsMiddleware`` over its own source paths (custom
subagents do NOT inherit the parent's skills — skill discovery is isolated per
subagent), while the parent ``backend`` is shared only as the file-storage
substrate. So one :class:`RegistrySkillBackend` serves several virtual
sources: the area source ``/skills`` (the area's bound subset, as in UX-B-3)
plus, per skill-bearing subagent, ``/skills/subagents/<name>`` exposing that
subagent's (⊆ area) subset. Each source's tree is ``{source}/{name}/SKILL.md``;
the file body is reconstructed from the registry record's verbatim frontmatter
+ markdown body — the same bytes the loader read, so the middleware's own
frontmatter parse (which requires ``name`` to match the parent directory)
succeeds. ``ls`` of a source lists ONLY that source's names — a subagent never
sees the area catalogue in its prompt. Mutating operations
(``write``/``edit``/``upload``) return a read-only error; ``grep``/``glob``
return a graceful *unsupported* result (never raise — the deepagents async
wrappers do not catch a backend ``NotImplementedError``, so raising would crash
the whole run when a model reaches for those builtins) and steer the model to
``read_file``/``ls`` by path (progressive disclosure).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    PERMISSION_DENIED,
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

from app.skills.registry import SkillRegistry

# The area (main agent) source directory. Every bound skill lives directly
# beneath it as ``<name>/SKILL.md``.
SKILLS_ROOT = "/skills"
# Per-subagent source directories live under here as ``<subagent>/<name>/...``.
# Nested under SKILLS_ROOT, but the backend is fully virtual: ``ls(SKILLS_ROOT)``
# lists only the AREA's skill names, never this directory (ADR-F017).
_SUBAGENT_SOURCE_ROOT = "/skills/subagents"
_SKILL_FILE = "SKILL.md"
_READ_ONLY = "skills library is read-only"


def subagent_source_path(subagent_name: str) -> str:
    """The virtual source directory for a subagent's isolated skill subset."""
    return f"{_SUBAGENT_SOURCE_ROOT}/{subagent_name}"


def reconstruct_skill_md(raw_yaml: str, body: str) -> str:
    """Rebuild a ``SKILL.md`` from a registry record's frontmatter + body.

    The loader split the file into the verbatim YAML block (between the
    leading ``---`` delimiters) and the markdown body; re-joining them with
    the delimiters yields bytes the deepagents frontmatter parser accepts
    (``^---\\s*\\n(.*?)\\n---\\s*\\n``).
    """
    return f"---\n{raw_yaml.strip(chr(10))}\n---\n\n{body.lstrip(chr(10))}"


def resolve_skill_files(registry: SkillRegistry, names: list[str]) -> dict[str, str]:
    """Map each allow-listed name the registry KNOWS to its ``SKILL.md`` text.

    Names the registry no longer knows are dropped (registry is source of
    truth) — the same filter :func:`app.agents.area_agent.render_area_agent`
    applies, re-asserted here so a backend can never be built around a name
    with no content. Order/dedup is by the registry's sorted view for a
    deterministic listing.
    """
    out: dict[str, str] = {}
    for name in names:
        record = registry.get(name)
        if record is not None and name not in out:
            out[name] = reconstruct_skill_md(record.raw_yaml, record.body)
    return out


class RegistrySkillBackend(BackendProtocol):
    """Read-only backend serving allow-listed registry skills over N sources.

    ``sources`` maps a source directory path → {skill name → full ``SKILL.md``
    text}. Only those names, under their source, are visible; every other path
    is ``file_not_found``. Constructed per run by :func:`build_area_skill_wiring`
    (the area source + per-subagent sources).
    """

    def __init__(self, sources: Mapping[str, Mapping[str, str]]) -> None:
        # Normalise each source root; sort names per source for a stable ls()
        # (the prompt skill list mirrors that order).
        self._sources: dict[str, dict[str, str]] = {
            (root.rstrip("/") or "/"): {n: skills[n] for n in sorted(skills)}
            for root, skills in sources.items()
        }

    # -- name/path resolution ------------------------------------------------

    def _owner_for_md(self, file_path: str) -> tuple[str, str] | None:
        """``{source}/<name>/SKILL.md`` → (source, name), or None.

        Exact-parts match per source disambiguates nested roots: an area path
        (``/skills/<name>/SKILL.md``, 4 parts) only matches the 2-part
        ``/skills`` source; a subagent path (6 parts) only its 4-part source.
        """
        parts = PurePosixPath(file_path).parts
        if not parts or parts[-1] != _SKILL_FILE:
            return None
        for root, skills in self._sources.items():
            root_parts = PurePosixPath(root).parts
            if len(parts) == len(root_parts) + 2 and parts[: len(root_parts)] == root_parts:
                name = parts[len(root_parts)]
                if name in skills:
                    return root, name
        return None

    def _owner_for_dir(self, path: str) -> tuple[str, str] | None:
        """``{source}/<name>`` → (source, name), or None."""
        parts = PurePosixPath(path).parts
        for root, skills in self._sources.items():
            root_parts = PurePosixPath(root).parts
            if len(parts) == len(root_parts) + 1 and parts[: len(root_parts)] == root_parts:
                name = parts[-1]
                if name in skills:
                    return root, name
        return None

    # -- read path (the only operations the middleware + read_file use) ------

    def ls(self, path: str) -> LsResult:
        norm = path.rstrip("/") or "/"
        skills = self._sources.get(norm)
        if skills is not None:
            # A source directory: one entry per allowed skill directory. Only
            # this source's names — a subagent source never reveals the area's.
            return LsResult(
                entries=[FileInfo(path=f"{norm}/{name}", is_dir=True) for name in skills]
            )
        owner = self._owner_for_dir(norm)
        if owner is not None:
            root, name = owner
            content = self._sources[root][name]
            return LsResult(
                entries=[
                    FileInfo(
                        path=f"{root}/{name}/{_SKILL_FILE}",
                        is_dir=False,
                        size=len(content.encode("utf-8")),
                    )
                ]
            )
        return LsResult(error=FILE_NOT_FOUND)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        owner = self._owner_for_md(file_path)
        if owner is None:
            return ReadResult(error=FILE_NOT_FOUND)
        root, name = owner
        # Window by line BEFORE returning: the read_file tool numbers lines from
        # ``offset + 1`` and does NOT re-slice — it assumes the backend already
        # dropped the first ``offset`` lines and capped at ``limit`` (the
        # StateBackend.read / slice_read_response contract). Returning the whole
        # text would mislabel paginated reads and ignore ``limit``.
        lines = (
            self._sources[root][name]
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .splitlines(keepends=True)
        )
        if offset and offset >= len(lines):
            return ReadResult(
                error=f"Line offset {offset} exceeds file length ({len(lines)} lines)"
            )
        windowed = "".join(lines[offset : offset + limit])
        return ReadResult(file_data={"content": windowed, "encoding": "utf-8"})

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        out: list[FileDownloadResponse] = []
        for path in paths:
            owner = self._owner_for_md(path)
            if owner is None:
                out.append(FileDownloadResponse(path=path, content=None, error=FILE_NOT_FOUND))
            else:
                root, name = owner
                out.append(
                    FileDownloadResponse(
                        path=path, content=self._sources[root][name].encode("utf-8"), error=None
                    )
                )
        return out

    # -- search: unsupported, but never raises -------------------------------
    # deepagents' agrep/aglob wrap the sync method in to_thread and DO NOT catch
    # a backend NotImplementedError (only agrep catches TimeoutError), so the
    # protocol default raise would propagate out of the tools node and fail the
    # whole run when a model reaches for the builtin grep/glob. Return a graceful
    # error instead — read_file/ls by path is the intended access (ADR-F016).
    _SEARCH_UNSUPPORTED = (
        "search is not supported on the skills library; list skills with ls and "
        "read a skill by its path with read_file"
    )

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        return GrepResult(error=self._SEARCH_UNSUPPORTED)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return GlobResult(error=self._SEARCH_UNSUPPORTED)

    # -- mutations: refused (curated, read-only library) ---------------------

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_READ_ONLY)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=_READ_ONLY)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error=PERMISSION_DENIED) for path, _ in files]


@dataclass(frozen=True)
class SkillWiring:
    """The composition seam's skill wiring for one run (ADR-F017).

    ``backend`` is the one multi-source backend shared with subagents (or None
    when no skill resolves). ``main_sources`` is the area agent's ``skills=``
    argument (``[SKILLS_ROOT]`` or None). ``subagents`` is the declarative spec
    list with each ``skills`` field REWRITTEN from names → its source path (or
    the key dropped when nothing resolves).
    """

    backend: RegistrySkillBackend | None
    main_sources: list[str] | None
    subagents: list[dict[str, Any]] = field(default_factory=list)


def build_area_skill_wiring(
    registry: SkillRegistry | None,
    *,
    area_skill_names: list[str],
    subagents: list[dict[str, Any]],
    org_skill_files: Mapping[str, str] | None = None,
) -> SkillWiring:
    """Build the run's skill backend + sources + rewritten subagent specs.

    The area source ``/skills`` carries the area's resolved bound subset. Each
    subagent that declares skills gets its OWN source ``/skills/subagents/<name>``
    exposing only its (⊆ area) subset — deepagents' isolated per-subagent skill
    model (ADR-F017). A subagent skill name not in the area's resolved set is
    dropped (⊆-area + drift, the UX-B-3 non-fatal posture; PATCH rejects it at
    config time). When ``registry`` is None (skills off — the UX-B-1/2 baseline)
    nothing resolves AT ALL: ``org_skill_files`` is ignored along with the registry
    (org skills ARE skills — ADR-F067 keeps them off when the whole feature is off),
    the backend is None and subagent ``skills`` are stripped, so a stored name can
    never reach deepagents as a bogus source.

    ``org_skill_files`` maps an approved org-authored skill slug → its FULL served
    ``SKILL.md`` text (provenance banner already prefixed at serve time — ADR-F067
    D3.5). Optional, default ``{}``, and honoured ONLY when a registry is present
    (see the None-registry invariant above). Org texts ride the SAME in-memory source
    dict as registry skills, so everything downstream — the ⊆-area subagent subsetting,
    the sources map, the read-only :class:`RegistrySkillBackend` posture — is
    unchanged and applies to them identically. Precedence mirrors the inventory's
    no-shadowing rule: an org slug is seeded first, then the registry OVERWRITES it
    on any collision (shipped wins, D2). The caller only passes slugs the registry
    does not know, so in practice there is no overlap — the merge order is the
    belt-and-braces guarantee.
    """
    # registry None ⇒ skills off entirely; org skills fail closed with it (ADR-F067). Seed
    # org-authored snapshots first (only those actually bound to the area), then let the
    # registry overwrite on any slug collision — shipped wins (ADR-F067 D2).
    org_files = (org_skill_files or {}) if registry is not None else {}
    area_files: dict[str, str] = {n: org_files[n] for n in area_skill_names if n in org_files}
    if registry is not None:
        area_files.update(resolve_skill_files(registry, area_skill_names))
    sources: dict[str, dict[str, str]] = {}
    if area_files:
        sources[SKILLS_ROOT] = area_files

    rewritten: list[dict[str, Any]] = []
    for spec in subagents:
        spec = dict(spec)
        declared = spec.get("skills") or []
        # ⊆ area + drift: keep only names the area actually exposes.
        sub_files = {n: area_files[n] for n in declared if n in area_files}
        if sub_files:
            source = subagent_source_path(spec["name"])
            sources[source] = sub_files
            spec["skills"] = [source]
        else:
            spec.pop("skills", None)
        rewritten.append(spec)

    backend = RegistrySkillBackend(sources) if sources else None
    main_sources = [SKILLS_ROOT] if area_files else None
    return SkillWiring(backend=backend, main_sources=main_sources, subagents=rewritten)
