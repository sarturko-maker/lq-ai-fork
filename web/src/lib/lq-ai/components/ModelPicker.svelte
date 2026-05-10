<script lang="ts">
	/**
	 * Model picker for the LQ.AI shell composer (D0 + ADR 0011 wave-3).
	 *
	 * Surfaces aliases (`smart`, `fast`, ...) plus live-discovered Ollama,
	 * Anthropic, and OpenAI catalog rows in a single dropdown, grouped
	 * by source. The selected model id flows through `MessageCreate.model`
	 * to `POST /chats/{id}/messages`; the gateway's router accepts both
	 * alias names and raw `provider/model` forms.
	 *
	 * ADR 0011 — transparency-first: each alias row publishes its
	 * resolved primary target inline (`smart → anthropic-prod/claude-opus-4-7`),
	 * along with the number of fallback entries. Users see what aliases
	 * actually do without spelunking through admin config.
	 */
	import type { ModelEntry, ModelListResponse } from '../api/models';
	import { groupModels } from '../api/models';

	export let models: ModelListResponse = { object: 'list', data: [] };
	export let selectedId: string | null = null;
	export let onSelect: (id: string) => void = () => undefined;

	let open = false;

	$: grouped = groupModels(models);
	$: selectedEntry = findSelected(models.data, selectedId);

	function findSelected(data: ModelEntry[], id: string | null): ModelEntry | null {
		if (!id) return null;
		return data.find((entry) => entry.id === id) ?? null;
	}

	function pick(entry: ModelEntry): void {
		open = false;
		if (entry.id === selectedId) return;
		onSelect(entry.id);
	}

	function tierLabel(tier?: number): string {
		if (!tier) return '';
		return `T${tier}`;
	}

	function aliasResolution(entry: ModelEntry): string {
		// "smart → anthropic-prod/claude-opus-4-7 (+2 fallbacks)"
		if (!entry.lq_ai_resolves_to) return '';
		const fb = entry.lq_ai_fallback_count ?? 0;
		const fbHint = fb > 0 ? ` (+${fb} fallback${fb === 1 ? '' : 's'})` : '';
		return `→ ${entry.lq_ai_resolves_to}${fbHint}`;
	}
</script>

<div class="relative inline-block" data-testid="lq-ai-model-picker">
	<button
		type="button"
		class="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
		on:click={() => (open = !open)}
		data-testid="lq-ai-model-picker-toggle"
		title={selectedEntry?.lq_ai_resolves_to
			? `${selectedEntry.id} ${aliasResolution(selectedEntry)}`
			: (selectedEntry?.id ?? 'Select model')}
	>
		<span class="font-medium">Model:</span>
		<span class="ml-1">{selectedEntry?.id ?? 'smart'}</span>
		{#if selectedEntry?.lq_ai_resolves_to}
			<span class="ml-1 text-[10px] text-gray-500" data-testid="lq-ai-model-picker-resolution">
				{aliasResolution(selectedEntry)}
			</span>
		{/if}
		{#if selectedEntry?.routed_inference_tier}
			<span
				class="ml-1 px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-[10px] uppercase tracking-wide"
				data-testid="lq-ai-model-picker-tier"
			>
				{tierLabel(selectedEntry.routed_inference_tier)}
			</span>
		{/if}
	</button>

	{#if open}
		<div
			class="absolute z-10 mt-1 w-72 max-h-80 overflow-auto rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg"
			data-testid="lq-ai-model-picker-dropdown"
		>
			{#if models.data.length === 0}
				<div class="p-3 text-xs text-gray-500" data-testid="lq-ai-model-picker-empty">
					No models available. Check that the Inference Gateway is reachable.
				</div>
			{:else}
				{#if grouped.aliases.length > 0}
					<div
						class="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-gray-500"
						title="Convenience defaults — each alias publishes its resolved provider/model below."
					>
						Aliases (defaults)
					</div>
					{#each grouped.aliases as entry (entry.id)}
						<button
							type="button"
							class="w-full text-left px-3 py-1.5 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/40 flex flex-col items-start"
							class:font-semibold={entry.id === selectedId}
							class:bg-indigo-50={entry.id === selectedId}
							on:click={() => pick(entry)}
							data-testid="lq-ai-model-picker-option"
						>
							<div class="flex items-center justify-between w-full">
								<span>{entry.id}</span>
								{#if entry.routed_inference_tier}
									<span
										class="ml-2 px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-[10px] uppercase tracking-wide"
									>
										{tierLabel(entry.routed_inference_tier)}
									</span>
								{/if}
							</div>
							{#if entry.lq_ai_resolves_to}
								<div
									class="text-[10px] text-gray-500 dark:text-gray-400 font-mono mt-0.5"
									data-testid="lq-ai-model-picker-alias-resolution"
								>
									{aliasResolution(entry)}
								</div>
							{/if}
						</button>
					{/each}
				{/if}

				{#each [...grouped.nativeByProvider.entries()] as [provider, entries] (provider)}
					<div
						class="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-gray-500"
					>
						{provider}
					</div>
					{#each entries as entry (entry.id)}
						<button
							type="button"
							class="w-full text-left px-3 py-1.5 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/40 flex items-center justify-between"
							class:font-semibold={entry.id === selectedId}
							class:bg-indigo-50={entry.id === selectedId}
							on:click={() => pick(entry)}
							data-testid="lq-ai-model-picker-option"
						>
							<span class="truncate">
								{entry.id.includes('/') ? entry.id.split('/').slice(1).join('/') : entry.id}
							</span>
							{#if entry.routed_inference_tier}
								<span
									class="ml-2 px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-[10px] uppercase tracking-wide"
								>
									{tierLabel(entry.routed_inference_tier)}
								</span>
							{/if}
						</button>
					{/each}
				{/each}
			{/if}
		</div>
	{/if}
</div>
