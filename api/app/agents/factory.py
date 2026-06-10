"""Factory seam for deep agents (F0-S1, ADR-F004 stability hygiene).

All ``deepagents`` construction goes through :func:`build_deep_agent` — the
package is pre-1.0 and ships breaking changes on minor versions, so call
sites never import it directly. All agent LLM traffic goes through the
Inference Gateway via :func:`build_gateway_chat_model`; a direct provider
call from agent code is a security regression (CLAUDE.md, ADR-F001).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.config import get_settings

_GATEWAY_KEY_HEADER = "X-LQ-AI-Gateway-Key"


def build_gateway_chat_model(
    *,
    model_alias: str = "smart",
    gateway_url: str | None = None,
    gateway_key: str | None = None,
    temperature: float = 0.0,
    timeout: float = 120.0,
) -> BaseChatModel:
    """Chat model speaking the gateway's OpenAI-compatible surface.

    ``api_key`` is a placeholder: the gateway authenticates on the
    ``X-LQ-AI-Gateway-Key`` header, not the OpenAI Authorization bearer.
    ``model_alias`` is a gateway alias (``smart``/``fast``/``budget``) so
    routing, tier floors, and the routing log all apply per request.
    """
    url = (gateway_url if gateway_url is not None else get_settings().lq_ai_gateway_url).rstrip("/")
    key = gateway_key if gateway_key is not None else get_settings().lq_ai_gateway_key
    return ChatOpenAI(
        model=model_alias,
        base_url=f"{url}/v1",
        # langchain-openai 1.x types api_key as SecretStr (not str); the
        # value is still a placeholder — auth rides the gateway header.
        api_key=SecretStr("gateway-key-in-header"),
        default_headers={_GATEWAY_KEY_HEADER: key},
        temperature=temperature,
        timeout=timeout,
        max_retries=1,
    )


def build_deep_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[Callable[..., Any]],
    system_prompt: str,
    **kwargs: Any,
) -> Any:
    """Construct a deep agent (compiled LangGraph graph).

    Single import site for ``deepagents``; absorb upstream API churn here.
    """
    from deepagents import create_deep_agent

    return create_deep_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        **kwargs,
    )
