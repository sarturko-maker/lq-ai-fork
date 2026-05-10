<script lang="ts">
	/**
	 * Inference Tier badge per PRD §3.13.
	 *
	 * C8 surfaced this as a static badge; D2 (this file) makes it
	 * clickable — the click event opens the TierDetailsPanel via the
	 * parent (MessageBubble owns the panel state). The badge stays
	 * compact: a tier number + colour + tooltip; the details panel
	 * shows the full provider/model + token usage + tier description.
	 *
	 * Keyboard accessibility: the badge is a button, so it focuses with
	 * Tab and activates with Enter/Space. The tooltip (`title` attr)
	 * still works for hover users who don't need the full panel.
	 */
	import { createEventDispatcher } from 'svelte';

	export let tier: 1 | 2 | 3 | 4 | 5 | null | undefined = null;
	export let provider: string | null | undefined = null;
	/**
	 * When `false` the badge renders as a static span (no click /
	 * keyboard handlers). Used by surfaces where the parent has its
	 * own interaction model (admin alias UI, model picker resolution
	 * preview).
	 */
	export let interactive: boolean = true;

	const dispatch = createEventDispatcher<{ open: void }>();

	const tierColour: Record<number, string> = {
		1: 'bg-emerald-100 text-emerald-800 border-emerald-300',
		2: 'bg-sky-100 text-sky-800 border-sky-300',
		3: 'bg-amber-100 text-amber-800 border-amber-300',
		4: 'bg-orange-100 text-orange-800 border-orange-300',
		5: 'bg-rose-100 text-rose-800 border-rose-300'
	};

	$: classes = tier ? tierColour[tier] : 'bg-gray-100 text-gray-700 border-gray-300';
	$: label = tier ? `Tier ${tier}` : 'Tier ?';
	$: title = provider
		? `${label} — ${provider} (click for details)`
		: `${label} — click for details`;

	function handleClick(): void {
		if (interactive) dispatch('open');
	}

	function handleKey(event: KeyboardEvent): void {
		if (!interactive) return;
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			dispatch('open');
		}
	}
</script>

{#if interactive}
	<button
		type="button"
		class="inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-indigo-400 {classes}"
		{title}
		on:click={handleClick}
		on:keydown={handleKey}
		data-testid="lq-ai-tier-badge"
	>
		{label}
	</button>
{:else}
	<span
		class="inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium {classes}"
		{title}
		data-testid="lq-ai-tier-badge"
	>
		{label}
	</span>
{/if}
