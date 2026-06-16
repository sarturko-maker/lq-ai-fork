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

# F0-S9: effective max input tokens THROUGH THE GATEWAY, for the model's
# ``profile`` — deepagents' summarization middleware falls back to a fixed
# 170k-token trigger for unprofiled models (compute_summarization_defaults);
# with ``max_input_tokens`` set, compaction triggers at 0.85 x this value
# (and post-compaction KEEP becomes fraction-based — intended). 200k is a
# conservative operating point under the gateway's DECLARED request cap
# (``request_validation.max_total_request_chars`` = 1e6 chars ≈ 250k tokens
# at ~4 chars/token; the cap is config-only today — not yet enforced in
# gateway/app), well inside MiniMax-M3's native 1M-token window.
DEFAULT_MAX_INPUT_TOKENS = 200_000


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
    max_input_tokens: int | None = DEFAULT_MAX_INPUT_TOKENS,
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
        # F0-S9 conformance: langchain-openai's Responses-API auto-detect
        # breaks OpenAI-compatible endpoints ("No generations found in
        # stream", deepagents#3190) — pin Chat Completions explicitly.
        use_responses_api=False,
        # F0-S9: without max_input_tokens deepagents never computes a
        # window-relative compaction trigger (see DEFAULT_MAX_INPUT_TOKENS).
        profile=({"max_input_tokens": max_input_tokens} if max_input_tokens is not None else None),
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

    ADR-F010 gate: if a ``subagents=`` list is passed, reject any spec
    carrying a non-gateway ``model`` BEFORE construction. deepagents resolves
    a string ``model`` via ``init_chat_model`` (direct provider SDK = gateway
    bypass); area subagents must omit ``model`` to inherit the gateway-bound
    parent. This is the one seam all agent construction passes through.
    """
    from deepagents import create_deep_agent

    from app.agents.area_agent import reject_model_bearing_subagents
    from app.agents.profiles import ensure_harness_profiles_registered

    reject_model_bearing_subagents(kwargs.get("subagents"))
    # UX-B-3 (ADR-F016): ``skills`` (source paths) + ``backend`` ride **kwargs
    # straight into create_deep_agent, which wires SkillsMiddleware over the
    # backend. The ADR-F010 gate is subagent-only — skills/backend carry no
    # model and cannot bypass the gateway.

    # F0-S9: qualification is per-(model, harness-profile) — the registry
    # must be populated before any agent resolves its profile.
    ensure_harness_profiles_registered()

    return create_deep_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        **kwargs,
    )
