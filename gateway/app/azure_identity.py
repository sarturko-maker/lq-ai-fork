"""Optional keyless auth for Azure OpenAI via the VM's managed identity (AZ-6, ADR-F072).

Motivation
----------
KV-1 (:mod:`app.keyvault`) removed the Azure OpenAI *API key* from disk by
sourcing it from Key Vault at boot. AZ-6 goes one step further and removes the
static key entirely: when ``AZURE_OPENAI_USE_MANAGED_IDENTITY=true`` the gateway
mints a short-lived Entra bearer token from the VM's **system-assigned managed
identity** and sends ``Authorization: Bearer <token>`` to Azure OpenAI instead of
``api-key: <key>``. No static model key exists anywhere; the token auto-expires
(~1 h) and is refreshed in place.

Everything here is stdlib-only (``urllib.request`` + ``json``) — the SAME IMDS
technique KV-1 already uses (``169.254.169.254``, ``Metadata: true``, no proxy,
capped read, one boot-retry). We deliberately do NOT pull the ``azure-identity``
SDK — a token mint is two dozen lines and a new dependency is supply-chain
surface (CLAUDE.md). This module is self-contained (KV-1 is left byte-identical);
the small IMDS-GET overlap with :mod:`app.keyvault` is accepted rather than
refactor a shipped, security-reviewed auth module in the same slice.

Token scope (the silent-401 trap — confirmed against current Microsoft docs)
---------------------------------------------------------------------------
The gateway's ``azure_openai`` adapter targets the **classic AOAI data-plane**
route ``/openai/deployments/<deployment>/chat/completions?api-version=…``. Its
Entra audience is ``https://cognitiveservices.azure.com``.

IMDS uses the v1 ``resource=`` form — the **bare audience, WITHOUT** the
``/.default`` suffix (``/.default`` belongs only to an MSAL/SDK ``scope``; putting
it in the IMDS ``resource=`` query is the classic silent 401). This mirrors KV-1's
working ``resource=https://vault.azure.net`` and Microsoft's documented
``az account get-access-token --resource https://cognitiveservices.azure.com``.

Route caveat: Microsoft's newer ``/openai/v1/`` route uses the audience
``https://ai.azure.com`` instead. The two genuinely diverge, so the audience is
CONFIGURABLE via :data:`IDENTITY_RESOURCE_ENV` — the default is correct for our
adapter's classic route; an operator on the newer route sets one env var.

Azure-side prerequisite (documented in the runbook): the VM's managed identity
needs a role granting **model inference** on the Foundry/AOAI resource — the
built-in **"Cognitive Services OpenAI User"** role — NOT merely "Key Vault
Secrets User" (which only unlocks KV-1).

Honesty note (recorded in ADR-F072)
-----------------------------------
Managed identity removes the on-disk key, but the trust boundary is the HOST, not
the process: **any process running on this VM can hit IMDS and mint the same
token.** Managed identity narrows the blast radius (no long-lived exfiltratable
key; auto-expiry; Azure-side RBAC + revocation) but does not isolate the gateway
process from co-tenant processes on the box. Same caveat as KV-1's IMDS token.

Secret hygiene
--------------
The minted token is a bearer credential: it is NEVER logged (nor its length). The
only things logged are the NON-secret resource audience and the token's numeric
expiry. The audience is validated against a strict ``https://`` allow-list regex
before it is ever interpolated into the IMDS URL (env-driven URL-injection guard).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "IDENTITY_RESOURCE_ENV",
    "USE_MANAGED_IDENTITY_ENV",
    "ManagedIdentityError",
    "ManagedIdentityTokenProvider",
    "TokenProvider",
    "build_managed_identity_provider",
    "managed_identity_enabled",
    "managed_identity_resource",
]


USE_MANAGED_IDENTITY_ENV = "AZURE_OPENAI_USE_MANAGED_IDENTITY"
"""Non-secret flag. Truthy (``1``/``true``/``yes``/``on``, case-insensitive) ⇒
the ``azure_openai`` adapter authenticates with a managed-identity bearer token
instead of an API key. Unset/empty ⇒ behaviour byte-identical to today."""

IDENTITY_RESOURCE_ENV = "AZURE_OPENAI_IDENTITY_RESOURCE"
"""Optional override for the Entra audience the token is minted for. Defaults to
:data:`_DEFAULT_IDENTITY_RESOURCE` (correct for the classic AOAI deployments
route); set to ``https://ai.azure.com`` for the newer ``/openai/v1/`` route."""

