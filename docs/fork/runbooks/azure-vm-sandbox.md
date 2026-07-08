# Runbook — Azure VM sandbox with Azure AI Foundry providers (AZ-5)

The ordered, operator-run steps that put the full stack (`docker-compose.prod.yml`)
on a single Azure VM and enable the three Azure AI Foundry model families through
the gateway: **azure-openai** (GPT — agent-capable), **azure-mistral**
(Mistral-Large-3 — agent-capable), **azure-claude** (Claude — agent-capable
since slice AZ-2b). Governing: `docs/fork/plans/AZURE-FOUNDRY-phase1.md` (confirmed
endpoints/auth/regions), `docs/fork/plans/PIVOT-modular-azure.md` § Workstream AZ,
ADR-F058 (delivery modes), ADR-F060 (hosted-stack posture).

This is a **sandbox** runbook: one VM, key-based auth, synthetic data only.
The general bring-up mechanics (backups, restore drills, status page, hardening
checklist) are in `docs/fork/runbooks/staging-bringup.md` and apply here
unchanged — this runbook covers only what is Azure- and Foundry-specific, plus
the gateway-config enablement and smoke tests.

> **Sandbox data hygiene (hard rule, carried from staging):** synthetic / sample
> data ONLY. No client or production data touches this stack.

## 0. Decisions (confirmed by the Phase-1 report)

- **One Azure AI Foundry resource** in **Sweden Central or East US2** — Claude's
  region restriction is the binding one across all three families (GPT and
  Mistral-Large-3 are available almost everywhere). For an EU data posture,
  Sweden Central is the natural pick. A single Foundry (AI Services) resource
  serves all three endpoint shapes, so all three `*_RESOURCE` env vars may carry
  the same resource name.
- **Keys only.** Entra ID (keyless) is deferred to AZ-6 — the gateway has no
  Entra support today. Keys live in the node's root-owned `.env.prod`, never in
  the repo, never in `gateway.yaml` (which references keys by env-var name via
  `api_key_env:`).
- **Claude = agent-capable (AZ-2b shipped).** The gateway's Anthropic adapter
  translates OpenAI-shape tools/tool_calls to and from Messages-API
  tool_use/tool_result blocks, unary and streaming — `azure-claude` may back
  chat AND agent-facing aliases. The §5.4 tool smoke against `azure-claude` is
  the AZ-2b live proof that was deferred to this sandbox (on record in the
  AZ-2b PR).
- **Embeddings stay local.** AZ-4 is parked; `EMBEDDING_PROVIDER=local` (bundled
  ONNX, in-process, $0) is the default and has no Azure dependency.

## 1. Azure AI Foundry resource + model deployments

1. **Resource group** — one throwaway group for the whole sandbox (VM + Foundry)
   makes teardown a single delete:
   ```sh
   az group create --name <your-sandbox-rg> --location swedencentral
   ```
2. **Foundry resource** — create an Azure AI Foundry resource in the portal
   (or `az cognitiveservices account create --kind AIServices`) in
   **Sweden Central or East US2**. Note: deploying Claude additionally requires
   your billing country to be on Anthropic's supported list.
3. **Model deployments** — in the Foundry portal, deploy (all Global Standard
   serverless — per-token billing, $0 when idle):
   - a **GPT** deployment (e.g. of gpt-4o) — required; the first provider to enable;
   - optionally **Claude** (e.g. claude-sonnet-5) — the deployment name defaults
     to the Anthropic model id but is customisable;
   - optionally **Mistral-Large-3** — "sold directly by Azure", no Marketplace
     subscription needed. Of the Mistral family on Azure only Large-3 has tool
     calling — the only one worth an agent alias.

   **The deployment NAMES you choose here are what goes into the `models:` lists
   in `gateway.yaml`** (see §4) — not the underlying model names. They are
   case-sensitive on the wire.
