<script lang="ts">
	/**
	 * F2 Tabular T2 — in-chat grid preview + Expand (ADR-F055).
	 *
	 * A durable artifact card the conversation shows for each grid a run
	 * finalized: a compact M×N preview (column pills + a clamped mini-table)
	 * with an Expand button. T6 (ADR-F055): Expand no longer self-hosts an
	 * overlay — it dispatches `expand` so the cockpit opens the grid as a
	 * stage-takeover (the docked `TabularWorkspace`, conversation stays mounted).
	 *
	 * It re-derives identically live and on reload because the parent anchors
	 * it on the settled `finalize_tabular_review` step (ADR-F004); the grid
	 * body comes from `GET /tabular/executions/{id}` (owner-scoped — the
	 * caller is the run's user; cross-user/missing → 404).
	 */
	import { createEventDispatcher, onDestroy, onMount } from 'svelte';
	import TableIcon from '@lucide/svelte/icons/table';
	import Maximize2Icon from '@lucide/svelte/icons/maximize-2';
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle';

	import { getTabularExecution } from '$lib/lq-ai/api/tabular';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { TabularExecution, TabularExecutionStatus } from '$lib/lq-ai/types';
	import {
		isTerminalGridStatus,
		summarizeGridForPreview
	} from '$lib/lq-ai/agents/tabular-preview';

	export let gridId: string;

	// T6: Expand no longer self-hosts an overlay — it asks the cockpit to open the
	// grid as a stage-takeover (the docked TabularWorkspace). ConversationPanel
	// forwards this to ConversationHost.openGrid. The conversation stays mounted.
	const dispatch = createEventDispatcher<{ expand: { gridId: string } }>();

	let execution: TabularExecution | null = null;
	let loading = true;
	let loadError: string | null = null;
	// A 404 means the grid does not exist for this user (e.g. the model finalized a
	// fabricated id) — render nothing rather than a spurious error card.
	let notFound = false;

	// The finalize step streams at tool-START, before the finalize body flips the
	// row to `completed` — so a mount-time fetch can race the commit and read a
	// non-terminal status. Poll (bounded) until terminal so that self-corrects
	// without a reload; on reload the grid is already terminal so this never fires.
	const POLL_INTERVAL_MS = 1500;
	const MAX_POLLS = 10;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let polls = 0;
	let destroyed = false;

	$: preview = execution ? summarizeGridForPreview(execution) : null;

	onMount(load);
	onDestroy(() => {
		destroyed = true;
		clearPoll();
	});

	function clearPoll(): void {
		if (pollTimer !== null) {
			clearTimeout(pollTimer);
			pollTimer = null;
		}
	}

	async function load(): Promise<void> {
		loading = true;
		loadError = null;
		clearPoll();
		try {
			execution = await getTabularExecution(gridId);
			if (destroyed) return;
			if (!isTerminalGridStatus(execution.status) && polls < MAX_POLLS) {
				polls += 1;
				pollTimer = setTimeout(() => void load(), POLL_INTERVAL_MS);
			}
		} catch (e) {
			if (e instanceof LQAIApiError && e.status === 404) {
				notFound = true;
			} else {
				loadError = e instanceof LQAIApiError ? e.message : 'Could not load this grid.';
			}
		} finally {
			loading = false;
		}
	}

	// Manual retry (error card) — reset the poll budget so a recovered backend
	// can still be polled to terminal.
	function retry(): void {
		polls = 0;
		void load();
	}

	const STATUS_LABEL: Record<TabularExecutionStatus, string> = {
		pending: 'Queued',
		running: 'Building…',
		completed: 'Ready',
		failed: 'Failed',
		cancelled: 'Cancelled'
	};
	function statusTone(status: TabularExecutionStatus): string {
		if (status === 'completed') return 'ok';
		if (status === 'failed' || status === 'cancelled') return 'warn';
		return 'busy';
	}

	function expand(): void {
		dispatch('expand', { gridId });
	}
</script>

