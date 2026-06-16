"""Registry-backed virtual skills backend — UX-B-3 (fork, ADR-F016).

deepagents' ``SkillsMiddleware`` discovers skills by ``ls``-ing a *source*
directory in a :class:`~deepagents.backends.protocol.BackendProtocol` and
``download``-ing each ``SKILL.md``; the model then reads a skill's full
instructions on demand via the builtin ``read_file`` tool, which also goes
through the backend. This adapter presents the in-memory
:class:`~app.skills.registry.SkillRegistry` as such a backend — but exposes
**only an explicit allow-list of skill names** (the practice area's bound
subset), never the whole library.

Why a backend over the registry instead of pointing deepagents at the
``/skills`` directory (ADR-F016, maintainer-ruled): one library, no
duplication (areas reference skills by name; nothing is copied per area),
**least privilege** (the builtin ``read_file``/``ls`` are NOT wrapped by the
``guarded_dispatch`` chokepoint — extending the guard to the full tool
universe is F1 — so the backend is the boundary: it is read-only, serves only
the allow-listed names, reaches no host filesystem and no matter data), and
**zero-copy per run** (the registry is already resident). A bound name the
registry no longer knows is simply absent here — the drift gap closes
structurally.

The virtual tree is ``{root}/{name}/SKILL.md`` per allowed skill. The file
body is reconstructed from the registry record's verbatim frontmatter +
markdown body — the same bytes the loader read, so the middleware's own
frontmatter parse (which requires ``name`` to match the parent directory)
succeeds. Mutating operations (``write``/``edit``/``upload``) return a
read-only error; ``grep``/``glob`` inherit the protocol default (unsupported)
— progressive disclosure steers the model to ``read_file`` by path.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath

from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    PERMISSION_DENIED,
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    LsResult,
    ReadResult,
    WriteResult,
)

from app.skills.registry import SkillRegistry

# The virtual source directory the middleware is pointed at. One source is
# enough — every bound skill lives directly beneath it as ``<name>/SKILL.md``.
SKILLS_ROOT = "/skills"
_SKILL_FILE = "SKILL.md"
_READ_ONLY = "skills library is read-only"


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
    """Read-only backend serving an allow-listed subset of registry skills.

    ``skills`` maps skill name → full ``SKILL.md`` text. Only these names are
    visible; every other path is ``file_not_found``. Constructed per run by
    :func:`build_area_skill_backend` from a registry snapshot + the area's
    bound names.
    """

    def __init__(self, skills: Mapping[str, str], *, root: str = SKILLS_ROOT) -> None:
        self._root = root.rstrip("/") or "/"
        # Sorted for a stable ls() ordering (the prompt skill list mirrors it).
        self._skills = {name: skills[name] for name in sorted(skills)}

    # -- name/path resolution ------------------------------------------------

    def _skill_md_path(self, name: str) -> str:
        return f"{self._root}/{name}/{_SKILL_FILE}"

    def _name_from_md_path(self, file_path: str) -> str | None:
        """``{root}/<name>/SKILL.md`` → ``<name>`` (or None if shape/name miss)."""
        parts = PurePosixPath(file_path).parts
        root_parts = PurePosixPath(self._root).parts
        # Expect root parts + (<name>, "SKILL.md").
        if len(parts) != len(root_parts) + 2:
            return None
        if parts[: len(root_parts)] != root_parts or parts[-1] != _SKILL_FILE:
            return None
        name = parts[len(root_parts)]
        return name if name in self._skills else None

    def _name_from_dir_path(self, path: str) -> str | None:
        """``{root}/<name>`` → ``<name>`` (or None)."""
        parts = PurePosixPath(path).parts
        root_parts = PurePosixPath(self._root).parts
        if len(parts) != len(root_parts) + 1:
            return None
        if parts[: len(root_parts)] != root_parts:
            return None
        name = parts[-1]
        return name if name in self._skills else None

    # -- read path (the only operations the middleware + read_file use) ------

    def ls(self, path: str) -> LsResult:
        norm = path.rstrip("/") or "/"
        if norm == self._root:
            # The source directory: one entry per allowed skill directory.
            entries: list[FileInfo] = [
                FileInfo(path=f"{self._root}/{name}", is_dir=True) for name in self._skills
            ]
            return LsResult(entries=entries)
        name = self._name_from_dir_path(norm)
        if name is not None:
            content = self._skills[name]
            return LsResult(
                entries=[
                    FileInfo(
                        path=self._skill_md_path(name),
                        is_dir=False,
                        size=len(content.encode("utf-8")),
                    )
                ]
            )
        return LsResult(error=FILE_NOT_FOUND)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        name = self._name_from_md_path(file_path)
        if name is None:
            return ReadResult(error=FILE_NOT_FOUND)
        # Window by line BEFORE returning: the read_file tool numbers lines from
        # ``offset + 1`` and does NOT re-slice — it assumes the backend already
        # dropped the first ``offset`` lines and capped at ``limit`` (the
        # StateBackend.read / slice_read_response contract). Returning the whole
        # text would mislabel paginated reads and ignore ``limit``.
        lines = (
            self._skills[name].replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
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
            name = self._name_from_md_path(path)
            if name is None:
                out.append(FileDownloadResponse(path=path, content=None, error=FILE_NOT_FOUND))
            else:
                out.append(
                    FileDownloadResponse(
                        path=path, content=self._skills[name].encode("utf-8"), error=None
                    )
                )
        return out

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


def build_area_skill_backend(
    registry: SkillRegistry, names: list[str]
) -> RegistrySkillBackend | None:
    """Build a backend exposing the area's bound skills, or None if none resolve.

    ``names`` is the area's ``practice_area_skills`` set; the registry filters
    it to known skills (drift). Returns None when nothing resolves so the
    composition point can skip wiring skills entirely — the qualified default
    graph (no skills source) is then unchanged.
    """
    skills = resolve_skill_files(registry, names)
    if not skills:
        return None
    return RegistrySkillBackend(skills)
