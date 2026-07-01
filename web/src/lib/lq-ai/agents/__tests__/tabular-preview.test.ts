import { describe, expect, it } from 'vitest';
import type { AgentRunStep } from '$lib/lq-ai/api/agents';
import type { TabularExecution, TabularCellResult } from '$lib/lq-ai/types';
import {
	buildDocumentNameById,
	isTerminalGridStatus,
	summarizeGridForPreview,
	tabularGridIdsForTurn,
	PREVIEW_VALUE_MAX
} from '../tabular-preview';

function step(overrides: Partial<AgentRunStep> = {}): AgentRunStep {
	return {
		id: `step-${overrides.seq ?? 1}`,
		run_id: 'run-1',
		seq: overrides.seq ?? 1,
		kind: 'tool_call',
		name: null,
		summary: null,
		parent_step_id: null,
		created_at: '2026-07-01T00:00:00Z',
		...overrides
	};
}

function finalize(gridId: string, seq = 1): AgentRunStep {
	return step({
		seq,
		kind: 'tool_call',
		name: 'finalize_tabular_review',
		summary: JSON.stringify({ grid_id: gridId })
	});
}

function cell(
	value: string | null,
	confidence: TabularCellResult['confidence'] = 'high'
): TabularCellResult {
	return { value, citations: [], confidence };
}

function execution(overrides: Partial<TabularExecution> = {}): TabularExecution {
	return {
		id: 'grid-1',
		user_id: 'u1',
		parent_execution_id: null,
		skill_name: null,
		status: 'completed',
		document_ids: ['d1', 'd2'],
		document_names: ['alpha.txt', 'beta.txt'],
		columns: [
			{ name: 'Term', query: 'term?' },
			{ name: 'Governing law', query: 'law?' }
		],
		results: {
			rows: [
				{
					document_id: 'd1',
					document_name: 'alpha.txt',
					cells: { Term: cell('2 years'), 'Governing law': cell('E&W') }
				},
				{
					document_id: 'd2',
					document_name: 'beta.txt',
					cells: { Term: cell('3 years'), 'Governing law': cell('NY') }
				}
			]
		},
		cost_estimate_usd: null,
		cost_actual_usd: null,
		error_text: null,
		created_at: '2026-07-01T00:00:00Z',
		started_at: null,
		completed_at: null,
		...overrides
	};
}

describe('tabularGridIdsForTurn', () => {
	it('extracts the grid id from a finalize tool-call step', () => {
		expect(tabularGridIdsForTurn([finalize('g-aaa')])).toEqual(['g-aaa']);
	});

	it('de-duplicates a grid finalized more than once (gap-fill retry)', () => {
		expect(tabularGridIdsForTurn([finalize('g-aaa', 1), finalize('g-aaa', 2)])).toEqual(['g-aaa']);
	});

	it('returns multiple distinct grids in first-seen order', () => {
		expect(tabularGridIdsForTurn([finalize('g-bbb', 1), finalize('g-aaa', 2)])).toEqual([
			'g-bbb',
			'g-aaa'
		]);
	});

	it('ignores other tabular tool calls (start / record) and tool_result rows', () => {
		const steps = [
			step({ seq: 1, kind: 'tool_call', name: 'start_tabular_review', summary: '{"columns":[]}' }),
			step({
				seq: 2,
				kind: 'tool_call',
				name: 'record_tabular_row',
				summary: '{"grid_id":"g-xxx","document":"a"}'
			}),
			step({
				seq: 3,
				kind: 'tool_result',
				name: 'finalize_tabular_review',
				summary: '{"grid_id":"g-yyy"}'
			})
		];
		expect(tabularGridIdsForTurn(steps)).toEqual([]);
	});

	it('skips an unparseable (truncated) finalize summary without throwing', () => {
		const steps = [
			step({ kind: 'tool_call', name: 'finalize_tabular_review', summary: '{"grid_id":"g-aaa' })
		];
		expect(tabularGridIdsForTurn(steps)).toEqual([]);
	});

	it('skips a finalize call whose payload has no grid_id', () => {
		const steps = [
			step({ kind: 'tool_call', name: 'finalize_tabular_review', summary: '{"note":"done"}' })
		];
		expect(tabularGridIdsForTurn(steps)).toEqual([]);
	});

	it('returns an empty list for a turn with no tabular steps', () => {
		expect(tabularGridIdsForTurn([step({ kind: 'model_turn' })])).toEqual([]);
	});
});

