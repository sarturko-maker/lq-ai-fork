<!--
	Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
	See ../../README.md for provenance + the token-remap convention.

	AE3: a single entry in the Sources list — a book icon + label. Faithful to
	the upstream `source.svelte` (zero registry deps), with two adaptations for
	our data: `href` is OPTIONAL (our sources are internal documents, not web
	URLs — the in-app source viewer is M2-D2, not yet shipped), so absent an
	`href` it renders a non-navigating `<span>` instead of an `<a>`. Tokens are
	identity (semantic only — born 0 `var(--lq-)`).
-->
<script lang="ts">
	import { cn } from '$lib/utils';
	import BookIcon from '@lucide/svelte/icons/book';
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	interface Props extends HTMLAttributes<HTMLElement> {
		class?: string;
		/** When set, the entry is an external link; otherwise a non-navigating span. */
		href?: string;
		title?: string;
		children?: Snippet;
	}

	let { class: className, href, title, children, ...restProps }: Props = $props();
</script>

{#if href}
	<a
		class={cn('flex items-center gap-2', className)}
		{href}
		rel="noreferrer"
		target="_blank"
		{...restProps}
	>
		{#if children}
			{@render children()}
		{:else}
			<BookIcon class="h-4 w-4 shrink-0" aria-hidden="true" />
			<span class="block font-medium">{title}</span>
		{/if}
	</a>
{:else}
	<span class={cn('flex items-center gap-2', className)} {...restProps}>
		{#if children}
			{@render children()}
		{:else}
			<BookIcon class="h-4 w-4 shrink-0" aria-hidden="true" />
			<span class="block font-medium">{title}</span>
		{/if}
	</span>
{/if}
