"""F2 Phase-3 Slice E (ADR-F049): the per-run fan-out safety quota.

Subagent fan-out is the deepagents builtin ``task`` tool (model-driven, zero
orchestration scaffolding — ADR-F034). It is added to the agent's ``ToolNode``
by deepagents' ``SubAgentMiddleware``, so — unlike the matter document/memory
tools — it does **not** pass through the :mod:`app.agents.guard`
``guarded_dispatch`` chokepoint. There is therefore nothing today that bounds
how many subagents a single run can spawn: the only brakes that fire are
``max_steps`` / ``recursion_limit`` / wall-clock (step caps, not a fan-out cap),
and an over-eager model can blow the token budget in one wide fan-out turn long
before it blows the step count (the ADR-F015 over-exploration finding).

This middleware is that missing chokepoint. langchain's agent factory builds the
``ToolNode`` with a ``wrap_tool_call`` chain composed from **every** middleware
that overrides the hook (``langchain.agents.factory``), and the ``task`` tool is
a normal registered tool — so our ``(a)wrap_tool_call`` sees every ``task``
dispatch *before* it executes. Past the per-run ceiling we return a
model-visible refusal ``ToolMessage`` *without* calling the handler: no subagent
spawns, the run is **not** killed, and the agent can adapt (consolidate findings,
or read the remaining documents directly with ``read_document``).

**This is a SAFETY ceiling, not a taste limit.** The ``retrieval-strategy``
doctrine teaches *when* to fan out (cheap-first, fan out only for independent
breadth that won't fit); this brake only bounds the blast radius if the model
misjudges — doctrine for taste, the brake for safety, never the reverse.

**Honest scope (carried into ADR-F049 Slice E):** this bounds fan-out *breadth*
(a step/dispatch ceiling). It is **not** a per-run token/cost budget — R4
(``app.agents.guard``) is still a no-op, so cost-safety is not claimed from this
slice; wiring R4 into a real token budget is a separate deferred slice.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)

# The deepagents builtin subagent-dispatch tool (middleware.subagents).
_FAN_OUT_TOOL = "task"


class FanOutQuotaMiddleware(AgentMiddleware):
    """Cap subagent (``task``) dispatches per run at a configurable ceiling.

    One instance per run (constructed in :mod:`app.agents.composition`), so the
    counter is run-scoped. ``quota <= 0`` disables the brake (the middleware
    becomes a pass-through). Non-``task`` tool calls always pass straight to the
    handler — this middleware governs *only* fan-out breadth.
    """

    # Registers no tools of its own.
    tools = ()

    def __init__(self, *, quota: int) -> None:
        super().__init__()
        self._quota = quota
        self._count = 0

    def _gate(self, request: ToolCallRequest) -> ToolMessage | None:
        """Return a refusal ToolMessage to deny, or ``None`` to allow.

        Check-and-increment carries **no ``await`` between the read and the
        write**, so under asyncio's cooperative scheduling it is atomic even when
        the ``ToolNode`` gathers several ``task`` calls emitted in one model turn
        — a wide single-turn fan-out cannot slip the ceiling.
        """
        if self._quota <= 0:
            return None
        if request.tool_call.get("name") != _FAN_OUT_TOOL:
            return None
        if self._count >= self._quota:
            return self._refusal(request)
        self._count += 1
        return None

    def _refusal(self, request: ToolCallRequest) -> ToolMessage:
        logger.warning(
            "fan-out quota reached; denying task dispatch",
            extra={"event": "fan_out_quota_denied", "quota": self._quota},
        )
        return ToolMessage(
            content=(
                f"Fan-out limit reached: this run has already dispatched {self._quota} "
                "subagent(s), the maximum allowed. Do not delegate further. Consolidate "
                "what the subagents already returned, or read the remaining documents "
                "directly with read_document, and answer from that."
            ),
            tool_call_id=request.tool_call.get("id", ""),
            name=_FAN_OUT_TOOL,
            status="error",
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        denial = self._gate(request)
        if denial is not None:
            return denial
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        denial = self._gate(request)
        if denial is not None:
            return denial
        return await handler(request)