{#if !notFound}
<div class="ag-grid-card" data-testid="lq-ai-tabular-preview" data-grid-id={gridId}>
	{#if loading}
		<p class="lq-text-caption ag-grid-card__loading" data-testid="lq-ai-tabular-preview-loading">
			<LoaderCircleIcon class="size-3.5 ag-grid-card__spin" aria-hidden="true" />
			Loading grid…
		</p>
	{:else if loadError}
		<p class="lq-text-body-sm ag-grid-card__error" data-testid="lq-ai-tabular-preview-error">
			{loadError}
			<button type="button" class="ag-grid-card__retry" on:click={retry}>Retry</button>
		</p>
	{:else if execution && preview}
		<header class="ag-grid-card__head">
			<span class="ag-grid-card__title">
				<TableIcon class="size-4" aria-hidden="true" />
				<span class="lq-text-label">Grid</span>
				<span class="lq-text-caption ag-grid-card__counts">
					{preview.docCount} document{preview.docCount === 1 ? '' : 's'} ·
					{preview.colCount} column{preview.colCount === 1 ? '' : 's'}
				</span>
			</span>
			<span
				class="ag-grid-card__status ag-grid-card__status--{statusTone(execution.status)}"
				data-testid="lq-ai-tabular-preview-status"
			>
				{STATUS_LABEL[execution.status] ?? execution.status}
			</span>
		</header>

		{#if preview.columnNames.length > 0}
			<ul class="ag-grid-pills" data-testid="lq-ai-tabular-preview-pills">
				{#each preview.columnNames as col (col)}
					<li class="ag-grid-pill">{col}</li>
				{/each}
			</ul>
		{/if}

		{#if preview.previewRows.length > 0 && preview.previewColumns.length > 0}
			<div class="ag-grid-mini__scroll">
				<table class="ag-grid-mini">
					<thead>
						<tr>
							<th scope="col" class="ag-grid-mini__doc">Document</th>
							{#each preview.previewColumns as col (col)}
								<th scope="col">{col}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each preview.previewRows as row (row.documentId)}
							<tr>
								<th scope="row" class="ag-grid-mini__doc" title={row.documentName}>
									{row.documentName}
								</th>
								{#each row.cells as cell, c (preview.previewColumns[c])}
									<td
										class:ag-grid-mini__failed={cell.failed}
										class:ag-grid-mini__empty={cell.empty}
									>
										{cell.empty ? '—' : cell.value}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		<footer class="ag-grid-card__foot">
			{#if preview.moreRows > 0 || preview.moreCols > 0}
				<span class="lq-text-caption ag-grid-card__more">
					{#if preview.moreRows > 0}+{preview.moreRows} more row{preview.moreRows === 1
							? ''
							: 's'}{/if}{#if preview.moreRows > 0 && preview.moreCols > 0}
						·
					{/if}{#if preview.moreCols > 0}+{preview.moreCols} more column{preview.moreCols === 1
							? ''
							: 's'}{/if}
				</span>
			{:else}
				<span></span>
			{/if}
			<button
				type="button"
				class="ag-grid-card__expand"
				data-testid="lq-ai-tabular-preview-expand"
				on:click={expand}
			>
				<Maximize2Icon class="size-3.5" aria-hidden="true" />
				Expand
			</button>
		</footer>
	{/if}
</div>
{/if}

<style>
	.ag-grid-card {
		margin-top: 0.75rem;
		border: 1px solid var(--lq-border, color-mix(in srgb, currentColor 14%, transparent));
		border-radius: var(--lq-radius-md, 0.625rem);
		background: var(--lq-surface-1, color-mix(in srgb, currentColor 3%, transparent));
		padding: 0.75rem 0.875rem;
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
	}
	.ag-grid-card__loading {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		opacity: 0.75;
	}
	.ag-grid-card__error {
		color: var(--lq-danger, #b42318);
	}
	.ag-grid-card__retry {
		margin-left: 0.5rem;
		background: none;
		border: none;
		text-decoration: underline;
		cursor: pointer;
		color: inherit;
		font: inherit;
	}
	.ag-grid-card__head,
	.ag-grid-card__foot {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.ag-grid-card__title {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		min-width: 0;
	}
	.ag-grid-card__counts {
		opacity: 0.7;
	}
	.ag-grid-card__status {
		flex: none;
		font-size: 0.6875rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		border: 1px solid transparent;
	}
	.ag-grid-card__status--ok {
		color: var(--lq-success-fg, #067647);
		background: var(--lq-success-bg, color-mix(in srgb, #067647 10%, transparent));
		border-color: color-mix(in srgb, #067647 28%, transparent);
	}
	.ag-grid-card__status--busy {
		color: var(--lq-accent-fg, #3538cd);
		background: color-mix(in srgb, #3538cd 10%, transparent);
		border-color: color-mix(in srgb, #3538cd 26%, transparent);
	}
	.ag-grid-card__status--warn {
		color: var(--lq-danger, #b42318);
		background: color-mix(in srgb, #b42318 9%, transparent);
		border-color: color-mix(in srgb, #b42318 26%, transparent);
	}
	.ag-grid-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.ag-grid-pill {
		font-size: 0.75rem;
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		background: var(--lq-surface-2, color-mix(in srgb, currentColor 7%, transparent));
		border: 1px solid color-mix(in srgb, currentColor 10%, transparent);
		white-space: nowrap;
	}
	.ag-grid-mini__scroll {
		overflow-x: auto;
	}
	.ag-grid-mini {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.78rem;
	}
	.ag-grid-mini th,
	.ag-grid-mini td {
		text-align: left;
		padding: 0.3rem 0.5rem;
		border-bottom: 1px solid color-mix(in srgb, currentColor 8%, transparent);
		vertical-align: top;
		max-width: 16rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.ag-grid-mini thead th {
		font-weight: 600;
		opacity: 0.85;
	}
	.ag-grid-mini__doc {
		font-weight: 600;
		max-width: 12rem;
	}
	.ag-grid-mini__failed {
		color: var(--lq-danger, #b42318);
	}
	.ag-grid-mini__empty {
		opacity: 0.5;
	}
	.ag-grid-card__more {
		opacity: 0.7;
	}
	.ag-grid-card__expand {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font: inherit;
		font-size: 0.78rem;
		font-weight: 600;
		cursor: pointer;
		padding: 0.3rem 0.6rem;
		border-radius: var(--lq-radius-sm, 0.4rem);
		border: 1px solid color-mix(in srgb, currentColor 16%, transparent);
		background: var(--lq-surface-2, color-mix(in srgb, currentColor 6%, transparent));
		color: inherit;
	}
	.ag-grid-card__expand:hover {
		background: color-mix(in srgb, currentColor 12%, transparent);
	}
	:global(.ag-grid-card__spin) {
		animation: ag-grid-spin 1s linear infinite;
	}
	@keyframes ag-grid-spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
