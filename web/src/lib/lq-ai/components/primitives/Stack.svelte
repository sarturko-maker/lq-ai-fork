<!--
	Stack — vertical rhythm primitive (F2-VL1, ADR-F013).

	A `flex flex-col` with a named gap from the F013 spacing rhythm (§3), so
	vertical spacing between blocks is set from ONE scale instead of ad-hoc
	`space-y-*`/`mt-*` on each surface. Presentation only; Tailwind's 4px scale
	(no new token scale — ADR-F013 §3 keeps the 4px base, just names the rungs).
	`2xl` is the cockpit "section gap" (64px / `gap-16`, spec §3).
-->
<script module lang="ts">
	export type StackGap = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';
	export type StackAlign = 'start' | 'center' | 'end' | 'stretch';

	const GAP: Record<StackGap, string> = {
		none: 'gap-0',
		xs: 'gap-2',
		sm: 'gap-3',
		md: 'gap-4',
		lg: 'gap-6',
		xl: 'gap-8',
		'2xl': 'gap-16'
	};

	const ALIGN: Record<StackAlign, string> = {
		start: 'items-start',
		center: 'items-center',
		end: 'items-end',
		stretch: 'items-stretch'
	};

	/** The full container class string for a gap + alignment (+ optional extra). */
	export function stackClass(
		gap: StackGap = 'md',
		align: StackAlign = 'stretch',
		extra = ''
	): string {
		const base = `flex flex-col ${GAP[gap]} ${ALIGN[align]}`;
		return extra.trim() ? `${base} ${extra.trim()}` : base;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		gap = 'md',
		align = 'stretch',
		class: klass = '',
		children,
		...rest
	}: {
		gap?: StackGap;
		align?: StackAlign;
		class?: string;
		children: Snippet;
	} & HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class={stackClass(gap, align, klass)} {...rest}>
	{@render children()}
</div>
