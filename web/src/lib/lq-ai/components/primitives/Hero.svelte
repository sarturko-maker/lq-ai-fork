<!--
	Hero — the display-type launcher block (F2-VL1, ADR-F013 §6/§7).

	The big editorial heading + lead the cockpit lands on ("What are you working
	on?"). The title uses the VL0 `text-display` token (44px, the type scale's
	flagship) — Hero is its first consumer, so it materialises that utility.
	`children` is the slot below the lead (the composer + chip row in the
	cockpit). Centred by default; `align="start"` for left-aligned page heroes.
	Presentation only; `title`/`subtitle` are escaped text bindings (no
	`{@html}`); semantic tokens + the F013 type scale only.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		title,
		subtitle = '',
		align = 'center',
		class: klass = '',
		children,
		...rest
	}: {
		title: string;
		subtitle?: string;
		align?: 'center' | 'start';
		class?: string;
		children?: Snippet;
	} & HTMLAttributes<HTMLDivElement> = $props();

	const wrap = $derived(align === 'center' ? 'items-center text-center' : 'items-start text-left');
</script>

<div class="flex flex-col gap-5 {wrap} {klass}" {...rest}>
	<h1 class="text-display text-foreground max-w-[15ch] text-balance">{title}</h1>
	{#if subtitle}
		<p class="text-muted-foreground max-w-[46ch] text-base text-balance">{subtitle}</p>
	{/if}
	{#if children}
		{@render children()}
	{/if}
</div>
