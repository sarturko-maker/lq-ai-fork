<script lang="ts">
	/**
	 * Cockpit centered intent entry (F2-M4, ADR-F012) — a calm launcher that
	 * sits ABOVE the area grid on the landing. It is NOT a composer (ADR-F002
	 * forbids an unbound free-floating chat): submitting never starts a
	 * conversation. It hands the typed text to the parent, which routes into
	 * the area→matter binding flow (carrying the text forward as the composer
	 * draft) when the destination is unambiguous — exactly one configured
	 * area — and otherwise points the user at the area grid below.
	 *
	 * Honest content only: the greeting/subtitle are static copy; the optional
	 * starter chips are the user's OWN SavedPrompts (the AE7 precedent), never
	 * model-invented. No SavedPrompts → no chips. Semantic tokens only.
	 */
	import { onMount } from 'svelte';
	import ArrowUpIcon from '@lucide/svelte/icons/arrow-up';

	import { Button } from '$lib/components/ui/button/index.js';
	import { savedPromptsApi } from '$lib/lq-ai/api';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { SavedPrompt } from '$lib/lq-ai/types';
	import { Suggestion, Suggestions } from '$lib/lq-ai/components/ai-elements/suggestion/index.js';

	let {
		areas,
		onLaunch
	}: {
		areas: PracticeArea[] | null;
		/** Hand the typed intent to the cockpit to route + carry as draft. */
		onLaunch: (text: string) => void;
	} = $props();

	let text = $state('');
	// Set once a submit landed but no single area could be entered — the hint
	// points the user at the grid below (their note is kept as the draft).
	let awaitingAreaPick = $state(false);
	let fieldEl = $state<HTMLTextAreaElement | null>(null);

	const configuredCount = $derived(areas?.filter((a) => a.configured).length ?? 0);

	// The user's own saved prompts → optional starter chips (AE7). Fail-soft:
	// any error just yields no chips (the launcher still works).
	let savedPrompts = $state<SavedPrompt[]>([]);
	onMount(async () => {
		try {
			savedPrompts = await savedPromptsApi.listSavedPrompts();
		} catch {
			savedPrompts = [];
		}
	});

	function submit() {
		const trimmed = text.trim();
		if (!trimmed) return;
		onLaunch(trimmed);
		// One configured area → the cockpit navigates away; otherwise stay put
		// and point the user at the grid (the draft is preserved upstream).
		awaitingAreaPick = configuredCount !== 1;
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			submit();
		}
	}

	function useChip(promptText: string) {
		text = text.trim() ? `${text.trimEnd()}\n\n${promptText}` : promptText;
		awaitingAreaPick = false;
		fieldEl?.focus();
	}
</script>

<div
	class="mx-auto w-full max-w-2xl px-6 pt-12 pb-2 text-center sm:px-8"
	data-testid="lq-cockpit-centered-entry"
>
	<h1 class="text-2xl font-semibold tracking-tight text-foreground">What are you working on?</h1>
	<p class="mt-1.5 text-sm text-muted-foreground">
		Describe the task — your practice-area agent runs it inside a matter.
	</p>

	<div
		class="mt-6 rounded-xl border border-input bg-card text-left shadow-sm transition-colors focus-within:border-ring focus-within:ring-1 focus-within:ring-ring"
	>
		<textarea
			bind:this={fieldEl}
			bind:value={text}
			onkeydown={onKeydown}
			oninput={() => (awaitingAreaPick = false)}
			rows="2"
			placeholder="e.g. Review this NDA for unusual indemnity terms…"
			class="block w-full resize-none bg-transparent px-3.5 pt-3 pb-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
			data-testid="lq-cockpit-entry-field"
		></textarea>
		<div class="flex items-center justify-end px-2 pb-2">
			<Button
				size="icon"
				class="size-8 rounded-lg"
				disabled={!text.trim()}
				onclick={submit}
				aria-label="Start"
				data-testid="lq-cockpit-entry-submit"
			>
				<ArrowUpIcon class="size-4" aria-hidden="true" />
			</Button>
		</div>
	</div>

	{#if awaitingAreaPick}
		<p class="mt-3 text-xs text-muted-foreground" data-testid="lq-cockpit-entry-hint">
			{configuredCount === 0
				? 'Configure a practice area below to start.'
				: 'Pick a practice area below to start — your note is kept.'}
		</p>
	{/if}

	{#if savedPrompts.length > 0}
		<div class="mt-5 flex justify-center" data-testid="lq-cockpit-entry-suggestions">
			<Suggestions class="justify-center">
				{#each savedPrompts as prompt (prompt.id)}
					<Suggestion
						suggestion={prompt.name}
						title={prompt.prompt_text}
						onclick={() => useChip(prompt.prompt_text)}
						data-testid="lq-cockpit-entry-suggestion"
					/>
				{/each}
			</Suggestions>
		</div>
	{/if}
</div>
