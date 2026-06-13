<!--
	ModalShell — the shared modal primitive for the LQ.AI surface (R1a).

	A thin composition over shadcn `ui/dialog` (bits-ui Dialog), which already
	provides focus-trap, Escape-to-close, overlay-click close, scroll-lock, the
	`role="dialog"`/`aria-modal` wiring, and `aria-labelledby`/`-describedby`
	bound to the title/description — so we do NOT re-implement any of that.

	`bind:open` is controlled by the caller. The footer is a snippet rendered in
	`Dialog.Footer`; put the form in `children` with `id=…` and give the footer's
	submit `<button form="…">` so the action lives in the footer bar yet still
	submits the form (and Enter-to-submit keeps working).
-->
<script lang="ts">
	import * as Dialog from '$lib/components/ui/dialog/index.js';
	import type { Snippet } from 'svelte';

	let {
		open = $bindable(false),
		title,
		description = undefined,
		contentClass = '',
		children,
		footer = undefined
	}: {
		open?: boolean;
		/** Dialog heading — rendered as the bits-ui Title (an `<h2>`), auto-linked as the aria label. */
		title: string;
		/** Optional sub-heading under the title. */
		description?: string;
		/** Extra classes for the content surface (e.g. `sm:max-w-lg`). */
		contentClass?: string;
		children: Snippet;
		/** Action row; rendered in the footer bar. */
		footer?: Snippet;
	} = $props();
</script>

<Dialog.Root bind:open>
	<Dialog.Content class={contentClass}>
		<Dialog.Header>
			<Dialog.Title>{title}</Dialog.Title>
			{#if description}
				<Dialog.Description>{description}</Dialog.Description>
			{/if}
		</Dialog.Header>

		{@render children()}

		{#if footer}
			<Dialog.Footer>{@render footer()}</Dialog.Footer>
		{/if}
	</Dialog.Content>
</Dialog.Root>
