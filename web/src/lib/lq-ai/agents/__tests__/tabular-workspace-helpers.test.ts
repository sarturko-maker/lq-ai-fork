import { describe, expect, it } from 'vitest';
import type { TabularCellResult, TabularExecution } from '$lib/lq-ai/types';
import {
	effectiveCellValue,
	findCellInExecution,
	formatCostUsd,
	isOverridden,
	parseCostUsd,
	workspaceTitle
} from '../tabular-workspace-helpers';

function cell(overrides: Partial<TabularCellResult> = {}): TabularCellResult {
	return {
		value: 'One (1) year',
		citations: [],
		confidence: 'high',
		...overrides
	};
}

function execution(overrides: Partial<TabularExecution> = {}): TabularExecution {
	return {
		id: 'grid-1',
		user_id: 'u1',
		parent_execution_id: null,
		skill_name: null,
		status: 'completed',
		document_ids: ['doc-1'],
		document_names: ['MSA.docx'],
		columns: [
			{ name: 'Term', query: '?' },
			{ name: 'Governing law', query: '?' }
		],
		results: {
			rows: [{ document_id: 'doc-1', document_name: 'MSA.docx', cells: { Term: cell() } }]
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

describe('workspaceTitle', () => {
	it('derives from column names', () => {
		expect(workspaceTitle(execution())).toBe('Term, Governing law');
	});
	it('falls back when there are no columns', () => {
		expect(workspaceTitle(execution({ columns: [] }))).toBe('Untitled grid');
		expect(workspaceTitle(null)).toBe('Untitled grid');
	});
	it('truncates a very long title', () => {
		const cols = Array.from({ length: 20 }, (_, i) => ({ name: `Column ${i}`, query: '?' }));
		const t = workspaceTitle(execution({ columns: cols }));
		expect(t.length).toBeLessThanOrEqual(64);
		expect(t.endsWith('…')).toBe(true);
	});
});

describe('effectiveCellValue — the ADR-F042 "human wins" display rule', () => {
	it('returns the agent value when un-overridden', () => {
		expect(effectiveCellValue(cell({ value: 'One (1) year' }))).toBe('One (1) year');
	});
	it('the override shadows the agent value', () => {
		expect(
			effectiveCellValue(cell({ value: 'One (1) year', override_value: 'Two (2) years' }))
		).toBe('Two (2) years');
	});
	it('respects an empty-string override but not a null one', () => {
		expect(effectiveCellValue(cell({ value: 'x', override_value: '' }))).toBe('');
		expect(effectiveCellValue(cell({ value: 'x', override_value: null }))).toBe('x');
	});
	it('is null for a missing cell', () => {
		expect(effectiveCellValue(undefined)).toBeNull();
	});
});

describe('isOverridden', () => {
	it('true only when override_value is set', () => {
		expect(isOverridden(cell())).toBe(false);
		expect(isOverridden(cell({ override_value: 'x' }))).toBe(true);
		expect(isOverridden(cell({ override_value: null }))).toBe(false);
		expect(isOverridden(undefined)).toBe(false);
	});
});

describe('findCellInExecution', () => {
	it('finds a present cell', () => {
		expect(findCellInExecution(execution(), 'doc-1', 'Term')?.value).toBe('One (1) year');
	});
	it('is undefined for an unknown document or column', () => {
		expect(findCellInExecution(execution(), 'doc-x', 'Term')).toBeUndefined();
		expect(findCellInExecution(execution(), 'doc-1', 'Nope')).toBeUndefined();
		expect(findCellInExecution(execution({ results: null }), 'doc-1', 'Term')).toBeUndefined();
	});
});

describe('cost parsing', () => {
	it('parses a JSON-string decimal', () => {
		expect(parseCostUsd('0.0123')).toBeCloseTo(0.0123);
		expect(parseCostUsd(null)).toBeNull();
		expect(parseCostUsd('not-a-number')).toBeNull();
	});
	it('formats sub-cent costs without rounding to zero', () => {
		expect(formatCostUsd('0.0009')).toBe('~ $0.0009');
		expect(formatCostUsd('0.25')).toBe('~ $0.250');
		expect(formatCostUsd('1.5')).toBe('~ $1.50');
		expect(formatCostUsd(null)).toBeNull();
	});
});
