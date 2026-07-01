<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import {
		getTabularExecution,
		cancelTabularExecution,
		exportTabularExecution,
		overrideTabularCell,
		clearTabularCellOverride
	} from '$lib/lq-ai/api/tabular';
	import { openFileInNewTab } from '$lib/lq-ai/api/files';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import TabularGrid from '$lib/lq-ai/components/TabularGrid.svelte';
	import TabularCellDrawer from '$lib/lq-ai/components/TabularCellDrawer.svelte';
	import { buildDocumentNameById } from '$lib/lq-ai/agents/tabular-preview';
	import { findCellInExecution } from '$lib/lq-ai/agents/tabular-workspace-helpers';
	import type { TabularExecution } from '$lib/lq-ai/types';

	import {
		isTerminalStatus,
		progressFraction,
		formatProgress,
		TABULAR_POLL_INTERVAL_MS
	} from './page-helpers';
	import { formatTabularStatus, formatCostUsd, skillNameDisplay } from '../page-helpers';

	let execution: TabularExecution | null = null;
	let loading = true;
	let loadError: string | null = null;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let cancelling = false;

	// Selected cell → docked drawer (T6, replaces the stacked citation modal).
	interface Selected {
		documentId: string;
		documentName: string;
		columnName: string;
	}
	let selected: Selected | null = null;
	let saving = false;
	let actionError: string | null = null;

	$: executionId = $page.params.id;
	$: docCount = execution?.document_ids.length ?? 0;
	$: colCount = execution?.columns.length ?? 0;
	$: fraction = execution
		? progressFraction(execution.status, execution.results, docCount, colCount)
		: 0;
	// Map document_id -> document_name (joined `document_names` first, row
	// name as fallback) — shared with the in-chat grid preview (T2).
	$: documentNameById = execution ? buildDocumentNameById(execution) : {};
	// Re-derive the selected cell from the live execution so the drawer shows
	// fresh data after an override refetch (never a stale captured object).
	$: selectedCell = selected
		? findCellInExecution(execution, selected.documentId, selected.columnName)
		: undefined;

	async function loadOnce(): Promise<void> {
		if (!executionId) return;
		loadError = null;
		try {
			const exec = await getTabularExecution(executionId);
			execution = exec;
			scheduleNextPoll();
		} catch (err) {
			loadError = err instanceof LQAIApiError ? err.message : 'Failed to load tabular execution.';
		} finally {
			loading = false;
		}
	}

	function scheduleNextPoll(): void {
		if (!execution) return;
		if (isTerminalStatus(execution.status)) {
			if (pollTimer) {
				clearTimeout(pollTimer);
				pollTimer = null;
			}
			return;
		}
		if (pollTimer) clearTimeout(pollTimer);
		pollTimer = setTimeout(loadOnce, TABULAR_POLL_INTERVAL_MS);
	}

	async function cancelRun(): Promise<void> {
		if (!execution || isTerminalStatus(execution.status)) return;
		cancelling = true;
		try {
			execution = await cancelTabularExecution(execution.id);
		} catch (err) {
			loadError = err instanceof LQAIApiError ? err.message : 'Failed to cancel.';
		} finally {
			cancelling = false;
		}
	}

	function handleCellOpen(event: CustomEvent<{
		documentId: string;
		documentName: string;
		columnName: string;
		cell: import('$lib/lq-ai/types').TabularCellResult | undefined;
	}>): void {
		const { documentId, documentName, columnName, cell } = event.detail;
		if (!cell) return;
		actionError = null;
		selected = { documentId, documentName, columnName };
	}

	function closeDrawer(): void {
		selected = null;
		actionError = null;
	}

	async function saveOverride(value: string, note: string | null): Promise<void> {
		if (!selected || !executionId) return;
		saving = true;
		actionError = null;
		try {
			execution = await overrideTabularCell(executionId, {
				document_id: selected.documentId,
				column_name: selected.columnName,
				override_value: value,
				override_note: note
			});
		} catch (err) {
			actionError = err instanceof LQAIApiError ? err.message : 'Could not save the override.';
		} finally {
			saving = false;
		}
	}

	async function clearOverride(): Promise<void> {
		if (!selected || !executionId) return;
		saving = true;
		actionError = null;
		try {
			execution = await clearTabularCellOverride(
				executionId,
				selected.documentId,
				selected.columnName
			);
		} catch (err) {
			actionError = err instanceof LQAIApiError ? err.message : 'Could not clear the override.';
		} finally {
			saving = false;
		}
	}

	async function openSource(fileId: string): Promise<void> {
		actionError = null;
		try {
			await openFileInNewTab(fileId);
		} catch (err) {
			actionError = err instanceof LQAIApiError ? err.message : 'Could not open the source document.';
		}
	}

	// M3-C4a — XLSX / CSV export.
	let exportingFormat: 'xlsx' | 'csv' | null = null;
	let exportError: string | null = null;

	async function handleExport(format: 'xlsx' | 'csv'): Promise<void> {
		if (!executionId || exportingFormat) return;
		exportingFormat = format;
		exportError = null;
		try {
			const { blob, filename } = await exportTabularExecution(executionId, format);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (err) {
			exportError = err instanceof LQAIApiError ? err.message : 'Export failed.';
		} finally {
			exportingFormat = null;
		}
	}

	onMount(loadOnce);
	onDestroy(() => {
		if (pollTimer) clearTimeout(pollTimer);
	});
</script>

<svelte:head>
	<title>Tabular result · LQ.AI</title>
</svelte:head>

<section class="lq-tabres">
	{#if loading && !execution}
		<div class="lq-tabres__state" data-testid="lq-tabres-loading">Loading…</div>
	{:else if loadError && !execution}
		<div class="lq-tabres__error" role="alert" data-testid="lq-tabres-error">{loadError}</div>
	{:else if execution}
		<header class="lq-tabres__header">
			<div>
				<h1>Tabular result</h1>
				<p class="lq-tabres__sub">
					<strong>{skillNameDisplay(execution.skill_name)}</strong>
					· {docCount} docs × {colCount} cols
				</p>
			</div>
			<div class="lq-tabres__actions">
				{#if execution.status === 'completed'}
					<button
						type="button"
						class="lq-tabres__export"
						data-testid="lq-tabres-export-xlsx"
						on:click={() => handleExport('xlsx')}
						disabled={exportingFormat !== null}
						title="Download the grid as an .xlsx workbook with citations carried in cell comments."
					>
						{exportingFormat === 'xlsx' ? 'Exporting…' : 'Export XLSX'}
					</button>
					<button
						type="button"
						class="lq-tabres__export"
						data-testid="lq-tabres-export-csv"
						on:click={() => handleExport('csv')}
						disabled={exportingFormat !== null}
						title="Download the grid as a .csv with citations in a trailing citation_links column."
					>
						{exportingFormat === 'csv' ? 'Exporting…' : 'Export CSV'}
					</button>
				{/if}
				<button
					type="button"
					class="lq-tabres__rerun"
					data-testid="lq-tabres-rerun"
					on:click={() => goto('/lq-ai/tabular/new')}>Re-run as new execution</button
				>
			</div>
		</header>
		{#if exportError}
			<div class="lq-tabres__error" role="alert" data-testid="lq-tabres-export-error">
				{exportError}
			</div>
		{/if}

		<!-- Status banner -->
		<div
			class="lq-tabres__banner"
			data-status={execution.status}
			data-testid="lq-tabres-banner"
		>
			<div class="lq-tabres__banner-row">
				<span class="lq-tabres__banner-label">Status:</span>
				<span class="lq-tabres__banner-status" data-testid="lq-tabres-status">
					{formatTabularStatus(execution.status)}
				</span>
				{#if !isTerminalStatus(execution.status)}
					<button
						type="button"
						class="lq-tabres__cancel"
						data-testid="lq-tabres-cancel"
						on:click={cancelRun}
						disabled={cancelling}
					>
						{cancelling ? 'Cancelling…' : 'Cancel'}
					</button>
				{/if}
				{#if execution.status === 'completed'}
					<span class="lq-tabres__banner-cost" data-testid="lq-tabres-cost">
						{formatCostUsd(execution.cost_actual_usd)} actual
						{#if execution.cost_estimate_usd}
							(est. {formatCostUsd(execution.cost_estimate_usd)})
						{/if}
					</span>
				{/if}
			</div>
			{#if !isTerminalStatus(execution.status)}
				<div
					class="lq-tabres__progress"
					data-testid="lq-tabres-progress"
					role="progressbar"
					aria-valuemin="0"
					aria-valuemax="100"
					aria-valuenow={Math.round(fraction * 100)}
				>
					<div class="lq-tabres__progress-bar" style="width: {fraction * 100}%"></div>
					<span class="lq-tabres__progress-text">{formatProgress(fraction)}</span>
				</div>
			{/if}
			{#if execution.error_text}
				<pre class="lq-tabres__banner-error" data-testid="lq-tabres-error-text"
					>{execution.error_text}</pre
				>
			{/if}
		</div>

		{#if execution.columns.length > 0 && execution.document_ids.length > 0}
			<div class="lq-tabres__stage">
				<div class="lq-tabres__grid">
					<TabularGrid
						results={execution.results}
						columns={execution.columns}
						documentIds={execution.document_ids}
						{documentNameById}
						on:open={handleCellOpen}
					/>
				</div>
				{#if selected && selectedCell}
					<div class="lq-tabres__drawer">
						<TabularCellDrawer
							cell={selectedCell}
							documentId={selected.documentId}
							documentName={selected.documentName}
							columnName={selected.columnName}
							{saving}
							{actionError}
							onClose={closeDrawer}
							onSaveOverride={saveOverride}
							onClearOverride={clearOverride}
							onOpenSource={openSource}
						/>
					</div>
				{/if}
			</div>
		{:else}
			<div class="lq-tabres__state">No grid to render (empty execution).</div>
		{/if}
	{/if}
</section>

<style>
	.lq-tabres {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 80rem;
		margin: 0 auto;
		padding: 1.5rem;
	}
	.lq-tabres__header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
	}
	.lq-tabres__header h1 {
		margin: 0;
		font-size: 1.5rem;
	}
	.lq-tabres__sub {
		margin: 0.25rem 0 0;
		color: var(--lq-text-secondary);
		font-size: 0.875rem;
	}
	.lq-tabres__actions {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		flex-wrap: wrap;
	}
	.lq-tabres__rerun,
	.lq-tabres__export {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--lq-border);
		border-radius: 0.375rem;
		background: var(--lq-surface);
		font-size: 0.875rem;
		cursor: pointer;
	}
	.lq-tabres__export:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.lq-tabres__banner {
		padding: 0.875rem 1rem;
		background: var(--lq-inset);
		border-radius: 0.5rem;
		border: 1px solid var(--lq-border);
	}
	.lq-tabres__banner[data-status='completed'] {
		background: var(--lq-success-soft, var(--lq-inset));
		border-color: var(--lq-success-border, var(--lq-border));
	}
	.lq-tabres__banner[data-status='failed'] {
		background: var(--lq-error-soft, var(--lq-inset));
		border-color: var(--lq-error-border, var(--lq-border));
	}
	.lq-tabres__banner[data-status='cancelled'] {
		background: var(--lq-inset);
		border-color: var(--lq-border);
	}
	.lq-tabres__banner-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.lq-tabres__banner-label {
		font-size: 0.75rem;
		color: var(--lq-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.lq-tabres__banner-status {
		font-weight: 600;
	}
	.lq-tabres__banner-cost {
		margin-left: auto;
		font-size: 0.8125rem;
		color: var(--lq-text-secondary);
	}
	.lq-tabres__cancel {
		padding: 0.25rem 0.625rem;
		border: 1px solid var(--lq-border);
		border-radius: 0.25rem;
		background: var(--lq-surface);
		font-size: 0.75rem;
		cursor: pointer;
	}
	.lq-tabres__cancel:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.lq-tabres__progress {
		position: relative;
		height: 1.25rem;
		margin-top: 0.5rem;
		background: var(--lq-surface);
		border-radius: 999px;
		border: 1px solid var(--lq-border);
		overflow: hidden;
	}
	.lq-tabres__progress-bar {
		height: 100%;
		background: var(--lq-accent, #4f46e5);
		transition: width 0.3s ease-out;
	}
	.lq-tabres__progress-text {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--lq-text);
		mix-blend-mode: difference;
	}
	.lq-tabres__banner-error {
		margin: 0.625rem 0 0;
		padding: 0.5rem 0.75rem;
		background: var(--lq-surface);
		border-radius: 0.25rem;
		font-size: 0.8125rem;
		white-space: pre-wrap;
		max-height: 6rem;
		overflow: auto;
	}
	.lq-tabres__stage {
		display: flex;
		gap: 1rem;
		align-items: stretch;
		min-height: 0;
	}
	.lq-tabres__grid {
		flex: 1;
		min-width: 0;
	}
	.lq-tabres__drawer {
		flex-shrink: 0;
		width: 24rem;
		max-width: 42%;
		border: 1px solid var(--lq-border);
		border-radius: 0.5rem;
		overflow: hidden;
	}
	.lq-tabres__state {
		padding: 1.5rem;
		text-align: center;
		color: var(--lq-text-secondary);
		background: var(--lq-inset);
		border-radius: 0.5rem;
	}
	.lq-tabres__error {
		padding: 0.875rem;
		background: var(--lq-error-soft, var(--lq-inset));
		border: 1px solid var(--lq-error-border, var(--lq-border));
		border-radius: 0.375rem;
		color: var(--lq-error, inherit);
	}
</style>
