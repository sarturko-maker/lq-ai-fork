/**
 * F2 Tabular T6 — pure helpers behind `TabularWorkspace.svelte` /
 * `TabularCellDrawer.svelte` (ADR-F055 T6).
 *
 * Framework-free so they are unit-testable without a DOM (the web suite has no
 * `@testing-library/svelte`; the components themselves are verified live).
 *
 * The load-bearing rule here is the ADR-F042 "human wins" display contract:
 * a lawyer override (`override_value`) shadows the agent's `value` everywhere
 * it renders, while the agent's value + citations stay visible in the drawer.
 */
import type { TabularCellResult, TabularExecution } from '$lib/lq-ai/types';

const TITLE_MAX = 64;

/**
 * A human title for the open grid: its column names (grids have no stored
 * title), else a neutral fallback. Mirrors `grids-panel-helpers.gridTitle`
 * but keys off the full execution's `columns` rather than the list summary.
 */
export function workspaceTitle(execution: TabularExecution | null): string {
	const names = (execution?.columns ?? []).map((c) => c.name.trim()).filter(Boolean);
	if (names.length === 0) return 'Untitled grid';
	const joined = names.join(', ');
	return joined.length > TITLE_MAX ? `${joined.slice(0, TITLE_MAX - 1)}…` : joined;
}

/**
 * The EFFECTIVE display value: the lawyer's override wins over the agent value
 * (ADR-F042). `null` when neither is present. Uses `!= null` so an override of
 * the empty string is respected but a `null`/absent override falls through.
 */
export function effectiveCellValue(cell: TabularCellResult | undefined | null): string | null {
	if (!cell) return null;
	if (cell.override_value != null) return cell.override_value;
	return cell.value;
}

/** True when a lawyer has overridden this cell. */
export function isOverridden(cell: TabularCellResult | undefined | null): boolean {
	return !!cell && cell.override_value != null;
}

/**
 * Look up one cell by (documentId, columnName) in a live execution. Used by the
 * workspace to re-derive the selected cell after an override refetch, so the
 * drawer always shows fresh data without threading the cell object through.
 */
export function findCellInExecution(
	execution: TabularExecution | null,
	documentId: string,
	columnName: string
): TabularCellResult | undefined {
	if (!execution?.results) return undefined;
	const row = execution.results.rows.find((r) => r.document_id === documentId);
	return row?.cells?.[columnName];
}

/** Parse the wire cost (a JSON-string `Decimal`) to a number, or `null`. */
export function parseCostUsd(cost: string | null | undefined): number | null {
	if (cost == null) return null;
	const n = Number(cost);
	return Number.isFinite(n) ? n : null;
}

/**
 * "~ $0.0123" — a compact per-cell cost label, or `null` when unknown. More
 * decimals for sub-cent costs so a real cost never rounds to "$0.00".
 */
export function formatCostUsd(cost: string | null | undefined): string | null {
	const n = parseCostUsd(cost);
	if (n == null) return null;
	const dp = n > 0 && n < 0.01 ? 4 : n < 1 ? 3 : 2;
	return `~ $${n.toFixed(dp)}`;
}
