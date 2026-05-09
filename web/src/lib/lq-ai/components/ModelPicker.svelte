<script lang="ts">
	/**
	 * Model picker for the LQ.AI shell composer (Task D0).
	 *
	 * Surfaces aliases (`smart`, `fast`, ...) plus live-discovered Ollama
	 * tags and Anthropic catalog rows in a single dropdown, grouped by
	 * source. The selected model id flows through `MessageCreate.model`
	 * to `POST /chats/{id}/messages`; the gateway's router accepts both
	 * alias names and raw `provider/model` forms.
	 *
	 * Props:
	 *   - `models`: the response from `modelsApi.listModels()`
	 *   - `selectedId`: current selection (controlled by parent)
	 *   - `onSelect(id)`: callback the parent uses to update selection
	 *
	 * Empty state: when `models.data` is empty (e.g., gateway is down at
	 * the precise moment the picker mounted), the dropdown shows a single
	 * read-only "no models available" row. Parent code falls back to
	 * `"smart"` for the actual send so the chat still works.
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
</script>

<div class="relative inline-block" data-testid="lq-ai-model-picker">
	<button
		type="button"
		class="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
		on:click={() => (open = !open)}
		data-testid="lq-ai-model-picker-toggle"
		title={selectedEntry?.id ?? 'Select model'}
	>
		<span class="font-medium">Model:</span>
		<span class="ml-1">{selectedEntry?.id ?? 'smart'}</span>
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
					>
						Aliases
					</div>
					{#each grouped.aliases as entry (entry.id)}
						<button
							type="button"
							class="w-full text-left px-3 py-1.5 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/40 flex items-center justify-between"
							class:font-semibold={entry.id === selectedId}
							class:bg-indigo-50={entry.id === selectedId}
							on:click={() => pick(entry)}
							data-testid="lq-ai-model-picker-option"
						>
							<span>{entry.id}</span>
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
