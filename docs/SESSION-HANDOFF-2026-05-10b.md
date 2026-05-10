# Session Handoff — 2026-05-10 (D7 + Wave-3 transparency pivot)

> **Purpose.** Resume in a fresh context window. Pair with `docs/M1-PROGRESS.md` (the canonical living ledger). This is the second handoff for 2026-05-10. The morning handoff (`SESSION-HANDOFF-2026-05-10.md`) covered D7 Saved Prompts; this one covers Wave-3 transparency pivot (ADR 0011 + encrypted keys + discovery enrichment + direct dispatch + ModelPicker rewrite + D2 tier badge).

---

## State at handoff

- **Branch:** `main`. Pushed through `9ae398a` (post-wave-3 OLLAMA env fix).
- **Last pushed before this session's wave-3 work:** `299c6eb` (D7 docs polish; SavedPromptsPanel browser-verified).
- **Wave-3 commits (all pushed):**
  ```
  9ae398a fix(env.example): default OLLAMA_BASE_URL to host.docker.internal
  4fb1e7d docs(wave-3): handoff + M1-PROGRESS snapshot for transparency pivot
  9a23b17 feat(picker): surface alias resolution + fallback count (ADR 0011)
  d0fa2dc docs(gateway-openapi): document direct provider/model dispatch
  e8b2f68 feat(gateway): live model discovery — OpenAI catalog + encrypted-key path
  a6e8b66 feat(web): D2 — tier badge click-for-details panel
  4ae9720 feat(gateway): encrypted-at-rest provider keys via Fernet
  072953c docs(adr): 0011 — transparency-first model selection posture
  ```
