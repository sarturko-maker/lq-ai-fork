# Research — self-maintained agent memory: auto-write vs approve (matter-memory design)

**For:** the unit-of-work memory tier (Commercial "deal context" / Privacy "Programme memory"); backs **ADR-F042**.
**Method:** 6 parallel web scouts (Claude Code · OpenClaw · Hermes · self-editing frameworks · product memory UX ·
Karpathy-notes + regulated governance) → synthesis. Every named system verified against primary sources
(official docs, repos, GitHub API). **Date:** 2026-06-23. **Honesty:** the two systems the maintainer named —
**OpenClaw** and **Hermes** — both resolved to real, documented systems (not substituted).

## Verdict

**Switch the matter tier from propose/accept to auto-write-then-correct.** Across the 12 systems surveyed,
**11 auto-write memory and let the human manage it after the fact**; the lone propose-then-approve example
(Cursor "Memories") was documented in secondary sources, did not durably survive, and its users were steered
back to version-controlled files. **Per-write approval is the anti-pattern.** The regulated/legal bar is met
*not* by a pre-write gate but by **provenance + write-receipts + supersede-not-overwrite + undo +
correction-as-first-class-(pinned)-memory** — which exceeds what any surveyed system ships.

## Landscape (one row per system)

| System | Auto vs approve | Stays brief | Correction | Conflict/staleness | Audit/provenance |
|---|---|---|---|---|---|
| **Claude Code auto memory** | Auto, silent (on/off only) | Index + spill files; inject first **200 lines/25 KB** of `MEMORY.md` | Primary human role, but just a markdown edit — no trail | Manual review; positional precedence | Transparent markdown; **no undo / no per-entry author** |
| **Anthropic memory tool** `memory_20250818` | Fully auto | "keep concise; rename/delete stale; don't create files unless necessary" | `str_replace`/`delete` | same + file-expiry | plain files; no versioning |
| **OpenClaw** (MIT, ~380k★) | Auto ("just ask: Remember…"); **"memory does not enforce policy"** | Two-tier: append-only daily logs ↔ curated `MEMORY.md`; truncate injected copy, keep file whole; pre-compaction flush | thin in core (another auto-write); Memory-Wiki plugin adds structured claims | human curation + **expiry-condition convention**; auto contradiction only in plugin | **git-backed markdown** — diffable/restorable (strongest transferable audit) |
| **Hermes Agent** (Nous, MIT) | Auto by default; optional `write_approval` | **hard char caps**; **error-then-consolidate, never silent truncate** | first-class content (`add/replace/remove`) + background review | agent judgment; dup-reject | markdown + capacity readout; **no version history** |
| **Letta/MemGPT** (Apache-2.0) | Auto; sleep-time agent rewrites dense | hard-capped block | human full-replaces the block | single-owner (rewrite not concurrency-safe) | rewrite **loses versions** |
| **mem0** (Apache-2.0) | Auto; LLM picks ADD/UPDATE/DELETE/NOOP vs top-k | one fact per memory | same op set | Conflict-detector **marks invalid, not delete** | SQLite event log per memory_id |
| **Zep/Graphiti** (Apache-2.0) | Auto (bi-temporal graph) | hides invalidated edges | new edge supersedes; nothing deleted | **old edge `invalid_at` = new edge `valid_at`** — "what was believed when" | **strongest**: nothing deleted, 4 timestamps + provenance |
| **ChatGPT memory** | Auto, "Memory updated" toast → manage | flat strings; periodic consolidation | conversational, persisted ("forget X") | self-rewrites; **cautionary: facts silently mutate** | list + per-item delete; opaque profile = transparency gap |
| **GitHub Copilot memory** | Auto; manage after | atomic cited statements; 28-day TTL | citation-revalidation auto-corrects stale | **each fact carries a citation re-checked before use** | **citations (fact→source)** + private/team scope split |
| **Windsurf Cascade** | Auto memories; **promote** to git Rule deliberate | auto tier lossy; durable = committed Rules | edit panel; promote to Rule | workspace-scoped | local files; durable tier git-reviewed |
| **Cursor "Memories" (beta)** | **Propose-then-approve** (the minority) | — | approve/reject | — | secondary-sourced; **removed/destabilized; users went back to Rules** |
| **Karpathy "LLM Wiki"** | Auto rewrite-in-place; separate append-only `log.md` | short wiki + periodic **Lint** | edit-in-place | Lint catches stale/superseded | plain files (git = undo) |

## The patterns the trustworthy systems add on top of "just write"

1. **Curate, don't append** — a short standing page kept brief by active rewrite; bulk in a log/spill files.
   Brevity via a **hard budget that triggers consolidation, never silent truncation** (Hermes/Letta/Claude/OpenClaw).
2. **Two tiers: lossy auto vs durable curated** (Windsurf, Claude, OpenClaw) — maps onto our read-only
   company/practice vs agent-writable matter/user split.
3. **Supersede, never silently overwrite** (Zep bi-temporal, mem0 mark-invalid). The failure mode to avoid is
   ChatGPT facts silently mutating.
4. **Provenance/citation is the #1 trust lever** (Copilot fact→source re-validated; Zep timestamps+source).
5. **Correction is itself a (higher-trust) memory write** — *but every surveyed system's correction story is
   weak*: none tag an entry "human-corrected, do-not-overwrite," none keep undo/version history. **This gap is
   our edge** and exactly the maintainer's intent ("the lawyer corrects, it records a memory").
6. **Memory describes; the gate authorizes** (OpenClaw, explicit). Memory text never grants authority — hard
   controls stay in `guarded_tool_call` R4/R5/R6.

## Governance reconciliation

The maintainer's request reverses two accepted decisions **for the matter tier only**: **ADR-0013 D4**
("applied only after the user keeps it... proposals surface for review, not silent write") and **ADR-F030 §2A**
(matter tier built as propose/accept). "System proposes, user owns" becomes **"agent writes, user owns" —
control moves from *before* the write to *after* it** (correct / undo / delete; human facts win; corrections
pinned). Ownership ≠ pre-approval. The user/autonomous tier keeps D4; company/practice stay read-only. This is
the substance of **ADR-F042**.

## Sources (verified)

Claude Code: code.claude.com/docs/en/memory · platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool ·
anthropic.com/news/context-management. OpenClaw: github.com/openclaw/openclaw + docs.openclaw.ai/concepts/memory.
Hermes: hermes-agent.nousresearch.com/docs/user-guide/features/memory. Letta: docs.letta.com/guides/agents/memory-blocks +
arxiv.org/abs/2310.08560. mem0: github.com/mem0ai/mem0. Zep/Graphiti: github.com/getzep/graphiti. ChatGPT/Copilot/
Windsurf/Cursor: official help docs + reputable writeups. Karpathy: gist 442a6bf555914893e9891c11519de94f.
