"""Registry-backed virtual skills backend — UX-B-3 (ADR-F016).

The load-bearing security property: the backend serves ONLY the allow-listed
skill names and nothing else (least privilege over the unguarded builtin
read_file), is read-only, and reaches no host filesystem. These tests lock
that, plus the drift filter (a bound name the registry forgot is dropped) and
the deepagents middleware contract (its own loader parses what we serve).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.agents.skill_backend import (
    SKILLS_ROOT,
    RegistrySkillBackend,
    build_area_skill_wiring,
    reconstruct_skill_md,
    resolve_skill_files,
    subagent_source_path,
)

pytestmark = pytest.mark.unit


# --- a minimal duck-typed registry (the _FakeRegistry precedent) -----------


@dataclass
class _Rec:
    raw_yaml: str
    body: str


class _FakeRegistry:
    def __init__(self, records: dict[str, _Rec]) -> None:
        self._records = records

    def get(self, name: str) -> _Rec | None:
        return self._records.get(name)

    def names(self) -> list[str]:
        return sorted(self._records)


def _md(name: str, desc: str = "Use when X.", body: str = "# Title\nDo the thing.") -> str:
    return reconstruct_skill_md(f"name: {name}\ndescription: {desc}", body)


def _backend(*names: str) -> RegistrySkillBackend:
    """Single-source (area) backend — the UX-B-3 shape, now under one source."""
    return RegistrySkillBackend({SKILLS_ROOT: {n: _md(n) for n in names}})


# --- the read path ----------------------------------------------------------


def test_ls_root_lists_only_allowed_skill_dirs() -> None:
    b = _backend("nda-review", "contract-qa")
    result = b.ls(SKILLS_ROOT)
    assert result.error is None
    paths = sorted(e["path"] for e in result.entries or [])
    assert paths == [f"{SKILLS_ROOT}/contract-qa", f"{SKILLS_ROOT}/nda-review"]
    assert all(e.get("is_dir") for e in result.entries or [])


def test_ls_skill_dir_lists_its_skill_md() -> None:
    b = _backend("nda-review")
    result = b.ls(f"{SKILLS_ROOT}/nda-review")
    assert result.error is None
    assert [e["path"] for e in result.entries or []] == [f"{SKILLS_ROOT}/nda-review/SKILL.md"]


def test_ls_unbound_dir_is_file_not_found() -> None:
    b = _backend("nda-review")
    assert b.ls(f"{SKILLS_ROOT}/evil").error == "file_not_found"


def test_read_bound_skill_returns_full_text() -> None:
    b = _backend("nda-review")
    result = b.read(f"{SKILLS_ROOT}/nda-review/SKILL.md")
    assert result.error is None
    assert result.file_data is not None
    assert "name: nda-review" in result.file_data["content"]
    assert result.file_data["encoding"] == "utf-8"


def test_read_windows_by_offset_and_limit() -> None:
    """read() slices lines before returning — the read_file tool numbers from
    offset+1 and does not re-slice (the StateBackend contract)."""
    md = reconstruct_skill_md("name: nda-review\ndescription: d", "L1\nL2\nL3\nL4\nL5")
    b = RegistrySkillBackend({SKILLS_ROOT: {"nda-review": md}})
    path = f"{SKILLS_ROOT}/nda-review/SKILL.md"
    full = b.read(path).file_data["content"]  # type: ignore[index]
    lines = full.splitlines()
    # offset past start + a small limit returns exactly that window.
    windowed = b.read(path, offset=2, limit=2).file_data["content"]  # type: ignore[index]
    assert windowed.splitlines() == lines[2:4]
    # offset beyond EOF is an honest error, not an empty success.
    assert b.read(path, offset=9999).error is not None


def test_read_unbound_skill_is_file_not_found() -> None:
    """The isolation property: a name not in the allow-list is unreachable."""
    b = _backend("nda-review")
    assert b.read(f"{SKILLS_ROOT}/contract-qa/SKILL.md").error == "file_not_found"
    # No path traversal / host-FS escape, either.
    assert b.read("/etc/passwd").error == "file_not_found"
    assert b.read(f"{SKILLS_ROOT}/../etc/passwd").error == "file_not_found"


def test_download_files_mixed_hits_and_misses() -> None:
    b = _backend("nda-review")
    hit, miss = b.download_files(
        [f"{SKILLS_ROOT}/nda-review/SKILL.md", f"{SKILLS_ROOT}/contract-qa/SKILL.md"]
    )
    assert hit.error is None and hit.content is not None and b"name: nda-review" in hit.content
    assert miss.error == "file_not_found" and miss.content is None


# --- read-only (curated library) --------------------------------------------


def test_mutations_are_refused() -> None:
    b = _backend("nda-review")
    assert b.write(f"{SKILLS_ROOT}/x/SKILL.md", "y").error == "skills library is read-only"
    assert (
        b.edit(f"{SKILLS_ROOT}/nda-review/SKILL.md", "a", "b").error
        == "skills library is read-only"
    )
    uploads = b.upload_files([(f"{SKILLS_ROOT}/x/SKILL.md", b"y")])
    assert uploads[0].error == "permission_denied"


def test_search_is_unsupported_but_never_raises() -> None:
    # deepagents' agrep/aglob do not catch a backend NotImplementedError, so the
    # protocol default raise would crash the whole run when a model calls the
    # builtin grep/glob. Lock the graceful error on BOTH the sync method and the
    # async wrapper the filesystem middleware actually invokes.
    b = _backend("nda-review")
    assert b.grep("indemnify").error is not None
    assert b.grep("indemnify").matches in (None, [])
    assert b.glob("**/*.md").error is not None

    async def _via_middleware_wrappers() -> tuple[object, object]:
        return (await b.agrep("indemnify"), await b.aglob("**/*.md"))

    grep_res, glob_res = asyncio.run(_via_middleware_wrappers())
    assert grep_res.error is not None  # type: ignore[attr-defined]
    assert glob_res.error is not None  # type: ignore[attr-defined]


# --- resolve / build (the registry filter + drift) --------------------------


def test_resolve_skill_files_drops_unknown_names() -> None:
    registry = _FakeRegistry({"nda-review": _Rec("name: nda-review\ndescription: d", "body")})
    resolved = resolve_skill_files(registry, ["nda-review", "ghost-skill"])  # type: ignore[arg-type]
    assert set(resolved) == {"nda-review"}


def test_wiring_backend_none_when_nothing_resolves() -> None:
    registry = _FakeRegistry({"nda-review": _Rec("name: nda-review\ndescription: d", "body")})
    assert build_area_skill_wiring(registry, area_skill_names=[], subagents=[]).backend is None  # type: ignore[arg-type]
    assert (
        build_area_skill_wiring(registry, area_skill_names=["ghost"], subagents=[]).backend is None  # type: ignore[arg-type]
    )


def test_wiring_area_source_serves_resolved_subset() -> None:
    registry = _FakeRegistry(
        {
            "nda-review": _Rec("name: nda-review\ndescription: d", "b1"),
            "contract-qa": _Rec("name: contract-qa\ndescription: d", "b2"),
        }
    )
    wiring = build_area_skill_wiring(
        registry,
        area_skill_names=["nda-review", "ghost"],
        subagents=[],  # type: ignore[arg-type]
    )
    assert wiring.backend is not None
    paths = sorted(e["path"] for e in (wiring.backend.ls(SKILLS_ROOT).entries or []))
    assert paths == [f"{SKILLS_ROOT}/nda-review"]  # ghost dropped


# --- multi-source isolation (UX-B-4, ADR-F017) ------------------------------


def test_multi_source_isolation_area_vs_subagent() -> None:
    """Each source lists ONLY its own names; a subagent source is invisible to
    the area source, and vice versa (deepagents' per-subagent skill isolation)."""
    sub = subagent_source_path("document-researcher")
    b = RegistrySkillBackend(
        {
            SKILLS_ROOT: {"contract-qa": _md("contract-qa"), "nda-review": _md("nda-review")},
            sub: {"nda-review": _md("nda-review")},
        }
    )
    # The area source lists its two names — and NOT the nested subagent dir.
    area_paths = sorted(e["path"] for e in (b.ls(SKILLS_ROOT).entries or []))
    assert area_paths == [f"{SKILLS_ROOT}/contract-qa", f"{SKILLS_ROOT}/nda-review"]
    assert all("subagents" not in p for p in area_paths)
    # The subagent source lists ONLY its own (⊆ area) subset.
    sub_paths = sorted(e["path"] for e in (b.ls(sub).entries or []))
    assert sub_paths == [f"{sub}/nda-review"]
    # Reads resolve per source; a name absent from a given source is not found
    # under it even though it exists under another source.
    assert b.read(f"{sub}/nda-review/SKILL.md").error is None
    assert b.read(f"{sub}/contract-qa/SKILL.md").error == "file_not_found"
    assert b.read(f"{SKILLS_ROOT}/contract-qa/SKILL.md").error is None


def test_subagent_source_path_is_under_skills_subagents() -> None:
    assert subagent_source_path("document-researcher") == "/skills/subagents/document-researcher"


# --- build_area_skill_wiring (the composition seam) -------------------------


def _wiring_registry() -> _FakeRegistry:
    return _FakeRegistry(
        {
            "contract-qa": _Rec("name: contract-qa\ndescription: d", "b1"),
            "nda-review": _Rec("name: nda-review\ndescription: d", "b2"),
            "msa-review-saas": _Rec("name: msa-review-saas\ndescription: d", "b3"),
        }
    )


def test_wiring_area_only_no_subagents() -> None:
    wiring = build_area_skill_wiring(
        _wiring_registry(),
        area_skill_names=["contract-qa", "nda-review"],
        subagents=[],  # type: ignore[arg-type]
    )
    assert wiring.main_sources == [SKILLS_ROOT]
    assert wiring.subagents == []
    assert wiring.backend is not None
    assert sorted(e["path"] for e in (wiring.backend.ls(SKILLS_ROOT).entries or [])) == [
        f"{SKILLS_ROOT}/contract-qa",
        f"{SKILLS_ROOT}/nda-review",
    ]


def test_wiring_subagent_gets_its_own_source() -> None:
    sub = {
        "name": "document-researcher",
        "description": "d",
        "system_prompt": "p",
        "skills": ["nda-review"],
    }
    wiring = build_area_skill_wiring(
        _wiring_registry(),
        area_skill_names=["contract-qa", "nda-review"],
        subagents=[sub],  # type: ignore[arg-type]
    )
    src = subagent_source_path("document-researcher")
    # The subagent spec's skills (names) are rewritten to its source path.
    assert wiring.subagents[0]["skills"] == [src]
    # The backend serves the subagent's isolated subset under that source.
    assert wiring.backend is not None
    assert [e["path"] for e in (wiring.backend.ls(src).entries or [])] == [f"{src}/nda-review"]
    # The original spec dict is NOT mutated (composition rebuilds).
    assert sub["skills"] == ["nda-review"]


def test_wiring_drops_subagent_skill_outside_area() -> None:
    """⊆-area + drift: a subagent name not in the area's resolved set is dropped,
    and a subagent left with nothing loses its skills key entirely."""
    sub = {
        "name": "x",
        "description": "d",
        "system_prompt": "p",
        "skills": ["nda-review", "msa-review-saas"],
    }  # msa-review-saas NOT area-bound below
    wiring = build_area_skill_wiring(
        _wiring_registry(),
        area_skill_names=["nda-review"],
        subagents=[sub],  # type: ignore[arg-type]
    )
    src = subagent_source_path("x")
    assert wiring.subagents[0]["skills"] == [src]
    assert [e["path"] for e in (wiring.backend.ls(src).entries or [])] == [f"{src}/nda-review"]

    sub2 = {"name": "y", "description": "d", "system_prompt": "p", "skills": ["msa-review-saas"]}
    wiring2 = build_area_skill_wiring(
        _wiring_registry(),
        area_skill_names=["nda-review"],
        subagents=[sub2],  # type: ignore[arg-type]
    )
    assert "skills" not in wiring2.subagents[0]  # nothing resolved → key dropped


def test_wiring_registry_none_strips_all_skills() -> None:
    """Skills off (no registry): backend None, subagent skills stripped so a
    stored name can never reach deepagents as a bogus source."""
    sub = {"name": "x", "description": "d", "system_prompt": "p", "skills": ["nda-review"]}
    wiring = build_area_skill_wiring(
        None,
        area_skill_names=["nda-review"],
        subagents=[sub],  # type: ignore[arg-type]
    )
    assert wiring.backend is None
    assert wiring.main_sources is None
    assert "skills" not in wiring.subagents[0]


def test_deepagents_loader_parses_our_backend() -> None:
    """deepagents' own skill loader (sync + async) accepts our backend —
    ls + download_files + frontmatter parse round-trip to name/description."""
    from deepagents.middleware.skills import (
        _alist_skills_with_errors,
        _list_skills_with_errors,
    )

    b = _backend("nda-review", "contract-qa")
    sync_skills, sync_err = _list_skills_with_errors(b, SKILLS_ROOT)
    assert sync_err is None
    assert sorted(s["name"] for s in sync_skills) == ["contract-qa", "nda-review"]

    async_skills, async_err = asyncio.run(_alist_skills_with_errors(b, SKILLS_ROOT))
    assert async_err is None
    assert sorted(s["name"] for s in async_skills) == ["contract-qa", "nda-review"]
