# F072 — AZ-6: keyless Azure OpenAI auth via the VM's managed identity

- Status: proposed
- Date: 2026-07-09
- Deciders: maintainer (Arturs), agent
- Supersedes/relates: extends ADR-F069 (KV-1 Key Vault sourcing); scoped to the
  `azure_openai` adapter (ADR-F066/AZ-CONFIG lineage).

## Context

The preferred security model for private-VM Azure deployments is **managed identity /
OAuth directly from the VM to Azure AI Foundry** — no static model key, short-lived
dynamic tokens. KV-1 (ADR-F069) was the hardened interim: it moved the
`AZURE_OPENAI_API_KEY` off disk by sourcing it from Key Vault at boot, but a
long-lived key still exists in the vault and is handed to the adapter verbatim.

AZ-6 removes the static key entirely: when enabled, the gateway mints a short-lived
Entra bearer token from the VM's **system-assigned managed identity** and sends
`Authorization: Bearer <token>` to Azure OpenAI instead of `api-key: <key>`. The token
auto-expires (~1 h) and is refreshed in place; nothing exfiltratable lives on disk or
in a vault.

Two facts drove the design (confirmed against current Microsoft Learn docs, 2026-07-09):

- **Scope (the silent-401 trap).** The gateway's `azure_openai` adapter targets the
  classic AOAI data-plane route `/openai/deployments/<deployment>/chat/completions`.
  Its Entra audience is `https://cognitiveservices.azure.com`. IMDS uses the v1
  `resource=` form — the **bare audience, WITHOUT** `/.default` (that suffix is only for
  an MSAL/SDK `scope`; putting it in the IMDS `resource=` query is the classic silent
  401). This mirrors KV-1's working `resource=https://vault.azure.net` and the
  documented `az account get-access-token --resource https://cognitiveservices.azure.com`.
  Microsoft's newer `/openai/v1/` route uses a different audience
  (`https://ai.azure.com`), so the audience is **configurable**.
- **RBAC.** The VM's managed identity needs a role granting **model inference** on the
  Foundry/AOAI resource — the built-in **"Cognitive Services OpenAI User"** role — NOT
  merely "Key Vault Secrets User" (which only unlocks KV-1).

## Considered options

1. **`azure-identity` SDK (`DefaultAzureCredential` + `get_bearer_token_provider`).**
   Microsoft's documented path. Rejected: a new runtime dependency is supply-chain
   surface (CLAUDE.md), and it is far heavier than needed — a managed-identity token is
   two IMDS calls we already make in KV-1. We keep stdlib-only.
2. **Stdlib IMDS token mint (CHOSEN).** Reuse KV-1's exact IMDS technique
   (`169.254.169.254`, `Metadata: true`, no-proxy, capped read, one boot-retry) in a new
   self-contained `app/azure_identity.py`, with expiry-aware caching. No new dependency;
   KV-1 left byte-identical (the small IMDS-GET overlap is accepted over refactoring a
   shipped, security-reviewed auth module in the same slice).
3. **Per-provider config field vs global env flag.** Chose a **global env flag**
   (`AZURE_OPENAI_USE_MANAGED_IDENTITY`) — minimal, consistent with KV-1's env-driven
   control, and correct for the Option-A stack-per-tenant topology (one `azure_openai`
   provider per stack). A per-provider field can layer on later without breaking this.

## Decision outcome

Chosen: **option 2**, env-flag-gated, additive, default-off.

- `AZURE_OPENAI_USE_MANAGED_IDENTITY=true` ⇒ the `azure_openai` adapter authenticates
  with a managed-identity bearer token; **no API key is resolved or required**. Unset ⇒
  behaviour byte-identical to today (API-key / Key-Vault path untouched).
- `ManagedIdentityTokenProvider` mints lazily on first request, caches the token on its
  `expires_on`, and refreshes 5 minutes before expiry under an `asyncio.Lock` (minted
  once per refresh, not per request); the blocking mint runs in a worker thread so it
  never stalls the event loop. A mint failure surfaces as `ProviderNetworkError` (handled
  like any provider-unreachable failure) and never leaks token material.
- Audience defaults to `https://cognitiveservices.azure.com` (correct for the classic
  route) and is overridable via `AZURE_OPENAI_IDENTITY_RESOURCE` (e.g.
  `https://ai.azure.com` for the newer `/openai/v1/` route). The override is validated
  against a strict `https://` allow-list before it is interpolated into the IMDS URL.

## Consequences

- **Positive.** No static Azure OpenAI key exists on disk or in Key Vault; the token
  auto-expires and is bounded by Azure-side RBAC (Cognitive Services OpenAI User) and
  revocation. Tool-calling and streaming are unchanged (auth is orthogonal to the body
  translation — the `_to_openai_request` path is reused verbatim).
- **Honesty note (load-bearing).** Managed identity removes the key but the trust
  boundary is the **HOST, not the process**: **any process running on this VM can hit
  IMDS and mint the same token.** MI narrows the blast radius (no long-lived
  exfiltratable key; auto-expiry; RBAC + revocation) but does not isolate the gateway
  process from co-tenant processes on the box — the same caveat KV-1 already carries for
  its IMDS token.
- **Rotation is easier than KV-1.** The token refreshes in-process on expiry — no
  gateway restart. (KV-1 key rotation needs a gateway recreate because adapters are not
  rebuilt on SIGHUP.)
- **Route caveat.** The audience genuinely differs between the classic deployments route
  and the newer `/openai/v1/` route; a wrong audience is a silent 401. Mitigated by the
  configurable, validated `AZURE_OPENAI_IDENTITY_RESOURCE` (default correct for our route).
- **Scope.** Covers the `azure_openai` adapter only — Azure OpenAI/GPT and
  Mistral-on-Foundry served over the AOAI deployments route. `azure-claude` (Anthropic on
  Foundry, `x-api-key`) is NOT covered by this slice; a managed-identity path for it is a
  separate, later slice if wanted.
- **Verification.** Deterministic unit tests are hermetic (IMDS faked). The live proof —
  GPT-5.4 chat + tool-calling through managed identity from a real VM — is an operator
  synthetic smoke in the runbook (§4c/§5), since dev/CI have no Azure resource.
