"""N2 gate (ADR-F049) — the conversation-history offload lands in the langgraph Store.

The N2 thesis, locked deterministically (no Postgres, no live model, CI-cheap):
deepagents' default ``SummarizationMiddleware`` — the one ``create_deep_agent``
always installs (graph.py: ``create_summarization_middleware(model, backend)``) —
offloads evicted history to ``/conversation_history/{thread_id}.md``, which the N0
``CompositeBackend`` (:mod:`app.agents.memory_backend`) routes verbatim into the
Store under namespace ``("conversation", thread_id)``. So a long conversation's
transcript persists in the Store and the agent recalls it via the path the
summary message embeds (a normal builtin ``read_file``).

These tests construct the **real** deepagents middleware over our **real**
``build_memory_backend`` composite + an ``InMemoryStore`` and drive its real
``_aoffload_to_backend`` method through a langgraph runtime (the offload path's
``_get_thread_id`` reads ``get_config()`` and the route's namespace callable reads
``rt.context`` — both resolve only DURING graph execution, the exact runner path).
They are a **drift-guard**: if deepagents changes ``artifacts_root`` handling, the
offload path, or the ``StoreBackend`` mapping, the routing test fails loudly
instead of silently orphaning transcripts.

Scope: the offload MECHANISM + routing. That ``create_deep_agent`` wires this
default middleware over our backend is a structural fact (graph.py) + is exercised
end-to-end by the provider-marked live A6 scenario (``test_track_a_eval.py``);
the recall *rate* is a finding there (ADR-F015), not asserted here.
"""

from __future__ import annotations

from typing import Any, TypedDict

from deepagents.middleware.summarization import create_summarization_middleware
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from app.agents.memory_backend import (
    CONVERSATION_ROUTE,
    AgentRuntimeContext,
    build_memory_backend,
)

_THREAD = "thread-1"


class _State(TypedDict, total=False):
    result: Any


def _backend(store: InMemoryStore, *, thread_id: str | None = _THREAD) -> Any:
    """Our N0 composite over ``store``, with the /conversation_history/ route on."""
    return build_memory_backend(
        skills_backend=None,
        store=store,
        owner_id="owner-1",
        project_id="matter-A",
        practice_area_id=None,
        thread_id=thread_id,
    )


def _middleware(backend: Any) -> Any:
    """The deepagents default summariser, exactly as ``create_deep_agent`` builds it
    (graph.py: ``create_summarization_middleware(model, backend)``). The fake model
    is never called — these tests drive the offload method directly."""
    model = GenericFakeChatModel(messages=iter([]))
    return create_summarization_middleware(model, backend)


async def _drive(op: Any, ctx: AgentRuntimeContext, store: InMemoryStore, *, thread_id: str) -> Any:
    """Run an async backend/offload op inside a langgraph runtime.

    The offload's ``_get_thread_id`` reads ``get_config().configurable.thread_id``
    and the route's namespace callable reads ``rt.context`` via ``get_runtime()`` —
    both resolve only during graph execution, so every op is driven through a
    one-node graph compiled with ``context_schema`` + a checkpointer and invoked
    with ``context=`` and a ``thread_id`` config (the exact runner wiring).
    """

    async def node(_state: _State) -> _State:
        return {"result": await op()}

    sg: StateGraph = StateGraph(_State, context_schema=AgentRuntimeContext)
    sg.add_node("op", node)
    sg.add_edge(START, "op")
    sg.add_edge("op", END)
    graph = sg.compile(store=store, checkpointer=InMemorySaver())
    out = await graph.ainvoke({}, config={"configurable": {"thread_id": thread_id}}, context=ctx)
    return out["result"]


def _content(read_result: Any) -> str:
    fd = getattr(read_result, "file_data", None)
    return fd["content"] if fd else ""


def _ctx(thread_id: str = _THREAD) -> AgentRuntimeContext:
    return AgentRuntimeContext(owner_id="owner-1", project_id="matter-A", thread_id=thread_id)


# -- the drift-guard: artifacts_root '/' -> the offload path hits our route ----


