# AZ-R — Azure AI Foundry Phase 1 research report

Date: 2026-07-07. Scope: the maintainer's Phase 1 brief — confirm Foundry surfaces for three model
families (OpenAI/GPT, Anthropic Claude, Mistral) + Voyage embeddings, inspect the repo, and deliver a
CONFIG-ONLY vs CODE-CHANGE verdict per family. **No code in this phase.** Sources: Microsoft Learn /
Anthropic platform docs fetched 2026-07-07 (page URLs at the end) + direct repo inspection.

## Verdict table

| Family | Verdict | Why |
|---|---|---|
| **OpenAI/GPT on Azure** | **CONFIG-ONLY** | A dedicated `azure_openai` adapter already exists in the gateway (`gateway/app/providers/azure_openai.py`): deployment-scoped path, `?api-version=`, `api-key` header, embeddings, streaming, tool-calling (OpenAI-family). `.env.example` + compose already carry `AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_RESOURCE`, and `gateway.yaml.example:140-160` already ships a commented entry. Enabling = fill the two env vars + set `models:` to your deployment names + add aliases. |
| **Claude on Foundry** | **CONFIG-ONLY for text · CODE CHANGE for agent (tool) use** | The existing `anthropic` provider type reads `base_url` from config and posts to `{base_url}/v1/messages` with `x-api-key` + `anthropic-version: 2023-06-01` — all three match Foundry's confirmed surface exactly, so pointing it at `https://<resource>.services.ai.azure.com/anthropic` works as-is for plain chat. **But the Anthropic adapter is still text-only** (`_to_anthropic_request` never forwards `tools` — the original fork blocker #2, deferred at B3). Deep Agents require tool calling, so using Claude as an *agent* model needs the tools translation built in `anthropic.py`. That is a real (well-scoped) gateway slice, useful for direct Anthropic too. |
| **Mistral via Foundry** | **CONFIG-ONLY** (verdict improved by research) | The `/models` Model Inference route we hypothesized is now the LEGACY path (its beta SDK retires 2026-08-26; the migration guide pushes to OpenAI/v1). Foundry now serves non-OpenAI "Foundry Models" (Mistral-Large-3, DeepSeek…) over routes the gateway already speaks: (i) the AOAI-classic deployments path `https://<resource>.services.ai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=2024-10-21` → our existing `azure_openai` adapter, config-only; (ii) the GA `/openai/v1/` route with plain-OpenAI wire + `Authorization: Bearer <foundry-key>` → our existing `type: openai`, config-only. No new adapter. Caveat: per-model tool-calling gaps on Azure (Mistral-Large-3 ✓; medium-3-5 and Codestral ✗) — only Large-3 is agent-capable. |
| **Voyage embeddings** | **CODE CHANGE + deployment cost — recommend defer/split** | Voyage IS on Azure, two ways, both awkward: serverless Foundry catalog has only general-purpose voyage-3.5/voyage-4 (Marketplace-billed, **Voyage-native schema** incl. `input_type`, endpoint shape not Learn-documented — verify post-deployment); **voyage-law-2 (the legal one) is only an Azure Managed App: ~$5+/hr always-on GPU in your own VNet**, HTTP private endpoint. Either way: new gateway adapter (Voyage shape) + additive `vector(1024)` column + `EmbeddingProvider` variant. Azure-native alternative that is CONFIG-ONLY today: `text-embedding-3-large/small` via the existing `azure_openai` embeddings path (supports the `dimensions` param our Door B already sends). |

## (a) OpenAI / GPT on Azure — confirmed facts

- **Base URL**: `https://<resource>.openai.azure.com`. Two live paths:
  - **Classic** (what our adapter implements): `POST /openai/deployments/{deployment}/chat/completions?api-version=YYYY-MM-DD` — `api-version` required; deployment name in the URL. Current classic GA data-plane version includes `2024-10-21`. Our example config pins `2024-08-01-preview` — recommend moving the example to a GA version when enabling.
  - **v1 GA** (newer): `POST /openai/v1/chat/completions` — no `api-version`, plain `openai` SDK with `base_url`, `model` = deployment name in the body. Confirmed GA; also served on `https://<resource>.services.ai.azure.com/openai/v1/`. **Recommendation: stay on the classic path** — our adapter already implements it and Microsoft keeps it fully supported; a v1 switch is a one-string path change later if ever needed.