- **Stack:** `docker compose up -d` — all 7 services healthy. Gateway + web rebuilt this session with wave-3 code; the live containers serve the new endpoints.
- **Auth:** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!`.
- **Migrations:** still `0001` → `0011` (no DB schema changes in wave-3).

---

## What landed in this wave

| Phase | Status | Surface |
|---|---|---|
| **ADR 0011** Transparency-first model selection | ✅ | docs/adr/ |
| **Encrypted-at-rest provider keys** | ✅ committed + 13 unit tests + CLI | gateway secrets module + adapters |
| **Live model discovery enrichment** | ✅ committed + 8 new tests | gateway discoverer + OpenAI catalog |
| **Direct provider/model dispatch** | ✅ already wired (D0); doc'd in OpenAPI sketch | docs/api/gateway-openapi.yaml |
| **ModelPicker alias resolution** | ✅ committed | gateway response + web UI |
| **D2 — Tier badge click-for-details** | ✅ committed | web TierBadge + new TierDetailsPanel |

**The big architectural shift.** ADR 0011 reframes model selection: aliases are *convenience defaults*, not *opacity*. Every alias now publishes its resolved primary target inline (`smart → anthropic-prod/claude-opus-4-7 (+2 fallbacks)`), users can pick a specific provider/model directly (`anthropic-prod/claude-opus-4-7` form already worked at the gateway level via `resolve_alias_chain`), and assistant messages let users open a click-for-details panel showing the routed provider+model+tier+token usage. Provider keys can now live encrypted at rest in `gateway.yaml` via Fernet, decrypted in-memory at startup with a master key the operator supplies via `LQ_AI_GATEWAY_MASTER_KEY`.

**Files touched (wave-3).**

* **ADR.** `docs/adr/0011-transparency-first-model-selection.md` (new).
* **Gateway secrets / encryption.**
  * `gateway/app/secrets.py` (new) — `ProviderKeyResolver`, `generate_master_key`, `encrypt_value`, `MasterKeyMissing`, `DecryptError`. Fernet-based.
  * `gateway/app/cli.py` (new) — `python -m app.cli generate-master-key | encrypt-key`. Reads stdin so plaintext keys never need to land on disk after operator runs the helper.
  * `gateway/app/config.py` — `ProviderConfig.api_key_encrypted` field + mutex validator (rejects providers with both `api_key_env` and `api_key_encrypted`).
  * `gateway/app/providers/{anthropic,openai,ollama}.py` — `from_config()` now takes optional `key_resolver: ProviderKeyResolver` and resolves keys through it. Default resolver builds from env (handles both paths transparently).
  * `gateway/pyproject.toml` — `cryptography>=42,<46` added (justified inline: stdlib has no AEAD).
  * `gateway/tests/test_secrets.py` (new) — 13 tests.
  * `gateway.yaml.example` — documents the encrypted path inline.
* **Live model discovery.**
  * `gateway/app/model_discovery.py` — `discover_openai()` + `_fetch_openai_uncached()` (calls `GET <base_url>/models`). Anthropic discoverer migrated to `ProviderKeyResolver` (encrypted keys now work for catalog calls). `DiscoveredModel.resolves_to` + `.fallback_count` (alias-only). `to_payload()` emits `lq_ai_resolves_to` + `lq_ai_fallback_count`.
  * `gateway/tests/test_model_discovery.py` — +8 new tests (discover_openai happy path / no-key skip / 401 / openai_compatible without key / encrypted-key path / alias resolution surfacing / payload-omits-on-native / payload-includes-on-alias).
* **Direct dispatch (no code change; OpenAPI sketch update).**
  * `docs/api/gateway-openapi.yaml` — `/v1/chat/completions` description names both alias and `provider/model` direct dispatch modes; spells out tier-floor enforcement applies to both.
* **ModelPicker rewrite.**
  * `web/src/lib/lq-ai/api/models.ts` — `ModelEntry.lq_ai_resolves_to` + `.lq_ai_fallback_count`.
  * `web/src/lib/lq-ai/components/ModelPicker.svelte` — alias optgroup label changed to "Aliases (defaults)"; each alias row shows the second-line resolution string in monospace gray; selected-display shows the resolution tail when an alias is current.
* **D2 — tier badge click-for-details.**
  * `web/src/lib/lq-ai/components/TierBadge.svelte` — gains `interactive` mode (default true). Click + Enter/Space dispatch `open`. Static span variant remains for non-clickable surfaces.
  * `web/src/lib/lq-ai/components/TierDetailsPanel.svelte` (new) — focus-trapped modal with tier label + 1-line description per tier (1: on-prem / 2: ZDR private cloud / 3: ZDR commercial / 4: standard commercial / 5: consumer); routed provider/model in monospace; prompt + completion tokens + cost estimate when populated; transparency-principle footer.
  * `web/src/lib/lq-ai/components/MessageBubble.svelte` — local `tierDetailsOpen` state owns the modal lifecycle.

**Test posture at end-of-session.**
- Gateway: **364 passed, 1 deselected** (provider-marked tests). +13 secrets + 8 discovery = +21 net.
- Web vitest: **59 passed, 8 files** (no new tests added beyond the existing API-client coverage; vitest run as a regression pass).

**Live verification.** `GET /api/v1/models` returns the enriched payload:

```json
{"id":"smart","routed_inference_tier":4,"lq_ai_resolves_to":"anthropic-prod/claude-opus-4-7","lq_ai_fallback_count":2}
{"id":"fast","routed_inference_tier":4,"lq_ai_resolves_to":"anthropic-prod/claude-sonnet-4-6","lq_ai_fallback_count":1}
...
{"id":"anthropic-prod/claude-opus-4-7","routed_inference_tier":4,"provider_type":"anthropic"}
```

Anthropic live catalog discovery is also working (returns the operator's available native models alongside aliases).

**Architectural decisions worth surfacing.**

1. **Aliases stay; their resolution becomes visible.** ADR 0011 doesn't kill the alias system — that work (D0/D0.5/D1/ADR 0010) is too foundational. Instead aliases now *publish* their resolved primary target so users see what they actually do. Direct provider/model selection is a parallel mode (no fallback chain).
2. **Encrypted-keys mutex at config-load time.** `ProviderConfig` validator rejects entries with both `api_key_env` and `api_key_encrypted` set. We could let one silently win, but explicit-error-at-load is the safer posture: a misconfigured operator finds out at startup, not on the first inference call.
3. **Operator master key is never persisted by the gateway.** `LQ_AI_GATEWAY_MASTER_KEY` lives in env only. The CLI helper reads stdin (not a file) so the plaintext key trip is keyboard → CLI → encrypted token; nothing else.
4. **Vertex/Bedrock discovery still deferred.** Their catalog APIs (`boto3.list_foundation_models`, GCP discovery client) pull substantial dependency surfaces. Operators routing to those today address them via aliases until those discoverers ship.
5. **D2's tier panel doesn't show "alias used"** even though it could — `Message.routed_provider`/`routed_model` are populated, but the alias label that the user originally picked isn't currently persisted on `Message`. If a user picked `smart` and it routed to `anthropic-prod/claude-opus-4-7`, the panel shows the latter. Adding `requested_model: 'smart'` to `Message` is a small, valuable enhancement — left as a follow-on.

6. **The OLLAMA_BASE_URL trap (post-push fix).** Kevin smoke-tested the new admin alias dropdown and saw only 4 ollama models from `gateway.yaml`'s static curated list, despite `ollama ls` showing 58 on his host. Root cause: `.env` had `OLLAMA_BASE_URL=http://ollama:11434` (the in-compose `ollama` service that only exists with `--profile local`); discovery's never-raise posture silently returned `[]` and the admin form fell back to the static list. Fix: flipped his local `.env` to `http://host.docker.internal:11434`, restarted gateway with `--force-recreate`, verified live `/api/v1/models` now returns 58 ollama + 9 anthropic native rows. Also flipped `.env.example`'s default to the host-internal path with a two-scenario decision-matrix comment so the next operator avoids the trap. **Memory entry written** (`feedback_ollama_discovery.md`) so this trap is the first place to look on similar future symptoms.

