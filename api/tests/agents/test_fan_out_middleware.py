"""F2 Phase-3 Slice E (ADR-F049): the fan-out safety quota middleware.

Two layers of proof:

* **Unit** — :class:`FanOutQuotaMiddleware`'s gate logic against a fake handler:
  it allows up to ``quota`` ``task`` dispatches, then DENIES with a model-visible
  refusal ``ToolMessage`` (the handler never runs → no subagent spawns), passes
  non-``task`` tools straight through, and ``quota <= 0`` disables the brake.
* **Integration** — a REAL deepagents graph with a subagent configured: the
  builtin ``task`` tool (which bypasses the ``guarded_dispatch`` chokepoint) IS
  routed through our ``awrap_tool_call``, so the quota can intercept fan-out before
  a subagent runs. This is the load-bearing assumption the whole slice rests on.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.factory import build_deep_agent
from app.agents.fan_out_middleware import FanOutQuotaMiddleware
from tests.agents.fakes import ScriptedToolCallingModel, final_message, tool_call_message


def _req(name: str, call_id: str = "c1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": {}, "id": call_id, "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


def _ok(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(
        content="ran", tool_call_id=request.tool_call["id"], name=request.tool_call["name"]
    )


# ----- unit: the gate logic -------------------------------------------------


async def test_allows_up_to_quota_then_denies() -> None:
    mw = FanOutQuotaMiddleware(quota=2)
    ran: list[str] = []

    async def handler(request: ToolCallRequest) -> ToolMessage:
        ran.append(request.tool_call["id"])
        return _ok(request)

    r1 = await mw.awrap_tool_call(_req("task", "a"), handler)
    r2 = await mw.awrap_tool_call(_req("task", "b"), handler)
    r3 = await mw.awrap_tool_call(_req("task", "c"), handler)

    assert ran == ["a", "b"]  # only the first two reached the handler (= ran)
    assert isinstance(r1, ToolMessage) and r1.content == "ran"
    assert isinstance(r2, ToolMessage) and r2.content == "ran"
    assert isinstance(r3, ToolMessage)
    assert r3.status == "error" and r3.tool_call_id == "c"
    assert "limit reached" in r3.content.lower()


async def test_non_task_tools_pass_through_and_never_count() -> None:
    mw = FanOutQuotaMiddleware(quota=1)
    ran: list[str] = []

    async def handler(request: ToolCallRequest) -> ToolMessage:
        ran.append(request.tool_call["name"])
        return _ok(request)

    for name in ("search_documents", "read_document", "estimate_read_cost"):
        out = await mw.awrap_tool_call(_req(name), handler)
        assert isinstance(out, ToolMessage) and out.content == "ran"
    # The single allowed task is still available — non-task calls didn't consume it.
    allowed = await mw.awrap_tool_call(_req("task", "t1"), handler)
    assert isinstance(allowed, ToolMessage) and allowed.content == "ran"
    denied = await mw.awrap_tool_call(_req("task", "t2"), handler)
    assert denied.status == "error"
    assert ran == ["search_documents", "read_document", "estimate_read_cost", "task"]


async def test_quota_zero_disables_the_brake() -> None:
    mw = FanOutQuotaMiddleware(quota=0)
    ran: list[str] = []

    async def handler(request: ToolCallRequest) -> ToolMessage:
        ran.append(request.tool_call["id"])
        return _ok(request)

    for i in range(5):
        out = await mw.awrap_tool_call(_req("task", str(i)), handler)
        assert isinstance(out, ToolMessage) and out.content == "ran"
    assert ran == ["0", "1", "2", "3", "4"]


def test_sync_path_matches_async() -> None:
    mw = FanOutQuotaMiddleware(quota=1)
    ran: list[str] = []

    def handler(request: ToolCallRequest) -> ToolMessage:
        ran.append(request.tool_call["id"])
        return _ok(request)

    out1 = mw.wrap_tool_call(_req("task", "a"), handler)
    out2 = mw.wrap_tool_call(_req("task", "b"), handler)
    assert isinstance(out1, ToolMessage) and out1.content == "ran"
    assert isinstance(out2, ToolMessage) and out2.status == "error"
    assert ran == ["a"]


# ----- integration: the builtin `task` tool IS intercepted -------------------


class _RecordingDenyFanOut(FanOutQuotaMiddleware):
    """Records every tool name its gate sees and denies ALL ``task`` calls, so the
    integration test never executes a subagent (the deny path skips the handler)."""

    def __init__(self) -> None:
        super().__init__(quota=1)
        self.seen: list[str | None] = []

    def _gate(self, request: ToolCallRequest) -> ToolMessage | None:
        name = request.tool_call.get("name")
        self.seen.append(name)
        if name == "task":
            return self._refusal(request)
        return None


async def test_middleware_intercepts_the_builtin_task_tool() -> None:
    """The deepagents builtin ``task`` tool reaches our ``awrap_tool_call`` in a real
    graph with a subagent configured — proving the quota can deny fan-out before a
    subagent spawns (``task`` bypasses guarded_dispatch, so this middleware IS its
    chokepoint). The denied run continues to a normal final answer."""
    spy = _RecordingDenyFanOut()
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "task", {"description": "investigate", "subagent_type": "researcher"}
            ),
            final_message("done"),
        ]
    )
    agent = build_deep_agent(
        model=model,
        tools=[],
        system_prompt="BASE.",
        subagents=[
            {"name": "researcher", "description": "reads documents", "system_prompt": "You read."}
        ],
        middleware=[spy],
    )

    result: dict[str, Any] = await agent.ainvoke({"messages": [HumanMessage("investigate")]})

    assert "task" in spy.seen  # the builtin task tool was routed through our middleware
    contents = [getattr(m, "content", "") for m in result["messages"]]
    assert "done" in contents  # the run completed normally after the denial
