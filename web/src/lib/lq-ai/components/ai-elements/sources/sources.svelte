<!--
	AE identity from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
	See ../../README.md for provenance + the token-remap convention.

	AE3 — OPTION-2 hand-build. The upstream `sources` block splits into
	Sources / SourcesTrigger / SourcesContent over shadcn `collapsible` (which we
	do NOT ship — same dep we dodged for the AE2 Reasoning ribbon). So we collapse
	the trio into ONE component on the accessible native `<details>`: the trigger
	("Used N sources" + rotating chevron) is the `<summary>`, the content snippet
	is the body. Zero new deps; keeps the AE identity (book/chevron, "Used N
	sources", text-xs). Semantic tokens only (born 0 `var(--lq-)`).

	Purely presentational — the caller supplies the list of <Source> items as the
	`children` snippet and is responsible for escaping any model/document text.
-->
<script lang="ts">
	import { cn } from '$lib/utils';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import type { Snippet } from 'svelte';

	let {
		count,
		open = false,
		class: className,
		children
	}: {
		/** Number of distinct sources — drives the "Used N sources" label. */
		count: number;
		/** Initial expanded state (native `<details>` owns it after first toggle). */
		open?: boolean;
		class?: string;
		/** The list of `<Source>` items. */
		children: Snippet;
	} = $props();
</script>

<details class={cn('group not-prose mt-2 text-xs', className)} data-testid="lq-ai-sources" {open}>
	<summary
		class="inline-flex cursor-pointer list-none items-center gap-1.5 rounded font-medium text-muted-foreground transition-colors select-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&::-webkit-details-marker]:hidden"
	>
		<span>Used {count} {count === 1 ? 'source' : 'sources'}</span>
		<ChevronDown
			class="h-3.5 w-3.5 shrink-0 transition-transform duration-150 group-open:rotate-180"
			aria-hidden="true"
		/>
	</summary>
	<div class="mt-2 flex w-full flex-col gap-2" data-testid="lq-ai-sources-content">
		{@render children()}
	</div>
</details>
