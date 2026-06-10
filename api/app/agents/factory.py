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

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.config import get_settings

_GATEWAY_KEY_HEADER = "X-LQ-AI-Gateway-Key"


def build_gateway_http_client(
    *,
    gateway_key: str | None = None,
    timeout: float = 120.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """The httpx client that carries the gateway key — and ONLY it does.

    The key lives in this client's transport-level headers, never on the
    ``ChatOpenAI`` object: ``default_headers`` is a serializable pydantic
    field that leaks into ``model_dump()`` / tracing payloads, while the
    injected client is excluded from serialization (S1-review carry-over,
    closed in F0-S4). The caller owns the lifecycle — ``aclose()`` when
    the run ends. ``transport`` is an injection seam for tests (mock the
    wire without monkeypatching).
    """
    key = gateway_key if gateway_key is not None else get_settings().lq_ai_gateway_key
    return httpx.AsyncClient(
        headers={_GATEWAY_KEY_HEADER: key}, timeout=timeout, transport=transport
    )


def build_gateway_chat_model(
    *,
    model_alias: str = "smart",
    gateway_url: str | None = None,
    purpose: str = "agent_loop",
    temperature: float = 0.0,
    timeout: float = 120.0,
    http_async_client: httpx.AsyncClient,
    project_minimum_inference_tier: int | None = None,
    privileged: bool = False,
) -> BaseChatModel:
    """Chat model speaking the gateway's OpenAI-compatible surface.

    ``api_key`` is a placeholder: the gateway authenticates on the
    ``X-LQ-AI-Gateway-Key`` header, which rides ``http_async_client``'s
    headers (REQUIRED — see :func:`build_gateway_http_client`; a model
    built without it has no credentials). Only the async client carries
    the key, so the agent loop must stay on async call paths.
    ``model_alias`` is a gateway alias (``smart``/``fast``/``budget``) so
    routing, tier floors, and the routing log all apply per request.

    ``extra_body`` merges into the top-level request JSON (unknown
    *kwargs* to ``create()`` would raise instead), so every request body
    carries ``lq_ai_purpose`` (F0-S2; ``_KNOWN_PURPOSES`` in
    ``gateway/app/api/inference.py``) — and, for a matter-bound run
    (F0-S4), the matter's tier floor and privilege flag, exactly the
    chat path's envelope (D1 / M2-B3): the gateway enforces the floor
    and skips anonymization for privileged matters.
    """
    url = (gateway_url if gateway_url is not None else get_settings().lq_ai_gateway_url).rstrip("/")
    extra_body: dict[str, Any] = {"lq_ai_purpose": purpose}
    if project_minimum_inference_tier is not None:
        extra_body["lq_ai_project_minimum_inference_tier"] = project_minimum_inference_tier
    if privileged:
        extra_body["lq_ai_privileged"] = True
    return ChatOpenAI(
        model=model_alias,
        base_url=f"{url}/v1",
        # langchain-openai 1.x types api_key as SecretStr (not str); the
        # value is still a placeholder — auth rides the client's header.
        api_key=SecretStr("gateway-key-in-header"),
        extra_body=extra_body,
        temperature=temperature,
        timeout=timeout,
        max_retries=1,
        http_async_client=http_async_client,
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
