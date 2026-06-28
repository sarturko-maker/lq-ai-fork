"""The per-run native memory backend — deepagents ``CompositeBackend`` over the
langgraph ``Store`` (F2 N0, ADR-F049).

CLAUDE.md's four-level memory model (company / practice / user / matter) runs on
the framework's memory tier: the agent's builtin filesystem tools
(``ls``/``read_file``/``write_file``/``edit_file``, provided unconditionally by
deepagents' ``FilesystemMiddleware``) are routed by path prefix to ``StoreBackend``
namespaces in the langgraph ``Store`` (:mod:`app.agents.store`). Because the
``Store`` is keyed only by the namespace tuple (NOT by ``thread_id`` — that is the
*checkpointer's* concern), a note the agent writes to ``/memories/matter/…`` in one
conversation is readable in another conversation of the **same matter** —
cross-thread persistence (verified live against deepagents 0.6.8 / langgraph 1.2.6).

Route layout (each route's namespace is keyed via ``rt.context`` — see
:class:`AgentRuntimeContext`):

| route                     | namespace                          | mode       |
|---------------------------|------------------------------------|------------|
| ``/memories/company/``    | ``("company",)``                   | read-only  |
| ``/memories/practice/``   | ``("practice", practice_area_id)`` | read-only  |
| ``/memories/user/``       | ``("user", owner_id)``             | read-write |
| ``/memories/matter/``     | ``("matter", project_id)``         | read-write |
| ``/conversation_history/``| ``("conversation", thread_id)``    | read-write |

- **company/practice are read-only** (curated; the prompt-injection / untrusted-
  input boundary — CLAUDE.md). The guard is a storage-level
  :class:`ReadOnlyStoreBackend`, NOT a ``FilesystemPermission`` rule, because
  deepagents subagent permissions *replace* the parent's (so a permission rule
  would not survive into a subagent; the storage wrapper always does).
- **No ``org_id`` exists** (single-tenant; CLAUDE.md blocker #5). The isolation
  segment is the existing owner key (``owner_id`` = ``run.user_id``); a run can
  only ever resolve its OWN owner-checked ``project_id`` (composition asserts
  ``Project.owner_id == run.user_id``), so no run can name another user's matter.
- **Routes are conditional**: only those whose id is bound are installed (a plain
  chat with no matter/area gets ``company`` + ``user`` only). ``/conversation_history/``
  is installed at N0 but **unwritten** until N2 (``SummarizationMiddleware`` offload).
- **Filter-only at N0** (the ``Store`` carries no semantic index); the existing
  skills backend is the CompositeBackend ``default`` so ``/skills`` is unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.protocol import (
    PERMISSION_DENIED,
    BackendProtocol,
    EditResult,
    FileUploadResponse,
    WriteResult,
)

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore

# CompositeBackend matches the longest route prefix; a path under no route falls
# to ``default`` (the skills backend / StateBackend). Trailing slash so e.g.
# ``/memories/matter/notes.md`` matches the matter route, never a broader one.
COMPANY_ROUTE = "/memories/company/"
PRACTICE_ROUTE = "/memories/practice/"
USER_ROUTE = "/memories/user/"
MATTER_ROUTE = "/memories/matter/"
CONVERSATION_ROUTE = "/conversation_history/"

_READ_ONLY = "this memory tier is curated and read-only to the agent"


@dataclass(frozen=True)
class AgentRuntimeContext:
    """The graph runtime context (``rt.context``) that keys the memory namespaces.

    Passed BOTH as ``context=`` at the ``astream_events`` invoke AND, via its
    type, as ``context_schema=`` to ``create_deep_agent`` — both are required or
    ``rt.context`` stays empty and every namespace callable raises (the single
    most load-bearing N0 wiring detail; verified against our pins). Every id is a
    string (UUID / key) so it passes langgraph's namespace-component validator
    (``^[A-Za-z0-9\\-_.@+:~]+$``); ``None`` only ever appears for an id whose
    route is NOT installed, so a namespace callable never sees a ``None`` segment.
    """

    owner_id: str | None = None
    project_id: str | None = None
    practice_area_id: str | None = None
    thread_id: str | None = None


class ReadOnlyStoreBackend(StoreBackend):
    """A ``StoreBackend`` that refuses agent writes — the company/practice tiers.

    Reads delegate to ``StoreBackend`` unchanged; every mutation (sync + async)
    returns an error result. Mirrors :class:`RegistrySkillBackend`'s discipline:
    return an error, **never raise** — deepagents' async tool wrappers do not
    catch a backend exception, so a raise would crash the whole run when a model
    reaches for ``write_file``/``edit_file`` on a read-only path.
    """

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_READ_ONLY)

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        return EditResult(error=_READ_ONLY)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error=PERMISSION_DENIED) for path, _ in files]

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_READ_ONLY)

    async def aedit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        return EditResult(error=_READ_ONLY)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error=PERMISSION_DENIED) for path, _ in files]


# -- namespace callables (receive the graph Runtime; read rt.context) ----------
# A callable is only ever invoked for a route that build_memory_backend installed,
# and a route is installed only when its id is bound — so the read is never None.


def _company_ns(rt: Any) -> tuple[str, ...]:
    # Org-global by design (single-tenant; no org_id) — ignores rt deliberately;
    # keeps the (rt) -> tuple shape so the route table treats all five uniformly.
    return ("company",)


def _practice_ns(rt: Any) -> tuple[str, ...]:
    return ("practice", rt.context.practice_area_id)


def _user_ns(rt: Any) -> tuple[str, ...]:
    return ("user", rt.context.owner_id)


def _matter_ns(rt: Any) -> tuple[str, ...]:
    return ("matter", rt.context.project_id)


def _conversation_ns(rt: Any) -> tuple[str, ...]:
    return ("conversation", rt.context.thread_id)


def build_memory_backend(
    *,
    skills_backend: BackendProtocol | None,
    store: BaseStore | None,
    owner_id: str | None,
    project_id: str | None,
    practice_area_id: str | None,
    thread_id: str | None,
) -> BackendProtocol | None:
    """Compose the run's ``CompositeBackend``: skills as ``default`` + memory routes.

    Returns the existing ``skills_backend`` UNCHANGED (possibly ``None``) when no
    ``store`` is available — i.e. exactly today's backend value, so a degraded
    Store (init failure) never changes agent behaviour. Otherwise the skills
    backend (or a fresh ``StateBackend`` when skills are off) is the composite
    ``default`` — preserving ``/skills`` resolution and today's scratch-write
    semantics — and the ``/memories/*`` (+ ``/conversation_history/``) routes are
    added for whichever ids are bound.
    """
    if store is None:
        # No native substrate (degraded / not yet wired) — behave as before N0.
        return skills_backend

    default: BackendProtocol = skills_backend if skills_backend is not None else StateBackend()
    routes: dict[str, BackendProtocol] = {
        # owner_id (run.user_id) is always present for a real run.
        COMPANY_ROUTE: ReadOnlyStoreBackend(store=store, namespace=_company_ns),
        USER_ROUTE: StoreBackend(store=store, namespace=_user_ns),
    }
    if practice_area_id is not None:
        routes[PRACTICE_ROUTE] = ReadOnlyStoreBackend(store=store, namespace=_practice_ns)
    if project_id is not None:
        routes[MATTER_ROUTE] = StoreBackend(store=store, namespace=_matter_ns)
    if thread_id is not None:
        # Installed but unwritten at N0; N2's SummarizationMiddleware fills it.
        routes[CONVERSATION_ROUTE] = StoreBackend(store=store, namespace=_conversation_ns)
    return CompositeBackend(default, routes)
