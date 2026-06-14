<script lang="ts" module>
	import { cn, type WithElementRef } from '$lib/utils';
	import type { HTMLAttributes } from 'svelte/elements';
	import type { Snippet } from 'svelte';

	export interface ConversationContentProps extends WithElementRef<HTMLAttributes<HTMLDivElement>> {
		children?: Snippet;
	}
</script>

<script lang="ts">
	import { getStickToBottomContext } from './stick-to-bottom-context.svelte.js';
	import { watch } from 'runed';

	let {
		class: className,
		children,
		ref = $bindable(null),
		...restProps
	}: ConversationContentProps = $props();

	const context = getStickToBottomContext();

	// NOTE (ADR-F011): upstream bound BOTH `element` and `ref` to this one <div>
	// (two `bind:this` on a single element — a Svelte 5 compile error). We bind
	// `ref` only and register it as the scroll element.
	watch(
		() => ref,
		() => {
			if (ref) {
				context.setElement(ref);
				// Initial scroll to bottom
				context.scrollToBottom('smooth');
			}
		}
	);
</script>

<div bind:this={ref} class={cn('flex flex-col gap-8 p-4', className)} {...restProps}>
	{@render children?.()}
</div>