- **Auth**: header `api-key: <key>` (implemented). Entra ID = `Authorization: Bearer`; scope is
  `https://cognitiveservices.azure.com/.default` (classic, still documented — safe default) with newer
  docs using `https://ai.azure.com/.default`. **The gateway has no Entra support today** (keys only,
  via `api_key_env` / encrypted store) — keyless auth would be a new dependency (`azure-identity`,
  SBOM) + a token-refresh seam. **Recommendation: key-based now; Entra as a separate later slice** (AZ-6
  enterprise posture), with the audience configurable.
- **`model` semantics**: deployment name (URL on classic; body on v1). Our config comment already says
  this (`gateway.yaml.example:154-157`).
- **Tools/streaming**: full OpenAI wire parity (SSE, `tools`/`tool_calls`, `parallel_tool_calls`).
  Azure adds `content_filter_results` fields to responses — our adapter parses the OpenAI shape and
  tolerates extras. No documented gaps for chat tool-calling/streaming.
- **Regions**: current GPT (4o/4.1/5.x) Global Standard in ~30 regions worldwide — effectively not a
  constraint. Newest models (gpt-5.5) may need quota-tier requests.

## (b) Anthropic Claude on Foundry — confirmed facts

- **GA** on Foundry; per-model choice of "Hosted on Azure" vs "Hosted on Anthropic infrastructure".
- **Base URL confirmed**: `https://<resource>.services.ai.azure.com/anthropic`; the Messages endpoint is
  `…/anthropic/v1/messages` — the client appends `/v1/messages`, exactly as our adapter does
  (`anthropic.py:311` posts `/v1/messages` onto the configured base_url). **Native Anthropic Messages
  shape**, not OpenAI-compatible.
- **Auth**: `api-key` **or** `x-api-key` header — our adapter sends `x-api-key` (accepted). Entra
  supported (`Authorization: Bearer`); the two vendors' docs currently *disagree* on the scope string
  (`https://ai.azure.com/.default` per Anthropic vs `https://ai.cognitiveservices.com/.default` per MS
  Learn) — if we ever add Entra, make the audience configurable. Note: Mythos-class gated previews are
  Entra-only, so key-based limits us to the standard catalog (fine).
- **`anthropic-version: 2023-06-01` still required** — our adapter sends exactly that (module constant
  `anthropic.py:72`).
- **`model` = deployment name**, which *defaults to* the Anthropic model ID (e.g. `claude-opus-4-8`)
  but is customizable — so `model_aliases` should map to whatever the deployment was named.
