/**
 * F2 Tabular T7 — pure presentation helpers for the cockpit Grids tab.
 *
 * Framework-free so they are unit-testable without a DOM (the web suite has no
 * `@testing-library/svelte`; the panel itself is verified live). A grid has no
 * stored title, so the list derives one from its column names.
 */
import type { TabularExecutionStatus, TabularExecutionSummary } from '$lib/lq-ai/types';

const TITLE_MAX = 64;

/** A human title for a grid row: its column names, else a neutral fallback. */
export function gridTitle(grid: TabularExecutionSummary): string {
	const names = (grid.column_names ?? []).map((n) => n.trim()).filter(Boolean);
	if (names.length === 0) return 'Untitled grid';
	const joined = names.join(', ');
	return joined.length > TITLE_MAX ? `${joined.slice(0, TITLE_MAX - 1)}…` : joined;
}

/** "3 documents · 2 columns · fan-out" — the one-line row subtitle. */
export function gridSubtitle(grid: TabularExecutionSummary): string {
	const docs = `${grid.document_count} document${grid.document_count === 1 ? '' : 's'}`;
	const cols = `${grid.column_count} column${grid.column_count === 1 ? '' : 's'}`;
	const fill = fillModeLabel(grid.fill_mode);
	return fill ? `${docs} · ${cols} · ${fill}` : `${docs} · ${cols}`;
}

/** fanout|retrieval → a readable label; anything else (incl. null) → null. */
export function fillModeLabel(fillMode: string | null | undefined): string | null {
	if (fillMode === 'fanout') return 'fan-out';
	if (fillMode === 'retrieval') return 'retrieval';
	return null;
}

const STATUS_LABEL: Record<TabularExecutionStatus, string> = {
	pending: 'Queued',
	running: 'Building…',
	completed: 'Ready',
	failed: 'Failed',
	cancelled: 'Cancelled'
};

export function gridStatusLabel(status: TabularExecutionStatus): string {
	return STATUS_LABEL[status] ?? status;
}

/** Badge tone bucket for a grid's status. */
export function gridStatusTone(status: TabularExecutionStatus): 'ok' | 'busy' | 'warn' {
	if (status === 'completed') return 'ok';
	if (status === 'failed' || status === 'cancelled') return 'warn';
	return 'busy';
}