describe('isTerminalGridStatus', () => {
	it('treats completed / failed / cancelled as terminal', () => {
		expect(isTerminalGridStatus('completed')).toBe(true);
		expect(isTerminalGridStatus('failed')).toBe(true);
		expect(isTerminalGridStatus('cancelled')).toBe(true);
	});
	it('treats pending / running as non-terminal (poll continues)', () => {
		expect(isTerminalGridStatus('pending')).toBe(false);
		expect(isTerminalGridStatus('running')).toBe(false);
	});
});

describe('buildDocumentNameById', () => {
	it('maps ids to joined document_names', () => {
		expect(buildDocumentNameById(execution())).toEqual({ d1: 'alpha.txt', d2: 'beta.txt' });
	});

	it('falls back to the worked row name when document_names is missing an entry', () => {
		const ex = execution({ document_names: ['alpha.txt'] }); // d2 absent from names
		expect(buildDocumentNameById(ex)).toEqual({ d1: 'alpha.txt', d2: 'beta.txt' });
	});

	it('prefers the joined name over the row name', () => {
		const ex = execution({
			document_names: ['ALPHA.txt', 'BETA.txt'],
			results: { rows: [{ document_id: 'd1', document_name: 'stale.txt', cells: {} }] }
		});
		expect(buildDocumentNameById(ex).d1).toBe('ALPHA.txt');
	});
});

describe('summarizeGridForPreview', () => {
	it('lists every column name and counts docs/cols', () => {
		const p = summarizeGridForPreview(execution());
		expect(p.columnNames).toEqual(['Term', 'Governing law']);
		expect(p.docCount).toBe(2);
		expect(p.colCount).toBe(2);
		expect(p.moreRows).toBe(0);
		expect(p.moreCols).toBe(0);
	});

	it('caps rows and columns and reports the overflow', () => {
		const ex = execution({
			document_ids: ['d1', 'd2', 'd3', 'd4', 'd5'],
			document_names: ['a', 'b', 'c', 'd', 'e'],
			columns: [1, 2, 3, 4].map((n) => ({ name: `C${n}`, query: 'q' })),
			results: { rows: [] }
		});
		const p = summarizeGridForPreview(ex, { maxRows: 4, maxCols: 3 });
		expect(p.previewRows).toHaveLength(4);
		expect(p.previewColumns).toEqual(['C1', 'C2', 'C3']);
		expect(p.moreRows).toBe(1);
		expect(p.moreCols).toBe(1);
	});

	it('follows document_ids order and fills cells per preview column', () => {
		const p = summarizeGridForPreview(execution());
		expect(p.previewRows.map((r) => r.documentName)).toEqual(['alpha.txt', 'beta.txt']);
		expect(p.previewRows[0].cells.map((c) => c.value)).toEqual(['2 years', 'E&W']);
	});

	it('clamps a long cell value', () => {
		const long = 'x'.repeat(PREVIEW_VALUE_MAX + 20);
		const ex = execution({
			document_ids: ['d1'],
			document_names: ['a'],
			columns: [{ name: 'Term', query: 'q' }],
			results: { rows: [{ document_id: 'd1', document_name: 'a', cells: { Term: cell(long) } }] }
		});
		const value = summarizeGridForPreview(ex).previewRows[0].cells[0].value;
		expect(value.length).toBe(PREVIEW_VALUE_MAX);
		expect(value.endsWith('…')).toBe(true);
	});

	it('flags a failed cell', () => {
		const ex = execution({
			document_ids: ['d1'],
			document_names: ['a'],
			columns: [{ name: 'Term', query: 'q' }],
			results: {
				rows: [{ document_id: 'd1', document_name: 'a', cells: { Term: cell(null, 'failed') } }]
			}
		});
		const c = summarizeGridForPreview(ex).previewRows[0].cells[0];
		expect(c.failed).toBe(true);
		expect(c.empty).toBe(false);
	});

	it('marks an unfilled cell empty (null results / missing row)', () => {
		const ex = execution({ results: null });
		const p = summarizeGridForPreview(ex);
		expect(p.previewRows[0].cells.every((c) => c.empty)).toBe(true);
	});
});
