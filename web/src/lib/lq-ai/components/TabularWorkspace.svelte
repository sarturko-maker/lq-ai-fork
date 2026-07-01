<script lang="ts">
	/**
	 * F2 Tabular T6 — the grid review WORKSPACE (ADR-F055 T6).
	 *
	 * The grid is a review STAGE, not a modal you pop open. This shell hosts the
	 * full `TabularGrid` beside ONE docked `TabularCellDrawer` that PUSHES the
	 * grid (no stacked modal, no backdrop). It is reused by BOTH the cockpit
	 * stage-takeover (`ConversationHost` fly-in, with `onClose`) and the
	 * standalone `/tabular/[id]` page (no `onClose`).
	 *
	 * Load + poll are lifted verbatim from `TabularPreview` (the finalize step
	 * streams at tool-START, so a mount-time fetch can race the commit → poll
	 * until terminal; a 404 renders nothing). A cell override refetches the grid
	 * and the selected cell re-derives from the fresh execution.
	 */
	import { onDestroy, onMount } from 'svelte';
	import XIcon from '@lucide/svelte/icons/x';
	import WrapTextIcon from '@lucide/svelte/icons/wrap-text';
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle';

	import {
		clearTabularCellOverride,
		getTabularExecution,
		overrideTabularCell
	} from '$lib/lq-ai/api/tabular';
	import { openFileInNewTab } from '$lib/lq-ai/api/files';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import TabularGrid, { type CellOpenEvent } from '$lib/lq-ai/components/TabularGrid.svelte';
	import TabularCellDrawer from '$lib/lq-ai/components/TabularCellDrawer.svelte';
	import type { TabularExecution, TabularExecutionStatus } from '$lib/lq-ai/types';
	import { buildDocumentNameById, isTerminalGridStatus } from '$lib/lq-ai/agents/tabular-preview';
	import { findCellInExecution, workspaceTitle } from '$lib/lq-ai/agents/tabular-workspace-helpers';

	export let gridId: string;
	/** Provided by the cockpit stage-takeover; absent on the standalone page. */
	export let onClose: (() => void) | undefined = undefined;

	let execution: TabularExecution | null = null;
	let loading = true;
	let loadError: string | null = null;
	let notFound = false;
	let wrap = false;

	interface Selected {
		documentId: string;
		documentName: string;
		columnName: string;
	}
	let selected: Selected | null = null;
	let saving = false;
	let actionError: string | null = null;

	const POLL_INTERVAL_MS = 1500;
	const MAX_POLLS = 10;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let polls = 0;
	let destroyed = false;

	$: documentNameById = execution ? buildDocumentNameById(execution) : {};
	$: title = workspaceTitle(execution);
	// Re-derive the selected cell from the live execution so the drawer shows
	// fresh data after an override refetch (never a stale captured object).
	$: selectedCell = selected
		? findCellInExecution(execution, selected.documentId, selected.columnName)
		: undefined;

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

	function retry(): void {
		polls = 0;
		notFound = false;
		void load();
	}

	function handleCellOpen(event: CustomEvent<CellOpenEvent>): void {
		const { documentId, documentName, columnName, cell } = event.detail;
		if (!cell) return; // empty cells aren't selectable
		actionError = null;
		selected = { documentId, documentName, columnName };
	}

	function closeDrawer(): void {
		selected = null;
		actionError = null;
	}

	async function saveOverride(value: string, note: string | null): Promise<void> {
		if (!selected) return;
		saving = true;
		actionError = null;
		try {
			execution = await overrideTabularCell(gridId, {
				document_id: selected.documentId,
				column_name: selected.columnName,
				override_value: value,
				override_note: note
			});
		} catch (e) {
			actionError = e instanceof LQAIApiError ? e.message : 'Could not save the override.';
		} finally {
			saving = false;
		}
	}

	async function clearOverride(): Promise<void> {
		if (!selected) return;
		saving = true;
		actionError = null;
		try {
			execution = await clearTabularCellOverride(
				gridId,
				selected.documentId,
				selected.columnName
			);
		} catch (e) {
			actionError = e instanceof LQAIApiError ? e.message : 'Could not clear the override.';
		} finally {
			saving = false;
		}
	}

	async function openSource(fileId: string): Promise<void> {
		actionError = null;
		try {
			await openFileInNewTab(fileId);
		} catch (e) {
			actionError = e instanceof LQAIApiError ? e.message : 'Could not open the source document.';
		}
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
</script>

<div class="lq-tabws" data-testid="lq-tabular-workspace" data-grid-id={gridId}>
	<header class="lq-tabws__head">
		<div class="lq-tabws__crumbs">
			{#if onClose}
				<button
					type="button"
					class="lq-tabws__back"
					data-testid="lq-tabular-workspace-back"
					on:click={() => onClose?.()}>‹ Grids</button
				>
				<span class="lq-tabws__sep" aria-hidden="true">/</span>
			{/if}
			<span class="lq-tabws__title" data-testid="lq-tabular-workspace-title">{title}</span>
			{#if execution}
				<span class="lq-tabws__status" data-tone={statusTone(execution.status)}
					>{STATUS_LABEL[execution.status]}</span
				>
			{/if}
		</div>
		<div class="lq-tabws__tools">
			<button
				type="button"
				class="lq-tabws__wrap"
				data-testid="lq-tabular-workspace-wrap"
				data-on={wrap}
				aria-pressed={wrap}
				on:click={() => (wrap = !wrap)}
			>
				<WrapTextIcon size={14} /> Wrap
			</button>
			{#if onClose}
				<button
					type="button"
					class="lq-tabws__close"
					aria-label="Close grid"
					on:click={() => onClose?.()}
				>
					<XIcon size={16} />
				</button>
			{/if}
		</div>
	</header>

	<div class="lq-tabws__stage">
		{#if loading && !execution}
			<div class="lq-tabws__center" data-testid="lq-tabular-workspace-loading">
				<LoaderCircleIcon size={20} class="lq-spin" />
			</div>
		{:else if notFound}
			<div class="lq-tabws__center lq-tabws__muted">This grid is not available.</div>
		{:else if loadError && !execution}
			<div class="lq-tabws__center">
				<p class="lq-tabws__muted">{loadError}</p>
				<button type="button" class="lq-tabws__retry" on:click={retry}>Retry</button>
			</div>
		{:else if execution}
			<div class="lq-tabws__grid">
				<TabularGrid
					results={execution.results}
					columns={execution.columns}
					documentIds={execution.document_ids}
					{documentNameById}
					{wrap}
					fill
					on:open={handleCellOpen}
				/>
			</div>
			{#if selected && selectedCell}
				<div class="lq-tabws__drawer">
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
		{/if}
	</div>
</div>

<style>
	.lq-tabws {
		display: flex;
		flex-direction: column;
		height: 100%;
		min-height: 0;
		background: var(--lq-surface);
	}
	.lq-tabws__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.625rem 0.875rem;
		border-bottom: 1px solid var(--lq-border);
		flex-shrink: 0;
	}
	.lq-tabws__crumbs {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
		font-size: 0.875rem;
	}
	.lq-tabws__back {
		background: none;
		border: none;
		color: var(--lq-text-secondary);
		font-size: 0.875rem;
		cursor: pointer;
		padding: 0.125rem 0.25rem;
		border-radius: 0.25rem;
	}
	.lq-tabws__back:hover {
		color: var(--lq-text);
		background: var(--lq-inset);
	}
	.lq-tabws__sep {
		color: var(--lq-text-tertiary, var(--lq-text-secondary));
	}
	.lq-tabws__title {
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.lq-tabws__status {
		flex-shrink: 0;
		padding: 0.0625rem 0.4375rem;
		border-radius: 999px;
		font-size: 0.6875rem;
		font-weight: 600;
	}
	.lq-tabws__status[data-tone='ok'] {
		background: var(--lq-success-soft, #dcfce7);
		color: var(--lq-success, #166534);
	}
	.lq-tabws__status[data-tone='warn'] {
		background: var(--lq-warning-soft, #fef3c7);
		color: var(--lq-warning, #92400e);
	}
	.lq-tabws__status[data-tone='busy'] {
		background: var(--lq-inset, #e5e7eb);
		color: var(--lq-text-secondary);
	}
	.lq-tabws__tools {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		flex-shrink: 0;
	}
	.lq-tabws__wrap {
		display: inline-flex;
		align-items: center;
		gap: 0.3125rem;
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--lq-text-secondary);
		background: none;
		border: 1px solid var(--lq-border);
		border-radius: 0.375rem;
		cursor: pointer;
	}
	.lq-tabws__wrap[data-on='true'] {
		color: var(--brand, #0070f3);
		border-color: color-mix(in srgb, var(--brand, #0070f3) 40%, transparent);
		background: color-mix(in srgb, var(--brand, #0070f3) 10%, transparent);
	}
	.lq-tabws__close {
		background: none;
		border: none;
		color: var(--lq-text-secondary);
		cursor: pointer;
		padding: 0.25rem;
		border-radius: 0.375rem;
		line-height: 0;
	}
	.lq-tabws__close:hover {
		background: var(--lq-inset);
	}
	.lq-tabws__stage {
		flex: 1;
		min-height: 0;
		display: flex;
		overflow: hidden;
	}
	.lq-tabws__grid {
		flex: 1;
		min-width: 0;
		min-height: 0;
		overflow: hidden;
		padding: 0.75rem;
	}
	.lq-tabws__drawer {
		flex-shrink: 0;
		width: 24rem;
		max-width: 46%;
		min-height: 0;
	}
	.lq-tabws__center {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
	}
	.lq-tabws__muted {
		color: var(--lq-text-secondary);
		font-size: 0.875rem;
	}
	.lq-tabws__retry {
		padding: 0.3125rem 0.75rem;
		font-size: 0.8125rem;
		border: 1px solid var(--lq-border);
		border-radius: 0.375rem;
		background: none;
		cursor: pointer;
		color: var(--lq-text);
	}
	:global(.lq-tabws .lq-spin) {
		animation: lq-tabws-spin 0.8s linear infinite;
	}
	@keyframes lq-tabws-spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