4. **Keys** — portal → your Foundry resource → *Keys and Endpoint*. You need the
   key and the **resource name only** (the `<your-resource>` part of
   `https://<your-resource>.services.ai.azure.com`) — the gateway builds the full
   URLs itself:
   - azure-openai: `https://<your-resource>.openai.azure.com` (classic
     deployments route, `api-version 2024-10-21`);
   - azure-claude: `https://<your-resource>.services.ai.azure.com/anthropic`
     (native Anthropic Messages API);
   - azure-mistral: `https://<your-resource>.services.ai.azure.com` (classic
     deployments route, same api-version).

   Keys go in `.env.prod` on the node (§3) and **nowhere else** — never
   committed, never inlined in `gateway.yaml`.

## 2. VM sizing, OS, network

1. **Size** — the prod compose runs 9 services with memory limits totalling
   ~13 GiB (see the `mem_limit` lines in `docker-compose.prod.yml`; the
   ingest-worker loads Docling + EasyOCR + the local ONNX embedder at ~2.5 GiB
   peak, and agent runs load the embedder in the arq-worker too). **Recommend a
   16 GiB / 4 vCPU VM** (e.g. `Standard_D4s_v5`, or burstable
   `Standard_B4ms`-class for a sandbox). The dev box runs the stack in 6.3 GiB
   but only barely (ADR-F056 OOM containment exists because of it) — an 8 GiB VM
   works only in the **reduced profile** (no Collabora,
   `LQ_AI_INGEST_WORKER_CONCURRENCY=1`; see staging-bringup.md § Reduced
   profile). Disk: ≥64 GiB Premium SSD (images, model caches, pgdata).
2. **OS** — Ubuntu LTS.
   ```sh
   apt-get update && apt-get install -y docker.io docker-compose-v2 age
   ```
3. **NSG (inbound)** — allow **443 TCP + 443 UDP** (Caddy serves HTTPS + HTTP/3);
   **80 TCP is optional** (HTTP→HTTPS redirect only — TLS issuance here is
   DNS-01, not HTTP-01). **SSH 22 source-restricted to your admin IP** — or skip
   public SSH entirely and reach the box over Tailscale (the tailnet pattern is
   documented in `deploy/caddy-tailscale/README.md`; for this runbook use it for
   *admin access*, the public edge stays the prod Caddy service).
4. **DNS reality check** — the prod edge issues its certificate via wildcard
   DNS-01, and the `lq-ai-caddy` image compiles in **only two DNS providers:
   `hetzner` and `ionos`** (SETUP-1; `scripts/setup-tenant.sh` rejects anything
   else). **Azure DNS is not supported.** Host the sandbox's zone — or delegate a
   subdomain zone — at Hetzner DNS or IONOS, create the A/AAAA records pointing
   at the VM's public IP (`deploy/dns/README.md`), and procure a zone-scoped API
   token → `LQ_AI_DNS_API_TOKEN`.
5. **Object storage** — the api requires an S3-compatible endpoint (`S3_*` are
   hard-required; prod has no MinIO fallback). **Azure Blob Storage is not
   S3-compatible** — procure any S3-compatible bucket (Hetzner Object Storage,
   IONOS S3, AWS S3, …); the storage vendor is independent of the VM vendor,
   same as staging.

## 3. Bring-up

1. **Clone the repo on the VM** (a sandbox convenience — hosted prod nodes hold
   no checkout; here the checkout gives you the compose file, scripts and the
   gateway seed in one step):
   ```sh
   git clone https://github.com/sarturko-maker/lq-ai-fork.git /opt/lq-ai-src
   install -d -m 750 /opt/lq-ai
   cp /opt/lq-ai-src/docker-compose.prod.yml \
      /opt/lq-ai-src/scripts/deploy.sh \
      /opt/lq-ai-src/scripts/backup.sh \
      /opt/lq-ai-src/scripts/restore-drill.sh /opt/lq-ai/
   # GHCR login so compose can pull the pinned images (a read:packages PAT):
   docker login ghcr.io -u <your-github-user>
   ```
