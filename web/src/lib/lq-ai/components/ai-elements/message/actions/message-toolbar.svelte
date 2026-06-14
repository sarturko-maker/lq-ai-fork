<!--
	Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
	See ../../README.md for provenance + the token-remap convention.

	AE2: the full-width footer row that hosts message actions (and, later, other
	per-message affordances). `justify-between` so an actions cluster sits
	opposite any metadata.
-->
<script lang="ts">
	import { cn } from '$lib/utils';
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	interface Props extends HTMLAttributes<HTMLDivElement> {
		class?: string;
		children?: Snippet;
	}

	let { class: className, children, ...restProps }: Props = $props();
</script>

<div class={cn('mt-4 flex w-full items-center justify-between gap-4', className)} {...restProps}>
	{@render children?.()}
</div>
