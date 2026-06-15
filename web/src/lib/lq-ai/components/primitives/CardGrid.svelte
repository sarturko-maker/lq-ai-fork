<!--
	CardGrid — the hairline-divided card grid (F2-VL1, ADR-F013 §6).

	Renders its `Card` children as a grid whose 1px gaps sit over a `--border`
	background with a single outer radius — so the cards read as one hairline-
	divided plane (the Vercel idiom), NOT free-floating shadowed boxes. The
	cells supply `bg-card`; the gap shows the border through. Collapses
	responsively (1 → 2 → N columns) per the "collapse panels when narrow"
	design rule. Presentation only; semantic tokens + Tailwind scale only.
-->
<script module lang="ts">
	export type CardGridCols = 1 | 2 | 3 | 4;

	const COLS: Record<CardGridCols, string> = {
		1: 'grid-cols-1',
		2: 'grid-cols-1 sm:grid-cols-2',
		3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
		4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4'
	};

	/** The hairline-grid container class for a column count (+ optional extra). */
	export function cardGridClass(cols: CardGridCols = 3, extra = ''): string {
		const base = `border-border bg-border grid gap-px overflow-hidden rounded-lg border ${COLS[cols]}`;
		return extra.trim() ? `${base} ${extra.trim()}` : base;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		cols = 3,
		class: klass = '',
		children,
		...rest
	}: {
		cols?: CardGridCols;
		class?: string;
		children: Snippet;
	} & HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class={cardGridClass(cols, klass)} {...rest}>
	{@render children()}
</div>
