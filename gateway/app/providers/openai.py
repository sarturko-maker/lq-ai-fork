"""OpenAI provider adapter — embeddings now, chat completions stubbed.

Per ADR 0008, C6 ships an OpenAI adapter scoped to the embeddings path.
The chat-completion method raises :class:`ProviderUnsupportedError` and
will be filled in by B6. The auth header wiring, error translation, and
httpx pool are all in place so B6 only adds the chat-completion
translation surface.

Wire-format notes
-----------------

* OpenAI's Embeddings API: ``POST /embeddings`` with body
  ``{"model": "text-embedding-3-small", "input": "..." | [...]}``.
  Returns ``{"data": [{"embedding": [...], "index": int, "object":
  "embedding"}, ...], "model": str, "usage": {"prompt_tokens": int,
  "total_tokens": int}}``. The shape is identical to OpenAI's so the
  gateway's OpenAI-compatible response model passes through almost
  verbatim — only the LQ.AI extensions (``routed_inference_tier``)
  are added by the route handler.
* The base URL convention is ``https://api.openai.com/v1`` (with the
  ``/v1`` already in ``base_url`` per ``gateway.yaml.example``); we do
  NOT prepend ``/v1`` to the path here.
* Authentication: ``Authorization: Bearer <key>``.

Why no ``openai`` SDK dependency
--------------------------------

Per PRD §4 / ADR 0008 §"Adapter scope" — the gateway hand-rolls httpx
to keep the supply-chain surface honest. The Embeddings request and
response shapes are small enough that a pydantic schema + a single
POST is cleaner than pulling the full openai SDK.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import ProviderConfig
from app.providers.base import (
    ProviderAdapter,
    ProviderAuthError,
    ProviderHealth,
    ProviderHTTPError,
    ProviderNetworkError,
    ProviderUnsupportedError,
)
from app.providers.openai_schema import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingObject,
    EmbeddingsRequest,
    EmbeddingsResponse,
    EmbeddingsUsage,
)

logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT_SECONDS = 60.0
"""Default per-request timeout. ``timeout_s`` on each provider entry
overrides; if absent we use this default."""


class OpenAIAdapter(ProviderAdapter):
    """Concrete :class:`ProviderAdapter` for OpenAI.

    M1 scope (per ADR 0008): :meth:`embeddings` is the load-bearing
    path. :meth:`chat_completion` raises :class:`ProviderUnsupportedError`
    until B6 fills in the OpenAI Chat Completions translation surface.

    Construct via :meth:`from_config` from a loaded ``ProviderConfig``.
    The adapter resolves the API key from the env var named in
    ``api_key_env`` (default ``OPENAI_API_KEY``); if unset, construction
    raises :class:`ValueError` so the failure is visible at startup.
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_s,
        )

    # --- Construction --------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        provider: ProviderConfig,
        *,
        env: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> OpenAIAdapter:
        """Build an adapter from a loaded :class:`ProviderConfig`.

        Accepts both ``type="openai"`` and ``type="openai_compatible"``
        provider entries (the latter for vLLM / llama-cpp servers that
        speak the OpenAI wire format). The API-key check is skipped when
        ``api_key_env`` is empty/None — many local OpenAI-compatible
        servers don't require a key.

        ``env`` defaults to :data:`os.environ`; tests override.
        """

        if provider.type not in ("openai", "openai_compatible"):
            raise ValueError(
                f"OpenAIAdapter requires provider.type in {{'openai', "
                f"'openai_compatible'}}; got {provider.type!r}"
            )
        env_lookup = env if env is not None else dict(os.environ)
        api_key_env = provider.api_key_env or "OPENAI_API_KEY"
        api_key: str
        if api_key_env:
            looked_up = env_lookup.get(api_key_env)
            if not looked_up:
                # For openai_compatible providers (local), an empty key is
                # acceptable; for cloud OpenAI it isn't.
                if provider.type == "openai":
                    raise ValueError(
                        f"OpenAI provider {provider.name!r} requires environment "
                        f"variable {api_key_env!r} to be set"
                    )
                api_key = ""
            else:
                api_key = looked_up
        else:
            api_key = ""

        extra = provider.model_extra or {}
        timeout_raw = extra.get("timeout_s")
        timeout_s = float(timeout_raw) if timeout_raw is not None else DEFAULT_TIMEOUT_SECONDS

        return cls(
            name=provider.name,
            base_url=provider.base_url,
            api_key=api_key,
            timeout_s=timeout_s,
            client=client,
        )

    # --- ProviderAdapter contract --------------------------------------------

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        model: str,
        stream: bool,
    ) -> ChatCompletionResponse | AsyncIterator[ChatCompletionChunk]:
        """OpenAI chat completions are deferred to B6.

        The adapter framing is in place so when B6 lands the chat
        translation surface (a thin pass-through, since OpenAI is the
        wire format the gateway already speaks) it goes here.
        """

        raise ProviderUnsupportedError(
            "OpenAI chat-completions are not yet implemented; lands with B6 "
            "(the OpenAI adapter currently only services embeddings, per ADR 0008)",
            details={"provider": self.name, "model": model},
        )

    async def embeddings(
        self,
        request: EmbeddingsRequest,
        *,
        model: str,
    ) -> EmbeddingsResponse:
        """POST to OpenAI's ``/embeddings`` and translate the response.

        OpenAI's wire format is what the gateway's OpenAI-compatible
        schema is modeled on; the translation is mostly identity. The
        only field that needs adapter-specific handling is the
        ``index`` integer (we trust OpenAI's numbering) and the
        ``encoding_format`` (we always send the default ``float`` —
        ``base64`` is a future optimization for bandwidth-constrained
        deployments).
        """

        body: dict[str, Any] = {
            "model": model,
            "input": request.input,
        }
        # OpenAI's text-embedding-3-* models support a ``dimensions``
        # parameter that returns shorter vectors. We pass through if the
        # caller set it (the route handler may set this; the KB layer
        # default-omits to use the model's native dim).
        if request.dimensions is not None:
            body["dimensions"] = request.dimensions
        if request.encoding_format is not None:
            body["encoding_format"] = request.encoding_format
        if request.user is not None:
            body["user"] = request.user

        try:
            response = await self._client.post(
                "/embeddings",
                json=body,
                headers=self._auth_headers(),
            )
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(
                f"failed to reach OpenAI: {type(exc).__name__}",
                details={"provider": self.name},
            ) from exc

        _raise_for_status(response, provider=self.name)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderHTTPError(
                "OpenAI returned a non-JSON response",
                upstream_status=response.status_code,
                details={"provider": self.name},
            ) from exc

        return _from_openai_embeddings_response(payload, requested_model=model)

    async def health_check(self) -> ProviderHealth:
        """Probe OpenAI's ``GET /models`` endpoint.

        Cheapest authenticated GET; validates that our key is accepted.
        Health probes use a shorter timeout so admin endpoints stay
        responsive when a provider is misbehaving.
        """

        start = time.monotonic()
        try:
            response = await self._client.get(
                "/models",
                headers=self._auth_headers(),
                timeout=min(self._timeout, 10.0),
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                name=self.name,
                reachable=False,
                latency_ms=None,
                error=f"network error: {type(exc).__name__}",
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        if response.status_code == 200:
            return ProviderHealth(name=self.name, reachable=True, latency_ms=latency_ms)
        if response.status_code in (401, 403):
            return ProviderHealth(
                name=self.name,
                reachable=True,
                latency_ms=latency_ms,
                error=f"upstream auth rejected ({response.status_code})",
            )
        return ProviderHealth(
            name=self.name,
            reachable=False,
            latency_ms=latency_ms,
            error=f"upstream returned HTTP {response.status_code}",
        )

    async def aclose(self) -> None:
        """Close the owned httpx client (if we created it)."""

        if self._owns_client:
            await self._client.aclose()

    # --- Internals -----------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """Headers required on every OpenAI call.

        ``Authorization: Bearer <key>`` is the OpenAI auth convention.
        For ``openai_compatible`` providers with no key configured we
        omit the header entirely (some local servers reject any
        ``Authorization`` header outright).
        """

        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        return headers


# --- Translation helpers -----------------------------------------------------


def _from_openai_embeddings_response(
    payload: dict[str, Any],
    *,
    requested_model: str,
) -> EmbeddingsResponse:
    """Translate OpenAI's embeddings JSON into :class:`EmbeddingsResponse`.

    OpenAI's body shape::

        {
          "object": "list",
          "data": [
            {"object": "embedding", "embedding": [0.1, 0.2, ...], "index": 0},
            ...
          ],
          "model": "text-embedding-3-small",
          "usage": {"prompt_tokens": 5, "total_tokens": 5}
        }

    We accept the response verbatim into our pydantic models. Defensive
    fallbacks: if ``data`` is missing the request had no embeddings to
    return (we surface as an empty response rather than raising — the
    caller's empty-input case lands here).
    """

    data_raw = payload.get("data") or []
    items: list[EmbeddingObject] = []
    if isinstance(data_raw, list):
        for entry in data_raw:
            if not isinstance(entry, dict):
                continue
            embedding = entry.get("embedding")
            index = entry.get("index", 0)
            if isinstance(embedding, list):
                items.append(
                    EmbeddingObject(
                        embedding=[float(v) for v in embedding],
                        index=int(index) if isinstance(index, int) else 0,
                    )
                )

    usage_raw = payload.get("usage") or {}
    usage = EmbeddingsUsage(
        prompt_tokens=int(usage_raw.get("prompt_tokens", 0)) if isinstance(usage_raw, dict) else 0,
        total_tokens=int(usage_raw.get("total_tokens", 0)) if isinstance(usage_raw, dict) else 0,
    )

    response_model = str(payload.get("model") or requested_model)

    return EmbeddingsResponse(
        data=items,
        model=response_model,
        usage=usage,
    )


# --- Error mapping -----------------------------------------------------------


def _raise_for_status(response: httpx.Response, *, provider: str) -> None:
    """Translate an upstream non-success status to a structured adapter error."""

    if response.status_code < 400:
        return
    body = response.content
    _raise_from_error_body(status_code=response.status_code, body=body, provider=provider)


def _raise_from_error_body(
    *,
    status_code: int,
    body: bytes,
    provider: str,
) -> None:
    """Parse an OpenAI error body and raise the right adapter error.

    OpenAI's error shape::

        {"error": {"message": "...", "type": "...", "code": "..."}}

    We surface ``error.message`` to the operator (it's API-key-free by
    OpenAI's convention) and tag the type/code in ``details``. The raw
    body is *not* echoed — protects against accidental key/PII leakage
    if a request is malformed in ways that echo the input back.
    """

    upstream_type: str | None = None
    upstream_code: str | None = None
    upstream_message: str | None = None
    try:
        parsed = json.loads(body or b"{}")
    except json.JSONDecodeError:
        parsed = {}
    if isinstance(parsed, dict):
        error_block = parsed.get("error")
        if isinstance(error_block, dict):
            raw_type = error_block.get("type")
            raw_code = error_block.get("code")
            raw_message = error_block.get("message")
            if isinstance(raw_type, str):
                upstream_type = raw_type
            if isinstance(raw_code, str):
                upstream_code = raw_code
            if isinstance(raw_message, str):
                upstream_message = raw_message

    details: dict[str, object] = {"provider": provider}
    if upstream_type:
        details["upstream_error_type"] = upstream_type
    if upstream_code:
        details["upstream_error_code"] = upstream_code

    safe_message = upstream_message or f"OpenAI returned HTTP {status_code}"

    if status_code in (401, 403):
        details["upstream_status"] = status_code
        raise ProviderAuthError(
            f"OpenAI rejected the gateway's credentials ({status_code})",
            details=details,
        )
    raise ProviderHTTPError(
        safe_message,
        upstream_status=status_code,
        details=details,
    )
