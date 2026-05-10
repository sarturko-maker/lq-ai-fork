<script lang="ts">
	/**
	 * /lq-ai/admin/audit-log — admin audit-log filter + paginated view (D3-coverage).
	 *
	 * Backed by ``GET /api/v1/admin/audit-log``. Admin-gated; non-admins
	 * see a flash error and are routed back to /lq-ai.
	 *
	 * Filters compose with AND on the server. Each filter has a sensible
	 * empty state — leaving a field blank means "any". The privilege
	 * dropdown is tri-state (any / privileged / non-privileged).
	 *
	 * Pagination is cursor-based; ``next_cursor`` carries forward into
	 * the next page request, and the table accumulates rows on
	 * "Load more" so an investigator can scroll a continuous timeline.
	 * Changing any filter resets the cursor + accumulation.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { auditLogApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { AuditLogEntry, AuditLogFilters } from '$lib/lq-ai/api/auditLog';

	let rows: AuditLogEntry[] = [];
	let nextCursor: string | null = null;
	let loading = false;
	let listError: string | null = null;

	// Filter form state. ``privilegeMarked`` is a tri-state string mapped
	// to boolean | null on submit; the rest are plain inputs.
	let privilegeMarked: 'any' | 'true' | 'false' = 'any';
	let routedTier: '' | '1' | '2' | '3' | '4' | '5' = '';
	let action = '';
	let userId = '';
	let since = '';
	let until = '';
	let limit = 50;

	$: filters = (): AuditLogFilters => ({
		privilege_marked: privilegeMarked === 'any' ? null : privilegeMarked === 'true',
		routed_inference_tier: routedTier === '' ? null : (Number(routedTier) as 1 | 2 | 3 | 4 | 5),
		action: action.trim() || null,
		user_id: userId.trim() || null,
		since: since ? new Date(since).toISOString() : null,
		until: until ? new Date(until).toISOString() : null,
		limit
	});

	async function load(reset: boolean) {
		loading = true;
		listError = null;
		try {
			const page = await auditLogApi.listAuditLog({
				...filters(),
				cursor: reset ? null : nextCursor
			});
			rows = reset ? page.items : [...rows, ...page.items];
			nextCursor = page.next_cursor;
		} catch (e) {
			console.error('audit-log: load failed', e);
			listError = e instanceof Error ? e.message : 'Failed to load audit log';
		} finally {
			loading = false;
		}
	}

	async function applyFilters() {
		await load(true);
	}

	async function loadMore() {
		await load(false);
	}

	function resetFilters() {
		privilegeMarked = 'any';
		routedTier = '';
		action = '';
		userId = '';
		since = '';
		until = '';
		limit = 50;
		applyFilters();
	}

	function formatTimestamp(iso: string): string {
		try {
			return new Date(iso).toLocaleString();
		} catch {
			return iso;
		}
	}

	function formatDetails(d: Record<string, unknown> | null): string {
		if (!d) return '';
		try {
			return JSON.stringify(d);
		} catch {
			return '';
		}
	}

	onMount(async () => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/audit-log; redirecting');
			goto('/lq-ai');
			return;
		}
		await load(true);
	});
</script>

<svelte:head>
	<title>Audit log — LQ.AI admin</title>
</svelte:head>

<div class="p-4 max-w-7xl mx-auto" data-testid="lq-ai-admin-audit-log">
	<header class="mb-4">
		<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Audit log</h1>
		<p class="text-xs text-gray-600 dark:text-gray-400 mt-1">
			Every state-changing API call writes one row here (PRD §5.3). Filters compose with AND;
			leaving a field blank means "any". Most-recent rows first.
		</p>
	</header>

	<form
		class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4 p-3 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900"
		on:submit|preventDefault={applyFilters}
		data-testid="lq-ai-admin-audit-log-filters"
	>
		<label class="flex flex-col text-xs">
			<span class="text-gray-500 mb-1">Privilege</span>
			<select
				bind:value={privilegeMarked}
				class="rounded border-gray-300 dark:border-gray-700 dark:bg-gray-800 text-sm"
				data-testid="lq-ai-audit-filter-privilege"
			>
				<option value="any">Any</option>
				<option value="true">Privileged only</option>
				<option value="false">Non-privileged only</option>
			</select>
		</label>

		<label class="flex flex-col text-xs">
			<span class="text-gray-500 mb-1">Routed tier</span>
			<select
				bind:value={routedTier}
				class="rounded border-gray-300 dark:border-gray-700 dark:bg-gray-800 text-sm"
				data-testid="lq-ai-audit-filter-tier"
			>
				<option value="">Any</option>
				<option value="1">Tier 1 — on-prem</option>
				<option value="2">Tier 2 — private cloud</option>
				<option value="3">Tier 3 — ZDR commercial</option>
				<option value="4">Tier 4 — standard commercial</option>
				<option value="5">Tier 5 — consumer</option>
			</select>
		</label>

		<label class="flex flex-col text-xs">
			<span class="text-gray-500 mb-1">Action (exact)</span>
			<input
				type="text"
				placeholder="e.g. chat.message_sent"
				bind:value={action}
				class="rounded border-gray-300 dark:border-gray-700 dark:bg-gray-800 text-sm"
				data-testid="lq-ai-audit-filter-action"
			/>
		</label>

		<label class="flex flex-col text-xs">
			<span class="text-gray-500 mb-1">User ID (UUID)</span>
			<input
				type="text"
				placeholder="00000000-0000-…"
				bind:value={userId}
				class="rounded border-gray-300 dark:border-gray-700 dark:bg-gray-800 text-sm font-mono"
				data-testid="lq-ai-audit-filter-user"
			/>
		</label>

		<label class="flex flex-col text-xs">
			<span class="text-gray-500 mb-1">Since</span>
			<input
				type="datetime-local"
				bind:value={since}
				class="rounded border-gray-300 dark:border-gray-700 dark:bg-gray-800 text-sm"
				data-testid="lq-ai-audit-filter-since"
			/>
		</label>

		<label class="flex flex-col text-xs">
			<span class="text-gray-500 mb-1">Until</span>
			<input
				type="datetime-local"
				bind:value={until}
				class="rounded border-gray-300 dark:border-gray-700 dark:bg-gray-800 text-sm"
				data-testid="lq-ai-audit-filter-until"
			/>
		</label>

		<div class="col-span-full flex items-center gap-2 justify-end">
			<button
				type="button"
				class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
				on:click={resetFilters}
				data-testid="lq-ai-audit-filter-reset"
			>
				Reset
			</button>
			<button
				type="submit"
				class="px-3 py-1.5 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
				disabled={loading}
				data-testid="lq-ai-audit-filter-apply"
			>
				{loading ? 'Loading…' : 'Apply filters'}
			</button>
		</div>
	</form>

	{#if listError}
		<div
			class="px-3 py-2 rounded border border-rose-300 bg-rose-50 text-rose-800 text-sm mb-3"
			data-testid="lq-ai-admin-audit-log-error"
		>
			{listError}
		</div>
	{/if}

	<div class="overflow-x-auto rounded border border-gray-200 dark:border-gray-700">
		<table class="min-w-full text-xs" data-testid="lq-ai-admin-audit-log-table">
			<thead class="bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200">
				<tr>
					<th class="px-2 py-1 text-left">Timestamp</th>
					<th class="px-2 py-1 text-left">Action</th>
					<th class="px-2 py-1 text-left">User</th>
					<th class="px-2 py-1 text-left">Resource</th>
					<th class="px-2 py-1 text-left">Priv</th>
					<th class="px-2 py-1 text-left">Tier</th>
					<th class="px-2 py-1 text-left">Provider</th>
					<th class="px-2 py-1 text-left">IP</th>
					<th class="px-2 py-1 text-left">Details</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as r (r.id)}
					<tr
						class="border-t border-gray-100 dark:border-gray-800 align-top"
						class:bg-amber-50={r.privilege_marked}
					>
						<td class="px-2 py-1 font-mono whitespace-nowrap">{formatTimestamp(r.timestamp)}</td>
						<td class="px-2 py-1 font-mono">{r.action}</td>
						<td class="px-2 py-1 font-mono truncate max-w-[12ch]" title={r.user_id ?? ''}>
							{r.user_id ?? '—'}
						</td>
						<td class="px-2 py-1">
							{r.resource_type}{r.resource_id ? `/${r.resource_id.slice(0, 8)}…` : ''}
						</td>
						<td class="px-2 py-1">
							{#if r.privilege_marked}
								<span class="px-1.5 py-0.5 rounded bg-amber-200 text-amber-900 text-[10px]">
									{r.privilege_basis ?? 'yes'}
								</span>
							{:else}
								—
							{/if}
						</td>
						<td class="px-2 py-1">{r.routed_inference_tier ?? '—'}</td>
						<td class="px-2 py-1 font-mono">{r.routed_provider ?? '—'}</td>
						<td class="px-2 py-1 font-mono">{r.ip_address ?? '—'}</td>
						<td class="px-2 py-1 font-mono truncate max-w-[28ch]" title={formatDetails(r.details)}>
							{formatDetails(r.details)}
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="9" class="px-2 py-6 text-center text-gray-500">
							{loading ? 'Loading…' : 'No audit entries match.'}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if nextCursor}
		<div class="flex justify-center mt-3">
			<button
				type="button"
				class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
				on:click={loadMore}
				disabled={loading}
				data-testid="lq-ai-admin-audit-log-load-more"
			>
				{loading ? 'Loading…' : 'Load more'}
			</button>
		</div>
	{/if}
</div>
