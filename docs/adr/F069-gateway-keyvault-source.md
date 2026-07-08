# F069 — Gateway provider keys sourced from Azure Key Vault (managed identity)

Status: proposed
Date: 2026-07-08
Deciders: maintainer + agent lead
Slice: KV-1 (gateway Key Vault provider-key sourcing)

## Context

On the Azure VM sandbox (ADR-F058 self-host, runbook `docs/fork/runbooks/azure-vm-sandbox.md`) the
three Azure AI Foundry provider keys reach the gateway as plaintext environment variables
(`AZURE_OPENAI_API_KEY` / `AZURE_ANTHROPIC_API_KEY` / `AZURE_FOUNDRY_API_KEY`), which means they live
in `.env.prod` on the VM's disk. The gateway already supports two key sources per provider
(ADR 0011): `api_key_encrypted` (Fernet, decrypted in-memory via `LQ_AI_GATEWAY_MASTER_KEY`) and
`api_key_env` (plain env var), resolved at adapter-build time by
`app.secrets.ProviderKeyResolver.resolve()` against an injected `env` mapping.

We want an OPTIONAL way to keep the Azure keys off disk by sourcing them from Azure Key Vault using
the VM's system-assigned managed identity — additive, with an exact fallback to today's behavior
when unconfigured. Two hard constraints: the repository is PUBLIC (no secrets, no real vault or
resource names anywhere), and the gateway is the security boundary (it must never crash over an
optional feature). The gateway image is `python:3.12-slim` (no `curl`), and `mypy --strict` gates
gateway code.

## Considered Options

1. **curl/REST in the container entrypoint** — the entrypoint fetches the secrets and exports them
   as env vars before starting uvicorn. Rejected: the slim image has no `curl`; it writes fetched
   values into the process env of a shell script (extra handling surface); and it splits the logic
   across shell + Python, invisible to `mypy`/tests.
2. **`azure-identity` + `azure-keyvault-secrets` SDKs** — the supported Azure path. Rejected for
   KV-1: two heavy new dependencies (plus transitive `azure-core`, `msal`, `cryptography` pins) are
   SBOM/supply-chain surface for two small REST calls, and they pull an opinionated auth-chain we
   don't need (we only ever want IMDS on the VM).
3. **stdlib, in-process, threaded through the existing key-resolution seam (CHOSEN)** — a new
   `app.keyvault` module (only `urllib.request` + `json`) fetches each configured secret via IMDS at
   config-load time; the values are merged over `os.environ` (overlay wins) into the env mapping the
   gateway already threads down to `ProviderKeyResolver`.

## Decision Outcome

Chosen: **option 3**. `app.keyvault.keyvault_env_overlay(env)` returns `{}` — making zero network
calls — unless `AZURE_KEY_VAULT_NAME` and at least one `AZURE_*_KEY_SECRET_NAME` are set. When
configured it fetches each opted-in secret through a `KeyVaultFetcher` (live `ImdsKeyVaultFetcher`;
tests inject a fake) and maps `target_env_var -> value`. The vault name and each secret name are
validated against strict allow-list regexes (`^[A-Za-z0-9-]{3,24}$`, `^[A-Za-z0-9-]{1,127}$`) BEFORE
any URL is built (env-driven URL-injection guard). The IMDS token is cached on the fetcher instance,
so one token serves all three secrets in a load pass.

`app.main.lifespan` computes the overlay ONCE per config load and threads
`{**os.environ, **overlay}` into `build_adapter(provider, env=...)` — the single chokepoint where
adapters are built — and thence into every `from_config` factory's `ProviderKeyResolver`. We thread
the mapping through the existing `env=` seam rather than mutating `os.environ`, matching the
project's dependency-injection rule and keeping fetched values in process memory only (never written
to a file or a global).

**Resolution order becomes: `api_key_encrypted` → Key Vault overlay → plain `api_key_env`.** The
overlay is additive per-pair (each Azure key configured independently) and **fail-open to env with a
loud warning**: a per-secret fetch failure logs one WARNING (no secret material) and omits that key,
so the provider falls back to its plain env var or, failing that, is skipped and routes 503 — the
existing posture. stdlib only, no new dependencies.

## Consequences

- Keys can be kept off disk on the Azure VM: set the vault + secret-name vars, drop the plaintext
  `AZURE_*_API_KEY` lines. Unconfigured, behavior is byte-identical to before KV-1 (empty overlay,
  no sockets opened).
- **Managed-identity honesty note.** Sourcing from Key Vault removes the keys at rest, but any
  process on the VM can hit IMDS and mint the same `vault.azure.net` token, then read the same
  secrets. This raises the bar against a stolen `.env.prod`, not against code running on the box.
- **Rotation is process-restart-scoped, NOT SIGHUP.** Adapters are (re)built at process start and on
  the BYOK admin hot-apply path — not on SIGHUP, which only swaps the in-memory config snapshot and
  never rebuilds adapters (`app.provider_keys` relies on this). So re-sourcing a rotated Key Vault
  secret requires recreating the gateway (`dc up -d gateway`); a SIGHUP does not re-fetch. (This
  corrects the KV-1 task's assumption that SIGHUP re-fetches — the current gateway does not rebuild
  adapters on SIGHUP.)
- The overlay wins over a stale plaintext env var, and logs an INFO line when it overrides, so a
  half-migrated `.env.prod` cannot silently pin an old key.
- New surface is small and hermetically testable (`gateway/tests/test_keyvault.py`) via the injected
  fetcher seam; no live Azure needed for CI. The one live proof is the runbook §4b log-line + §5.3
  smoke.
- Supersedes nothing; extends ADR 0011's key-source model with a third source. If a future slice
  needs cross-cloud secret managers or non-IMDS auth, revisit option 2.
