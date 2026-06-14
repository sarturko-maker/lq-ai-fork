<!--
	Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
	See ../../README.md for provenance + the token-remap convention.

	AE2: the inline container for a row of MessageAction buttons.
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

<div class={cn('flex items-center gap-1', className)} {...restProps}>
	{@render children?.()}
</div>
