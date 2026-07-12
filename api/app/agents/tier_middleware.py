"""F2 N1 (ADR-F049): the per-run memory-tier injection middleware.

The four read-only DATA memory tiers — **House Brief** (company/client
context), **Matter File** (the matter wiki), **Matter Corrections**
(lawyer-pinned facts) and **Matter Roster** (who-is-who) — are injected into
the agent's system prompt by THIS middleware (F2 N1) rather than baked into
the static ``system_prompt`` string. This puts tier injection on our own
middleware seam (the seam the future **Practice Knowledge** tier will plug
into) while keeping the rendered blocks byte-identical and SQL the source of
truth (ADR-F042 ownership unchanged).

deepagents' stock ``MemoryMiddleware`` is deliberately NOT used: it injects
generic ``edit_file`` self-learning guidelines that conflict with the fork's
human-owned, auto-write-then-correct memory model. This is a thin fork
middleware that only appends already-rendered, data-only-fenced tier text —
no self-learning, no backend reads.

The tier text is rendered once per run by
:func:`app.agents.composition.render_memory_tiers` (the single source of the
fence constants + order + degradation) and passed in via the constructor, so
this class stays a trivial, well-tested appender. It appends on EVERY model
call (``wrap_model_call``) because a state-returning hook cannot mutate
``system_message``; the tier blocks land AFTER the static base prompt
(identity + matter doctrine + area method).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import ContentBlock, SystemMessage


def _append_text_block(system_message: SystemMessage | None, text: str) -> SystemMessage:
    """Append ``text`` as a new text content block on a (copied) system message.

    Mirrors deepagents' private ``append_to_system_message`` — reimplemented
    here to avoid depending on a deepagents private module (loose coupling,
    CLAUDE.md). A pre-existing block gets a blank-line separator.
    """
    blocks: list[ContentBlock] = (
        list(system_message.content_blocks) if system_message is not None else []
    )
    if blocks:
        text = f"\n\n{text}"
    blocks.append({"type": "text", "text": text})
    return SystemMessage(content_blocks=blocks)


class TierMemoryMiddleware(AgentMiddleware):
    """Appends the per-run read-only memory-tier blocks to the system prompt.

    ``tier_text`` is the already-rendered concatenation of the present data
    tiers (House Brief → Practice Playbook → Matter File → Matter Corrections →
    Matter Roster → Matter Documents), in
    the same deliberate order as the legacy ``system_prompt_for`` assembly. An
    empty string is a no-op (degradation preserved: an absent/empty tier adds
    nothing). The blocks land AFTER the static base prompt on every model call.
    """

    # Registers no tools (the base annotates ``tools`` with no default).
    tools = ()

    def __init__(self, *, tier_text: str) -> None:
        super().__init__()
        # Strip the leading blank line the fence constants carry; the appender
        # re-adds exactly one separator, so block spacing matches the legacy
        # in-prompt rendering.
        self._tier_text = tier_text.lstrip("\n")

    def _inject(self, request: ModelRequest) -> ModelRequest:
        if not self._tier_text:
            return request
        return request.override(
            system_message=_append_text_block(request.system_message, self._tier_text)
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._inject(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._inject(request))