2. **Build `.env.prod`** (root-owned, chmod 600). Seed the generated secrets,
   then copy the remaining lines from `.env.prod.example` and fill them:
   ```sh
   /opt/lq-ai-src/scripts/gen-secrets.sh >> /opt/lq-ai/.env.prod
   chmod 600 /opt/lq-ai/.env.prod
   # Now paste + fill the procured values from .env.prod.example (see the table).
   ```

   **Mandatory** (the compose file uses `${VAR:?}` for these —
   `docker compose config` fails loudly if any is missing):

   | Var | Source |
   |---|---|
   | `LQ_AI_IMAGE_TAG` | a published `sha-<hex>` tag from the Images workflow — never `:main` |
   | `POSTGRES_PASSWORD`, `JWT_SECRET`, `LQ_AI_GATEWAY_KEY`, `COLLABORA_ADMIN_USER`, `COLLABORA_ADMIN_PASSWORD` | `scripts/gen-secrets.sh` |
   | `GATEWAY_CONFIG_FILE` | node path to the gateway seed — `/opt/lq-ai/gateway.yaml` (§4) |
   | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION` | your S3-compatible provider (§2.5) |
   | `LQ_AI_PUBLIC_HOST`, `LQ_AI_PUBLIC_ORIGIN`, `LQ_AI_ACME_EMAIL`, `LQ_AI_DNS_API_TOKEN` (+ `LQ_AI_DNS_PROVIDER`, default `hetzner`) | your DNS setup (§2.4) |

   **Azure provider vars — all optional, enabled per pair.** A family is live
   only when BOTH its vars are set; unset pairs leave the gateway booting
   normally (it skips key-less providers with a warning and 503s requests routed
   to them). `AZURE_OPENAI_*` predates this work; the other four are new with
   AZ-CONFIG. All six are forwarded to the gateway by
   `docker-compose.prod.yml` and listed in `.env.prod.example`:

   | Pair | Enables | Notes |
   |---|---|---|
   | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_RESOURCE` | `azure-openai` (GPT) | agent-capable today |
   | `AZURE_ANTHROPIC_API_KEY` + `AZURE_ANTHROPIC_RESOURCE` | `azure-claude` | agent-capable (since AZ-2b) |
   | `AZURE_FOUNDRY_API_KEY` + `AZURE_FOUNDRY_RESOURCE` | `azure-mistral` (Mistral-Large-3) | agent-capable today |

   `*_RESOURCE` is the resource NAME only — no URL, no scheme. One Foundry
   resource serving all three families means the same name (and key) in all
   three pairs.

   **Optional** (sane defaults; see `.env.prod.example` for the full commented
   list): `EMBEDDING_PROVIDER=local` + `RERANK_ENABLED=true` (keep — the local
   Door-A retrieval stack, no Azure dependency), `FIRST_RUN_ADMIN_EMAIL`,
   `FIRST_RUN_OPERATOR_EMAIL`, `SMTP_*`, the auth/rate-limit knobs,
   `RUN_DEFAULT_BUDGET_PROFILE`, `LQ_AI_GATEWAY_MASTER_KEY`, backup/ops vars,
   and the non-Azure provider keys. Keep `MINIMAX_API_KEY` / `DEEPSEEK_API_KEY`
   unset on anything internet-facing (the PRC fence, ADR-F060).
3. **Prepare the gateway seed BEFORE first boot** — see §4 Path A. Doing it now
   avoids the named-volume dance entirely.
