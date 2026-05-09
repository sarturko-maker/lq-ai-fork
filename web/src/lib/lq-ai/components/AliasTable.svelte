<script lang="ts">
	/**
	 * AliasTable — the admin view of model_aliases (D0.5).
	 *
	 * Renders one row per configured alias with name / provider / model /
	 * fallback-count / Edit + Delete actions. Parent owns the data + handlers
	 * so this component is purely presentational.
	 */
	import type { Alias } from '../api/admin';

	export let aliases: Alias[] = [];
	export let onEdit: (alias: Alias) => void = () => undefined;
	export let onDelete: (alias: Alias) => void = () => undefined;
	export let busy: boolean = false;
</script>

<div class="border border-gray-200 dark:border-gray-700 rounded-md overflow-hidden" data-testid="lq-ai-alias-table">
	<table class="w-full text-sm">
		<thead class="bg-gray-50 dark:bg-gray-800 text-xs uppercase tracking-wide text-gray-500">
			<tr>
				<th class="text-left px-3 py-2">Alias</th>
				<th class="text-left px-3 py-2">Provider</th>
				<th class="text-left px-3 py-2">Model</th>
				<th class="text-left px-3 py-2">Fallback</th>
				<th class="text-right px-3 py-2">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#if aliases.length === 0}
				<tr>
					<td colspan="5" class="px-3 py-6 text-center text-gray-500" data-testid="lq-ai-alias-table-empty">
						No aliases configured.
					</td>
				</tr>
			{:else}
				{#each aliases as alias (alias.name)}
					<tr
						class="border-t border-gray-200 dark:border-gray-700"
						data-testid="lq-ai-alias-row"
						data-alias-name={alias.name}
					>
						<td class="px-3 py-2 font-medium">{alias.name}</td>
						<td class="px-3 py-2 text-gray-700 dark:text-gray-300">{alias.provider}</td>
						<td class="px-3 py-2 text-gray-700 dark:text-gray-300 font-mono text-xs">
							{alias.model}
						</td>
						<td class="px-3 py-2 text-gray-500 text-xs">
							{alias.fallback.length > 0
								? `${alias.fallback.length} fallback${alias.fallback.length === 1 ? '' : 's'}`
								: '—'}
						</td>
						<td class="px-3 py-2 text-right space-x-2">
							<button
								type="button"
								class="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
								on:click={() => onEdit(alias)}
								disabled={busy}
								data-testid="lq-ai-alias-edit-btn"
							>
								Edit
							</button>
							<button
								type="button"
								class="text-xs px-2 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-900/30"
								on:click={() => onDelete(alias)}
								disabled={busy}
								data-testid="lq-ai-alias-delete-btn"
							>
								Delete
							</button>
						</td>
					</tr>
				{/each}
			{/if}
		</tbody>
	</table>
</div>
