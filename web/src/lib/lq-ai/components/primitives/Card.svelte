<!--
	Card — a calm surface cell (F2-VL1, ADR-F013 §6).

	A `bg-card` panel with the F013 padding rhythm. Inside a `CardGrid` it fills
	a cell (the grid supplies the hairline + radius); standalone, pass
	`bordered` for its own hairline + 12px radius (`rounded-lg`). `interactive`
	adds a hover wash + pointer and renders the calm idiom as a real `<button>`
	(or `<a>` when `href` is set) for keyboard/a11y — Vercel's flat, border-led
	card (shadows reserved for true float, spec §5). Presentation only; semantic
	tokens + Tailwind scale only.
-->
<script module lang="ts">
	export type CardPad = 'default' | 'compact';

	const PAD: Record<CardPad, string> = {
		default: 'p-6',
		compact: 'p-4'
	};

	/** The surface class string for a card (pad / interactive / bordered). */
	export function cardClass(
		pad: CardPad = 'default',
		interactive = false,
		bordered = false,
		extra = ''
	): string {
		const parts = ['bg-card', 'text-card-foreground', 'flex', 'flex-col', PAD[pad]];
		if (bordered) parts.push('border-border', 'rounded-lg', 'border');
		if (interactive)
			parts.push(
				'hover:bg-muted',
				'cursor-pointer',
				'transition-colors',
				'text-left',
				'focus-visible:ring-ring/50',
				'focus-visible:ring-2',
				'outline-none'
			);
		const base = parts.join(' ');
		return extra.trim() ? `${base} ${extra.trim()}` : base;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		pad = 'default',
		interactive = false,
		bordered = false,
		href = undefined,
		class: klass = '',
		children,
		...rest
	}: {
		pad?: CardPad;
		interactive?: boolean;
		bordered?: boolean;
		href?: string;
		class?: string;
		children: Snippet;
	} & HTMLAttributes<HTMLElement> = $props();

	// Interactive cards render as a real control for keyboard + a11y; a plain
	// card stays a <div>. An href wins (link), else a clickable card is a button.
	const tag = $derived(href ? 'a' : interactive ? 'button' : 'div');
</script>

<svelte:element
	this={tag}
	class={cardClass(pad, interactive, bordered, klass)}
	{href}
	type={tag === 'button' ? 'button' : undefined}
	role={tag === 'a' ? 'link' : undefined}
	{...rest}
>
	{@render children()}
</svelte:element>
