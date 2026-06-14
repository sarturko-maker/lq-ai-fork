<!--
	ReasoningRibbon — collapsed disclosure for model reasoning (R6; AE2 identity).

	MiniMax-M3 emits its chain-of-thought as inline `<think>…</think>` (and, on
	the agent surface, as `reasoning` deltas). Rendered raw, it leaks into the
	answer prose. This ribbon collapses it: a quiet brain-iconed "Reasoning"
	summary the user can expand, with the body in a muted inset panel — the same
	affordance the agent surface's `ag-thinking` block already offers.

	AE2 (ADR-F011): adopts the Vercel AI Elements **Reasoning** *identity* — brain
	icon, rotating chevron, a "Thinking…" shimmer while streaming and a
	"Thought for Ns" duration when done, auto-open while streaming + a one-shot
	auto-collapse a beat after it completes. The AE `reasoning` registry block
	pulls four deps we avoid (`streamdown-svelte`, `@shikijs/themes`,
	`mode-watcher`, plus a `collapsible` we don't vendor + its Streamdown
	`Response` sink), so per ADR-F011's option-2 we hand-build the identity on our
	accessible native `<details>` (zero new deps, keeps the sanitized slot).

	The streaming/duration machinery stays DORMANT until a caller passes
	`streaming` — the M1 chat surface has no separate reasoning stream (deltas
	land with F1-S4), so there it renders a static collapsed "Reasoning". It is
	exercised today on the internal `_ae-lab` route.

	Purely presentational. The CALLER is responsible for sanitising the body
	(`<think>` content is model output) — pass already-sanitised markup as the
	default child, e.g. `<ReasoningRibbon>{@html domPurified}</ReasoningRibbon>`.
	Semantic tokens only (no `--lq-*`); reads AA in light and dark.
-->
<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import Brain from '@lucide/svelte/icons/brain';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';

	let {
		summary = 'Reasoning',
		open = false,
		streaming = false,
		durationSeconds = undefined,
		children
	}: {
		/** Disclosure label when idle (no duration known). */
		summary?: string;
		/** Initial expanded state (native `<details>` owns it after first toggle). */
		open?: boolean;
		/** True while reasoning is actively streaming — shows the shimmer + auto-opens. */
		streaming?: boolean;
		/** Caller-supplied duration; when omitted it's measured from the stream. */
		durationSeconds?: number;
		/** Sanitised body markup. */
		children: Snippet;
	} = $props();

	const AUTO_CLOSE_DELAY = 1000;

	// Local open state: auto-opens while streaming, auto-collapses once shortly
	// after the stream ends, and otherwise follows the `open` prop. User toggles
	// flow back through `bind:open`, so we never fight the reader.
	let isOpen = $state(untrack(() => open || streaming));
	let hasAutoClosed = $state(false);

	// Duration measurement on the browser perf clock — only used when the caller
	// streams without supplying `durationSeconds`. `performance.now()` is safe:
	// effects never run during SSR.
	let startedAt = $state<number | null>(null);
	let measured = $state<number | null>(null);

	$effect(() => {
		if (streaming) {
			isOpen = true;
			hasAutoClosed = false;
			if (startedAt === null) startedAt = performance.now();
			measured = null;
		} else if (startedAt !== null) {
			measured = Math.max(1, Math.ceil((performance.now() - startedAt) / 1000));
			startedAt = null;
		}
	});

	// One-shot auto-collapse a beat after streaming completes — lets the final
	// lines land before the ribbon folds away.
	$effect(() => {
		if (
			!streaming &&
			isOpen &&
			!hasAutoClosed &&
			(measured !== null || durationSeconds !== undefined)
		) {
			const timer = setTimeout(() => {
				isOpen = false;
				hasAutoClosed = true;
			}, AUTO_CLOSE_DELAY);
			return () => clearTimeout(timer);
		}
	});

	const duration = $derived(durationSeconds ?? measured ?? null);
	const label = $derived(
		streaming ? 'Thinking…' : duration !== null ? `Thought for ${duration}s` : summary
	);
</script>

<details class="group mt-1" data-testid="lq-ai-reasoning-ribbon" bind:open={isOpen}>
	<summary
		class="inline-flex cursor-pointer list-none items-center gap-1.5 rounded text-xs text-muted-foreground transition-colors select-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&::-webkit-details-marker]:hidden"
	>
		<Brain class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
		<span class={streaming ? 'animate-pulse' : ''}>{label}</span>
		<ChevronDown
			class="h-3.5 w-3.5 shrink-0 transition-transform duration-150 group-open:rotate-180"
			aria-hidden="true"
		/>
	</summary>
	<div
		class="mt-1 rounded-md bg-muted px-3 py-2 text-[13px] leading-relaxed text-muted-foreground"
		data-testid="lq-ai-reasoning-ribbon-body"
	>
		{@render children()}
	</div>
</details>
