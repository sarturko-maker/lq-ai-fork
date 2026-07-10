# Upstream

- Upstream: https://github.com/LegalQuants/lq-ai
- Baseline: `f91149a` (cloned 2026-06-10; post-v0.4.0 / M4, migrations at 0047)
- Policy: hard fork, upstream FROZEN — no merges, no cherry-picks, no proposals to upstream without
  the maintainer's explicit per-case approval. See `docs/adr/F001-fork-charter.md`.
- Rationale: upstream is not ours; we show our own progress first before any upstream interaction.

## Awareness reviews

Read-only surveys of upstream activity (no code taken). Per ADR-F001 we track upstream for awareness only.

| Date | Range reviewed | Output |
|---|---|---|
| 2026-07-10 | 115 PRs + 25 issues, `f91149a`..upstream-2026-07-09 (upstream now v0.6.1, migs ~0065) | `docs/fork/plans/UPSTREAM-REVIEW-2026-07.md` — 10 include / 10 defer / 23 not-needed / 15 features-noted |

**Convergences found (we fixed the same bug independently — no code taken):** upstream #154 gateway
`lq_ai_*` strip = our GW-STRIP #249 · #155 provider-4xx classify = our PR #96 · #187 Anthropic tool bridge
+ HITL gate = our AZ-2b + ADR-F071 · #193 retire OpenWebUI MCP stub = our F0-S6/ADR-F006 · #198 DOCX ingest
= our ADR-F029 reader registry · #288 audit subset (XSS/viewer-RBAC/rate-limit) = our DOMPurify + ADR-F064
+ Redis limiter.

**Live bugs the review surfaced in our OWN kept substrate (inherited from baseline, upstream also found via
#288):** SEC-1 keyless gateway inference routes; SEC-2 `create_chat` project IDOR + unscoped KB read. Both
✅ **FIXED as `UP-SEC-1`** (branch `up-sec-1-gateway-key-chat-idor`): `/v1` router now key-gated (mirrors
admin), `create_chat` 404s a non-owned project + KB load is owner-scoped. These were **re-authored** as our
own fixes to our own kept substrate (frozen upstream) — **no upstream code was taken**, so they are recorded
here and NOT in the Sync log below (which is reserved for code actually pulled from upstream).

## Sync log

| Date | Upstream ref | What was taken | Why |
|---|---|---|---|
| — | — | — | — |
