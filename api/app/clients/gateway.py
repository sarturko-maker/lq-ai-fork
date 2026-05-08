"""HTTP client for the LQ.AI Inference Gateway.

A4 scope: just the construction + a `health_check()` method so the
backend's `/ready` endpoint can confirm the gateway is reachable. The
full OpenAI-compatible surface (`chat.completions.create`, etc.) lands
in Task B5 — those methods will live on this same class.

Per ADR 0002 / `.env.example`: every backend → gateway request includes
`X-LQ-AI-Gateway-Key`, the shared secret. The gateway rejects requests
without it.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

GATEWAY_KEY_HEADER = "X-LQ-AI-Gateway-Key"


class GatewayClient:
    """Async HTTP client wrapping calls to the Inference Gateway."""

    def __init__(self, base_url: str, gateway_key: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._gateway_key = gateway_key
        # The /health endpoint is unauthenticated; chat / embeddings (later)
        # require the gateway key. We attach default headers so all calls go
        # through with the shared secret unless explicitly overridden.
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={GATEWAY_KEY_HEADER: self._gateway_key} if self._gateway_key else {},
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def health_check(self) -> bool:
        """GET /health on the gateway; True iff the gateway returns 200.

        Used by the backend's /ready endpoint. Times out fast — the gateway
        being slow to respond is itself a not-ready signal.
        """
        try:
            response = await self._client.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception as exc:
            # Readiness probes never raise; report failure in the response body.
            log.warning("Gateway health check failed: %s", exc)
            return False

    async def aclose(self) -> None:
        await self._client.aclose()


_client: GatewayClient | None = None


def get_gateway_client() -> GatewayClient:
    """Return the process-global gateway client, building it on first call."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = GatewayClient(
            base_url=settings.lq_ai_gateway_url,
            gateway_key=settings.lq_ai_gateway_key,
        )
    return _client


async def close_gateway_client() -> None:
    """Close the gateway HTTP client on shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
