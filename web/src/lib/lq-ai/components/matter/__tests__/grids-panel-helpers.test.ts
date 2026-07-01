import { describe, expect, it } from 'vitest';
import type { TabularExecutionSummary } from '$lib/lq-ai/types';
import {
	fillModeLabel,
	gridStatusLabel,
	gridStatusTone,
	gridSubtitle,
	gridTitle
} from '../grids-panel-helpers';

function grid(overrides: Partial<TabularExecutionSummary> = {}): TabularExecutionSummary {
	return {
		id: 'g1',
		user_id: 'u1',
		parent_execution_id: null,
		skill_name: null,
		status: 'completed',
		document_count: 3,
		column_count: 2,
		column_names: ['Term', 'Governing law'],
		fill_mode: 'fanout',
		cost_estimate_usd: null,
		cost_actual_usd: null,
		created_at: '2026-07-01T00:00:00Z',
		completed_at: '2026-07-01T00:01:00Z',
		...overrides
	};
}

describe('gridTitle', () => {
	it('joins column names', () => {
		expect(gridTitle(grid())).toBe('Term, Governing law');
	});
	it('falls back when there are no column names', () => {
		expect(gridTitle(grid({ column_names: [] }))).toBe('Untitled grid');
		expect(gridTitle(grid({ column_names: undefined }))).toBe('Untitled grid');
	});
	it('drops blank names and truncates a very long title', () => {
		expect(gridTitle(grid({ column_names: ['A', '   ', 'B'] }))).toBe('A, B');
		const many = Array.from({ length: 30 }, (_, i) => `Column${i}`);
		expect(gridTitle(grid({ column_names: many })).endsWith('…')).toBe(true);
	});
});

describe('gridSubtitle', () => {
	it('renders docs, columns, and fill mode with singular/plural', () => {
		expect(gridSubtitle(grid())).toBe('3 documents · 2 columns · fan-out');
		expect(gridSubtitle(grid({ document_count: 1, column_count: 1, fill_mode: 'retrieval' }))).toBe(
			'1 document · 1 column · retrieval'
		);
	});
	it('omits the fill mode when absent', () => {
		expect(gridSubtitle(grid({ fill_mode: null }))).toBe('3 documents · 2 columns');
	});
});

describe('fillModeLabel', () => {
	it('maps known modes and ignores others', () => {
		expect(fillModeLabel('fanout')).toBe('fan-out');
		expect(fillModeLabel('retrieval')).toBe('retrieval');
		expect(fillModeLabel(null)).toBeNull();
		expect(fillModeLabel(undefined)).toBeNull();
		expect(fillModeLabel('linear')).toBeNull();
	});
});

describe('gridStatus', () => {
	it('labels and tones statuses', () => {
		expect(gridStatusLabel('completed')).toBe('Ready');
		expect(gridStatusTone('completed')).toBe('ok');
		expect(gridStatusTone('running')).toBe('busy');
		expect(gridStatusTone('failed')).toBe('warn');
		expect(gridStatusTone('cancelled')).toBe('warn');
	});
});
