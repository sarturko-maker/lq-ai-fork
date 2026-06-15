<!--
	SectionHeader — a calm title + optional subtitle (F2-M1, ADR-F012).

	Extracts the heading idiom repeated across the cockpit (a `font-semibold
	tracking-tight text-foreground` title over a `text-muted-foreground`
	subtitle) into one primitive so the typographic hierarchy is set once.
	`size` picks both the heading element and the type scale:
	  • `page`    → <h1>, text-2xl, text-sm subtitle  (a surface's main title)
	  • `section` → <h2>, text-sm,  text-xs subtitle  (a block within a surface)
	Both observed in `cockpit/AreaGrid.svelte` ("Your practice" / "Unfiled
	matters"). Title + subtitle are escaped text bindings (no `{@html}`).
	Semantic tokens only — no new token scale (ADR-F012).
-->
<script module lang="ts">
	export type SectionHeaderSize = 'page' | 'section';

	const SCALE: Record<SectionHeaderSize, { tag: 'h1' | 'h2'; title: string; subtitle: string }> = {
		page: {
			tag: 'h1',
			title: 'text-2xl font-semibold tracking-tight text-foreground',
			subtitle: 'mt-1.5 text-sm text-muted-foreground'
		},
		section: {
			tag: 'h2',
			title: 'text-sm font-semibold tracking-tight text-foreground',
			subtitle: 'mt-0.5 text-xs text-muted-foreground'
		}
	};

	export function sectionHeaderScale(size: SectionHeaderSize) {
		return SCALE[size];
	}
</script>

<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		title,
		subtitle = '',
		size = 'page',
		class: klass = '',
		...rest
	}: {
		title: string;
		subtitle?: string;
		size?: SectionHeaderSize;
		class?: string;
	} & HTMLAttributes<HTMLDivElement> = $props();

	const scale = $derived(sectionHeaderScale(size));
</script>

<div class={klass} {...rest}>
	<svelte:element this={scale.tag} class={scale.title}>{title}</svelte:element>
	{#if subtitle}
		<p class={scale.subtitle}>{subtitle}</p>
	{/if}
</div>
