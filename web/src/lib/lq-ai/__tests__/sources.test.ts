/**
 * Unit tests for `buildMessageSources` — the AE3 "Sources" card grouping
 * logic. Pure + DOM-free; the visual rendering of the card + its 5-state
 * marker is covered by the Cypress `ae3-sources-citations` spec.
 */
import { describe, expect, it } from 'vitest';
import { buildMessageSources } from '../citations/sources';
import type { Citation } from '../types';

function makeCitation(overrides: Partial<Citation> = {}): Citation {
	return {
		id: 'cite-1',
		source_file_id: 'file-1',
		source_offset_start: 0,
		source_offset_end: 10,
		source_text: '',
		verified: true,
		verification_method: 'exact_match',
		...overrides
	};
}

describe('buildMessageSources', () => {
	it('returns an empty list for no citations', () => {
		expect(buildMessageSources([])).toEqual([]);
	});

	it('groups passages by source document, preserving first-seen order', () => {
		const sources = buildMessageSources([
			makeCitation({ id: 'a', source_file_id: 'f2', source_filename: 'B.pdf' }),
			makeCitation({ id: 'b', source_file_id: 'f1', source_filename: 'A.pdf' }),
			makeCitation({ id: 'c', source_file_id: 'f2', source_filename: 'B.pdf' })
		]);
		expect(sources).toHaveLength(2);
		expect(sources[0].sourceFileId).toBe('f2');
		expect(sources[0].label).toBe('B.pdf');
		expect(sources[0].passageCount).toBe(2);
		expect(sources[1].sourceFileId).toBe('f1');
		expect(sources[1].passageCount).toBe(1);
	});

	it('falls back to an ordinal label when no filename joined', () => {
		const sources = buildMessageSources([
			makeCitation({ source_file_id: 'f1', source_filename: null }),
			makeCitation({ source_file_id: 'f2' }) // source_filename omitted entirely
		]);
		expect(sources[0].label).toBe('Source 1');
		expect(sources[1].label).toBe('Source 2');
	});

	it('uses a joined filename from any passage in the group', () => {
		// First row of the group lacks a name, a later row carries it.
		const sources = buildMessageSources([
			makeCitation({ source_file_id: 'f1', source_filename: null }),
			makeCitation({ source_file_id: 'f1', source_filename: 'Found.pdf' })
		]);
		expect(sources).toHaveLength(1);
		expect(sources[0].label).toBe('Found.pdf');
	});

	it('collects sorted distinct pages', () => {
		const sources = buildMessageSources([
			makeCitation({ source_file_id: 'f1', source_page: 7 }),
			makeCitation({ source_file_id: 'f1', source_page: 2 }),
			makeCitation({ source_file_id: 'f1', source_page: 7 }),
			makeCitation({ source_file_id: 'f1', source_page: null })
		]);
		expect(sources[0].pages).toEqual([2, 7]);
	});

	it('rolls up to the most cautionary state across passages', () => {
		// exact + paraphrase + unverified → unverified wins (worst).
		const sources = buildMessageSources([
			makeCitation({ source_file_id: 'f1', verification_method: 'exact_match' }),
			makeCitation({ source_file_id: 'f1', verification_method: 'paraphrase_judge' }),
			makeCitation({ source_file_id: 'f1', verified: false, verification_method: 'failed' })
		]);
		expect(sources[0].state).toBe('unverified');
	});

	it('keeps an all-exact group green', () => {
		const sources = buildMessageSources([
			makeCitation({ source_file_id: 'f1', verification_method: 'exact_match' }),
			makeCitation({ source_file_id: 'f1', verification_method: 'exact_match' })
		]);
		expect(sources[0].state).toBe('verified-exact');
	});

	it('truncates a long representative quote', () => {
		const long = 'x'.repeat(200);
		const sources = buildMessageSources([
			makeCitation({ source_file_id: 'f1', source_text: long })
		]);
		expect(sources[0].quotePreview.length).toBeLessThanOrEqual(120);
		expect(sources[0].quotePreview.endsWith('…')).toBe(true);
	});
});
