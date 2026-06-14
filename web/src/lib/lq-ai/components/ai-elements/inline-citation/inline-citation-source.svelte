<!--
	Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
	See ../../README.md for provenance + the token-remap convention.

	AE3: a source's identity block — a truncated title, an optional url, and an
	optional description. We use it for the document name + cited-pages line in
	the Sources card. Tokens are identity (semantic only). All fields are
	plain-text bindings (Svelte auto-escapes) — never `{@html}`.
-->
<script lang="ts">
	import { cn } from '$lib/utils';
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	type Props = HTMLAttributes<HTMLDivElement> & {
		title?: string;
		url?: string;
		description?: string;
		children?: Snippet;
		class?: string;
	};

	let { title, url, description, children, class: className, ...restProps }: Props = $props();
</script>

<div class={cn('space-y-1', className)} {...restProps}>
	{#if title}
		<h4 class="truncate text-sm leading-tight font-medium">{title}</h4>
	{/if}
	{#if url}
		<p class="truncate text-xs break-all text-muted-foreground">{url}</p>
	{/if}
	{#if description}
		<p class="line-clamp-3 text-sm leading-relaxed text-muted-foreground">
			{description}
		</p>
	{/if}
	{#if children}
		{@render children()}
	{/if}
</div>
