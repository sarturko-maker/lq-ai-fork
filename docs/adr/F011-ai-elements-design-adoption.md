# F011 — Adopt the AI Elements look via the Svelte port; keep Svelte; keep our transport + sanitizer

- Status: accepted
- Date: 2026-06-14
- Deciders: maintainer (Arturs) — accepted 2026-06-14 ("proceed on the basis of best practice")
- Supersedes: none (extends the design rollout governed by F006)

## Context

The maintainer wants the LQ.AI conversation and agent surfaces to adopt the **look-and-feel of
Vercel's [AI Elements](https://github.com/vercel/ai-elements)** — clean, document-style full-width
assistant responses, polished streaming (shimmer + auto-collapsing reasoning with a duration),
syntax-highlighted code blocks, hover actions, and collapsible tool/task/sources cards. The one hard
rule: **default clean light/white theme + dark mode** (already our house rule — see
[[design-rule-light-clean-cutting-edge]] and F006).

Key facts established by research (2026-06-14):

- **AI Elements is React-only** (shadcn/ui + Vercel AI SDK; `npx ai-elements add` writes JSX into a
  Next.js app). LQ.AI's web client is **SvelteKit** (OpenWebUI heritage), already on
  **shadcn-svelte 1.3 + bits-ui 2.18 + Tailwind v4 + semantic tokens** (the in-flight `--lq-*` →
  semantic-token rollout). So the AI Elements *code* is not portable; the *design* is.
- A faithful **MIT-licensed Svelte port exists**: `SikandarJODD/ai-elements` ("Svelte AI Elements"),
  a **shadcn-svelte-based copy-paste registry** (distributed via `jsrepo`), ~40 components, Svelte 5,
  Tailwind v4 — the same "own the source" model we already use for shadcn-svelte primitives.
- Vercel ships **first-party `@ai-sdk/svelte`** (a Svelte-5 `Chat` class, the analog of React's
  `useChat`, rewritten by the Svelte core team) and an official `vercel/ai-chatbot-svelte` template on
  *exactly* our stack.
- **Svelte 5 is #1 in developer satisfaction/retention** (State of JS 2025, 91% retention) and a
  first-class AI-ecosystem target. React leads only in raw usage / hiring pool / enterprise ubiquity.
- LQ.AI's transport is **NOT** the Vercel AI SDK: every model call routes through the **Inference
  Gateway** (sole egress / key-holder), streams over a **custom SSE protocol**, and every agent action
  passes the **`guarded_tool_call`** chokepoint (R4/R5/R6) with an **audit** contract. These are
  load-bearing (CLAUDE.md "KEEP unchanged"). Model output is rendered through our hardened
  `renderModelMarkdown` (`marked` + `DOMPurify` with a media-forbid `FORBID_TAGS` policy).

## Considered options

1. **Rewrite the web client in React and adopt AI Elements directly.** Rejected. Milestone-scale
   rewrite of the *entire* frontend (cockpit, agents, chat, skills, settings), restarts the design
   rollout, and stalls the practice-area pivot — for **zero architectural payoff** (the gateway / audit
   / agent substrate is Python and framework-agnostic). The only React edge (hiring / ubiquity) is
   irrelevant to an agent-coded solo fork.
2. **Hand-build the AI Elements look from scratch in Svelte.** Rejected as the default. Redundant — a
   faithful MIT Svelte port already exists. (Retained as the **fallback** for any component the port
   lacks or whose port quality is poor.)
3. **Adopt the full Vercel stack, including the `@ai-sdk/svelte` `Chat` transport.** Rejected. The
   `Chat` class expects an AI-SDK-shaped endpoint; wiring it would bypass the Inference Gateway, the
   custom SSE protocol, the `guarded_tool_call` chokepoint, and the audit contract — all load-bearing.
4. **(Chosen) Keep Svelte. Vendor the Svelte AI Elements components (MIT, via `jsrepo`), re-token to
   our semantic palette, and wire them to our EXISTING data** (message store / SSE frames / Citation
   Engine / agent steps). Keep our transport and our sanitizer; adopt only the components' *presentation*.

## Decision outcome

Chosen: **option 4.**

- **Svelte is retained.** No React rewrite. (This is the hard-to-reverse, cross-cutting call this ADR
  primarily records.)
- **AI Elements design adopted via the vendored Svelte port**, copied into
  `web/src/lib/lq-ai/components/ai-elements/` as **source we own** (same model as `ui/*`), and
  re-skinned to our semantic tokens (`--background/foreground/card/muted/accent/primary/border/ring/
  popover/destructive`). No `var(--lq-*)` in vendored components — they are born semantic, so they do
  not regress the R-LAST deletion gate.
- **Message identity: full-width assistant (document-style Response) + soft right-aligned user bubble**
  (the AI Elements signature). A proposed default the maintainer may overturn.
- **Transport/data unchanged:** gateway + custom SSE + `guarded_tool_call` + audit. We do **not** adopt
  `@ai-sdk/svelte`'s `Chat`. Components are pure presentation fed by our stores.
- **Sanitizer unchanged:** keep `renderModelMarkdown` (`marked` + `DOMPurify`, media-forbid). The
  port's "Response" likely ships an unhardened markdown sink (Streamdown/marked) — we adopt its *prose
  styling* and replace its *sink* with ours. Any vendored component carrying `{@html}` is a
  security-review item on its slice.
- **New dependencies, justified (the rollout's "no new dependency" note gets a recorded exception
  here):** `shiki` (code-block highlighting; an SBOM entry — it tokenizes text, no `eval`/network).
  `jsrepo` is a **dev-time vendoring CLI**, not shipped. Each vendored component is an SBOM +
  supply-chain review on its slice; the MIT attribution is added to `NOTICES.md`.
- **Folds into the existing rollout as an AE-series** (see
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` § "AI Elements visual adoption"):
  AE-slices upgrade **R9 → Prompt Input** and **R-CONV-2 → Tool/Task** in place and restyle the
  already-migrated message surface (R6) to full-width; the R-series continues for non-conversation
  surfaces. The token-migration foundation is the *prerequisite*, so the two efforts are complementary.

## Consequences

- (+) Fast path to a polished, modern look on the stack we already run; the design stays **transparent**
  (source we own and can read), honoring the transparency invariant.
- (+) Tailwind v4 + shadcn-svelte + bits-ui already present → low integration risk; the token system is
  identical to what AI Elements expects.
- (+) Complementary to the rollout — no architectural churn; the gateway/audit/agent substrate is
  untouched.
- (−) Net-new supply-chain surface (`shiki`, vendored component source) — mitigated by per-slice SBOM +
  security review and the fact Shiki only tokenizes text.
- (−) Some already-merged surfaces (R6 message bubbles) get **restyled again** (full-width). Accepted:
  the token migration was independently necessary; the AE restyle layers on top of it.
- (−) Vendored components must be re-tokened and re-wired to our data + sanitizer before they ship — a
  vendored component is a starting point, not a drop-in.
- Code is canonical: verify each vendored component compiles under our Svelte 5 / Tailwind v4 setup;
  where the port lags, fall back to option 2 (hand-build on shadcn-svelte) for that component.

Reference this ADR (F011) in a one-line comment at the AE component vendoring seam
(`web/src/lib/lq-ai/components/ai-elements/`).
