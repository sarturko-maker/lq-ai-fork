"""Test fakes for the agent runner — F0-S2.

:class:`ScriptedToolCallingModel` is a hand-rolled fake chat model (the
``GenericFakeChatModel`` in langchain-core cannot bind tools) that emits
a scripted sequence of ``AIMessage``s — typically one tool-call turn
then a final answer — so runner tests exercise the REAL deepagents loop
(agent build, tool dispatch, astream_events) with no provider and no
gateway. Injected through :func:`app.agents.runner.execute_agent_run`'s
``model`` parameter — the same seam S3+ uses — per the CLAUDE.md DI
rule (substitute fakes through seams; don't monkeypatch).
"""

from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Iterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr


def tool_call_message(name: str, args: dict[str, Any]) -> AIMessage:
    """An assistant turn that requests one tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": "call_scripted", "type": "tool_call"}],
    )


def final_message(text: str) -> AIMessage:
    """An assistant turn with a plain final answer (no tool calls)."""
    return AIMessage(content=text)


class ScriptedToolCallingModel(BaseChatModel):
    """Fake chat model that replays ``responses`` across successive calls.

    With ``loop_last=True`` the final scripted message repeats forever
    (fresh tool-call ids each time) — used to trip the ``max_steps``
    cap. Without it, exhausting the script raises, which the runner
    records as a failed run.

    ``seen_messages`` records every prompt the model received — the
    F0-S5 multi-turn tests assert a follow-up run's model call contains
    the FIRST run's conversation (the checkpointer's whole point).
    """

    responses: list[AIMessage]
    loop_last: bool = False
    # F2 Slice F (ADR-F051): total tokens this model reports PER turn, so a runner
    # token-budget test is deterministic. 0 = report no usage (the default; usage_metadata
    # stays absent, exactly like a provider that does not return usage). When > 0, each
    # turn emits a trailing usage chunk (mirroring ChatOpenAI's final include_usage chunk),
    # so the merged on_chat_model_end message carries usage_metadata.total_tokens.
    usage_per_turn: int = 0

    _idx: int = PrivateAttr(default=0)
    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)
    _bound_tool_names: set[str] = PrivateAttr(default_factory=set)

    def _usage_md(self) -> dict[str, int] | None:
        if self.usage_per_turn <= 0:
            return None
        out = self.usage_per_turn // 2
        return {
            "input_tokens": self.usage_per_turn - out,
            "output_tokens": out,
            "total_tokens": self.usage_per_turn,
        }

    @property
    def seen_messages(self) -> list[list[BaseMessage]]:
        return self._seen

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-calling"

    @property
    def bound_tool_names(self) -> set[str]:
        """Every tool name this model was bound with, across all binds.

        The script decides the OUTPUTS, but "which tools did composition build for
        this run" is only observable here — the graph binds them to the model
        (INTAKE-5a.1 S2: a read-only summarise pass must hold no write tool).
        Includes deepagents builtins; callers intersect with the grant vocabulary.
        """
        return self._bound_tool_names

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedToolCallingModel:
        # The script decides the outputs; tool schemas are irrelevant. The NAMES are
        # recorded (see bound_tool_names) — nothing else about them is.
        for tool in tools or []:
            name = getattr(tool, "name", None)
            if name is None and isinstance(tool, dict):
                function = tool.get("function")
                name = tool.get("name") or (
                    function.get("name") if isinstance(function, dict) else None
                )
            if isinstance(name, str):
                self._bound_tool_names.add(name)
        return self

    def _next_message(self) -> AIMessage:
        if self._idx < len(self.responses):
            message = self.responses[self._idx]
        elif self.loop_last:
            message = self.responses[-1]
        else:
            raise RuntimeError("scripted model exhausted its responses")
        self._idx += 1
        if message.tool_calls:
            # Fresh ids per emission — looped turns must not collide.
            message = copy.deepcopy(message)
            for call in message.tool_calls:
                call["id"] = f"call_{uuid.uuid4().hex[:8]}"
        return message

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._seen.append(list(messages))
        message = self._next_message()
        usage = self._usage_md()
        if usage is not None:
            message = message.model_copy(update={"usage_metadata": usage})
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream the scripted turn (F0-S7).

        langchain auto-upgrades ``invoke`` to streaming only for models
        that implement ``_stream`` — exactly how the production
        ChatOpenAI path feeds ``on_chat_model_stream`` events, which the
        runner forwards as the thinking ribbon's reasoning deltas. Text
        turns stream in two chunks so delta accumulation is exercised;
        the aggregated message is identical to the non-streamed one.
        """
        self._seen.append(list(messages))
        message = self._next_message()
        usage = self._usage_md()
        if message.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=message.content,
                    tool_call_chunks=[
                        {
                            "name": call["name"],
                            "args": json.dumps(call["args"]),
                            "id": call["id"],
                            "index": i,
                            "type": "tool_call_chunk",
                        }
                        for i, call in enumerate(message.tool_calls)
                    ],
                )
            )
            if usage is not None:
                yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=usage))
            return
        text = message.content if isinstance(message.content, str) else ""
        mid = max(1, len(text) // 2)
        yield ChatGenerationChunk(message=AIMessageChunk(content=text[:mid]))
        if text[mid:]:
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[mid:]))
        # F2 Slice F: trailing usage chunk (mirrors ChatOpenAI's final include_usage
        # chunk) so the merged on_chat_model_end message carries usage_metadata.
        if usage is not None:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=usage))


class ExplodingModel(BaseChatModel):
    """Fake chat model whose first call raises — the runner's generic
    exception path must persist ``failed`` with a bounded, traceless error."""

    message: str = "provider exploded"

    @property
    def _llm_type(self) -> str:
        return "exploding"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ExplodingModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError(self.message)
