<script lang="ts">
	/**
	 * AliasForm — modal/inline form for create + edit (D0.5).
	 *
	 * - `alias = null` → create mode (name field is editable).
	 * - `alias != null` → edit mode (name field locked; the gateway PATCH
	 *    endpoint identifies the row by name).
	 *
	 * Provider dropdown is populated from `availableProviders` (the parent
	 * pulls this from the admin/config endpoint). Model field is free-text
	 * with a `<datalist>` for autocomplete fed from the parent's
	 * provider→models map (the same source).
	 *
	 * Validation:
	 *   - name (create mode only): non-empty, lowercase ascii / digits / hyphen
	 *   - provider: must be selected
	 *   - model: non-empty
	 * Submit calls `onSubmit({name, provider, model, fallback})`.
	 *
	 * The form renders inline validation errors next to each field; the
	 * parent renders server-side errors (409 conflict, 422 validation)
	 * separately above the form.
	 */
	import type { Alias, AliasFallback } from '../api/admin';

	export let alias: Alias | null = null;
	export let availableProviders: Array<{ name: string; type: string }> = [];
	/** Optional autocomplete map: provider → list of native models. */
	export let providerModels: Record<string, string[]> = {};
	export let onSubmit: (next: {
		name: string;
		provider: string;
		model: string;
		fallback: AliasFallback[];
	}) => void = () => undefined;
	export let onCancel: () => void = () => undefined;
	export let submitting: boolean = false;
	export let serverError: string | null = null;

	const isEdit = alias !== null;

	let name = alias?.name ?? '';
	let provider = alias?.provider ?? '';
	let model = alias?.model ?? '';
	let fallbacks: AliasFallback[] = alias ? alias.fallback.map((f) => ({ ...f })) : [];

	let nameError: string | null = null;
	let providerError: string | null = null;
	let modelError: string | null = null;

	function validate(): boolean {
		nameError = null;
		providerError = null;
		modelError = null;
		if (!isEdit) {
			if (!name.trim()) {
				nameError = 'Required';
			} else if (!/^[a-z0-9][a-z0-9_-]*$/.test(name)) {
				nameError = 'Lowercase letters, digits, hyphen, underscore';
			}
		}
		if (!provider.trim()) {
			providerError = 'Pick a provider';
		}
		if (!model.trim()) {
			modelError = 'Required';
		}
		return !nameError && !providerError && !modelError;
	}

	function submit() {
		if (!validate()) return;
		onSubmit({
			name: name.trim(),
			provider: provider.trim(),
			model: model.trim(),
			fallback: fallbacks
				.map((f) => ({ provider: f.provider.trim(), model: f.model.trim() }))
				.filter((f) => f.provider !== '' && f.model !== '')
		});
	}

	function addFallback() {
		fallbacks = [...fallbacks, { provider: '', model: '' }];
	}

	function removeFallback(idx: number) {
		fallbacks = fallbacks.filter((_, i) => i !== idx);
	}

	$: modelOptions = providerModels[provider] ?? [];
</script>

<form
	class="space-y-3 p-4 border border-gray-200 rounded-md bg-white"
	on:submit|preventDefault={submit}
	data-testid="lq-ai-alias-form"
>
	<div class="text-sm font-semibold text-gray-800">
		{isEdit ? `Edit alias “${alias?.name}”` : 'New alias'}
	</div>

	{#if serverError}
		<div
			class="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1"
			data-testid="lq-ai-alias-form-error"
		>
			{serverError}
		</div>
	{/if}

	{#if !isEdit}
		<div>
			<label for="alias-name" class="text-xs font-medium text-gray-600">Name</label>
			<input
				id="alias-name"
				type="text"
				class="w-full text-sm border border-gray-300 rounded px-2 py-1"
				bind:value={name}
				placeholder="smart, fast, my-budget-alias"
				data-testid="lq-ai-alias-form-name"
			/>
			{#if nameError}
				<p class="text-xs text-rose-700 mt-1">{nameError}</p>
			{/if}
		</div>
	{/if}

	<div>
		<label for="alias-provider" class="text-xs font-medium text-gray-600">Provider</label>
		<select
			id="alias-provider"
			class="w-full text-sm border border-gray-300 rounded px-2 py-1"
			bind:value={provider}
			data-testid="lq-ai-alias-form-provider"
		>
			<option value="">— pick a provider —</option>
			{#each availableProviders as p (p.name)}
				<option value={p.name}>{p.name} ({p.type})</option>
			{/each}
		</select>
		{#if providerError}
			<p class="text-xs text-rose-700 mt-1">{providerError}</p>
		{/if}
	</div>

	<div>
		<label for="alias-model" class="text-xs font-medium text-gray-600">Model</label>
		<input
			id="alias-model"
			type="text"
			class="w-full text-sm border border-gray-300 rounded px-2 py-1 font-mono"
			bind:value={model}
			placeholder="claude-sonnet-4-6, gpt-4o, llama3.1:8b"
			list="alias-model-options"
			data-testid="lq-ai-alias-form-model"
		/>
		<datalist id="alias-model-options">
			{#each modelOptions as opt}
				<option value={opt}></option>
			{/each}
		</datalist>
		{#if modelError}
			<p class="text-xs text-rose-700 mt-1">{modelError}</p>
		{/if}
	</div>

	<div>
		<div class="flex items-center justify-between">
			<span class="text-xs font-medium text-gray-600">Fallback chain</span>
			<button
				type="button"
				class="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
				on:click={addFallback}
				data-testid="lq-ai-alias-form-add-fallback"
			>
				+ add fallback
			</button>
		</div>
		{#if fallbacks.length === 0}
			<p class="text-xs text-gray-500 mt-1">No fallbacks. Primary provider must be reachable.</p>
		{/if}
		{#each fallbacks as fb, idx}
			<div class="flex items-center gap-2 mt-2" data-testid="lq-ai-alias-form-fallback-row">
				<select
					class="flex-1 text-xs border border-gray-300 rounded px-2 py-1"
					bind:value={fb.provider}
				>
					<option value="">— provider —</option>
					{#each availableProviders as p (p.name)}
						<option value={p.name}>{p.name}</option>
					{/each}
				</select>
				<input
					type="text"
					class="flex-1 text-xs border border-gray-300 rounded px-2 py-1 font-mono"
					bind:value={fb.model}
					placeholder="model-id"
				/>
				<button
					type="button"
					class="text-xs px-2 py-1 text-rose-700 hover:bg-rose-50 rounded"
					on:click={() => removeFallback(idx)}
					aria-label="Remove fallback"
				>
					×
				</button>
			</div>
		{/each}
	</div>

	<div class="flex items-center justify-end gap-2 pt-2">
		<button
			type="button"
			class="text-sm px-3 py-1 rounded border border-gray-300 hover:bg-gray-50"
			on:click={onCancel}
			data-testid="lq-ai-alias-form-cancel"
		>
			Cancel
		</button>
		<button
			type="submit"
			class="text-sm px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
			disabled={submitting}
			data-testid="lq-ai-alias-form-submit"
		>
			{submitting ? 'Saving…' : isEdit ? 'Save' : 'Create'}
		</button>
	</div>
</form>