---

## What's NOT done

### Wave-3 follow-ons

* **Browser click-through verification of the new picker + tier panel.** Backend live-verified; web `npm run check` shows no new D7/wave-3-related typecheck errors; vitest suites pass. The picker rewrite + TierDetailsPanel are not yet exercised in a browser this session. Recommend a quick smoke (similar to the D7 SavedPromptsPanel Playwright run earlier in the day) before declaring the UI fully validated.
* **Persist `requested_model` (alias label) on `Message`.** Today the routed provider/model goes on the row but the alias the user picked is lost; the tier panel shows the resolved target without the alias indicator. ~30-line backend change + UI text tweak.
* **OpenAI key encryption in the live `.env`.** The encrypted-keys path is fully tested via unit tests + a respx-mocked discovery call. No operator has migrated their actual `.env` keys yet — a one-time operator action when they're ready.
* **Vertex/Bedrock discovery + adapters.** Still B6 remainder.

### Other queued work

- **D3-coverage** (~6–10h) — auth/MFA/projects/files/KBs audit writes + retroactive backfill + admin filtering UI. Unchanged from prior handoff.
- **D8** (~1–2 days) — DB-backed user/team skills + LQ.AI Skill Creator. Unchanged from prior handoff.

### Push status

All 8 wave-3 commits pushed (`299c6eb..9ae398a`). Tree is clean
modulo `docs/MODEL_PICKER_ARCHITECTURE.md` which stays untracked
per memory rule (reference doc, not part of this milestone).

---

## How to resume next session

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. `git status` should be clean; `git log --oneline -5` should show
   `9ae398a` at the top.
3. `docker compose ps` — all 7 services healthy. Gateway + web were
   rebuilt with wave-3 code; gateway was force-recreated post-fix
   so it has the host-Ollama env. No rebuild needed unless the next
   task touches one of those subsystems.
