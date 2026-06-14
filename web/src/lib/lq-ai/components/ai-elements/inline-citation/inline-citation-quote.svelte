<!--
	Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
	See ../../README.md for provenance + the token-remap convention.

	AE3: a cited passage rendered as a muted, left-bordered blockquote. We use it
	for the representative quote in a Sources entry. Tokens are identity (semantic
	only). The quote is a plain-text binding (Svelte auto-escapes) — never `{@html}`.
-->
<script lang="ts">
	import { cn } from '$lib/utils';
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	type Props = HTMLAttributes<HTMLQuoteElement> & {
		children: Snippet;
		class?: string;
	};

	let { children, class: className, ...restProps }: Props = $props();
</script>

<blockquote
	class={cn('border-l-2 border-muted pl-3 text-sm italic text-muted-foreground', className)}
	{...restProps}
>
	{@render children()}
</blockquote>
