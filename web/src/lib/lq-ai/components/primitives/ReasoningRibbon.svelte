<!--
	ReasoningRibbon — collapsed `<details>` disclosure for model reasoning (R6).

	MiniMax-M3 emits its chain-of-thought as inline `<think>…</think>` (and, on
	the agent surface, as `reasoning` deltas). Rendered raw, it leaks into the
	answer prose. This ribbon collapses it: a quiet "Reasoning" summary the user
	can expand, with the body in a muted inset panel — the same affordance the
	agent surface's `ag-thinking` block already offers, extracted here as the
	shared idiom (R-CONV-2 adopts it for ConversationPanel).

	Purely presentational. The CALLER is responsible for sanitising the body
	(`<think>` content is model output) — pass already-sanitised markup as the
	default child, e.g. `<ReasoningRibbon>{@html domPurified}</ReasoningRibbon>`.
	Semantic tokens only (no `--lq-*`); reads AA in light and dark.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		summary = 'Reasoning',
		open = false,
		children
	}: {
		/** Disclosure label. */
		summary?: string;
		/** Initial expanded state (native `<details>` owns it after first toggle). */
		open?: boolean;
		/** Sanitised body markup. */
		children: Snippet;
	} = $props();
</script>

<details class="group mt-1" data-testid="lq-ai-reasoning-ribbon" {open}>
	<summary
		class="inline-flex cursor-pointer select-none items-center gap-1 rounded text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden"
	>
		<!-- Chevron rotates when the parent <details> is open. -->
		<svg
			class="h-3 w-3 transition-transform duration-150 group-open:rotate-90"
			viewBox="0 0 12 12"
			fill="currentColor"
			aria-hidden="true"
		>
			<path d="M4 2l4 4-4 4z" />
		</svg>
		<span>{summary}</span>
	</summary>
	<div class="mt-1 rounded-md bg-muted px-3 py-2 text-[13px] leading-relaxed text-muted-foreground">
		{@render children()}
	</div>
</details>