4. **Bring the stack up.** Preferred — `deploy.sh` (pull → dedicated
   `alembic upgrade head` → `up -d --wait` → public smoke against
   `https://<host>/health`):
   ```sh
   LQ_AI_STACK_DIR=/opt/lq-ai bash /opt/lq-ai/deploy.sh sha-<12hex>
   ```
   Or plain compose — the api entrypoint auto-runs migrations on boot (the api
   is the single migrator; workers wait on its health and skip their own run):
   ```sh
   docker compose -p lq-ai -f /opt/lq-ai/docker-compose.prod.yml \
     --env-file /opt/lq-ai/.env.prod up -d --wait
   ```
   First cert issuance can lag DNS propagation; `deploy.sh` retries its smoke.
   Admin handover: with SMTP unset, the one-time bootstrap password appears once
   in the api log (`docker compose -p lq-ai ... logs api | grep 'First-run admin
   password'`) — record it, change it at first login.

   > `scripts/setup-tenant.sh` (the tenant wizard) can render `.env.prod` +
   > `gateway.yaml` + deploy in one pass, but its v1 model-provider choice is
   > `anthropic` (direct API) only and it copies
   > `deploy/gateway/tenant-gateway.yaml.example`, where the three azure blocks
   > are present but commented — after a wizard run you still perform §4/§5 by
   > hand. For this sandbox the manual path above is simpler.

## 4. Gateway config — enable the Azure providers (the named-volume trap)

**How the config actually works** (this bites everyone once): the file at
`GATEWAY_CONFIG_FILE` is mounted read-only into the gateway container at
`/usr/share/lq-ai/gateway.yaml.example`. On boot, `gateway/entrypoint.sh` copies
it to `/etc/lq-ai/gateway.yaml` inside the `gateway-config` **named volume** —
**only if that file is absent**, i.e. on the FIRST boot only. From then on the
volume's copy is the live config (it is mutable at runtime via the admin API),
and **editing the seed file on the node does nothing**. Two paths follow.

### Path A — fresh VM (before the first `up`)

Prepare the seed from the repo-root example, which already ships the three Azure
provider entries wired to the env vars, plus commented aliases:

```sh
cp /opt/lq-ai-src/gateway.yaml.example /opt/lq-ai/gateway.yaml
```

Edit `/opt/lq-ai/gateway.yaml`:

1. In the `providers:` section, replace the placeholder deployment names in each
   `models:` list with YOUR deployment names from §1.3:
   - `azure-openai` → your GPT deployment(s) (example placeholders
     `gpt-4-turbo-prod` / `gpt-4o-prod`);
   - `azure-claude` → your Claude deployment(s) (example `claude-sonnet-5` /
     `claude-opus-4-8`);
   - `azure-mistral` → `Mistral-Large-3` (or your name for it — case-sensitive).

   Do **not** touch the `base_url:` lines — the `${AZURE_*_RESOURCE:-disabled}`
   expansion happens inside the gateway from the container's environment.
