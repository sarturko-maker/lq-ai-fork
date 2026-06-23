# Research — matter memory: reuse vs build (license + gateway-routability)

**For:** the matter-memory track (C3a/b/c); backs **ADR-F042**. **Method:** 4 parallel scouts (Karpathy wiki ·
OpenClaw memory module · Letta+mem0 · formats/Graphiti) → synthesis; licenses verified against actual LICENSE
files / GitHub API `/license` / PyPI, **not badges**. **Date:** 2026-06-23.

## Verdict

**Take formats and patterns; add ZERO new runtime dependencies.** Adopt the `MEMORY.md` "index + spill +
frontmatter" format, **port** Graphiti's ~6 bi-temporal supersede fields (not the package — no graph DB),
and **copy** mem0's extract→retrieve→ADD/UPDATE/DELETE/NOOP consolidation loop as **gateway-routed prompts**.
Everything that is actually ours — the **enforced pinned-correction primitive**, audit/undo, the gateway-routed
consolidation pass — we build. No copyleft appears in any verified candidate.

## Reuse table

| Project / format | License (verified) | Lang | Gateway-routable? | Reusable artifact | Verdict |
|---|---|---|---|---|---|
| **Karpathy "LLM Wiki" gist** (`442a6bf…`, ~38k★) | **No license / all-rights-reserved** (gist has no LICENSE; the "Apache-2.0" web claim is false). *Not a blocker — we reuse an uncopyrightable markdown convention.* | prose | N/A (zero egress) | 3-layer split (raw immutable · wiki agent-owned · schema in SKILL.md); `index.md` catalog read-first (works "surprisingly well" at ~100 sources w/o embeddings); `log.md` append-only grep-able `## [date] op \| title`; **Ingest/Query/Lint** triad; "git repo of markdown = undo for free" | **copy format/pattern** |
| `Astro-Han/karpathy-llm-wiki` | **MIT** (API-confirmed) | pure Skill | N/A | concrete SKILL.md + page/frontmatter instantiation in our Agent-Skills format | **mine for format** |
| **OpenClaw** `memory-core` + `memory-wiki` | **MIT** (resolved — API "NOASSERTION" is a false negative from one extra line after the MIT body; `package.json` MIT; notices MIT-only) | TypeScript | yes (keyword=zero egress; semantic = `openai-compatible` provider w/ overridable `baseUrl` → our gateway) | two-tier format; **truncate-injected-copy-keep-file-whole**; **managed-block vs preserved-human-note-block** (= our pinned correction); typed-claim+evidence schema (`id/text/status/confidence/evidence[]/updatedAt`); lint-as-quality-gate. *Gap: no typed supersedes/expiry edge — curation/prose only* | **copy format/pattern** |
| **mem0** | **Apache-2.0** (clean LICENSE, no Commons Clause; hosted Platform is a separate service) | Python | **yes, fully** — `base_url = config.openai_base_url or env or api.openai.com` on LLM + embedder | the two-stage loop (extract facts → retrieve neighbors → LLM-judge **ADD/UPDATE/DELETE/NOOP**); overridable `custom_fact_extraction_prompt`/`custom_update_memory_prompt`; per-`memory_id` SQLite event log (undo substrate) | **copy the loop/prompts**; pkg = avoid (mandatory vector store) |
| **Letta/MemGPT** | **Apache-2.0** | Python | **poor fit** — docs discourage proxy endpoints; needs OpenAI-format tool-calling our Anthropic adapter doesn't forward; 50+ deps | "blocks pinned into prompt" + "sleep-time subagent rewrites" — validates our always-injected wiki + consolidation design | **reference only** |
| **Graphiti** (`getzep/graphiti`) | **Apache-2.0** (raw LICENSE, no riders) | Python | yes via Generic client — **CAVEAT bug #1116: strict `OpenAIClient` ignores `api_base`** → use Generic + egress guard | **the bi-temporal field set** (`edges.py`): `created_at`, `valid_at`, `invalid_at`, `expired_at`, `reference_time`, `episodes[]` (provenance), `fact`. Supersede = set `invalid_at`, never delete | **port the ~6 fields** (not the pkg → no Neo4j) |
| **Claude Code `MEMORY.md` convention** | documented convention | prose | N/A | "index + spill files" layout; YAML frontmatter `name/description/type` (enum); LLM-rewrites-markdown consolidation | **adopt the format** |
| cognee / memobase / txtai | Apache-2.0 | Python | yes | heavier; no bi-temporal supersede | reference only |
| AGENTS.md standard | MIT | — | N/A | placement idea only; **no schema/provenance** | reference only |

## What we adopt, concretely

- **Format.** `context_md` (the wiki) = always-injected, budget-capped catalog/TOC (Karpathy `index.md` + Claude
  `MEMORY.md`). On overflow: **keep the file whole, truncate only the injected copy + consolidate**, never silent
  drop. An append-only **log** (`## [date] op | title`, grep-able). **Typed entries** for facts:
  `id · value(fact) · author(agent|lawyer) · source_citation(→ Citation Engine ids) · trust(normal|human-pinned) ·
  superseded_by · created_at · valid_at · invalid_at · type`.
- **Supersede/temporal** = port Graphiti: a changed fact sets `invalid_at` (never deletes); `valid_at`/`invalid_at`
  are *world-time* (distinct from `created_at` ingestion-time) → answers **"what did we believe at signing"** via an
  as-of query. `superseded_by` is our explicit forward link (Graphiti leaves it implicit).
- **Consolidation/Lint** = port mem0's decision loop + Karpathy/OpenClaw Lint (contradictions, stale, orphans),
  **every model/embedding call through our gateway** via `guarded_tool_call`.

## What we build ourselves (no analog ships it)

1. **Enforced pinned-correction primitive** — `trust=human-pinned` entries the auto-curation is **forbidden to
   touch/supersede** (gate-enforced, not prose convention). OpenClaw's "preserved human note block" is the only
   near-analog and it's convention only.
2. **Audit + undo** — append-only event log + prior-version snapshots; audit rows carry counts/types/IDs, **never
   raw values** (our audit contract); undo = revert to a snapshot.
3. **Gateway-routed consolidation** — net-new code; no candidate routes through our gateway out of the box.
4. **Egress guards** — ADR-F010-style no-`api.openai.com` assertion on any ported path (motivated by Graphiti #1116).

## Red flags (do NOT pull in)

- Don't depend on the Karpathy gist as code or cite its "Apache-2.0" (it's unlicensed) — reuse the convention only.
- Don't adopt `lucasastorian/llmwiki` (Claude/MCP-bound + a direct `MISTRAL_API_KEY` OCR call = egress outside our
  gateway). Don't route through Letta. Don't adopt mem0 the package (mandatory Qdrant + dep stack). Don't adopt
  Graphiti the package (Neo4j). No GPL/AGPL/LGPL/MPL / Commons-Clause found in the verified set.

## Sources (verified)

gist.github.com/karpathy/442a6bf555914893e9891c11519de94f · api.github.com/repos/{openclaw/openclaw,
Astro-Han/karpathy-llm-wiki, mem0ai/mem0, letta-ai/letta, getzep/graphiti}/license · raw LICENSE files +
package.json + THIRD_PARTY_NOTICES.md (OpenClaw) · raw `mem0/llms/openai.py` (base_url) · Graphiti `edges.py`
(field set) · docs.mem0.ai/components/{llms,embedders}/config · code.claude.com/docs/en/memory.
