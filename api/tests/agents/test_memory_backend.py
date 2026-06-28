"""N0 gate (ADR-F049) — the native memory CompositeBackend over a langgraph Store.

The maintainer-ruled N0 gate: prove the SUBSTRATE, not the A5 recall *rate*
(that arrives at N2/N3). These tests run on an in-memory Store — no Postgres, no
model, CI-cheap — and assert:

- a note written to ``/memories/matter/`` under one conversation (thread) is
  readable under a DIFFERENT thread of the SAME matter (cross-thread persistence
  — the whole point of the substrate), and a DIFFERENT matter sees nothing
  (namespace isolation; cross-user/cross-matter safety);
- the company/practice tiers REFUSE agent writes (read-only at the storage
  layer, the backstop that survives subagent permission replacement);
- the route map is conditional on bound ids (a plain chat gets company+user only);
- ``/skills`` still resolves through the composite ``default`` (no regression);
- a missing Store degrades to today's backend value unchanged.
"""

from __future__ import annotations

from typing import Any, TypedDict

from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from app.agents.factory import build_deep_agent
from app.agents.memory_backend import (
    COMPANY_ROUTE,
    CONVERSATION_ROUTE,
    MATTER_ROUTE,
    PRACTICE_ROUTE,
    USER_ROUTE,
    AgentRuntimeContext,
    ReadOnlyStoreBackend,
    build_memory_backend,
)
from app.agents.skill_backend import SKILLS_ROOT, RegistrySkillBackend, reconstruct_skill_md
from tests.agents.fakes import ScriptedToolCallingModel, final_message, tool_call_message


class _State(TypedDict, total=False):
    result: Any


async def _drive(op: Any, ctx: AgentRuntimeContext, store: InMemoryStore) -> Any:
    """Run an async backend op inside a langgraph runtime carrying ``ctx``.

    A ``StoreBackend`` namespace callable reads ``rt.context`` via
    ``get_runtime()`` — which only resolves DURING graph execution. So every
    namespace-keyed op is driven through a one-node graph compiled with
    ``context_schema`` and invoked with ``context=ctx`` (the exact runner path).
    """

    async def node(_state: _State) -> _State:
        return {"result": await op()}

    sg: StateGraph = StateGraph(_State, context_schema=AgentRuntimeContext)
    sg.add_node("op", node)
    sg.add_edge(START, "op")
    sg.add_edge("op", END)
    graph = sg.compile(store=store)
    out = await graph.ainvoke({}, context=ctx)
    return out["result"]


def _content(read_result: Any) -> str:
    fd = getattr(read_result, "file_data", None)
    return fd["content"] if fd else ""


# -- the gate: cross-thread persistence + cross-matter isolation ---------------


async def test_matter_note_persists_across_threads_and_isolates_by_matter() -> None:
    store = InMemoryStore()
    backend = build_memory_backend(
        skills_backend=None,
        store=store,
        owner_id="owner-1",
        project_id="matter-A",
        practice_area_id=None,
        thread_id="thread-1",
    )

    # Write in thread-1.
    written = await _drive(
        lambda: backend.awrite("/memories/matter/note.md", "the answer is 42"),
        AgentRuntimeContext(owner_id="owner-1", project_id="matter-A", thread_id="thread-1"),
        store,
    )
    assert getattr(written, "error", None) is None

    # Read in a DIFFERENT thread of the SAME matter — present (cross-thread).
    same_matter = await _drive(
        lambda: backend.aread("/memories/matter/note.md"),
        AgentRuntimeContext(owner_id="owner-1", project_id="matter-A", thread_id="thread-2"),
        store,
    )
    assert same_matter.error is None
    assert "42" in _content(same_matter)

    # Read under a DIFFERENT matter — absent (namespace isolation).
    other_matter = await _drive(
        lambda: backend.aread("/memories/matter/note.md"),
        AgentRuntimeContext(owner_id="owner-1", project_id="matter-B", thread_id="thread-3"),
        store,
    )
    assert other_matter.error is not None


async def test_company_and_practice_refuse_writes_user_and_matter_allow() -> None:
    store = InMemoryStore()
    backend = build_memory_backend(
        skills_backend=None,
        store=store,
        owner_id="owner-1",
        project_id="matter-A",
        practice_area_id="area-X",
        thread_id="thread-1",
    )
    ctx = AgentRuntimeContext(
        owner_id="owner-1", project_id="matter-A", practice_area_id="area-X", thread_id="thread-1"
    )

    company = await _drive(lambda: backend.awrite("/memories/company/x.md", "nope"), ctx, store)
    practice = await _drive(lambda: backend.awrite("/memories/practice/x.md", "nope"), ctx, store)
    assert company.error is not None
    assert practice.error is not None

    user = await _drive(lambda: backend.awrite("/memories/user/x.md", "ok"), ctx, store)
    matter = await _drive(lambda: backend.awrite("/memories/matter/x.md", "ok"), ctx, store)
    assert user.error is None
    assert matter.error is None


# -- route map (conditional on bound ids) -------------------------------------


