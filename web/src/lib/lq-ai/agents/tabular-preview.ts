/**
 * F2 Tabular T2 — in-chat grid-preview helpers (ADR-F055).
 *
 * Pure, framework-free logic behind `TabularPreview.svelte`, kept here so
 * it is unit-testable without a DOM (the web suite has no
 * `@testing-library/svelte`; the component itself is verified live).
 *
 * The preview is a DURABLE artifact: it re-derives identically live and on
 * reload because its anchor is the SETTLED `finalize_tabular_review` step
 * already in the run timeline (ADR-F004) — not a live-only `data-*` stream
 * frame (the SSE replay path re-emits only `data-step` rows, so such a
 * frame would vanish on reload). The grid body is then fetched from the
 * existing `GET /tabular/executions/{id}` endpoint.
 */
import type { AgentRunStep } from '$lib/lq-ai/api/agents';
import type { TabularCellResult, TabularExecution, TabularResults } from '$lib/lq-ai/types';

/** Tool name whose settled call anchors a grid preview (one per finalized grid). */
export const FINALIZE_TOOL_NAME = 'finalize_tabular_review';

/** Compact-preview caps — the mini-table shows at most this many rows / columns. */
export const PREVIEW_MAX_ROWS = 4;
export const PREVIEW_MAX_COLS = 3;
/** Cell values are clamped so a long clause can't blow out the mini-table. */
export const PREVIEW_VALUE_MAX = 60;

/**
 * Grid ids this turn finalized, in first-seen order, de-duplicated.
 *
 * Derives from the SETTLED `finalize_tabular_review` tool-call rows: that
 * call's input is a short `{"grid_id": "<uuid>"}` digest, well under the
 * ~2000-char step-summary cap, so `JSON.parse` is reliable. Anything
 * unparseable (truncation, a future shape change) is skipped — never fatal;
 * the grid stays reachable elsewhere (the future Grids tab, `/tabular/[id]`).
 */
export function tabularGridIdsForTurn(steps: AgentRunStep[]): string[] {
	const ids: string[] = [];
	const seen = new Set<string>();
	for (const step of steps) {
		if (step.kind !== 'tool_call' || step.name !== FINALIZE_TOOL_NAME) continue;
		const gridId = gridIdFromSummary(step.summary);
		if (gridId && !seen.has(gridId)) {
			seen.add(gridId);
			ids.push(gridId);
		}
	}
	return ids;
}

function gridIdFromSummary(summary: string | null): string | null {
	if (!summary) return null;
	let parsed: unknown;
	try {
		parsed = JSON.parse(summary);
	} catch {
		return null;
	}
	if (typeof parsed !== 'object' || parsed === null) return null;
	const gridId = (parsed as Record<string, unknown>).grid_id;
	return typeof gridId === 'string' && gridId.length > 0 ? gridId : null;
}

/**
 * documentId → filename. Prefers the response's joined `document_names`
 * (present from creation, before any row is filled), falling back to each
 * worked row's `document_name`. Mirrors the `/tabular/[id]` page so the
 * preview and the full grid label rows identically.
 */
export function buildDocumentNameById(execution: TabularExecution): Record<string, string> {
	const m: Record<string, string> = {};
	const ids = execution.document_ids ?? [];
	const names = execution.document_names ?? [];
	for (let i = 0; i < ids.length; i++) {
		if (names[i]) m[ids[i]] = names[i];
	}
	for (const row of execution.results?.rows ?? []) {
		if (!m[row.document_id]) m[row.document_id] = row.document_name;
	}
	return m;
}

export interface PreviewCell {
	/** Display text (clamped); empty string when the cell is unfilled. */
	value: string;
	/** The extraction failed (Decision C-10) — render muted/marked. */
	failed: boolean;
	/** No cell recorded yet for this (document, column). */
	empty: boolean;
}

export interface PreviewRow {
	documentId: string;
	documentName: string;
	/** One entry per `previewColumns`, in that order. */
	cells: PreviewCell[];
}

export interface GridPreview {
	/** Every column name — drives the pill row. */
	columnNames: string[];
	/** The (capped) columns shown in the mini-table. */
	previewColumns: string[];
	/** The (capped) rows shown in the mini-table. */
	previewRows: PreviewRow[];
	docCount: number;
	colCount: number;
	/** Documents not shown in the mini-table (≥ 0). */
	moreRows: number;
	/** Columns not shown in the mini-table (≥ 0). */
	moreCols: number;
}

/**
 * Reduce a full execution to the compact shape the in-chat card renders.
 * Rows follow the execution's `document_ids` order (the operator's order),
 * so the preview matches the full grid; cells are clamped for display.
 */
export function summarizeGridForPreview(
	execution: TabularExecution,
	opts: { maxRows?: number; maxCols?: number } = {}
): GridPreview {
	const maxRows = opts.maxRows ?? PREVIEW_MAX_ROWS;
	const maxCols = opts.maxCols ?? PREVIEW_MAX_COLS;
	const columnNames = execution.columns.map((c) => c.name);
	const docIds = execution.document_ids ?? [];
	const nameById = buildDocumentNameById(execution);

	const rowByDocId: Record<string, TabularResults['rows'][number]> = {};
	for (const row of execution.results?.rows ?? []) rowByDocId[row.document_id] = row;

	const previewColumns = columnNames.slice(0, maxCols);
	const previewRows: PreviewRow[] = docIds.slice(0, maxRows).map((docId) => ({
		documentId: docId,
		documentName: nameById[docId] ?? '(unknown document)',
		cells: previewColumns.map((col) => toPreviewCell(rowByDocId[docId]?.cells?.[col]))
	}));

	return {
		columnNames,
		previewColumns,
		previewRows,
		docCount: docIds.length,
		colCount: columnNames.length,
		moreRows: Math.max(0, docIds.length - previewRows.length),
		moreCols: Math.max(0, columnNames.length - previewColumns.length)
	};
}

function toPreviewCell(cell: TabularCellResult | undefined): PreviewCell {
	if (!cell) return { value: '', failed: false, empty: true };
	if (cell.confidence === 'failed') {
		return { value: cell.value ? clampValue(cell.value) : '—', failed: true, empty: false };
	}
	const value = cell.value ?? '';
	return { value: clampValue(value), failed: false, empty: value.trim().length === 0 };
}

function clampValue(s: string): string {
	const t = s.trim();
	return t.length > PREVIEW_VALUE_MAX ? `${t.slice(0, PREVIEW_VALUE_MAX - 1)}…` : t;
}
