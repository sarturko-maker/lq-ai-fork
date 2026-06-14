<!--
	Vendored from Svelte AI Elements (SikandarJODD/ai-elements), MIT — ADR-F011.
	See ../../README.md for provenance + the token-remap convention.

	AE2: a single hover-action button (icon + tooltip + sr-only label) for the
	message toolbar. Pure presentation — the CALLER supplies the icon child and
	the `onclick` handler. Tokens are identity (delegates color to our `Button`).
-->
<script lang="ts">
	import { Button, type ButtonProps } from '$lib/components/ui/button/index.js';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';
	import { cn } from '$lib/utils';
	import type { Snippet } from 'svelte';

	type MessageButtonProps = Omit<ButtonProps, 'children' | 'type' | 'href'>;

	type Props = MessageButtonProps & {
		tooltip?: string;
		label?: string;
		class?: string;
		children?: Snippet;
	};

	let {
		tooltip,
		label,
		variant = 'ghost',
		size = 'icon',
		class: className,
		children,
		...restProps
	}: Props = $props();

	const srOnlyLabel = $derived(label || tooltip);
</script>

{#if tooltip}
	<Tooltip.Provider>
		<Tooltip.Root>
			<Tooltip.Trigger>
				{#snippet child({ props })}
					<Button
						{...props}
						{...restProps}
						{size}
						type="button"
						{variant}
						class={cn('size-7', className)}
					>
						{@render children?.()}
						{#if srOnlyLabel}
							<span class="sr-only">{srOnlyLabel}</span>
						{/if}
					</Button>
				{/snippet}
			</Tooltip.Trigger>
			<Tooltip.Content>
				<p>{tooltip}</p>
			</Tooltip.Content>
		</Tooltip.Root>
	</Tooltip.Provider>
{:else}
	<Button {...restProps} {size} type="button" {variant} class={cn('size-7', className)}>
		{@render children?.()}
		{#if srOnlyLabel}
			<span class="sr-only">{srOnlyLabel}</span>
		{/if}
	</Button>
{/if}