def test_route_map_plain_chat_is_company_and_user_only() -> None:
    backend = build_memory_backend(
        skills_backend=None,
        store=InMemoryStore(),
        owner_id="owner-1",
        project_id=None,
        practice_area_id=None,
        thread_id=None,
    )
    assert isinstance(backend, CompositeBackend)
    assert set(backend.routes) == {COMPANY_ROUTE, USER_ROUTE}
    assert isinstance(backend.default, StateBackend)


def test_route_map_full_matter_install_all_routes_with_readonly_tiers() -> None:
    backend = build_memory_backend(
        skills_backend=None,
        store=InMemoryStore(),
        owner_id="owner-1",
        project_id="matter-A",
        practice_area_id="area-X",
        thread_id="thread-1",
    )
    assert isinstance(backend, CompositeBackend)
    assert set(backend.routes) == {
        COMPANY_ROUTE,
        PRACTICE_ROUTE,
        USER_ROUTE,
        MATTER_ROUTE,
        CONVERSATION_ROUTE,
    }
    # company + practice are the read-only wrapper; user + matter are writable.
    assert isinstance(backend.routes[COMPANY_ROUTE], ReadOnlyStoreBackend)
    assert isinstance(backend.routes[PRACTICE_ROUTE], ReadOnlyStoreBackend)
    assert isinstance(backend.routes[USER_ROUTE], StoreBackend)
    assert not isinstance(backend.routes[USER_ROUTE], ReadOnlyStoreBackend)
    assert not isinstance(backend.routes[MATTER_ROUTE], ReadOnlyStoreBackend)


# -- degraded mode + skills coexistence ---------------------------------------


def test_no_store_degrades_to_skills_backend_unchanged() -> None:
    skills = RegistrySkillBackend({})
    # store=None → return the skills backend value UNCHANGED (today's behaviour).
    assert (
        build_memory_backend(
            skills_backend=skills,
            store=None,
            owner_id="o",
            project_id=None,
            practice_area_id=None,
            thread_id=None,
        )
        is skills
    )
    # skills off + no store → None (deepagents' default StateBackend, as today).
    assert (
        build_memory_backend(
            skills_backend=None,
            store=None,
            owner_id="o",
            project_id=None,
            practice_area_id=None,
            thread_id=None,
        )
        is None
    )


async def test_skills_resolve_through_composite_default() -> None:
    skill_md = reconstruct_skill_md("name: demo\ndescription: a demo skill", "the skill body")
    skills = RegistrySkillBackend({SKILLS_ROOT: {"demo": skill_md}})
    backend = build_memory_backend(
        skills_backend=skills,
        store=InMemoryStore(),
        owner_id="owner-1",
        project_id=None,
        practice_area_id=None,
        thread_id=None,
    )
    assert isinstance(backend, CompositeBackend)
    # /skills/* matches no memory route → falls to default (the skills backend).
    res = await backend.aread(f"{SKILLS_ROOT}/demo/SKILL.md")
    assert res.error is None
    assert "the skill body" in _content(res)


# -- the read-only wrapper in isolation (mutations short-circuit, never raise) -


async def test_readonly_store_backend_refuses_all_mutations() -> None:
    b = ReadOnlyStoreBackend(store=InMemoryStore(), namespace=lambda rt: ("company",))
    assert b.write("/x.md", "y").error is not None
    assert b.edit("/x.md", "a", "b").error is not None
    assert all(r.error is not None for r in b.upload_files([("/x.md", b"y")]))
    assert (await b.awrite("/x.md", "y")).error is not None
    assert (await b.aedit("/x.md", "a", "b")).error is not None
    assert all(r.error is not None for r in await b.aupload_files([("/x.md", b"y")]))


# -- end-to-end: the builtin write_file routes through create_deep_agent to the
#    Store (the regression guard that store=+context_schema= wire together and the
#    rt.context-keyed namespace resolves inside the real deepagents graph).


async def test_builtin_write_file_routes_through_deep_agent_to_store() -> None:
    store = InMemoryStore()
    backend = build_memory_backend(
        skills_backend=None,
        store=store,
        owner_id="owner-1",
        project_id="matter-A",
        practice_area_id=None,
        thread_id="thread-1",
    )
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "write_file",
                {"file_path": "/memories/matter/note.md", "content": "the answer is 42"},
            ),
            final_message("saved"),
        ]
    )
    agent = build_deep_agent(
        model=model,
        tools=[],
        system_prompt="test",
        store=store,
        context_schema=AgentRuntimeContext,
        backend=backend,
    )
    await agent.ainvoke(
        {"messages": [{"role": "user", "content": "save a note"}]},
        context=AgentRuntimeContext(
            owner_id="owner-1", project_id="matter-A", thread_id="thread-1"
        ),
    )
    # The write landed in the matter namespace — proving the builtin write_file
    # tool routed CompositeBackend -> StoreBackend -> store.aput keyed by rt.context.
    items = list(store.search(("matter", "matter-A")))
    assert any("note.md" in item.key for item in items)
    # Nothing leaked into a different matter's namespace.
    assert not list(store.search(("matter", "matter-B")))