# The v1 IMDS `resource` form — the BARE audience, no `/.default` (see module docstring).
_DEFAULT_IDENTITY_RESOURCE = "https://cognitiveservices.azure.com"

# IMDS token endpoint (fixed literal + one url-encoded, regex-validated audience).
_IMDS_TOKEN_URL_PREFIX = (
    "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource="
)
_IMDS_TIMEOUT_SECONDS = 5.0
# Refresh this many seconds BEFORE the token's stated expiry so an in-flight
# request never carries an about-to-expire (or just-expired) token.
_REFRESH_SKEW_SECONDS = 300.0
# Conservative lifetime if IMDS omits an expiry (should not happen): short vs the
# real ~1 h so we re-mint soon, but comfortably ABOVE the refresh skew so even the
# fallback still yields cache hits (never a re-mint on every single request).
_FALLBACK_TTL_SECONDS = 600.0

# The audience is interpolated into the IMDS URL, so validate it first: a bare
# ``https://host`` with no path/query/fragment (both documented audiences fit).
_RESOURCE_RE = re.compile(r"^https://[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def managed_identity_enabled(env: Mapping[str, str]) -> bool:
    """Whether the managed-identity flag is set truthy in ``env``."""

    return (env.get(USE_MANAGED_IDENTITY_ENV) or "").strip().lower() in _TRUTHY


class ManagedIdentityError(RuntimeError):
    """A managed-identity token mint failed. Carries no token material."""


@runtime_checkable
class TokenProvider(Protocol):
    """Yield a currently-valid bearer token. Async so the adapter can await a
    refresh without blocking the event loop; a :class:`~typing.Protocol` so tests
    inject a hermetic fake through the same seam the live provider satisfies."""

    async def token(self) -> str: ...


class ManagedIdentityTokenProvider:
    """Mint + cache an Entra bearer token from the VM's managed identity via IMDS.

    The token is fetched lazily on first use and cached until
    :data:`_REFRESH_SKEW_SECONDS` before its ``expires_on``; concurrent callers
    serialize on an :class:`asyncio.Lock` so the token is minted once per refresh,
    not once per request. The blocking ``urllib`` mint runs in a worker thread
    (:func:`asyncio.to_thread`) so it never stalls the event loop.
    """

    def __init__(self, *, resource: str, now: Callable[[], float] = time.time) -> None:
        self._resource = resource
        self._token_url = _IMDS_TOKEN_URL_PREFIX + urllib.parse.quote(resource, safe="")
        self._now = now
        self._cached: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        """Return a valid bearer token, refreshing it if within the skew of expiry."""

        cached = self._cached
        if cached is not None and self._now() < self._expires_at - _REFRESH_SKEW_SECONDS:
            return cached
        async with self._lock:
            # Re-check under the lock: a concurrent caller may have just refreshed.
            cached = self._cached
            if cached is not None and self._now() < self._expires_at - _REFRESH_SKEW_SECONDS:
                return cached
            try:
                payload = await asyncio.to_thread(self._mint_blocking)
            except ManagedIdentityError:
                # A refresh that fails INSIDE the early-refresh skew window must not
                # 503 the request while the cached token is still valid — refreshing
                # early exists precisely to absorb a transient IMDS blip. Serve the
                # still-valid token; a later request retries the refresh. Only
                # re-raise once there is no un-expired token left to fall back to.
                if cached is not None and self._now() < self._expires_at:
                    logger.warning(
                        "Azure managed-identity token refresh failed; serving the "
                        "still-valid cached token (resource=%s, expires_at=%d)",
                        self._resource,
                        int(self._expires_at),
                    )
                    return cached
                raise
            access = payload.get("access_token")
            if not isinstance(access, str) or not access:
                raise ManagedIdentityError("IMDS token response had no 'access_token'")
            self._cached = access
            self._expires_at = self._expiry_from(payload)
            logger.info(
                "minted Azure managed-identity token (resource=%s, expires_at=%d)",
                self._resource,
                int(self._expires_at),
            )
            return access

    def _expiry_from(self, payload: Mapping[str, Any]) -> float:
        """Absolute epoch expiry from the IMDS payload.

        Prefer ``expires_on`` (absolute epoch seconds, IMDS's canonical field);
        fall back to ``expires_in`` (relative seconds) and finally a short floor,
        so a missing/garbled expiry causes prompt re-minting, never a stale token
        trusted for an hour.
        """

        raw_on = payload.get("expires_on")
        if raw_on is not None:
            try:
                return float(int(raw_on))
            except (TypeError, ValueError):
                pass
        raw_in = payload.get("expires_in")
        if raw_in is not None:
            try:
                return self._now() + float(int(raw_in))
            except (TypeError, ValueError):
                pass
        return self._now() + _FALLBACK_TTL_SECONDS

    def _mint_blocking(self) -> dict[str, Any]:
        try:
            return self._get_json_with_one_retry(
                self._token_url,
                headers={"Metadata": "true"},
                timeout=_IMDS_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise ManagedIdentityError(
                f"IMDS token mint failed for resource {self._resource!r}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _get_json_with_one_retry(
        self, url: str, *, headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        """GET+parse ``url``, retrying exactly once (IMDS can blip at VM boot)."""

        try:
            return self._get_json(url, headers=headers, timeout=timeout)
        except (urllib.error.URLError, OSError, ValueError):
            return self._get_json(url, headers=headers, timeout=timeout)

    @staticmethod
    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        """Issue a GET and parse a JSON object body (proxies bypassed, read capped).

        Azure mandates IMDS traffic never route through a proxy; the read is capped
        so a link-local endpoint cannot drip-feed bytes past the timeout and stall.
        """

        request = urllib.request.Request(url, headers=headers, method="GET")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(1 << 20)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ManagedIdentityError("IMDS returned a non-object JSON body")
        return parsed


def managed_identity_resource(env: Mapping[str, str]) -> str:
    """The validated Entra audience to mint for — the override or the default.

    Raises :class:`ManagedIdentityError` if the override is not a bare
    ``https://host`` audience (env-driven URL-injection guard): a malformed value
    must fail loudly at construction, never silently build a wrong-scope URL that
    401s at request time.
    """

    resource = (env.get(IDENTITY_RESOURCE_ENV) or "").strip() or _DEFAULT_IDENTITY_RESOURCE
    if _RESOURCE_RE.fullmatch(resource) is None:
        raise ManagedIdentityError(
            f"{IDENTITY_RESOURCE_ENV} must be a bare https audience URL "
            f"(e.g. https://cognitiveservices.azure.com); got {resource!r}"
        )
    return resource


def build_managed_identity_provider(
    env: Mapping[str, str],
) -> ManagedIdentityTokenProvider | None:
    """A token provider when the flag is set, else ``None`` (the api-key path).

    Constructs no socket and mints no token here — the provider fetches lazily on
    first request — so a mis-set flag never delays or fails gateway boot beyond
    the audience-validation guard.
    """

    if not managed_identity_enabled(env):
        return None
    return ManagedIdentityTokenProvider(resource=managed_identity_resource(env))