- **Models (mid-2026)**: opus-4-8, sonnet-5, haiku-4-5 available BOTH hosted-on-Azure and
  hosted-on-Anthropic (GA); fable-5 hosted-on-Anthropic (preview). **Regions: resource must be East US2
  or Sweden Central** (Global Standard; billing country must be on Anthropic's supported list).
- **Tools/streaming**: client-executed tool use + SSE streaming fully supported — which is what we need
  (all our tools execute app-side behind `guarded_tool_call`). Prompt caching supported. Gaps: no
  Batches API; "Hosted on Azure" 400s on *server-side* tools (web search/code exec/Files API) — not
  used by us. Anthropic rate-limit headers absent (use Azure monitoring).
- **The load-bearing catch is ours, not Azure's**: `gateway/app/providers/anthropic.py`
  `_to_anthropic_request` (`:338-411`) forwards no `tools`, collapses block content to `""`, and the
  response parser extracts only `text` blocks. Claude via Foundry will answer chat today with a pure
  config entry, but cannot drive a Deep Agent until the adapter grows tool-call translation
  (request: `tools` + assistant `tool_use` + `tool_result`; response: `tool_use` blocks → OpenAI-shape
  `tool_calls`; streaming: named-event deltas). This is the original fork blocker #2 — building it
  unlocks Claude everywhere (direct API too), so it's a worthwhile standalone slice with `respx`
  tests + mypy --strict.

## (c) Mistral on Foundry — confirmed facts

- **The hypothesized `/models` route exists but is legacy.** The Azure AI Model Inference API
  (`POST https://<resource>.services.ai.azure.com/models/chat/completions?api-version=2025-04-01`) is
  real and documented, but: its beta `azure-ai-inference` SDK **retires 2026-08-26**, Microsoft's
  migration guide moves everything to the **OpenAI/v1 GA route**, and the `/models` route has its own
  quirks (mandatory api-version, `extra-parameters` header for vendor params like `safe_prompt`, own
  error schema). We should NOT build for it.
- **Two routes the gateway already speaks (both confirmed for non-OpenAI Foundry Models):**
  1. AOAI-classic style: `https://<resource>.services.ai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=2024-10-21`
     → matches our `azure_openai` adapter byte-for-byte (path + `?api-version=` + `api-key` header).
  2. `/openai/v1/` GA: `base_url = https://<resource>.services.ai.azure.com/openai/v1/` (also served on
     `<resource>.openai.azure.com`), plain OpenAI wire, NO api-version, and the plain OpenAI SDK
     pattern `Authorization: Bearer <foundry-key>` → matches our `type: openai` adapter. (Entra scope
     on this route: `https://ai.azure.com/.default`; legacy `/models` route uses
     `https://cognitiveservices.azure.com/.default`.)
- **`model` = deployment name** (required on /openai/v1; case-sensitive).
- **Commercial classes**: Mistral-Large-3 + medium-3-5 + Document AI/OCR are "sold directly by Azure"
  (first-party serverless token billing, no Marketplace subscription); Codestral-2501 / Ministral-3B /
  small-2503 / medium-2505 are Marketplace MaaS (needs `Microsoft.SaaS` purchase permissions);
  Mistral-Large-2 generations are retired.
- **Tool calling per model on Azure**: Mistral-Large-3 ✓, Ministral-3B ✓, small-2503 ✓;
  **mistral-medium-3-5 ✗ and Codestral-2501 ✗** (per Learn) even though Mistral's own platform has
  function calling — treat the Azure tables as authoritative for agent capability. Streaming: SSE
  supported, no Mistral-specific caveat.
- **Regions**: Mistral-Large-3 Global Standard in ~all (~30) regions + Data Zone US/EU; the partner
  (Marketplace) models need the project in East US/East US 2/North Central US/South Central US/
  Sweden Central/West US/West US 3.

## (d) Voyage embeddings on Azure — confirmed facts

- **Voyage is on Azure** (MongoDB acquisition Feb 2025 *expanded* availability), two routes:
  - **Foundry model catalog (serverless, Marketplace SaaS billing)**: voyage-3.5 (Nov 2025) and
    voyage-4 (GA catalog entry; 32K context; dims 2048/1024/512/256; quantization options). Exposes
    the **Voyage-native inference API** (incl. `input_type: query|document`) — NOT OpenAI-shaped, NOT
    the `/models/embeddings` route; the deployed endpoint URL shape is not Learn-documented
    (UNCONFIRMED until we deploy one and look). **voyage-law-2 is NOT in the serverless catalog.**
  - **Azure Managed Application (BYO-VNet GPU)**: per-model offers incl. **voyage-law-2** — a private
    HTTP endpoint in your own VNet at ~**$5/hr + GPU instance cost, always-on**, needs A100/H100
    quota. Voyage-native schema (`/embeddings`, `input_type`), no key auth (VNet isolation).
- **Model specs**: voyage-law-2 = 1024 dims fixed / 16K context (legal-optimized — beats
  text-embedding-3-large and Cohere v3 on legal benchmarks per Voyage). voyage-4 family = 1024
  default with 256/512/2048 Matryoshka. Rerankers (rerank-2.5) on Azure: UNCONFIRMED ("coming soon").
- **Nothing Voyage appears in Microsoft Learn's Foundry model tables** — catalog/Marketplace listings
  only. Treat as real but thinly documented.
- **Repo fit**: gateway would need a Voyage-native adapter (new `ProviderType`, `input_type`
  asymmetric query/document semantics — note our Store embeds queries via `aembed_documents`, so
  input_type-aware wiring needs care) + an additive `vector(1024)` column (the mig-0078 pattern;
  `docs/M1-PROGRESS.md:1516` anticipated exactly this) + an `EmbeddingProvider` variant + re-ingest.
- **Config-only alternative available NOW**: Azure OpenAI `text-embedding-3-large` (3072, reducible
  via `dimensions`) / `-small` (1536) through the existing `azure_openai` embeddings path — our Door B
  already forwards `dimensions`, so it can even fill the existing 768-dim local column symmetrically.
  Cohere embed-v4 is also first-party on Foundry but its 512-token context is poor for legal chunks.
- **Recommendation**: split AZ-4. **AZ-4a (config-only, with AZ-1): Door B via Azure OpenAI
  text-embedding-3** for operators who want Azure-managed embeddings. **AZ-4b (deferred until a
  Foundry resource exists): Voyage** — deploy voyage-4 serverless in the sandbox, capture the real
  endpoint shape, then decide law-2-on-GPU vs voyage-4-serverless vs stay-local; only then write the
  adapter + 1024 column. Local bge (Door A) stays the default — $0 and nothing egresses.

## Repo inspection summary (what the brief asked to quote — full detail on request)

- **Config**: providers live in `gateway.yaml` (operator copy in the **named volume `gateway-config`**,
  seeded from `gateway.yaml.example` on FIRST boot only — edits to the example do NOT propagate to an
  already-seeded volume; edit the live file or hot-reload. Known trap.) `ProviderConfig` allows extra
  fields (`api_version` etc.); `${VAR:-default}` expansion in the loader; missing required env →
  refuses to start. `model_aliases` = friendly name → `{primary:{provider,model}, fallback:[…]}`, plus
  raw `provider/model` passthrough.
- **Existing entries**: `azure-openai` (`type: azure_openai`, `base_url:
  https://${AZURE_OPENAI_RESOURCE:-disabled}.openai.azure.com`, `api_key_env: AZURE_OPENAI_API_KEY`,
  `api_version`, `tier: 3`) — already in the example; `anthropic-prod` (`type: anthropic`,
  `base_url: https://api.anthropic.com`, `tier: 4`); live config adds `minimax`/`deepseek` as
  `type: openai`.
- **Auth construction**: OpenAI-family = `Authorization: Bearer` (omitted when keyless);
  `azure_openai` = `api-key`; `anthropic` = `x-api-key` + `anthropic-version` (constant).
- **Tool forwarding**: first-class on `openai`/`openai_compatible`/`azure_openai` (schema fields pass
  through; stream tool-call id synthesis exists). `anthropic` = text-only (above). Vertex/Bedrock/
  Cohere types exist in the enum but have no adapters.
- **Env plumbing**: `.env` gitignored (verified); compose forwards all provider keys as `${VAR:-}` (no
  hard dependency when unset). Adding a provider key = one line in compose + one in `.env.example`.
- **Coupling flags (do NOT change without maintainer):**
  1. `inference_tiers.defaults` keys are validated against the `ProviderType` enum — a new type must
     be added to the enum and should get a defaults entry (`azure_openai: 3` already present).
  2. **Tier trap**: `type: openai_compatible` defaults to tier 1 (self-hosted); a cloud provider wired
     that way would silently under-classify — use a cloud type or explicit `tier:`.
  3. api-side MiniMax hard-codes (harness profiles baseline, factory context sizing, eval rates,
     migration-baked default area profiles) — informational; nothing breaks by adding providers, but
     agent-model swaps route through area config, not just gateway aliases.
  4. `cost_tracking.rates` is optional per model (absent → cost_estimate NULL, no crash); blended cost
     estimation (api `cost.py`) is provider-agnostic.
- **Tests**: `respx`-based adapter test pattern established (`test_azure_openai_adapter.py` is the
  template — asserts path, `api-key` header, api-version); `build_adapter` dispatch tests; gateway is
  mypy `--strict`.

## Proposed Phase 2 shape (for approval)

1. **AZ-1 Azure OpenAI** — CONFIG-ONLY: gateway.yaml entry (deployment names as `models:`) + the two
   env vars already scaffolded + `azure-` aliases + `cost_tracking.rates` entries; smoke test. Enable
   first (maintainer's stated order). One PR.
2. **AZ-2a Claude-on-Foundry chat** — CONFIG-ONLY + trivial env plumb (`AZURE_ANTHROPIC_API_KEY` +
   resource var in compose/.env.example): point a second `anthropic`-type provider at
   `https://<resource>.services.ai.azure.com/anthropic`. Works for chat today.
   **AZ-2b Anthropic adapter tool-calling** — the one real gateway slice: `tools`/`tool_use`/
   `tool_result` translation + streaming tool deltas in `anthropic.py`, respx tests, mypy --strict.
   Unlocks Claude as an AGENT model on Foundry AND the direct API (retires fork blocker #2).
3. **AZ-3 Mistral** — CONFIG-ONLY: Mistral-Large-3 as a second `azure_openai`-type provider entry
   (classic deployments route on the services.ai.azure.com host) or via `/openai/v1` as `type: openai`.
   Pick ONE in implementation (recommend the `azure_openai` route — it reuses the api-key header and
   the existing adapter tests). Only Large-3 gets an agent-facing alias (tool-calling ✓).
4. **AZ-4a Azure-managed embeddings** — CONFIG-ONLY: `embedding` alias → azure-openai
   text-embedding-3 deployment (Door B). **AZ-4b Voyage** — DEFERRED until the sandbox Foundry
   resource exists (verify the catalog endpoint shape live); then adapter + 1024-dim column decision.
5. **AZ-5 VM sandbox runbook** — compose on an Azure VM, secrets via env, the gateway-config named-
   volume seeding procedure, smoke tests per provider (synthetic text only).
6. Key-based auth everywhere first; **Entra ID (keyless) deferred** to the enterprise-posture slice
   (AZ-6) with a configurable audience (scope strings recorded above; they differ per route and the
   vendors' docs currently disagree for Claude).

Each independently enableable; nothing changes for existing providers when `AZURE_*` is unset. Region
note for the sandbox resource: **East US2 or Sweden Central** satisfies ALL THREE families (Claude's
restriction is the binding one; GPT + Mistral-Large-3 are ~everywhere). For EU data posture, Sweden
Central is the natural pick.

## Cited sources

- Azure OpenAI v1 API lifecycle: https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle
- Azure OpenAI REST reference (classic): https://learn.microsoft.com/en-us/azure/ai-foundry/openai/reference
- Entra ID / keyless auth: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/configure-entra-id
- Foundry models sold by Azure (+ region matrix): https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure · …/models-sold-directly-by-azure-region-availability
- Claude on Foundry (MS): https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude · …/concepts/claude-models
- Claude in Microsoft Foundry (Anthropic): https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry
- GA announcement: https://azure.microsoft.com/en-us/blog/claude-in-microsoft-foundry-is-now-generally-available/
- Foundry endpoints (/openai/v1 for non-OpenAI models, auth, deployment names): https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints
- Model Inference → OpenAI/v1 migration (SDK retirement 2026-08-26, scope change): https://learn.microsoft.com/en-us/azure/foundry/how-to/model-inference-to-openai-migration
- Model Inference REST reference (legacy /models route, api-version 2025-04-01): https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/modelinference/
- Models from partners (Marketplace MaaS classes): https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-from-partners
- Mistral on Azure (Mistral's own docs): https://docs.mistral.ai/models/deployment/cloud-deployments/azure
- Voyage models + Azure Managed App docs: https://www.mongodb.com/docs/voyageai/models/ · https://www.mongodb.com/docs/voyageai/management/azure-marketplace/ · https://docs.voyageai.com/docs/azure-marketplace-mongodb-voyage
- Voyage on Foundry catalog / Marketplace: https://ai.azure.com/catalog/models/voyage-4-embedding-model · https://marketplace.microsoft.com/en-us/product/saas/mongodb.voyage-models?tab=overview · https://marketplace.microsoft.com/en-us/product/azure-applications/voyageaiinnovationsinc1718340344903.voyage-law-2?tab=overview
