<!--
	Inline — horizontal rhythm primitive (F2-VL1, ADR-F013).

	A `flex` row with a named gap + alignment + optional wrap, the horizontal
	counterpart to Stack. Used for chip rows, toolbars, and label+value pairs.
	Presentation only; Tailwind's 4px scale (no new token scale). All variants
	are literal class strings (no interpolation) so Tailwind's JIT scanner keeps
	them. `text-link` chip rows (spec §6) compose as `<Inline gap="lg">`.
-->
<script module lang="ts">
	export type InlineGap = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl';
	export type InlineAlign = 'start' | 'center' | 'end' | 'baseline' | 'stretch';
	export type InlineJustify = 'start' | 'center' | 'between' | 'end';

	const GAP: Record<InlineGap, string> = {
		none: 'gap-0',
		xs: 'gap-1.5',
		sm: 'gap-2',
		md: 'gap-3',
		lg: 'gap-5',
		xl: 'gap-8'
	};

	const ALIGN: Record<InlineAlign, string> = {
		start: 'items-start',
		center: 'items-center',
		end: 'items-end',
		baseline: 'items-baseline',
		stretch: 'items-stretch'
	};

	const JUSTIFY: Record<InlineJustify, string> = {
		start: 'justify-start',
		center: 'justify-center',
		between: 'justify-between',
		end: 'justify-end'
	};

	/** The full row class string for a gap + alignment + justify + wrap. */
	export function inlineClass(
		gap: InlineGap = 'sm',
		align: InlineAlign = 'center',
		justify: InlineJustify = 'start',
		wrap = false,
		extra = ''
	): string {
		const base =
			`flex ${wrap ? 'flex-wrap' : ''} ${GAP[gap]} ${ALIGN[align]} ${JUSTIFY[justify]}`.replace(
				/\s+/g,
				' '
			);
		return extra.trim() ? `${base} ${extra.trim()}` : base;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		gap = 'sm',
		align = 'center',
		justify = 'start',
		wrap = false,
		class: klass = '',
		children,
		...rest
	}: {
		gap?: InlineGap;
		align?: InlineAlign;
		justify?: InlineJustify;
		wrap?: boolean;
		class?: string;
		children: Snippet;
	} & HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class={inlineClass(gap, align, justify, wrap, klass)} {...rest}>
	{@render children()}
</div>
