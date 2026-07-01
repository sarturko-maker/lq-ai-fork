<script lang="ts">
	/**
	 * Single tabular cell — M3-C3 sub-phase 4.
	 *
	 * Renders the cell value + a confidence chip (right-aligned). Click
	 * dispatches `open` so the result-view parent can pop the citation
	 * modal for this cell (Decision C-2: hybrid chip + click surface).
	 * Failed cells (Decision C-10) render italic "not found" + amber
	 * chip; visually distinct from the Citation Engine's red unverified.
	 */
	import { createEventDispatcher } from 'svelte';

	import type { TabularCellConfidence, TabularCellResult } from '$lib/lq-ai/types';
	import { effectiveCellValue, isOverridden } from '$lib/lq-ai/agents/tabular-workspace-helpers';

	type CellRenderState = 'empty' | 'failed' | 'high' | 'medium' | 'low';

	function cellRenderState(c: TabularCellResult | undefined): CellRenderState {
		if (c === undefined) return 'empty';
		return c.confidence;
	}

	function confidenceChipLabel(confidence: TabularCellConfidence): string {
		switch (confidence) {
			case 'high':
				return 'High';
			case 'medium':
				return 'Med';
			case 'low':
				return 'Low';
			case 'failed':
				return 'Failed';
		}
	}

	export let cell: TabularCellResult | undefined;
	/**
	 * Optional metadata — only used for the dispatched `open` event so
	 * the parent's citation modal can show a header like
	 * `<column> — <document>`.
	 */
	export let documentName: string = '';
	export let columnName: string = '';
	/** T6: wrap (line-clamp) the value instead of a single ellipsised line. */
	export let wrap = false;

	const dispatch = createEventDispatcher<{ open: { documentName: string; columnName: string } }>();

	$: state = cellRenderState(cell) as CellRenderState;
	$: clickable = state !== 'empty';
	// The effective display value: a lawyer override shadows the agent value
	// (ADR-F042 "human wins"); the drawer still shows the agent value underneath.
	$: shownValue = effectiveCellValue(cell) ?? '';
	$: overridden = isOverridden(cell);

	function handleClick(): void {
		if (!clickable) return;
		dispatch('open', { documentName, columnName });
	}

	function handleKey(e: KeyboardEvent): void {
		if (!clickable) return;
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			handleClick();
		}
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<!-- role + tabindex are gated together on `clickable`; the static
     analyzer flags the dynamic tabindex without seeing the role guard. -->
<div
	class="lq-tabcell"
	class:lq-tabcell--wrap={wrap}
	data-state={state}
	data-testid="lq-tabcell"
	data-document-name={documentName}
	data-column-name={columnName}
	data-overridden={overridden ? 'true' : undefined}
	role={clickable ? 'button' : undefined}
	tabindex={clickable ? 0 : undefined}
	on:click={handleClick}
	on:keydown={handleKey}
>
	{#if state === 'empty' && !overridden}
		<span class="lq-tabcell__placeholder" aria-label="not yet computed">…</span>
	{:else if state === 'failed' && !overridden}
		<span class="lq-tabcell__failed" data-testid="lq-tabcell-failed">not found</span>
	{:else}
		<span class="lq-tabcell__value" class:lq-tabcell__value--wrap={wrap} data-testid="lq-tabcell-value"
			>{shownValue}</span
		>
	{/if}

	<span class="lq-tabcell__marks">
		{#if overridden}
			<span class="lq-tabcell__edited" data-testid="lq-tabcell-edited" title="Overridden by lawyer"
				>edited</span
			>
		{/if}
		{#if cell && state !== 'empty'}
			<span
				class="lq-tabcell__chip"
				data-confidence={cell.confidence}
				data-testid="lq-tabcell-chip"
				aria-label={`Confidence: ${confidenceChipLabel(cell.confidence)}`}
			>
				{confidenceChipLabel(cell.confidence)}
			</span>
		{/if}
	</span>
</div>

<style>
	.lq-tabcell {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.5rem 0.625rem;
		min-height: 2.5rem;
		font-size: 0.875rem;
		color: var(--lq-text);
		background: var(--lq-surface);
		border: 1px solid transparent;
		cursor: default;
	}
	.lq-tabcell[role='button'] {
		cursor: pointer;
	}
	.lq-tabcell[role='button']:hover {
		background: var(--lq-inset);
	}
	.lq-tabcell[role='button']:focus-visible {
		outline: 2px solid var(--lq-accent, #4f46e5);
		outline-offset: -2px;
	}
	.lq-tabcell--wrap {
		align-items: flex-start;
	}
	.lq-tabcell__placeholder {
		color: var(--lq-text-secondary);
	}
	.lq-tabcell__value {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.lq-tabcell__value--wrap {
		white-space: normal;
		text-overflow: clip;
		display: -webkit-box;
		-webkit-line-clamp: 6;
		line-clamp: 6;
		-webkit-box-orient: vertical;
		overflow: hidden;
		word-break: break-word;
	}
	.lq-tabcell__marks {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}
	.lq-tabcell__edited {
		display: inline-block;
		padding: 0.0625rem 0.375rem;
		border-radius: 999px;
		font-size: 0.625rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.02em;
		background: color-mix(in srgb, var(--brand, #0070f3) 14%, transparent);
		color: var(--brand, #0070f3);
	}
	.lq-tabcell__failed {
		flex: 1;
		font-style: italic;
		color: var(--lq-text-secondary);
	}
	.lq-tabcell__chip {
		flex-shrink: 0;
		display: inline-block;
		padding: 0.0625rem 0.375rem;
		border-radius: 999px;
		font-size: 0.6875rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		text-transform: uppercase;
	}
	.lq-tabcell__chip[data-confidence='high'] {
		background: var(--lq-success-soft, #dcfce7);
		color: var(--lq-success, #166534);
	}
	.lq-tabcell__chip[data-confidence='medium'] {
		background: var(--lq-inset, #e5e7eb);
		color: var(--lq-text, #1f2937);
	}
	.lq-tabcell__chip[data-confidence='low'] {
		background: var(--lq-warning-soft, #fef3c7);
		color: var(--lq-warning, #92400e);
	}
	.lq-tabcell__chip[data-confidence='failed'] {
		/* Amber per Decision C-10 — distinct from Citation Engine's red
		   unverified state. */
		background: var(--lq-warning-soft, #fef3c7);
		color: var(--lq-warning, #92400e);
		border: 1px solid var(--lq-warning, #92400e);
	}
</style>