def test_offload_path_prefix_matches_the_conversation_route() -> None:
    """The default middleware's offload target resolves to the N0 Store route.

    Our composite leaves ``artifacts_root='/'`` (build_memory_backend passes none),
    so the middleware computes ``_history_path_prefix == '/conversation_history'``
    and offloads to ``/conversation_history/{thread}.md`` — under
    ``CONVERSATION_ROUTE``. Breaks loudly if deepagents changes artifacts_root
    handling or the offload path (the orphaned-transcript regression).
    """
    store = InMemoryStore()
    backend = _backend(store)
    assert getattr(backend, "artifacts_root", None) == "/"
    mw = _middleware(backend)
    assert mw._history_path_prefix == "/conversation_history"
    assert f"{mw._history_path_prefix}/x.md".startswith(CONVERSATION_ROUTE)
    # The middleware offloads to OUR composite (not some default backend).
    assert mw._backend is backend


# -- the real offload method lands in the Store under the conversation namespace --


async def test_offload_lands_in_store_under_conversation_namespace() -> None:
    store = InMemoryStore()
    backend = _backend(store)
    mw = _middleware(backend)

    path = await _drive(
        lambda: mw._aoffload_to_backend(backend, [HumanMessage("q1"), AIMessage("a1")]),
        _ctx(),
        store,
        thread_id=_THREAD,
    )
    assert path == f"/conversation_history/{_THREAD}.md"

    items = list(store.search(("conversation", _THREAD)))
    assert len(items) == 1
    # The Store key is the route-stripped path; the namespace segment is the
    # thread id — both carry str(thread_id), so file name and namespace agree
    # (the tidy path the degraded-mode edge would lose; HANDOFF/ADR-F049 addendum).
    assert items[0].key == f"/{_THREAD}.md"
    assert path.endswith(items[0].key)
    content = items[0].value["content"]
    assert "q1" in content and "a1" in content
    assert "## Summarized" in content


async def test_second_offload_appends_to_a_single_key() -> None:
    store = InMemoryStore()
    backend = _backend(store)
    mw = _middleware(backend)

    await _drive(
        lambda: mw._aoffload_to_backend(backend, [HumanMessage("q1"), AIMessage("a1")]),
        _ctx(),
        store,
        thread_id=_THREAD,
    )
    await _drive(
        lambda: mw._aoffload_to_backend(backend, [HumanMessage("q2"), AIMessage("a2")]),
        _ctx(),
        store,
        thread_id=_THREAD,
    )

    items = list(store.search(("conversation", _THREAD)))
    assert len(items) == 1  # appended to the same file, not a second key
    content = items[0].value["content"]
    assert content.count("## Summarized") == 2
    assert all(turn in content for turn in ("q1", "a1", "q2", "a2"))


async def test_offload_is_thread_isolated() -> None:
    store = InMemoryStore()
    backend = _backend(store)
    mw = _middleware(backend)

    await _drive(
        lambda: mw._aoffload_to_backend(backend, [HumanMessage("secret-1")]),
        _ctx("thread-1"),
        store,
        thread_id="thread-1",
    )
    await _drive(
        lambda: mw._aoffload_to_backend(backend, [HumanMessage("secret-2")]),
        _ctx("thread-2"),
        store,
        thread_id="thread-2",
    )

    one = list(store.search(("conversation", "thread-1")))
    two = list(store.search(("conversation", "thread-2")))
    assert len(one) == 1 and len(two) == 1
    assert "secret-1" in one[0].value["content"] and "secret-2" not in one[0].value["content"]
    assert "secret-2" in two[0].value["content"] and "secret-1" not in two[0].value["content"]


async def test_offloaded_history_reads_back_through_the_composite() -> None:
    """Recall path: the summary embeds ``/conversation_history/{thread}.md`` and the
    agent re-opens it via builtin ``read_file`` — same composite routing as aread."""
    store = InMemoryStore()
    backend = _backend(store)
    mw = _middleware(backend)

    path = await _drive(
        lambda: mw._aoffload_to_backend(backend, [HumanMessage("the access code is HELIX-7741")]),
        _ctx(),
        store,
        thread_id=_THREAD,
    )
    read = await _drive(lambda: backend.aread(path), _ctx(), store, thread_id=_THREAD)
    assert read.error is None
    assert "HELIX-7741" in _content(read)
