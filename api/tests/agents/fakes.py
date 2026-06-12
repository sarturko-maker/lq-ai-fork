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
        tool_calls=[
            {"name": name, "args": args, "id": "call_scripted", "type": "tool_call"}
        ],
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

    _idx: int = PrivateAttr(default=0)
    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    @property
    def seen_messages(self) -> list[list[BaseMessage]]:
        return self._seen

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-calling"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedToolCallingModel:
        # The script decides the outputs; tool schemas are irrelevant.
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
        return ChatResult(generations=[ChatGeneration(message=self._next_message())])

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
            return
        text = message.content if isinstance(message.content, str) else ""
        mid = max(1, len(text) // 2)
        yield ChatGenerationChunk(message=AIMessageChunk(content=text[:mid]))
        if text[mid:]:
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[mid:]))


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