2. In `model_aliases:`, uncomment the **Azure AI Foundry aliases** block —
   `azure-smart` (→ azure-openai), `azure-mistral-large` (→ azure-mistral),
   `azure-claude-chat` (→ azure-claude) — and point each `model:` at your
   deployment name. All three are agent-capable (azure-claude since AZ-2b —
   the example's inline comments say so).
3. Optionally fill the commented `cost_tracking.rates` entries
   (`'azure-openai/<deployment>'` etc.) from your Azure price sheet — keys must
   match your deployment names; a missing row just means a NULL cost estimate.

Confirm the `AZURE_*` pairs are in `.env.prod` (§3.2), then boot. Done — skip
Path B.

### Path B — the stack has already booted

The named volume is seeded; edit the LIVE file and reload:

```sh
dc() { docker compose -p lq-ai -f /opt/lq-ai/docker-compose.prod.yml --env-file /opt/lq-ai/.env.prod "$@"; }

dc cp gateway:/etc/lq-ai/gateway.yaml ./gateway.live.yaml
"$EDITOR" gateway.live.yaml            # same three edits as Path A
dc cp ./gateway.live.yaml gateway:/etc/lq-ai/gateway.yaml
```

Then activate — the distinction matters:

- **If you added/changed `AZURE_*` values in `.env.prod`**: the container must be
  RECREATED to see new environment — `dc up -d gateway`. A restart or SIGHUP
  does not re-read env.
- **Config-file-only change**: hot-reload via SIGHUP —
  `dc kill -s SIGHUP gateway`. A failed parse keeps the prior snapshot and logs
  the error; check `dc logs gateway`.

Aliases (only) can instead be managed through the admin API — authenticated by
the `X-LQ-AI-Gateway-Key` header — `GET/POST/PATCH/DELETE /admin/v1/aliases`,
which writes the live file and hot-swaps in one step. Provider ENTRIES cannot be
added via the admin API; they must be in the file. To force a full re-seed from
the node file: stop the stack, `docker volume rm lq-ai_gateway-config` (this
discards live edits), boot again. Never `docker volume prune` — it removes named
volumes wholesale.

## 4b. Optional — source the Azure keys from Key Vault (managed identity)

By default the three Azure keys ride into the gateway as plaintext
`AZURE_*_API_KEY` values in `.env.prod` (on disk). KV-1 (ADR-F069) lets you
source them from Azure Key Vault instead, using the VM's **system-assigned
managed identity**, so no key material lives on disk. It is additive and
per-key: any pair you don't configure keeps reading its plain env var.

**Honesty note.** Managed identity removes the keys *at rest*, but it is not a
process-level secret boundary: any process running on this VM can hit the IMDS
endpoint and mint the same `vault.azure.net` token, then read the same secrets.
This raises the bar against a stolen `.env.prod`, not against code running on the
box.

Provision (placeholders only — substitute your names):

```sh
# 1. Give the VM a system-assigned identity and capture its principal id.
az vm identity assign -g <your-sandbox-rg> -n <your-vm>
VM_PRINCIPAL_ID=$(az vm show -g <your-sandbox-rg> -n <your-vm> \
  --query identity.principalId -o tsv)

# 2. Create an RBAC-authorization vault and capture its resource id.
az keyvault create -g <your-sandbox-rg> -n <your-vault-name> \
  -l <your-region> --enable-rbac-authorization true
VAULT_ID=$(az keyvault show -n <your-vault-name> --query id -o tsv)

# 3. Grant the VM identity read access to secrets (data-plane RBAC).
az role assignment create --role "Key Vault Secrets User" \
  --assignee-object-id "$VM_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --scope "$VAULT_ID"

# 4. Store each provider key as a secret (names are your choice).
az keyvault secret set --vault-name <your-vault-name> \
  --name <azure-openai-secret-name>    --value <the-azure-openai-key>
az keyvault secret set --vault-name <your-vault-name> \
  --name <azure-anthropic-secret-name> --value <the-azure-anthropic-key>
az keyvault secret set --vault-name <your-vault-name> \
  --name <azure-foundry-secret-name>   --value <the-azure-foundry-key>
```

Then wire it in `.env.prod` (all NON-secret — only names, never the keys):

```sh
AZURE_KEY_VAULT_NAME=<your-vault-name>
AZURE_OPENAI_KEY_SECRET_NAME=<azure-openai-secret-name>
AZURE_ANTHROPIC_KEY_SECRET_NAME=<azure-anthropic-secret-name>
AZURE_FOUNDRY_KEY_SECRET_NAME=<azure-foundry-secret-name>
```

You may now **remove** the plaintext `AZURE_OPENAI_API_KEY` / `AZURE_ANTHROPIC_API_KEY`
/ `AZURE_FOUNDRY_API_KEY` lines from `.env.prod` (the Key Vault value is used; if
both are present the Key Vault value wins and the gateway logs the override).

Activate by **recreating** the gateway so it re-reads the env and re-runs the
fetch — a restart or SIGHUP does NOT re-read env, and note SIGHUP only swaps the
config snapshot (it does not rebuild adapters), so **SIGHUP does not re-source
keys**. To rotate a key later: update the Key Vault secret, then recreate the
gateway again.

```sh
dc up -d gateway
```

Verify:

- `dc logs gateway | grep 'from Azure Key Vault'` — one INFO line per sourced
  key, e.g. `sourced AZURE_OPENAI_API_KEY from Azure Key Vault (vault=<your-vault-name> secret=<azure-openai-secret-name>)`.
  No key value or length is ever logged. A per-key failure logs a `Key Vault
  fetch failed for …` WARNING and the gateway falls back to the plain env var if
  present (else that provider routes 503).
- Then run the §5.3 chat-completion smoke per enabled provider — a 200 with
  `pong` proves the Key-Vault-sourced key reached the upstream call.

## 5. Per-provider smoke tests (synthetic only)

The gateway publishes **no host port** in prod (Caddy fronts api + web only), so
run the curls from a throwaway container on the stack's network
(`lq-ai_default` for project `lq-ai`). Load the env into your (root) shell
first — the key then rides into the container via `-e LQ_AI_GATEWAY_KEY` with no
value, i.e. read from the environment, never appearing in `docker`'s argv:

```sh
set -a; . /opt/lq-ai/.env.prod; set +a
```

Inference routes are network-gated rather than key-gated (only `/admin/v1/*`
enforces the key), but the smokes send the header anyway — it is what the app
sends and it exercises the same path.

### 5.1 Liveness + readiness (no auth)

```sh
docker run --rm --network lq-ai_default curlimages/curl:latest \
  -fsS http://gateway:8001/health
docker run --rm --network lq-ai_default curlimages/curl:latest \
  -fsS http://gateway:8001/ready
```

Expected: `/health` → `{"status":"alive","service":...,"version":...}`;
`/ready` → 200 once the config has loaded.

### 5.2 Aliases visible

```sh
docker run --rm --network lq-ai_default curlimages/curl:latest \
  -fsS http://gateway:8001/v1/models
```

Expected: OpenAI `{"object":"list","data":[...]}` shape; after §4 the entries
include `azure-smart`, `azure-mistral-large`, `azure-claude-chat` with
`"lq_ai_kind":"alias"`.

### 5.3 One chat completion per enabled provider

These use the raw `provider/model` passthrough (`"model": "<provider>/<deployment>"`),
so they prove each provider independently of the alias map. Run one per enabled
family, substituting YOUR deployment names.

```sh
docker run --rm -i --network lq-ai_default -e LQ_AI_GATEWAY_KEY \
  --entrypoint sh curlimages/curl:latest -c \
  'curl -fsS -D /dev/stderr http://gateway:8001/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "X-LQ-AI-Gateway-Key: $LQ_AI_GATEWAY_KEY" \
     -d @-' <<'JSON'
{"model": "azure-openai/<your-gpt-deployment>",
 "messages": [{"role": "user", "content": "Reply with the single word: pong"}],
 "max_tokens": 20}
JSON
```

Repeat with:

- `"model": "azure-mistral/Mistral-Large-3"` (your deployment name,
  case-sensitive);
- `"model": "azure-claude/<your-claude-deployment>"` — the AZ-2a chat proof
  (tool use is 5.4).

Expected per call: HTTP 200; `choices[0].message.content` contains `pong`;
`choices[0].finish_reason` = `"stop"`; the body carries
`"routed_inference_tier": 3` and the response headers include
`X-LQ-AI-Routed-Provider: azure-openai` (resp. `azure-mistral`, `azure-claude`)
and `X-LQ-AI-Routed-Inference-Tier: 3`.

Failure modes worth knowing: a 503 naming the provider means the gateway skipped
it at load (its env-var pair was unset when the container started — recreate the
gateway after fixing `.env.prod`, §4 Path B); a 401/404 from Azure inside the
error envelope means a wrong key, wrong resource name, or a deployment-name
mismatch (deployment names are what the URL is built from — check spelling and
case against the portal).

### 5.4 Tool-calling smoke (all three families)

Run against `azure-openai` and `azure-mistral` (the `azure_openai` adapter
forwards `tools`/`tool_calls` with full OpenAI wire parity) AND
`azure-claude` (the anthropic adapter translates them — AZ-2b):

```sh
docker run --rm -i --network lq-ai_default -e LQ_AI_GATEWAY_KEY \
  --entrypoint sh curlimages/curl:latest -c \
  'curl -fsS http://gateway:8001/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "X-LQ-AI-Gateway-Key: $LQ_AI_GATEWAY_KEY" \
     -d @-' <<'JSON'
{"model": "azure-openai/<your-gpt-deployment>",
 "messages": [{"role": "user",
   "content": "What is the weather in Stockholm right now? You must use the tool."}],
 "tools": [{"type": "function", "function": {
   "name": "get_weather",
   "description": "Get the current weather for a city",
   "parameters": {"type": "object",
     "properties": {"city": {"type": "string"}},
     "required": ["city"]}}}],
 "tool_choice": "auto",
 "max_tokens": 100}
JSON
```

Expected: `choices[0].finish_reason` = `"tool_calls"` and
`choices[0].message.tool_calls[0].function.name` = `"get_weather"` with
arguments naming Stockholm. Repeat with `"model": "azure-mistral/Mistral-Large-3"`
and `"model": "azure-claude/<your-claude-deployment>"`.

**The `azure-claude` run here is load-bearing**: it is the LIVE proof of the
AZ-2b tool translation, deferred on record from the AZ-2b PR (which shipped on
respx tests — no Anthropic/Foundry key existed on the dev box). If it returns
`finish_reason: "stop"` with a plain-text answer instead of `tool_calls`,
capture the gateway logs and report — do not shrug it off as model choice.

### 5.5 Alias resolution

Re-run one 5.3 call with `"model": "azure-smart"` (no slash) to prove the
uncommented alias resolves. Same expected output.

Once 5.3–5.5 pass, the Foundry providers are usable app-wide: point an area's
model or the `smart`/`fast` aliases at them per the normal alias mechanics —
all three families are agent-capable.

## 6. Rollback, teardown, cost hygiene

- **App rollback** — deploys are roll-forward-only, pinned to image SHAs:
  re-run `deploy.sh sha-<previous>` (staging runbook §5).
- **Stack stop** — `dc down` (keeps named volumes: pgdata, gateway-config,
  caddy certs). Never `docker compose down -v`, never `docker volume prune`.
  After image pulls/updates: `docker image prune -f` (dangling only).
- **Pause the VM** — `az vm deallocate -g <your-sandbox-rg> -n <your-vm>` stops
  compute billing; the disk and public IP still bill until deleted.
- **Full teardown** — `az group delete --name <your-sandbox-rg>` removes VM,
  disk, IP, NSG and (if co-located) the Foundry resource in one shot.
- **What idles at $0** — the Foundry model deployments in this runbook are all
  Global Standard **serverless, billed per token**: an idle deployment costs
  nothing, so you can keep the Foundry resource and delete only the VM between
  sessions. Nothing here provisions always-on compute — no provisioned
  throughput, and no managed-app GPUs (the Voyage voyage-law-2 managed app,
  which does bill ~$5+/hr always-on, is explicitly out of scope; AZ-4 parked).
- **Key hygiene** — if you tear down the VM but keep the Foundry resource,
  rotate its keys (the VM's disk held `.env.prod`); if you tear down everything,
  the keys die with the resource.

## 7. What this sandbox does NOT cover (honest scope)

- **AKS / enterprise posture** — that is AZ-6, unplanned. This is one VM, one
  compose stack.
- **Entra ID (keyless) auth** — deferred; the gateway is key-only today. The
  per-route scope strings are recorded in the Phase-1 report for when AZ-6
  picks this up.
- **Voyage / Azure-managed embeddings** — AZ-4 is parked. The local Door-A
  embedder (`EMBEDDING_PROVIDER=local`, bundled ONNX, in-process) is the
  shipping default and never talks to Azure. A commented `embedding`-alias
  example for Azure OpenAI text-embedding-3 exists in `gateway.yaml.example`
  for reference only.
- **Production duties** — backups + restore drills, the status page, the
  pre-exposure hardening checklist, and the reduced 8 GiB profile are all in
  `docs/fork/runbooks/staging-bringup.md` and are not repeated here; run the
  hardening checklist before sharing the URL with anyone.
- **PRC-provider fence** — unchanged: keep `MINIMAX_API_KEY` /
  `DEEPSEEK_API_KEY` unset on an internet-facing stack (ADR-F060).
