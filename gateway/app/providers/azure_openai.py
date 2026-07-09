"""Azure OpenAI provider adapter — M2-E1 (closes DE-267 API-key path).

Subclasses :class:`~app.providers.openai.OpenAIAdapter` because the
wire format is identical to OpenAI's; only the URL shape and auth
header differ. The chat/embeddings request and response bodies, the
streaming SSE format, the LQ.AI extension-key strip, and the error
mapping are all reused verbatim from the OpenAI helpers.

Wire-format differences from OpenAI
-----------------------------------

* **URL shape.** OpenAI uses ``POST /v1/chat/completions``. Azure uses
  ``POST /openai/deployments/<deployment-id>/chat/completions?api-version=<version>``
  where ``deployment-id`` is an operator-named string (not the model
  name; many operators run multiple deployments of the same underlying
  model with different SKUs / capacities). The gateway's existing
  model-alias mechanism doubles as the deployment-id resolver: each
  alias's ``model`` field is the Azure deployment-id, and the adapter
  receives it as the ``model`` argument on each call.
* **Auth header.** ``api-key: <key>`` instead of
  ``Authorization: Bearer <key>``. The OpenAI strip-key-from-error
  posture still applies (the key never appears in surfaced error
  envelopes).
* **api_version.** Required on every URL. Configured per provider in
  ``gateway.yaml`` under ``api_version`` (e.g., ``"2024-10-21"``); no
  default — operators must pin a version explicitly because Azure
  rolls features in/out per version and silent defaults would mask
  capability changes.

Auth (M2-E1 + AZ-6)
-------------------

Two paths, selected by the ``AZURE_OPENAI_USE_MANAGED_IDENTITY`` flag:

* **API key (default, M2-E1).** ``api-key: <key>``; the key comes from
  ``api_key_env`` / ``api_key_encrypted`` (or, since KV-1, Key Vault).
* **Keyless managed identity (AZ-6, ADR-F072).** When the flag is set,
  the adapter mints a short-lived Entra bearer token from the VM's
  system-assigned managed identity (via IMDS, stdlib only — NO
  ``azure-identity`` SDK) and sends ``Authorization: Bearer <token>``;
  no static key is resolved or required. See :mod:`app.azure_identity`
  for the token provider, the confirmed scope, and the honesty note.

The flag defaults off, so the API-key path is byte-identical to today.

Tier defaults: operators set ``tier: 3`` for the typical Azure OpenAI
enterprise-agreement deployment (Azure carries ZDR + BAA under the
Online Services Subscription Agreement). The adapter does not enforce
a default — the tier comes from each provider entry in
``gateway.yaml`` so operators with non-EA Azure subscriptions can
configure a lower tier.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.azure_identity import (
    USE_MANAGED_IDENTITY_ENV,
    ManagedIdentityError,
    TokenProvider,
    build_managed_identity_provider,
)
from app.config import ProviderConfig
from app.providers.base import (
    ProviderHealth,
    ProviderHTTPError,
    ProviderNetworkError,
)
from app.providers.openai import (
    DEFAULT_TIMEOUT_SECONDS,
    OpenAIAdapter,
    _from_openai_chat_response,
    _from_openai_embeddings_response,
    _openai_stream_iter,
    _raise_for_status,
    _to_openai_request,
)
from app.providers.openai_schema import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingsRequest,
    EmbeddingsResponse,
)
from app.secrets import ProviderKeyResolver

logger = logging.getLogger(__name__)


class AzureOpenAIAdapter(OpenAIAdapter):
    """Azure OpenAI subclass — OpenAI wire format, Azure URL + auth.

    Constructed via :meth:`from_config` from a ``provider.type='azure_openai'``
    ``ProviderConfig`` entry. The provider entry must carry
    ``api_version`` (e.g., ``"2024-10-21"``) and an API key source
    (``api_key_env`` or ``api_key_encrypted``); construction raises
    ``ValueError`` if either is missing.
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        api_version: str,
        timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        token_provider: TokenProvider | None = None,
    ) -> None:
        super().__init__(
            name=name,
            base_url=base_url,
            api_key=api_key,
            timeout_s=timeout_s,
            client=client,
        )
        self._api_version = api_version
        # AZ-6 (ADR-F072): when set, authenticate with a managed-identity bearer
        # token instead of ``api-key``. ``None`` ⇒ the unchanged API-key path.
        self._token_provider = token_provider

    # --- Construction --------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        provider: ProviderConfig,
        *,
        env: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        key_resolver: ProviderKeyResolver | None = None,
    ) -> AzureOpenAIAdapter:
        """Build an Azure adapter from a loaded :class:`ProviderConfig`.

        Required provider fields:

        * ``type`` — must be ``"azure_openai"``.
        * ``base_url`` — the Azure resource endpoint
          (``https://<resource>.openai.azure.com``; no ``/v1`` and no
          trailing slash).
        * ``api_version`` — required Azure API version
          (``"2024-10-21"`` or similar; rides in via ``model_extra``).
        * One of ``api_key_env`` or ``api_key_encrypted`` — the API
          key source. M2-E1 ships API-key auth only; Azure AD lands in
          a follow-on DE.

        ``env`` defaults to :data:`os.environ`; tests override.
        """

        if provider.type != "azure_openai":
            raise ValueError(
                f"AzureOpenAIAdapter requires provider.type='azure_openai'; got {provider.type!r}"
            )

        env_lookup = env if env is not None else dict(os.environ)

        # AZ-6 (ADR-F072): keyless managed-identity auth when the flag is set.
        # ``None`` ⇒ the flag is unset and we take the unchanged API-key path
        # below (byte-identical to today). When keyless, NO API key is resolved
        # or required — the adapter mints a bearer token per refresh instead.
        token_provider = build_managed_identity_provider(env_lookup)

        api_key = ""
        if token_provider is None:
            if key_resolver is None:
                key_resolver = ProviderKeyResolver(
                    master_key=env_lookup.get("LQ_AI_GATEWAY_MASTER_KEY") or None,
                    env=env_lookup,
                )
            effective_env = provider.api_key_env or (
                None if provider.api_key_encrypted else "AZURE_OPENAI_API_KEY"
            )
            api_key = key_resolver.resolve(
                provider_name=provider.name,
                api_key_env=effective_env,
                api_key_encrypted=provider.api_key_encrypted,
            )
            if not api_key:
                raise ValueError(
                    f"Azure OpenAI provider {provider.name!r} requires either "
                    f"api_key_encrypted or environment variable "
                    f"{(effective_env or 'AZURE_OPENAI_API_KEY')!r} to be set "
                    f"(or set {USE_MANAGED_IDENTITY_ENV}=true for keyless managed identity)"
                )

        extra = provider.model_extra or {}
        api_version_raw = extra.get("api_version")
        if not isinstance(api_version_raw, str) or not api_version_raw:
            raise ValueError(
                f"Azure OpenAI provider {provider.name!r} requires "
                f"'api_version' in the provider config "
                f"(e.g., '2024-10-21')"
            )
        timeout_raw = extra.get("timeout_s")
        timeout_s = float(timeout_raw) if timeout_raw is not None else DEFAULT_TIMEOUT_SECONDS

        return cls(
            name=provider.name,
            base_url=provider.base_url,
            api_key=api_key,
            api_version=api_version_raw,
            timeout_s=timeout_s,
            client=client,
            token_provider=token_provider,
        )

    # --- ProviderAdapter contract --------------------------------------------

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        model: str,
        stream: bool,
    ) -> ChatCompletionResponse | AsyncIterator[ChatCompletionChunk]:
        """Issue a chat completion against an Azure deployment.

        ``model`` is the Azure deployment-id (operator-named via the
        gateway's alias map), not the underlying model name. The body
        translation, LQ.AI extension-key strip, and SSE parsing are
        reused verbatim from the OpenAI helpers.
        """

        body = _to_openai_request(request, model=model, stream=stream)
        path = self._chat_completions_path(deployment_id=model)
        headers = await self._auth_headers_async()

        if stream:
            return _openai_stream_iter(
                client=self._client,
                body=body,
                headers=headers,
                provider_name=self.name,
                requested_model=model,
                path=path,
            )
        return await self._chat_completion_unary_azure(body, path, headers, model=model)

    async def _chat_completion_unary_azure(
        self,
        body: dict[str, Any],
        path: str,
        headers: dict[str, str],
        *,
        model: str,
    ) -> ChatCompletionResponse:
        try:
            response = await self._client.post(
                path,
                json=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(
                f"failed to reach Azure OpenAI: {type(exc).__name__}",
                details={"provider": self.name},
            ) from exc

        _raise_for_status(response, provider=self.name)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderHTTPError(
                "Azure OpenAI returned a non-JSON response",
                upstream_status=response.status_code,
                details={"provider": self.name},
            ) from exc

        return _from_openai_chat_response(payload, requested_model=model)

    async def embeddings(
        self,
        request: EmbeddingsRequest,
        *,
        model: str,
    ) -> EmbeddingsResponse:
        """POST to Azure's deployment-scoped ``/embeddings``.

        Body shape mirrors OpenAI's (``input``, ``dimensions``,
        ``encoding_format``, ``user``); only the URL path differs.
        """

        body: dict[str, Any] = {
            "model": model,
            "input": request.input,
        }
        if request.dimensions is not None:
            body["dimensions"] = request.dimensions
        if request.encoding_format is not None:
            body["encoding_format"] = request.encoding_format
        if request.user is not None:
            body["user"] = request.user

        path = self._embeddings_path(deployment_id=model)
        headers = await self._auth_headers_async()

        try:
            response = await self._client.post(
                path,
                json=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(
                f"failed to reach Azure OpenAI: {type(exc).__name__}",
                details={"provider": self.name},
            ) from exc

        _raise_for_status(response, provider=self.name)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderHTTPError(
                "Azure OpenAI returned a non-JSON response",
                upstream_status=response.status_code,
                details={"provider": self.name},
            ) from exc

        return _from_openai_embeddings_response(payload, requested_model=model)

    async def health_check(self) -> ProviderHealth:
        """Probe Azure's ``GET /openai/models?api-version=...`` endpoint."""

        start = time.monotonic()
        try:
            headers = await self._auth_headers_async()
            response = await self._client.get(
                self._models_path(),
                headers=headers,
                timeout=min(self._timeout, 10.0),
            )
        except (httpx.HTTPError, ProviderNetworkError) as exc:
            # ProviderNetworkError also covers a managed-identity token-mint
            # failure (IMDS unreachable/misconfigured) — the provider is unusable.
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

    # --- Internals -----------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """Azure uses ``api-key: <key>`` rather than OpenAI's Bearer auth."""

        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers

    async def _auth_headers_async(self) -> dict[str, str]:
        """Auth headers for a request, minting/refreshing a managed-identity token
        when keyless (AZ-6). Without a token provider this is the unchanged
        ``api-key`` path (delegates to :meth:`_auth_headers`, byte-identical).

        With a token provider, the token replaces the key entirely:
        ``Authorization: Bearer <token>`` and NO ``api-key`` header. A token-mint
        failure is surfaced as :class:`ProviderNetworkError` so it flows through
        the same handling as any other provider-reachability failure (and never
        leaks token material)."""

        if self._token_provider is None:
            return self._auth_headers()
        try:
            token = await self._token_provider.token()
        except ManagedIdentityError as exc:
            raise ProviderNetworkError(
                f"failed to mint Azure managed-identity token: {type(exc).__name__}",
                details={"provider": self.name},
            ) from exc
        return {"content-type": "application/json", "authorization": f"Bearer {token}"}

    def _chat_completions_path(self, *, deployment_id: str) -> str:
        return (
            f"/openai/deployments/{deployment_id}/chat/completions?api-version={self._api_version}"
        )

    def _embeddings_path(self, *, deployment_id: str) -> str:
        return f"/openai/deployments/{deployment_id}/embeddings?api-version={self._api_version}"

    def _models_path(self) -> str:
        return f"/openai/models?api-version={self._api_version}"
