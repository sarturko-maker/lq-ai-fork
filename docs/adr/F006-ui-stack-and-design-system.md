# F006 — UI stack: extract the shell, adopt the AI SDK stream spec, build a legal-grade design system

Status: proposed (maintainer accepts/rejects)
Date: 2026-06-10
Inputs: two research workflows (stack: 5 agents incl. repo audit; visual benchmark: legal-AI teardown +
frontier design language), maintainer feedback on live F0-S3 ("the entire system looks really basic";
"cutting edge visually — think top-tier Legal AI Platforms or Gemini or Claude.ai").

## Context

The web UI is a fork of OpenWebUI v0.9.2. A full audit found our code (254 files, ~50k LOC under
`web/src/{lib,routes}/lq-ai/`) has **zero imports from the OpenWebUI husk** — while the husk costs
~129k LOC unused frontend, an unused ~90k-LOC Python backend container (HF model downloads at boot,
`webui.db` — which broke `/lq-ai/*` login during S3 verification), 103 runtime deps where we use ~8,
slow builds (OOM on the dev box unless the stack is stopped), and the OpenWebUI license §4 branding
clause (>50 users) — a live obligation we carry for nothing.

The target UX (maintainer, 2026-06-10): left panel practice areas → Matters; center conversation with
Claude-Code-like streamed reasoning and visible tool calls; right panel Skills / Playbooks / legal
Tools + collapsed utilities + a Claude.ai-style Memory manager. The visual benchmark validates this
IA against the market: Harvey's "Matter OS" pivot (Oct 2025) answers the same "tool-organized, not
matter-organized" criticism this fork was founded on; Legora's aOS ships the deep-agent-with-skills
model (Plan → Execute → Review → Deliver, plan shown to the user); CoCounsel streams agent reasoning
"as it unfolds". **No vendor has shipped a user-editable memory manager** (Harvey announced one,
co-building since Jan 2026) — our F2 surface is differentiating, with Claude.ai's manage-memory modal
(synthesized summary, edit-in-place, pause vs reset, per-project scoping) as the design reference.

Hard constraints: gateway is the only egress (UI talks only to our FastAPI api); ADR-F004
render-determinism (settled rows decide; streams animate); Apache-2.0 target for public release;
one maintainer + AI agents do all the work.

## Considered options

1. **Stay and polish the OpenWebUI fork.** Zero migration; perpetual tax (boot, build, deps, §4,
   masked typecheck), and upstream is FROZEN (ADR-F001) so the husk buys nothing — ever.
2. **Extract + arm (chosen):** lift the lq-ai code into a standalone SvelteKit app; adopt the Vercel
   **AI SDK UI Message Stream v1 as the SSE v2 wire spec** (Apache-2.0, spec-only — a small
   hand-rolled FastAPI emitter; no Vercel runtime; gateway untouched; our `data-*` parts carry
   subagent ancestry / interrupts / plan / receipts, each referencing its settled `agent_run_steps`
   row id); build a **new design system** on shadcn-svelte + bits-ui + paneforge + Tailwind v4 —
   semantic intent tokens (the Harvey pattern), light+dark, denser work-tool spacing — with bespoke
   Svelte agent components (collapsed-by-default reasoning ribbon with shimmer status, plan/task
   cards, tool cards, subagent tree), using Vercel AI Elements and deep-agents-ui as *semantic*
   references.
3. **Flip to a React agent framework** (assistant-ui / CopilotKit / deep-agents-ui / AI Elements).
   Best out-of-box agent chrome — AI Elements maps 1:1 onto our target (Reasoning, Plan, Task, Tool,
   Confirmation) and deep-agents-ui is purpose-built for deepagents. But: most LangGraph UIs expect
   the **Elastic-licensed LangGraph Server** in production (only the AG-UI path avoids it, and its
   interrupt spec is draft); client-owned transcript state fights ADR-F004; and a 50k-LOC rewrite
   lands mid-F0 while the agent loop itself is half-built.
4. **Adopt another platform** (LibreChat, LobeChat, Chainlit, HF chat-ui). Structurally broken:
   they run their own agent loops, so their UIs would not reflect *our* deepagents runs — and none
   offers an extension surface for practice areas / Matters / memory. LobeChat's license
   disqualifies it outright.

## Decision outcome

Option 2, sequenced so nothing blocks current work: S4 (real tools) and S5 (multi-turn) proceed on
the existing shell now → **S6 — the shell shed** (new lean SvelteKit app, lq-ai code nearly
verbatim, kills the husk + §4) → **S7 — SSE v2 emits the AI SDK stream spec** onto the clean shell
→ design-system build-out runs with F1's practice-area home (left/right panels land on the new
system, not the husk). The wire-spec decision is the time-critical one: it must be accepted before
S7 implementation starts.

## Consequences

- (+) Sheds the §4 branding obligation and ~220k LOC of dead weight; every later slice gets faster
  builds, honest typechecks, and screenshot-gated merges without the boot tax. No-regret under every
  future framework outcome (the same wire feeds React AI Elements if we ever flip).
- (+) The differentiating 60% of the UX (subagent ancestry, decision inbox, receipts, capability
  rail, render-determinism) is custom on EVERY path — we build it once, on our architecture.
- (−) All agent chrome is hand-rolled in Svelte; the React agent ecosystem compounds while we do.
  **Revisit trigger:** if F1/F2 find us cloning deep-agents-ui piece by piece, flip at the F2
  boundary on the same wire (supersede this ADR).
- (−) The public Apache-2.0 relicensing claim is conditional on a **per-file provenance pass** over
  the ~123 lq-ai `.svelte` components before release (extraction slice includes it; `app.html`'s
  theme script must be rewritten, not copied).
- (−) Vercel controls the stream spec's evolution; we pin to v1 and own the emitter, so drift is
  absorbable.