4. **Pick the next move:**

   ### Option A — Persist `requested_model` on `Message` (~1h)

   *Smallest. Closes the ADR-0011 disclosure-loop hole completely.*

   Today the chat handler sends `model: "smart"` to the gateway, the
   gateway resolves to `anthropic-prod/claude-opus-4-7`, and only
   the resolved provider/model lands on `Message.routed_provider /
   routed_model`. The alias the user picked is lost — TierDetailsPanel
   can't say "you asked for `smart`, it routed to opus".

   Touchpoints:
   * `api/alembic/versions/0012_*.py` — add `requested_model TEXT`
     column to `messages` (nullable for backwards compat).
   * `api/app/models/chat.py` — add the field to the ORM.
   * `api/app/api/chats.py` (or wherever message-create lives) —
     persist `request.model` on the assistant message.
   * `web/src/lib/lq-ai/types.ts` — add to `Message`.
   * `web/src/lib/lq-ai/components/TierDetailsPanel.svelte` —
     render `Requested: smart → routed to anthropic-prod/claude-opus-4-7`
     when `requested_model` differs from the routed pair.

   ### Option B — D3-coverage audit-write expansion (~6–10h)

   *Distributed; easy to commit incrementally.*

   D3-core covered project / chat / message audit writes. D3-coverage
   extends to: auth (login / refresh / logout), MFA (setup / enable /
   verify / disable), files (upload / delete), KBs (CRUD + attach /
   detach), users (export / deletion-schedule / cancel — partly done
   in D6 already). Plus the admin filtering UI on
   `/lq-ai/admin/audit-log` (currently the route exists but the
   client-side filter form isn't wired).

   Entry points: every callsite of `audit_action()` is a hit; the
   gaps are paths that mutate state but don't yet call it. Grep
   `db.commit\(\)` across `api/app/api/` and audit each that lacks
   an `audit_action` call upstream.

   ### Option C — D8 DB-backed user/team skills (~1–2 days)

   *Largest. Surfaced by D7's "Save as SKILL.md" stand-in.*

   ADR amendment to 0004 (filesystem-canonical built-ins coexist
   with DB user/team scopes). Migration `0012_user_skills`. POST /
   PATCH / DELETE `/api/v1/skills`. Skill Service registry merge.
   Gateway internal-skills user-scope path. LQ.AI Skill Creator
   page at `/lq-ai/skills/new`. Rewire D7's Promote-to-Skill from
   download-as-SKILL.md to the Creator.

   Per the wave-3 cadence: pre-write the ADR amendment first so the
   migration + endpoint shapes have a north star.

   ### Option D — Encrypted-keys operator workflow doc (~30 min)

   `docs/security/encrypted-keys.md` — generate-master-key,
   encrypt-key, paste-into-gateway.yaml, master-key rotation,
   recovery-from-lost-master-key procedure. Not strictly code;
   protects procurement-readiness story. Could bundle with B
   above as part of D3-coverage's docs pass.

   **Recommended sequence:** A first (closes a clean loose end),
   then C (the bigger feature) or B (the wider audit pass) based
   on which feels higher-leverage when you re-open. D as a tag-along.

---

## Things that should NOT regress

(Carry-forward from prior handoffs.)

- `OLLAMA_BASE_URL` should point at host Ollama unless `--profile local` is intentionally active.
- Anthropic key in `.env` is real — DO NOT overwrite when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (host postgres collision; tidepool currently down).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only; production: leave unset).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev; production: relative `/api/v1`).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai`.
- Pre-existing test failures still on `main` HEAD (predate wave-3):
  - `api: tests/test_endpoints.py::test_endpoint_returns_canonical_501_body[GET|PATCH /api/v1/admin/tier-policy]` (D1 deferred surface).
  - `web: npm run check` shows ~9k pre-existing OpenWebUI fork errors (i18n typing, unrelated routes) — unchanged.

---

## Wave-3 live verification commands (for the next session's confidence check)

```bash
# 1) /api/v1/models alias rows now carry resolution metadata
TOKEN=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-smoke-test-Pw1!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/models \
  | python3 -m json.tool | head -40

# Should show, for each alias, a `lq_ai_resolves_to` field like
# "anthropic-prod/claude-opus-4-7" and a `lq_ai_fallback_count`.

# 2) Encrypted-keys CLI sanity
docker compose exec -T gateway python -m app.cli generate-master-key 2>&1 | head -3
# Set LQ_AI_GATEWAY_MASTER_KEY=<output>, then:
echo "sk-ant-test-key" | docker compose exec -T -e LQ_AI_GATEWAY_MASTER_KEY=<key> gateway python -m app.cli encrypt-key --provider anthropic-prod
```
