# F1-R6 — MessageBubble family + `<think>` reasoning ribbon

Slice R6 of the legacy-design rollout (`F1-legacy-design-rollout-decomposition.md`). One PR.
Reads first: HANDOFF.md, the decomposition plan, ADR-F006 (UI stack), the R1a primitives kit.

## Re-scope on entry (HANDOFF said to)

The coverage table assigns R6 exactly **two** `var(--lq-)` files: `ProvenancePill.svelte` (12) and
`M2Citations.svelte` (1). Verified on entry:

- **MessageBubble.svelte itself has NO `var(--lq-)`** and **no `color:white` literal** — its bubble
  colours are hardcoded Tailwind *palette* utilities (`bg-indigo-600 text-white`, `bg-white
  dark:bg-gray-800 …`, `bg-gray-100`). The "kill `color:white` literal" line in the decomposition
  plan was inaccurate for this file (the literal lives in `RefusalMessageBubble`, see Deferred).
- **TierBadge / TierDetailsPanel: already clean** (0 `var(--lq-)`, 0 hardcoded hex) — OUT of scope.
- **`splitThink()` already exists** (`agents/helpers.ts:78`, unit-tested in `agents/__tests__/helpers.test.ts`).
  It is the canonical MiniMax-M3 `<think>…</think>` splitter (handles unclosed trailing `<think>`).
  R6 **reuses it** — no duplicate parser.
- **ConversationPanel already renders a collapsed `<details class="ag-thinking">` reasoning ribbon**
  (F0-S7/S8) for the *agent* surface. The *legacy chat* surface (`MessageBubble`) has none, so
  MiniMax-M3's inline `<think>` currently **leaks as prose** (DOMPurify strips the unknown tag but
  keeps its text). R6 fixes that for the chat surface and extracts the ribbon into a reusable
  primitive that R-CONV-2 will adopt for ConversationPanel.

## Goal

The legacy chat MessageBubble (1) stops leaking model reasoning as prose — `<think>` content
collapses into a "Reasoning" ribbon; (2) renders on semantic tokens (light+dark via tokens, not the
bridge); and the two token-bearing family members move off `--lq-*`, closing them toward R-LAST.

## Non-goals

- **No `marked`/DOMPurify memoization** (behaviour change — its own slice, per critique).
- **No image-beacon / DOMPurify hardening** (tracked in backlog).
- **RefusalMessageBubble restyle** — Deferred (see below).
- No change to citation fetch semantics, ARIA contracts, or the M2 five-state colour system
  (M2Citations' emerald/amber/grey hex are deliberately AA-tuned and are NOT `--lq-*` — left as-is;
  only the one `--lq-accent` focus outline moves).

## Files (4)

1. **NEW `web/src/lib/lq-ai/components/primitives/ReasoningRibbon.svelte`** — reusable collapsed
   `<details>` "Reasoning" disclosure. Props `{ summary?='Reasoning', open?=false, children: Snippet }`.
   Markup mirrors the `ag-thinking` idiom: a `<summary>` (muted, pointer) + an inset body
   (`bg-muted text-muted-foreground rounded-md`). Caller sanitises and passes the body. Semantic
   tokens only. This is the idiom R-CONV-2 reuses.

2. **`MessageBubble.svelte`**
   - `splitThink(message.content)` for assistant messages → render `visible` as the markdown prose
     (was the whole content), render `thinking` (when present) in `<ReasoningRibbon>` above the prose,
     same `marked`+DOMPurify sanitisation the bubble already uses.
   - `bubbleClasses` palette → semantic tokens: user `bg-primary text-primary-foreground`; assistant
     `bg-card text-card-foreground border-border`; system `bg-muted text-muted-foreground`.
     `--primary` ≈ indigo-600, `--card` ≈ white/gray-800 → near-identical render, now token-driven.
   - `error_code` banner → reuse R1a `<Alert intent="error">` (kills the hardcoded rose block).
   - Citation single-fetch `$:` guard unchanged (adversarial focus — verify it still fires once).

3. **`ProvenancePill.svelte`** — delete the `<style>` block (12 `var(--lq-)`). Tone → semantic
   Tailwind classes on the button (module helpers `iconFor`/`toneFor`/`descriptionFor` and their
   tests unchanged):
   - `sage` → `bg-accent text-accent-foreground` (soft-indigo tint; default skill/provider/kb/audit/enhanced)
   - `slate` → `bg-muted text-muted-foreground` (tier OK)
   - `amber` → `border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300` (tier mismatch;
     same idiom as R1a Alert warning — dark AA verified)
   - focus → `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`

4. **`M2Citations.svelte`** — the single `outline: 2px solid var(--lq-accent, #4338ca)` → `var(--ring)`.
   Everything else (emerald/amber/grey five-state) is intentional AA-tuned hex, untouched.

## Deferred (on record)

- **RefusalMessageBubble.svelte** — has the `color:#fff` + `#4338ca` literals but **zero `var(--lq-)`**,
  so it does NOT block R-LAST's deletion gate. It is a *conditional* surface (renders only on a real
  tier-floor refusal — un-triggerable on the dev stack with the tier-4-only model and no area floor),
  so it can't get an honest live before/after screenshot in R6. Its restyle (hardcoded hex → semantic
  amber-warn idiom) folds into **R-CONV-2** (conversation-core, refusal-adjacent). Its pure helpers
  stay unit-tested meanwhile.

## The four disciplines (per-slice DoD)

1. **Testing + visual screenshots.** vitest + svelte-check green in-container. Headed Cypress
   before/after of the chat surface — assistant reply carrying `<think>` (ribbon collapsed/expanded),
   citations, an error banner, and an enhanced ProvenancePill — **light + dark, wide + narrow** →
   `docs/fork/evidence/r6/`. Add vitest coverage for the bubble's split/render derivation if a pure
   seam exists; otherwise rely on the existing `splitThink` tests + the Cypress render proof.
2. **Code simplification.** Delete ProvenancePill's whole `<style>` block; delete MessageBubble's
   hardcoded rose error block (→ Alert); no new parser (reuse `splitThink`); no new ribbon
   markup duplicated (one primitive, two future consumers).
3. **Adversarial review** (fresh-context subagent) — focus: citation single-fetch race after the
   split refactor; accent-on-accent dark contrast (ProvenancePill sage, ribbon body); ribbon
   sanitisation (thinking is model output — must go through DOMPurify); `<details>` ARIA/keyboard;
   streaming with an unclosed `<think>`.
4. **HANDOFF** overwritten at slice close → next = R7.

## Verification gate (ADR-F005)

CI green (svelte-check + vitest + …) · containerized suite counts quoted · fresh-context adversarial
review (blockers/should-fixes fixed or deferred on record) · live screenshot evidence · HANDOFF updated
→ squash-merge to `main` with `--repo sarturko-maker/lq-ai-fork --head fork/r6-messagebubble-think-ribbon`.
