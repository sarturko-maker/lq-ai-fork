<script lang="ts">
	/**
	 * Cockpit centered intent entry (F2-M4, ADR-F012; re-skinned to the F013
	 * Vercel language in F2-VL2). A calm launcher that sits ABOVE the area grid
	 * on the landing. It is NOT a composer (ADR-F002 forbids an unbound
	 * free-floating chat): submitting never starts a conversation. It hands the
	 * typed text to the parent, which routes into the area→matter binding flow
	 * (carrying the text forward as the composer draft) when the destination is
	 * unambiguous — exactly one configured area — and otherwise points the user
	 * at the area grid below.
	 *
	 * VL2: the greeting + lead render through the `Hero` primitive (the first
	 * `text-display` consumer on a live surface); the starter chips render as
	 * calm text-links (the direction-vercel idiom) instead of filled pills.
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
	import Hero from '$lib/lq-ai/components/primitives/Hero.svelte';
	import Inline from '$lib/lq-ai/components/primitives/Inline.svelte';

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
	class="mx-auto w-full max-w-3xl px-6 pt-14 pb-4 sm:px-8"
	data-testid="lq-cockpit-centered-entry"
>
	<Hero
		title="What are you working on?"
		subtitle="State the intent — your practice-area deep agent picks its own tools, skills and playbooks, and works visibly inside a matter."
	>
		<!-- The launcher field: a calm prompt-styled surface (NOT a composer —
		     ADR-F002): submit routes into the area→matter flow, never starts a
		     thread. The brand-ink submit + hairline border are the VL0 tokens. -->
		<div
			class="border-input bg-card focus-within:border-foreground mt-1 flex w-full max-w-[600px] items-end gap-2.5 rounded-xl border px-4 py-3 text-left shadow-sm transition-colors"
		>
			<textarea
				bind:this={fieldEl}
				bind:value={text}
				onkeydown={onKeydown}
				oninput={() => (awaitingAreaPick = false)}
				rows="1"
				aria-label="Describe your matter"
				placeholder="Draft a mutual NDA for a SaaS pilot, UK law, 2-year term…"
				class="text-foreground placeholder:text-muted-foreground min-h-[28px] flex-1 resize-none border-0 bg-transparent text-sm outline-none"
				data-testid="lq-cockpit-entry-field"
			></textarea>
			<Button
				size="icon"
				class="size-9 shrink-0 rounded-full"
				disabled={!text.trim()}
				onclick={submit}
				aria-label="Start"
				data-testid="lq-cockpit-entry-submit"
			>
				<ArrowUpIcon class="size-4" aria-hidden="true" />
			</Button>
		</div>

		{#if awaitingAreaPick}
			<p class="text-caption text-muted-foreground" data-testid="lq-cockpit-entry-hint">
				{configuredCount === 0
					? 'Configure a practice area below to start.'
					: 'Pick a practice area below to start — your note is kept.'}
			</p>
		{/if}

		{#if savedPrompts.length > 0}
			<!-- Starter chips as calm text-links (direction-vercel): the user's own
			     SavedPrompts, never model-invented (AE7). `name` + inserted body are
			     escaped text/attribute bindings (no {@html}). -->
			<Inline gap="lg" wrap justify="center" data-testid="lq-cockpit-entry-suggestions">
				{#each savedPrompts as prompt (prompt.id)}
					<button
						type="button"
						class="text-caption text-muted-foreground hover:text-foreground border-b border-transparent pb-0.5 transition-colors hover:border-current"
						title={prompt.prompt_text}
						onclick={() => useChip(prompt.prompt_text)}
						data-testid="lq-cockpit-entry-suggestion"
					>
						{prompt.name}
					</button>
				{/each}
			</Inline>
		{/if}
	</Hero>
</div>
