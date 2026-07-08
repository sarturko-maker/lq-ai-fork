"""Optional Azure Key Vault sourcing for provider API keys (ADR-F069, slice KV-1).

Threat model & motivation
-------------------------
Today the three Azure AI Foundry provider keys reach the gateway as plaintext
environment variables (``AZURE_OPENAI_API_KEY`` / ``AZURE_ANTHROPIC_API_KEY`` /
``AZURE_FOUNDRY_API_KEY``), which means they sit in ``.env.prod`` on the VM's
disk. This module offers an OPTIONAL, additive alternative: fetch those keys
from Azure Key Vault at gateway startup using the VM's **system-assigned managed
identity** (via the Instance Metadata Service, IMDS), so no key material lives on
disk.

Everything here is stdlib-only (``urllib.request`` + ``json``); we deliberately
do NOT pull the ``azure-identity`` / ``azure-keyvault-secrets`` SDKs — the two
REST calls are small and a new dependency is supply-chain surface (CLAUDE.md).

The feature is controlled entirely by NON-secret env vars (the vault name plus a
per-key secret name). When they are unset the module makes **zero** network calls
and returns an empty overlay, so the gateway's behavior is byte-identical to
today's (keys read from the plain env var).

Resolution order (ADR-F069) becomes::

    api_key_encrypted (Fernet)  ->  Key Vault overlay  ->  plain api_key_env

The overlay is fail-open: any per-secret failure logs ONE warning and omits that
key, and the existing "provider skipped, routes 503" posture covers the rest.
The gateway MUST NEVER crash over Key Vault.

Wiring choice (see ``app.main.lifespan``)
-----------------------------------------
:func:`keyvault_env_overlay` is computed ONCE per config load and its result is
merged over ``os.environ`` (the overlay WINS) into the env mapping threaded
through ``app.main.build_adapter`` -> ``<Adapter>.from_config(env=...)`` ->
:class:`app.secrets.ProviderKeyResolver`. We thread an env mapping through the
existing ``env=`` seam rather than mutating ``os.environ`` — this matches the
project's dependency-injection rule ("never reach for globals") and keeps the
fetched values in process memory only, never written to any file or global.

Rotation caveat (HONEST scope)
------------------------------
Adapters are (re)built at process start and on the BYOK admin hot-apply path —
**not** on SIGHUP. SIGHUP's ``reload_from_disk`` only swaps the in-memory config
snapshot; it does not rebuild adapters (see ``app.provider_keys`` module notes).
So to pick up a ROTATED Key Vault secret you must recreate the gateway process
(``dc up -d gateway``); a SIGHUP alone does not re-source keys.

And the managed-identity honesty note: sourcing keys from Key Vault removes them
from disk, but any process on the VM can mint the same IMDS token — the token is
host-scoped, not process-scoped.

Secret hygiene
--------------
No fetched value (nor its length) is ever logged. The only things logged are the
NON-secret target env-var name, the vault name, and the secret name. Env-driven
values that build URLs (the vault name and the secret name) are validated against
a strict allow-list regex BEFORE any URL is constructed (env-driven URL-injection
guard).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol

logger = logging.getLogger(__name__)

__all__ = [
    "KEY_VAULT_NAME_ENV",
    "SECRET_NAME_ENVS",
    "ImdsKeyVaultFetcher",
    "KeyVaultFetchError",
    "KeyVaultFetcher",
    "keyvault_env_overlay",
]


KEY_VAULT_NAME_ENV = "AZURE_KEY_VAULT_NAME"
"""Non-secret env var naming the Key Vault (the ``<name>`` in
``https://<name>.vault.azure.net``). Unset/empty ⇒ Key Vault sourcing is off."""

SECRET_NAME_ENVS: dict[str, str] = {
    "AZURE_OPENAI_API_KEY": "AZURE_OPENAI_KEY_SECRET_NAME",
    "AZURE_ANTHROPIC_API_KEY": "AZURE_ANTHROPIC_KEY_SECRET_NAME",
    "AZURE_FOUNDRY_API_KEY": "AZURE_FOUNDRY_KEY_SECRET_NAME",
}
"""Map each target provider-key env var → the NON-secret env var that names its
Key Vault secret. A target is sourced from Key Vault only when its secret-name
env var is set; otherwise the plain provider-key env var is used (today's
behavior)."""


# Env-driven values interpolated into request URLs are validated against these
# allow-lists BEFORE any URL is built. Azure's own naming rules: vault names are
# 3-24 chars of ``[A-Za-z0-9-]``; secret names are 1-127 chars of the same set.
_VAULT_NAME_RE = re.compile(r"^[A-Za-z0-9-]{3,24}$")
_SECRET_NAME_RE = re.compile(r"^[A-Za-z0-9-]{1,127}$")

# IMDS token endpoint for the Key Vault data-plane audience. The whole URL is a
# fixed literal — no env-driven interpolation — so it needs no validation.
_IMDS_TOKEN_URL = (
    "http://169.254.169.254/metadata/identity/oauth2/token"
    "?api-version=2018-02-01&resource=https%3A%2F%2Fvault.azure.net"
)
_IMDS_TIMEOUT_SECONDS = 5.0
_VAULT_TIMEOUT_SECONDS = 10.0
_SECRET_API_VERSION = "7.4"


class KeyVaultFetchError(RuntimeError):
    """A single Key Vault fetch failed (IMDS token mint or secret read).

    Carries no secret material — only enough context (vault, secret name) for an
    operator to diagnose. Callers catch this per-secret, log ONE warning, and
    omit that key (fail-open to the plain env var).
    """


class KeyVaultFetcher(Protocol):
    """Fetch one Key Vault secret's value by ``(vault, secret_name)``.

    A :class:`~typing.Protocol` so tests inject a hermetic fake through the same
    seam the live :class:`ImdsKeyVaultFetcher` satisfies — no network in unit
    tests.
    """

    def fetch(self, vault: str, secret_name: str) -> str: ...


class ImdsKeyVaultFetcher:
    """Fetch Key Vault secrets via the VM's system-assigned managed identity.

    Two REST calls, stdlib only:

    1. GET the IMDS token endpoint (``169.254.169.254``) with header
       ``Metadata: true`` to mint a ``vault.azure.net`` access token (5s timeout,
       one retry on failure).
    2. GET ``https://{vault}.vault.azure.net/secrets/{secret}?api-version=7.4``
       with ``Authorization: Bearer <token>`` (10s timeout); return the JSON
       ``value``.

    The IMDS token is cached for the life of the instance, so one token serves
    all three secrets in a single config-load pass.
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_error: str | None = None

    def fetch(self, vault: str, secret_name: str) -> str:
        """Return the plaintext value of ``secret_name`` in ``vault``.

        Callers (``keyvault_env_overlay``) validate ``vault`` and ``secret_name``
        against the allow-list regexes before invoking this; the secret name is
        additionally percent-quoted here as defense in depth.
        """

        token = self._token_cached()
        secret_url = (
            f"https://{vault}.vault.azure.net/secrets/"
            f"{urllib.parse.quote(secret_name, safe='')}"
            f"?api-version={_SECRET_API_VERSION}"
        )
        payload = self._get_json(
            secret_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=_VAULT_TIMEOUT_SECONDS,
        )
        value = payload.get("value")
        if not isinstance(value, str) or not value:
            raise KeyVaultFetchError(
                f"Key Vault secret {secret_name!r} in vault {vault!r} "
                "had no non-empty string 'value' field"
            )
        return value

    def _token_cached(self) -> str:
        """Return the cached IMDS token, minting it on first use.

        A FAILED mint is cached too: without that, every configured secret
        re-attempts the mint (retry included), turning an absent IMDS into a
        per-secret boot delay instead of one bounded failure.
        """

        if self._token_error is not None:
            raise KeyVaultFetchError(self._token_error)
        if self._token is not None:
            return self._token
        try:
            payload = self._get_json_with_one_retry(
                _IMDS_TOKEN_URL,
                headers={"Metadata": "true"},
                timeout=_IMDS_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            self._token_error = f"IMDS token mint failed: {type(exc).__name__}: {exc}"
            raise KeyVaultFetchError(self._token_error) from exc
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            self._token_error = "IMDS token response had no 'access_token'"
            raise KeyVaultFetchError(self._token_error)
        self._token = token
        return token

    def _get_json_with_one_retry(
        self, url: str, *, headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        """GET+parse ``url``, retrying exactly once on a network/parse failure.

        IMDS can be briefly unavailable right at VM/container boot; a single
        retry smooths that without turning a persistent outage into a hang.
        """

        try:
            return self._get_json(url, headers=headers, timeout=timeout)
        except (urllib.error.URLError, OSError, ValueError):
            return self._get_json(url, headers=headers, timeout=timeout)

    @staticmethod
    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        """Issue a GET and parse a JSON object body. Raises on a non-object body.

        Proxies are deliberately bypassed: Azure mandates that IMDS traffic
        never routes through a proxy, and the vault call is direct TLS. The
        read is capped so a link-local endpoint cannot drip-feed bytes past
        the per-recv timeout and stall boot.
        """

        request = urllib.request.Request(url, headers=headers, method="GET")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(1 << 20)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise KeyVaultFetchError("Key Vault / IMDS returned a non-object JSON body")
        return parsed


def keyvault_env_overlay(
    env: Mapping[str, str],
    *,
    fetcher: KeyVaultFetcher | None = None,
) -> dict[str, str]:
    """Return provider-key env overrides sourced from Azure Key Vault.

    Returns ``{}`` immediately — making ZERO network calls — when
    :data:`KEY_VAULT_NAME_ENV` is unset/empty or no ``*_SECRET_NAME`` var in
    :data:`SECRET_NAME_ENVS` is set. That is today's behavior.

    Otherwise, for each target whose secret-name var is set, fetch the secret and
    map ``target_env_var -> fetched_value`` in the returned overlay. Per-secret
    failures are fail-open: log ONE warning (carrying no secret material) and omit
    that key so the caller falls back to the plain env var if present. The gateway
    never crashes over Key Vault.

    ``fetcher`` is injected for tests; the live default is a single
    :class:`ImdsKeyVaultFetcher` built lazily only when there is real work to do
    (so the ``{}`` fast path constructs nothing and opens no socket). Reusing one
    instance across all targets is what lets the IMDS token be minted once.
    """

    vault = (env.get(KEY_VAULT_NAME_ENV) or "").strip()
    if not vault:
        return {}

    # Which targets did the operator opt into (their secret-name var is set)?
    requested: list[tuple[str, str]] = []  # (target_env, secret_name)
    for target_env, secret_name_env in SECRET_NAME_ENVS.items():
        secret_name = (env.get(secret_name_env) or "").strip()
        if secret_name:
            requested.append((target_env, secret_name))
    if not requested:
        # Vault named but no per-key secret configured → nothing to source.
        return {}

    if _VAULT_NAME_RE.fullmatch(vault) is None:
        # Env-driven URL-injection guard: refuse to build a URL from a bad name.
        logger.warning(
            "Key Vault sourcing skipped: %s is not a valid vault name (must match %s)",
            KEY_VAULT_NAME_ENV,
            _VAULT_NAME_RE.pattern,
        )
        return {}

    active_fetcher: KeyVaultFetcher = fetcher if fetcher is not None else ImdsKeyVaultFetcher()
    overlay: dict[str, str] = {}
    for target_env, secret_name in requested:
        if _SECRET_NAME_RE.fullmatch(secret_name) is None:
            logger.warning(
                "Key Vault sourcing skipped for %s: secret name from %s is invalid (must match %s)",
                target_env,
                SECRET_NAME_ENVS[target_env],
                _SECRET_NAME_RE.pattern,
            )
            continue
        try:
            value = active_fetcher.fetch(vault, secret_name)
        except Exception as exc:  # fail-open: never crash the gateway over Key Vault
            logger.warning(
                "Key Vault fetch failed for %s (vault=%s secret=%s): %s: %s "
                "— falling back to the plain environment variable if set",
                target_env,
                vault,
                secret_name,
                type(exc).__name__,
                exc,
            )
            continue
        if not value:
            # An empty secret must never override a valid plaintext key with ""
            # (the provider would be skipped while the log claimed success).
            logger.warning(
                "Key Vault returned an EMPTY value for %s (vault=%s secret=%s) "
                "— ignoring it; falling back to the plain environment variable if set",
                target_env,
                vault,
                secret_name,
            )
            continue
        overlay[target_env] = value
        if env.get(target_env):
            logger.info(
                "sourced %s from Azure Key Vault (vault=%s secret=%s) — "
                "overriding the existing plaintext environment variable",
                target_env,
                vault,
                secret_name,
            )
        else:
            logger.info(
                "sourced %s from Azure Key Vault (vault=%s secret=%s)",
                target_env,
                vault,
                secret_name,
            )
    return overlay
